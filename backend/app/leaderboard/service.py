from collections import defaultdict
from decimal import Decimal
from typing import Callable, Hashable, Sequence, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.model import AppUser, Association
from app.auth.schemas import Token
from app.core.model import UserType
from app.database import utcnow
from app.leaderboard.schemas import (
    ClassLeaderboardEntry,
    ClassLeaderboardOut,
    PaperLeaderboardEntry,
    PaperLeaderboardOut,
)
from app.papers.model import QuestionPaper
from app.papers.service import PaperService
from app.submissions.model import Submission

T = TypeVar("T")


def _percentage(obtained: Decimal, total: Decimal) -> float:
    if total <= 0:
        return 0.0
    return round(float(obtained / total * 100), 1)


def _ranks(rows: Sequence[T], score: Callable[[T], Hashable]) -> list[int]:
    """Competition ranking of rows already sorted best first: 1, 2, 2, 4."""
    ranks: list[int] = []
    for i, row in enumerate(rows):
        if i > 0 and score(row) == score(rows[i - 1]):
            ranks.append(ranks[-1])
        else:
            ranks.append(i + 1)
    return ranks


class LeaderboardService:
    @staticmethod
    async def _readable_paper(
        qpid: int, current_user: Token, db: AsyncSession
    ) -> QuestionPaper:
        """The paper, if this user may see how the class did on it."""
        if current_user.role == UserType.teacher.value:
            return await PaperService.get_owned_paper(qpid, current_user.email, db)

        paper = await db.get(QuestionPaper, qpid)
        if paper is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question paper not found",
            )
        if await PaperService.has_submission(db, qpid, current_user.email):
            return paper
        if (
            await PaperService.is_associated(db, paper.t_email, current_user.email)
            and paper.is_published
            and paper.start_date <= utcnow()
        ):
            return paper
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this leaderboard",
        )

    @staticmethod
    async def paper_leaderboard(
        qpid: int, current_user: Token, db: AsyncSession
    ) -> PaperLeaderboardOut:
        """Evaluated submissions of one paper, best first."""
        paper = await LeaderboardService._readable_paper(qpid, current_user, db)
        is_teacher = current_user.role == UserType.teacher.value

        rows = (
            await db.execute(
                select(Submission, AppUser.full_name)
                .join(AppUser, AppUser.email == Submission.s_email)
                .where(Submission.qpid == qpid)
            )
        ).all()

        # Only evaluated results are ranked: marks stay hidden until then
        ranked = sorted(
            (row for row in rows if row.Submission.evaluated),
            key=lambda row: (
                -row.Submission.total_marks_obtained,
                row.full_name.casefold(),
            ),
        )
        ranks = _ranks(ranked, lambda row: row.Submission.total_marks_obtained)

        entries = [
            PaperLeaderboardEntry(
                rank=rank,
                full_name=row.full_name,
                s_email=(
                    row.Submission.s_email
                    if is_teacher or row.Submission.s_email == current_user.email
                    else None
                ),
                is_you=row.Submission.s_email == current_user.email,
                marks_obtained=row.Submission.total_marks_obtained,
                percentage=_percentage(
                    row.Submission.total_marks_obtained, paper.total_marks
                ),
            )
            for rank, row in zip(ranks, ranked)
        ]
        return PaperLeaderboardOut(
            qpid=paper.qpid,
            title=paper.title,
            total_marks=paper.total_marks,
            pending_count=len(rows) - len(ranked),
            entries=entries,
        )

    @staticmethod
    async def class_leaderboards(
        current_user: Token, db: AsyncSession
    ) -> list[ClassLeaderboardOut]:
        """
        Overall standings of each class the user belongs to: the teacher's own
        class, or every class the student is in.
        """
        if current_user.role == UserType.teacher.value:
            teacher_emails = [current_user.email]
        else:
            teacher_emails = list(
                (
                    await db.execute(
                        select(Association.t_email).where(
                            Association.s_email == current_user.email
                        )
                    )
                ).scalars()
            )

        boards = [
            await LeaderboardService._class_leaderboard(t_email, current_user, db)
            for t_email in teacher_emails
        ]
        return [board for board in boards if board is not None]

    @staticmethod
    async def _class_leaderboard(
        t_email: str, current_user: Token, db: AsyncSession
    ) -> ClassLeaderboardOut | None:
        teacher_name = (
            await db.execute(select(AppUser.full_name).where(AppUser.email == t_email))
        ).scalar_one_or_none()
        if teacher_name is None:
            return None
        is_teacher = current_user.role == UserType.teacher.value

        papers = dict(
            (
                await db.execute(
                    select(QuestionPaper.qpid, QuestionPaper.total_marks).where(
                        QuestionPaper.t_email == t_email,
                        QuestionPaper.is_published.is_(True),
                    )
                )
            ).all()
        )

        if not papers:
            return ClassLeaderboardOut(
                t_email=t_email, teacher_name=teacher_name, papers_count=0, entries=[]
            )

        # Students currently in the class, with their evaluated results
        rows = (
            await db.execute(
                select(
                    Submission.s_email,
                    Submission.qpid,
                    Submission.total_marks_obtained,
                    AppUser.full_name,
                )
                .join(AppUser, AppUser.email == Submission.s_email)
                .join(
                    Association,
                    (Association.s_email == Submission.s_email)
                    & (Association.t_email == t_email),
                )
                .where(
                    Submission.qpid.in_(papers.keys()),
                    Submission.evaluated.is_(True),
                )
            )
        ).all()

        totals: dict[str, dict] = defaultdict(
            lambda: {
                "name": "",
                "papers": 0,
                "obtained": Decimal(0),
                "total": Decimal(0),
            }
        )
        for row in rows:
            student = totals[row.s_email]
            student["name"] = row.full_name
            student["papers"] += 1
            student["obtained"] += row.total_marks_obtained
            student["total"] += papers[row.qpid]

        # Ranked by percentage over the papers each student was evaluated on
        standings = sorted(
            (
                (email, data, _percentage(data["obtained"], data["total"]))
                for email, data in totals.items()
            ),
            key=lambda s: (-s[2], -s[1]["papers"], s[1]["name"].casefold()),
        )
        ranks = _ranks(standings, lambda s: (s[2], s[1]["papers"]))

        return ClassLeaderboardOut(
            t_email=t_email,
            teacher_name=teacher_name,
            papers_count=len(papers),
            entries=[
                ClassLeaderboardEntry(
                    rank=rank,
                    full_name=data["name"],
                    s_email=(
                        email if is_teacher or email == current_user.email else None
                    ),
                    is_you=email == current_user.email,
                    papers_evaluated=data["papers"],
                    marks_obtained=data["obtained"],
                    total_marks=data["total"],
                    percentage=percentage,
                )
                for rank, (email, data, percentage) in zip(ranks, standings)
            ],
        )
