from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import usage as usage_service
from app.auth.model import AppUser, Association
from app.auth.schemas import Token
from app.core.model import UserType
from app.database import utcnow
from app.papers.model import Question, QuestionPaper
from app.papers.schemas import (
    QuestionPaperCreate,
    QuestionPaperOut,
    QuestionPaperUpdate,
)
from app.submissions.model import Submission


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Question paper not found"
    )


class PaperService:
    @staticmethod
    async def _load_paper(qpid: int, db: AsyncSession) -> QuestionPaper | None:
        result = await db.execute(
            select(QuestionPaper)
            .options(selectinload(QuestionPaper.questions))
            .where(QuestionPaper.qpid == qpid)
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()

    @staticmethod
    async def is_associated(db: AsyncSession, t_email: str, s_email: str) -> bool:
        result = await db.execute(
            select(Association).where(
                Association.t_email == t_email, Association.s_email == s_email
            )
        )
        return result.scalars().first() is not None

    @staticmethod
    async def has_submission(db: AsyncSession, qpid: int, s_email: str) -> bool:
        result = await db.execute(
            select(Submission.qpid).where(
                Submission.qpid == qpid, Submission.s_email == s_email
            )
        )
        return result.first() is not None

    @staticmethod
    async def get_owned_paper(
        qpid: int, teacher_email: str, db: AsyncSession
    ) -> QuestionPaper:
        """The paper, if it exists and belongs to this teacher."""
        paper = await PaperService._load_paper(qpid, db)
        if paper is None:
            raise _not_found()
        if paper.t_email != teacher_email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This paper belongs to another teacher",
            )
        return paper

    @staticmethod
    async def create_paper(
        paper_in: QuestionPaperCreate, current_teacher: Token, db: AsyncSession
    ) -> QuestionPaper:
        await usage_service.get_usage(db, current_teacher.email)

        # Taken atomically, and rolled back with the rest if the paper fails
        if not await usage_service.consume(db, current_teacher.email, "papers"):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Monthly paper creation limit reached.",
            )

        paper_data = paper_in.model_dump(exclude={"questions"})
        total_marks = sum(
            (q.marks_assigned for q in paper_in.questions), start=Decimal("0")
        )
        db_paper = QuestionPaper(
            t_email=current_teacher.email,
            **paper_data,
            total_marks=total_marks,
            is_closed=False,
        )

        for q_in in paper_in.questions:
            db_paper.questions.append(Question(**q_in.model_dump()))

        db.add(db_paper)

        await db.commit()

        # Reload so server-side defaults and the question order are populated
        return await PaperService._load_paper(db_paper.qpid, db)

    @staticmethod
    async def get_papers(
        skip: int, limit: int, current_token: Token, db: AsyncSession
    ) -> list[QuestionPaperOut]:
        """Papers of a teacher, or papers assigned to a student."""
        question_count = (
            select(func.count(Question.qid))
            .where(Question.qpid == QuestionPaper.qpid)
            .correlate(QuestionPaper)
            .scalar_subquery()
        )

        if current_token.role == UserType.student.value:
            return await PaperService._get_papers_for_student(
                skip, limit, current_token.email, question_count, db
            )

        submission_count = (
            select(func.count())
            .select_from(Submission)
            .where(Submission.qpid == QuestionPaper.qpid)
            .correlate(QuestionPaper)
            .scalar_subquery()
        )
        evaluated_count = (
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.qpid == QuestionPaper.qpid, Submission.evaluated.is_(True)
            )
            .correlate(QuestionPaper)
            .scalar_subquery()
        )

        query = (
            select(QuestionPaper, question_count, submission_count, evaluated_count)
            .where(QuestionPaper.t_email == current_token.email)
            .order_by(QuestionPaper.created_at.desc(), QuestionPaper.qpid.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await db.execute(query)).all()

        papers = []
        for paper, n_questions, n_submissions, n_evaluated in rows:
            out = QuestionPaperOut.model_validate(paper)
            out.question_count = n_questions or 0
            out.submission_count = n_submissions or 0
            out.evaluated_count = n_evaluated or 0
            papers.append(out)
        return papers

    @staticmethod
    async def _get_papers_for_student(
        skip: int, limit: int, s_email: str, question_count, db: AsyncSession
    ) -> list[QuestionPaperOut]:
        query = (
            select(
                QuestionPaper,
                question_count,
                AppUser.full_name,
                Submission.s_email,
                Submission.evaluated,
                Submission.total_marks_obtained,
            )
            .join(
                Association,
                and_(
                    Association.t_email == QuestionPaper.t_email,
                    Association.s_email == s_email,
                ),
            )
            .join(AppUser, AppUser.email == QuestionPaper.t_email)
            .outerjoin(
                Submission,
                and_(
                    Submission.qpid == QuestionPaper.qpid,
                    Submission.s_email == s_email,
                ),
            )
            # Published papers, plus anything the student already answered
            .where(
                or_(
                    QuestionPaper.is_published.is_(True),
                    Submission.s_email.is_not(None),
                )
            )
            .order_by(QuestionPaper.start_date.desc(), QuestionPaper.qpid.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await db.execute(query)).all()

        papers = []
        for paper, n_questions, teacher_name, sub_email, evaluated, marks in rows:
            out = QuestionPaperOut.model_validate(paper)
            out.question_count = n_questions or 0
            out.teacher_name = teacher_name
            out.attempted = sub_email is not None
            out.evaluated = bool(evaluated) if sub_email is not None else False
            # Marks stay hidden until the teacher has evaluated the submission
            out.marks_obtained = marks if out.evaluated else None
            papers.append(out)
        return papers

    @staticmethod
    async def get_paper(
        qpid: int, current_token: Token, db: AsyncSession
    ) -> QuestionPaper:
        paper = await PaperService._load_paper(qpid, db)

        if not paper:
            raise _not_found()

        if current_token.role == UserType.student.value:
            # A student who already answered can always look at the paper again.
            if await PaperService.has_submission(db, qpid, current_token.email):
                return paper

            if not await PaperService.is_associated(
                db, paper.t_email, current_token.email
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this paper",
                )
            if not paper.is_published or paper.start_date > utcnow():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Paper not yet available",
                )
            if paper.is_closed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This paper is closed",
                )
            return paper

        if paper.t_email != current_token.email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this paper",
            )

        return paper

    @staticmethod
    async def update_paper(
        qpid: int,
        paper_in: QuestionPaperUpdate,
        current_teacher: Token,
        db: AsyncSession,
    ) -> QuestionPaper:
        query = (
            select(QuestionPaper)
            .options(selectinload(QuestionPaper.questions))
            .where(
                QuestionPaper.qpid == qpid,
                QuestionPaper.t_email == current_teacher.email,
            )
        )
        result = await db.execute(query)
        db_paper = result.scalars().first()

        if not db_paper:
            raise _not_found()

        update_data = paper_in.model_dump(exclude_unset=True, exclude={"questions"})

        for field, value in update_data.items():
            # Only the duration can be cleared; the other columns are required.
            if value is None and field != "duration_minutes":
                continue
            setattr(db_paper, field, value)

        if paper_in.questions is not None:
            has_submissions = (
                await db.execute(
                    select(Submission.qpid).where(Submission.qpid == qpid).limit(1)
                )
            ).first() is not None
            PaperService._apply_question_changes(db_paper, paper_in, has_submissions)

        if db_paper.is_published and not db_paper.questions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A published paper needs at least one question",
            )

        db_paper.total_marks = sum(
            (Decimal(str(q.marks_assigned)) for q in db_paper.questions),
            start=Decimal("0"),
        )

        await db.commit()

        return await PaperService._load_paper(qpid, db)

    @staticmethod
    def _apply_question_changes(
        db_paper: QuestionPaper, paper_in: QuestionPaperUpdate, has_submissions: bool
    ) -> None:
        """Replace the paper's questions with the list in the request.

        Once students have answered, the questions and their marks are frozen:
        changing them would silently invalidate the answers and the grading.
        The model answer, rubric and order can still be refined.
        """
        existing = {q.qid: q for q in db_paper.questions}
        incoming_qids = [q.qid for q in paper_in.questions if q.qid is not None]

        if len(incoming_qids) != len(set(incoming_qids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The same question appears more than once",
            )
        unknown = [qid for qid in incoming_qids if qid not in existing]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question {unknown[0]} does not belong to this paper",
            )

        frozen = HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This paper already has submissions, so questions cannot be "
                "added, removed or reworded and their marks cannot change. "
                "You can still edit the model answer and the rubric."
            ),
        )

        removed = [q for q in db_paper.questions if q.qid not in set(incoming_qids)]
        added = [q for q in paper_in.questions if q.qid is None]
        if has_submissions and (removed or added):
            raise frozen

        for old_q in removed:
            db_paper.questions.remove(old_q)

        for q_in in paper_in.questions:
            if q_in.qid is None:
                if q_in.question_text is None or q_in.marks_assigned is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="A new question needs question_text and marks_assigned",
                    )
                q_data = q_in.model_dump(exclude={"qid"})
                if q_data["sort_order"] is None:
                    q_data["sort_order"] = 0
                db_paper.questions.append(Question(**q_data))
                continue

            existing_q = existing[q_in.qid]
            q_data = q_in.model_dump(exclude_unset=True, exclude={"qid"})
            for field, value in q_data.items():
                # model_answer and rubric may be cleared; the rest are required
                if value is None and field not in ("model_answer", "rubric"):
                    continue
                if has_submissions and field in ("question_text", "marks_assigned"):
                    current = getattr(existing_q, field)
                    changed = (
                        Decimal(str(current)) != Decimal(str(value))
                        if field == "marks_assigned"
                        else current != value
                    )
                    if changed:
                        raise frozen
                    continue
                setattr(existing_q, field, value)

    @staticmethod
    async def delete_paper(qpid: int, current_teacher: Token, db: AsyncSession) -> None:
        query = (
            select(QuestionPaper)
            .options(selectinload(QuestionPaper.questions))
            .where(
                QuestionPaper.qpid == qpid,
                QuestionPaper.t_email == current_teacher.email,
            )
        )
        result = await db.execute(query)
        db_paper = result.scalars().first()

        if not db_paper:
            raise _not_found()

        await db.delete(db_paper)
        await db.commit()
