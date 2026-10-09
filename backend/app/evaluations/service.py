"""Grading of submissions with the LLM, and the teacher's review actions.

An evaluation has three phases, and the database is only touched in the first
and the last:

1. Read the answers that need grading and end the transaction.
2. Call the LLM (seconds to minutes). No transaction and no connection is held.
3. In a new, short transaction, read the rows again and store each result only
   if the answer it belongs to is still there and unchanged.

Phase 3 matters because the world can change during phase 2: the student may
withdraw, the teacher may reset or override a mark in another tab. Results are
never written over data that is newer than what the LLM saw.
"""

import asyncio
import weakref
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import usage as usage_service
from app.auth.model import AppUser
from app.auth.schemas import Token
from app.config import settings
from app.core.model import EvaluationStatus
from app.core.validation import clean_email_param
from app.evaluations.schemas import AnswerOverride
from app.papers.model import QuestionPaper
from app.papers.service import PaperService
from app.submissions.model import Answer, Submission
from app.submissions.service import SubmissionService
from app.utils.evaluator import EvaluationService as LLMEvaluationService
from app.utils.evaluator import (
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitError,
)
from app.utils.logging import logger

_TWO_PLACES = Decimal("0.01")

# One semaphore per event loop, shared by all requests, so the provider's
# rate limit is respected even when several teachers evaluate at once.
_semaphores: (
    "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]"
) = weakref.WeakKeyDictionary()


def _llm_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    semaphore = _semaphores.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(max(1, settings.LLM_MAX_CONCURRENCY))
        _semaphores[loop] = semaphore
    return semaphore


def _to_marks(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class QuestionSnapshot:
    """The parts of a question the grader needs, detached from the database."""

    qid: int
    question_text: str
    model_answer: str | None
    rubric: str | None
    marks_assigned: Decimal


@dataclass
class GradeJob:
    """One answer to grade, and afterwards what the LLM said about it."""

    question: QuestionSnapshot
    # The exact text that is sent to the LLM
    answer_text: str
    # "graded", "failed", or None when the LLM was not asked (run stopped)
    outcome: str | None = None
    marks: Decimal = Decimal("0")
    feedback: str | None = None


@dataclass
class EvaluationRun:
    """State shared by all answers graded during one request."""

    token_budget: int
    force: bool = False
    tokens_used: int = 0
    # Tokens already deducted from the teacher's balance
    tokens_charged: int = 0
    graded: int = 0
    failed: int = 0
    pending: int = 0
    # Results dropped because the answer changed or vanished meanwhile
    discarded: int = 0
    # Set when it is pointless to send more requests in this run
    stop_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def budget_left(self) -> int:
        return self.token_budget - self.tokens_used

    def message(self) -> str | None:
        parts = []
        if self.stop_reason:
            parts.append(self.stop_reason)
        if self.failed:
            detail = f" ({self.errors[0]})" if self.errors else ""
            parts.append(
                f"{self.failed} answer(s) could not be graded{detail}. "
                "Run the evaluation again to retry them, or grade them yourself."
            )
        if self.pending and not self.stop_reason:
            parts.append(f"{self.pending} answer(s) are still pending.")
        if self.discarded:
            parts.append(
                f"{self.discarded} result(s) were discarded because the "
                "submission changed while it was being evaluated."
            )
        return " ".join(parts) or None


def recompute_submission(submission: Submission, answers: list[Answer]) -> None:
    """Derive the submission's total and evaluated flag from its answers."""
    submission.total_marks_obtained = sum(
        (
            Decimal(str(a.marks_obtained))
            for a in answers
            if a.status == EvaluationStatus.success
        ),
        start=Decimal("0"),
    )
    submission.evaluated = bool(answers) and all(
        a.status == EvaluationStatus.success for a in answers
    )
    if submission.evaluated:
        # From now on the student has been able to read the feedback
        submission.results_released = True


class SubEvaluationService:
    @staticmethod
    def _require_llm() -> None:
        if not LLMEvaluationService.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "AI evaluation is not configured: set GROQ_API_KEY in the "
                    "backend .env file and restart the server."
                ),
            )

    @staticmethod
    async def _start_run(
        teacher_email: str, force: bool, db: AsyncSession
    ) -> EvaluationRun:
        teacher_usage = await usage_service.get_usage(db, teacher_email)
        if teacher_usage.llm_tokens_balance_monthly <= 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Monthly LLM token limit reached.",
            )
        return EvaluationRun(
            token_budget=teacher_usage.llm_tokens_balance_monthly, force=force
        )

    @staticmethod
    def _snapshot_questions(paper: QuestionPaper) -> dict[int, QuestionSnapshot]:
        return {
            q.qid: QuestionSnapshot(
                qid=q.qid,
                question_text=q.question_text,
                model_answer=q.model_answer,
                rubric=q.rubric,
                marks_assigned=_to_marks(q.marks_assigned),
            )
            for q in paper.questions
        }

    @staticmethod
    async def _load_submission(
        qpid: int, s_email: str, db: AsyncSession, *, lock: bool = False
    ) -> Submission | None:
        """A submission with the student's name. `lock` serialises writers."""
        query = (
            select(Submission, AppUser.full_name)
            .join(AppUser, AppUser.email == Submission.s_email)
            .where(Submission.qpid == qpid, Submission.s_email == s_email)
            .execution_options(populate_existing=True)
        )
        if lock:
            # Row lock on PostgreSQL; SQLite serialises writers by itself
            query = query.with_for_update(of=Submission)
        row = (await db.execute(query)).first()
        if row is None:
            return None
        submission, full_name = row
        submission.student_name = full_name
        return submission

    @staticmethod
    async def _require_submission(
        qpid: int, s_email: str, db: AsyncSession, *, lock: bool = False
    ) -> Submission:
        submission = await SubEvaluationService._load_submission(
            qpid, s_email, db, lock=lock
        )
        if submission is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
            )
        return submission

    @staticmethod
    async def _attach_answers(submission: Submission, db: AsyncSession) -> Submission:
        """Read a submission again after a commit and attach its answers."""
        fresh = await SubEvaluationService._require_submission(
            submission.qpid, submission.s_email, db
        )
        fresh.answers = await SubmissionService.load_answers(
            db, fresh.qpid, fresh.s_email
        )
        return fresh

    # ------------------------------------------------------------------
    # Phase 2: the LLM
    # ------------------------------------------------------------------

    @staticmethod
    async def _grade_job(job: GradeJob, run: EvaluationRun) -> None:
        """Ask the LLM about one answer. Never raises; never touches the database."""
        async with _llm_semaphore():
            if run.stop_reason:
                return
            if run.budget_left <= 0:
                run.stop_reason = (
                    "Monthly LLM token limit reached; the remaining answers "
                    "were not evaluated."
                )
                return

            question = job.question
            try:
                result, tokens = await LLMEvaluationService.evaluate(
                    question=question.question_text,
                    student_answer=job.answer_text,
                    max_marks=float(question.marks_assigned),
                    teacher_answer=question.model_answer,
                    rubric=question.rubric,
                )
            except LLMRateLimitError as exc:
                run.tokens_used += exc.tokens_used
                # Further requests would only wait and fail the same way.
                run.stop_reason = (
                    "The AI provider's rate limit was reached. Wait a minute "
                    "and run the evaluation again; answers already graded are kept."
                )
                return
            except LLMNotConfiguredError as exc:
                run.tokens_used += exc.tokens_used
                run.stop_reason = str(exc)
                return
            except (
                Exception
            ) as exc:  # noqa: BLE001 - one bad answer must not sink the run
                run.tokens_used += getattr(exc, "tokens_used", 0)
                if not isinstance(exc, LLMError):
                    logger.exception("Unexpected error while grading an answer")
                    exc = LLMError("Unexpected error while grading")
                else:
                    logger.warning(
                        "Answer evaluation failed", qid=question.qid, error=str(exc)
                    )
                job.outcome = "failed"
                if str(exc) not in run.errors:
                    run.errors.append(str(exc))
                return

            run.tokens_used += tokens
            # Second line of defence: never keep more than the question is worth.
            awarded = min(_to_marks(result.score), question.marks_assigned)
            job.marks = max(awarded, Decimal("0"))
            job.feedback = result.feedback
            job.outcome = "graded"

    # ------------------------------------------------------------------
    # Phases 1 and 3: the database
    # ------------------------------------------------------------------

    @staticmethod
    async def _grade_submission(
        qpid: int,
        s_email: str,
        teacher_email: str,
        questions: dict[int, QuestionSnapshot],
        run: EvaluationRun,
        db: AsyncSession,
    ) -> Submission | None:
        """Grade one submission. Returns None if it disappeared meanwhile."""
        # Phase 1: what needs grading right now?
        answers = await SubmissionService.load_answers(db, qpid, s_email)
        jobs = [
            GradeJob(question=questions[a.qid], answer_text=a.student_answer or "")
            for a in answers
            if a.qid in questions
            and (run.force or a.status != EvaluationStatus.success)
        ]
        # End the transaction: nothing is held open while the LLM works.
        await db.commit()

        # Phase 2
        await asyncio.gather(
            *(SubEvaluationService._grade_job(job, run) for job in jobs)
        )

        # Phase 3: store the results against the rows as they are now
        submission = await SubEvaluationService._load_submission(
            qpid, s_email, db, lock=True
        )
        if submission is None:
            # Withdrawn or deleted while it was being graded
            run.discarded += sum(1 for job in jobs if job.outcome)
            await SubEvaluationService._charge(teacher_email, run, db)
            await db.commit()
            return None

        current = {
            a.qid: a for a in await SubmissionService.load_answers(db, qpid, s_email)
        }
        for job in jobs:
            if job.outcome is None:
                run.pending += 1
                continue

            answer = current.get(job.question.qid)
            if answer is None or (answer.student_answer or "") != job.answer_text:
                # A different answer than the one the LLM read
                run.discarded += 1
                continue
            if answer.status == EvaluationStatus.success and not run.force:
                # Graded by the teacher in the meantime: their mark stands
                run.discarded += 1
                continue

            if job.outcome == "graded":
                answer.marks_obtained = job.marks
                answer.feedback = job.feedback
                answer.status = EvaluationStatus.success
                run.graded += 1
            else:
                # A stale mark must not survive a failed re-evaluation
                answer.marks_obtained = Decimal("0")
                answer.feedback = None
                answer.status = EvaluationStatus.failed
                run.failed += 1

        recompute_submission(submission, list(current.values()))
        await SubEvaluationService._charge(teacher_email, run, db)
        await db.commit()
        return submission

    @staticmethod
    async def _charge(teacher_email: str, run: EvaluationRun, db: AsyncSession) -> None:
        """Bill the tokens used since the last call (atomic in the database)."""
        delta = run.tokens_used - run.tokens_charged
        if delta > 0:
            await usage_service.charge_tokens(db, teacher_email, delta)
            run.tokens_charged = run.tokens_used

    @staticmethod
    async def evaluate_submission(
        qpid: int,
        s_email: str,
        current_teacher: Token,
        db: AsyncSession,
        force: bool = False,
    ) -> tuple[Submission, EvaluationRun]:
        """Grade one student's submission with the LLM.

        Answers that already have a mark are kept unless ``force`` is set, so a
        partly failed run can simply be repeated.
        """
        s_email = clean_email_param(s_email)
        paper = await PaperService.get_owned_paper(qpid, current_teacher.email, db)
        await SubEvaluationService._require_submission(qpid, s_email, db)

        SubEvaluationService._require_llm()
        run = await SubEvaluationService._start_run(current_teacher.email, force, db)
        questions = SubEvaluationService._snapshot_questions(paper)

        submission = await SubEvaluationService._grade_submission(
            qpid, s_email, current_teacher.email, questions, run, db
        )
        if submission is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The submission was withdrawn while it was being evaluated.",
            )

        return await SubEvaluationService._attach_answers(submission, db), run

    @staticmethod
    async def evaluate_paper(
        qpid: int,
        current_teacher: Token,
        db: AsyncSession,
        force: bool = False,
    ) -> tuple[list[Submission], EvaluationRun]:
        """Grade every submission of a paper, one student after another."""
        paper = await PaperService.get_owned_paper(qpid, current_teacher.email, db)

        todo = (
            await db.execute(
                select(Submission.s_email, Submission.evaluated)
                .where(Submission.qpid == qpid)
                .order_by(Submission.created_at, Submission.s_email)
            )
        ).all()
        if not todo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This paper has no submissions to evaluate yet.",
            )

        SubEvaluationService._require_llm()
        run = await SubEvaluationService._start_run(current_teacher.email, force, db)
        questions = SubEvaluationService._snapshot_questions(paper)

        for s_email, evaluated in todo:
            if evaluated and not force:
                continue
            # Each student is committed separately: a long run that is
            # interrupted keeps the work it has done.
            await SubEvaluationService._grade_submission(
                qpid, s_email, current_teacher.email, questions, run, db
            )

        # Report the submissions as they are now
        rows = (
            await db.execute(
                select(Submission, AppUser.full_name)
                .join(AppUser, AppUser.email == Submission.s_email)
                .where(Submission.qpid == qpid)
                .order_by(Submission.created_at, Submission.s_email)
                .execution_options(populate_existing=True)
            )
        ).all()
        submissions = []
        for submission, full_name in rows:
            submission.student_name = full_name
            submissions.append(submission)
        return submissions, run

    # ------------------------------------------------------------------
    # Teacher review
    # ------------------------------------------------------------------

    @staticmethod
    async def reset_submission(
        qpid: int, s_email: str, current_teacher: Token, db: AsyncSession
    ) -> Submission:
        """Discard the marks and feedback of one submission."""
        s_email = clean_email_param(s_email)
        await PaperService.get_owned_paper(qpid, current_teacher.email, db)
        submission = await SubEvaluationService._require_submission(
            qpid, s_email, db, lock=True
        )

        answers = await SubmissionService.load_answers(db, qpid, s_email)
        SubEvaluationService._reset(submission, answers)

        await db.commit()
        return await SubEvaluationService._attach_answers(submission, db)

    @staticmethod
    async def reset_paper(qpid: int, current_teacher: Token, db: AsyncSession) -> int:
        """Discard the marks and feedback of every submission of a paper."""
        await PaperService.get_owned_paper(qpid, current_teacher.email, db)

        submissions = list(
            (
                await db.execute(
                    select(Submission)
                    .where(Submission.qpid == qpid)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        answers = list(
            (
                await db.execute(
                    select(Answer)
                    .where(Answer.qpid == qpid)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        by_student: dict[str, list[Answer]] = {}
        for answer in answers:
            by_student.setdefault(answer.s_email, []).append(answer)

        for submission in submissions:
            SubEvaluationService._reset(
                submission, by_student.get(submission.s_email, [])
            )

        await db.commit()
        return len(submissions)

    @staticmethod
    def _reset(submission: Submission, answers: list[Answer]) -> None:
        for answer in answers:
            answer.marks_obtained = Decimal("0")
            answer.feedback = None
            answer.status = EvaluationStatus.pending
        submission.evaluated = False
        submission.total_marks_obtained = Decimal("0")

    @staticmethod
    async def override_answer(
        qpid: int,
        s_email: str,
        qid: int,
        override: AnswerOverride,
        current_teacher: Token,
        db: AsyncSession,
    ) -> Submission:
        """Let the teacher set the mark (and feedback) of one answer."""
        s_email = clean_email_param(s_email)
        paper = await PaperService.get_owned_paper(qpid, current_teacher.email, db)
        submission = await SubEvaluationService._require_submission(
            qpid, s_email, db, lock=True
        )

        question = next((q for q in paper.questions if q.qid == qid), None)
        answers = await SubmissionService.load_answers(db, qpid, s_email)
        answer = next((a for a in answers if a.qid == qid), None)
        if question is None or answer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Answer not found"
            )

        max_marks = _to_marks(question.marks_assigned)
        if override.marks_obtained > max_marks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Marks cannot exceed the maximum of {max_marks:f} for this question.",
            )

        answer.marks_obtained = _to_marks(override.marks_obtained)
        if override.feedback is not None:
            answer.feedback = override.feedback or None
        answer.status = EvaluationStatus.success

        recompute_submission(submission, answers)

        await db.commit()
        return await SubEvaluationService._attach_answers(submission, db)
