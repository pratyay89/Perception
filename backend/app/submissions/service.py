from decimal import Decimal
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import usage as usage_service
from app.auth.model import AppUser
from app.auth.schemas import Token
from app.core.model import EvaluationStatus, PaperStatus, UserType
from app.core.validation import clean_email_param
from app.papers.model import Question, QuestionPaper
from app.papers.service import PaperService
from app.submissions.model import Answer, Submission
from app.submissions.schemas import SubmissionCreate


def _already_submitted() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Submission already exists for this question paper.",
    )


class SubmissionService:
    @staticmethod
    async def load_answers(db: AsyncSession, qpid: int, s_email: str) -> List[Answer]:
        """Answers of one submission, in the order of the questions."""
        result = await db.execute(
            select(Answer)
            .join(Question, Question.qid == Answer.qid)
            .where(Answer.qpid == qpid, Answer.s_email == s_email)
            .order_by(Question.sort_order, Question.qid)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    @staticmethod
    async def _require_teacher_owns_paper(
        qpid: int, teacher_email: str, db: AsyncSession
    ) -> QuestionPaper:
        result = await db.execute(
            select(QuestionPaper).where(QuestionPaper.qpid == qpid)
        )
        paper = result.scalar_one_or_none()
        if paper is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question paper not found.",
            )
        if paper.t_email != teacher_email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access submissions of this paper.",
            )
        return paper

    @staticmethod
    async def create_submission(
        qpid: int,
        submission_in: SubmissionCreate,
        current_user: Token,
        db: AsyncSession,
    ) -> Submission:
        if current_user.role != UserType.student.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students can submit answers.",
            )

        paper = await PaperService._load_paper(qpid, db)

        if not paper:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question paper not found.",
            )

        if not await PaperService.is_associated(db, paper.t_email, current_user.email):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This paper is not assigned to you.",
            )

        if await PaperService.has_submission(db, qpid, current_user.email):
            raise _already_submitted()

        paper_status = paper.status
        if paper_status != PaperStatus.open:
            reason = {
                PaperStatus.draft: "This paper is not available yet.",
                PaperStatus.scheduled: "This paper has not started yet.",
                PaperStatus.closed: "This paper is closed and no longer accepts submissions.",
            }[paper_status]
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

        # Every answer must point at a question of this paper, once.
        question_ids = {q.qid for q in paper.questions}
        answers_by_qid: dict[int, str] = {}
        for ans in submission_in.answers:
            if ans.qid not in question_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Question {ans.qid} does not belong to this paper.",
                )
            if ans.qid in answers_by_qid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Question {ans.qid} was answered more than once.",
                )
            answers_by_qid[ans.qid] = ans.student_answer

        await usage_service.get_usage(db, current_user.email)

        # Taken atomically, and rolled back with the rest if anything fails
        if not await usage_service.consume(db, current_user.email, "submissions"):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Monthly submission limit reached.",
            )

        submission = Submission(
            qpid=qpid,
            s_email=current_user.email,
            evaluated=False,
            results_released=False,
            total_marks_obtained=Decimal("0"),
        )
        db.add(submission)

        try:
            await db.flush()
        except IntegrityError:
            # The same student submitted twice at the same moment.
            await db.rollback()
            raise _already_submitted()

        # One row per question, so skipped questions are graded as blank
        # and the total is always out of the full marks of the paper.
        for question in paper.questions:
            db.add(
                Answer(
                    qpid=qpid,
                    s_email=current_user.email,
                    qid=question.qid,
                    student_answer=answers_by_qid.get(question.qid, ""),
                    marks_obtained=Decimal("0"),
                    status=EvaluationStatus.pending,
                )
            )

        await db.commit()
        await db.refresh(submission)

        submission.answers = await SubmissionService.load_answers(
            db, qpid, current_user.email
        )
        return submission

    @staticmethod
    async def get_submissions_for_paper(
        qpid: int,
        skip: int,
        limit: int,
        current_user: Token,
        db: AsyncSession,
    ) -> List[Submission]:
        stmt = (
            select(Submission, AppUser.full_name)
            .join(AppUser, AppUser.email == Submission.s_email)
            .where(Submission.qpid == qpid)
        )

        if current_user.role == UserType.student.value:
            # Students only ever see their own submission
            stmt = stmt.where(Submission.s_email == current_user.email)
        else:
            await SubmissionService._require_teacher_owns_paper(
                qpid, current_user.email, db
            )

        stmt = stmt.order_by(Submission.created_at, Submission.s_email)
        stmt = stmt.offset(skip).limit(limit)
        rows = (await db.execute(stmt)).all()

        submissions = []
        for submission, full_name in rows:
            submission.student_name = full_name
            submissions.append(submission)
        return submissions

    @staticmethod
    async def get_submission(
        qpid: int,
        s_email: str,
        current_user: Token,
        db: AsyncSession,
    ) -> Submission:
        s_email = clean_email_param(s_email)

        if current_user.role == UserType.student.value:
            if current_user.email != s_email:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to access this submission.",
                )
        else:
            await SubmissionService._require_teacher_owns_paper(
                qpid, current_user.email, db
            )

        row = (
            await db.execute(
                select(Submission, AppUser.full_name)
                .join(AppUser, AppUser.email == Submission.s_email)
                .where(Submission.qpid == qpid, Submission.s_email == s_email)
            )
        ).first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found.",
            )

        submission, full_name = row
        submission.student_name = full_name
        submission.answers = await SubmissionService.load_answers(db, qpid, s_email)

        return submission

    @staticmethod
    async def delete_submission(
        qpid: int,
        s_email: str,
        current_user: Token,
        db: AsyncSession,
    ) -> None:
        s_email = clean_email_param(s_email)

        if current_user.role == UserType.student.value:
            if current_user.email != s_email:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to delete this submission.",
                )
        else:
            await SubmissionService._require_teacher_owns_paper(
                qpid, current_user.email, db
            )

        stmt = select(Submission).where(
            Submission.qpid == qpid, Submission.s_email == s_email
        )
        res = await db.execute(stmt)
        submission = res.scalar_one_or_none()

        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found.",
            )

        if current_user.role == UserType.student.value:
            # Withdrawing after grading would let a student read the feedback
            # and then try again.
            graded = (
                await db.execute(
                    select(Answer.qid)
                    .where(
                        Answer.qpid == qpid,
                        Answer.s_email == s_email,
                        Answer.status != EvaluationStatus.pending,
                    )
                    .limit(1)
                )
            ).first()
            if submission.evaluated or submission.results_released or graded:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="A submission cannot be withdrawn once it has been evaluated.",
                )

        await db.delete(submission)
        await db.commit()
