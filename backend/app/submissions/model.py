from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.model import EvaluationStatus
from app.database import Base, UTCDateTime


class Submission(Base):
    """One student's attempt at one question paper."""

    __tablename__ = "submissions"

    qpid: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("question_papers.qpid", ondelete="CASCADE"),
        primary_key=True,
    )
    s_email: Mapped[str] = mapped_column(
        String, ForeignKey("app_users.email", ondelete="CASCADE"), primary_key=True
    )

    # True once every answer has a mark (from the AI or from the teacher).
    evaluated: Mapped[bool] = mapped_column(Boolean, default=False)
    # True from the first time the results were visible to the student. It
    # survives a reset, so a student who has read the feedback cannot
    # withdraw the submission and try again.
    results_released: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    total_marks_obtained: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0")
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now()
    )


class Answer(Base):
    """The student's answer to one question, with its mark and feedback."""

    __tablename__ = "answers"

    qpid: Mapped[int] = mapped_column(Integer, primary_key=True)
    s_email: Mapped[str] = mapped_column(String, primary_key=True)
    qid: Mapped[int] = mapped_column(Integer, primary_key=True)

    student_answer: Mapped[Optional[str]] = mapped_column(Text)
    marks_obtained: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0")
    )
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[EvaluationStatus] = mapped_column(
        SQLEnum(EvaluationStatus), default=EvaluationStatus.pending
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["qpid", "s_email"],
            ["submissions.qpid", "submissions.s_email"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["qpid", "qid"],
            ["paper_questions.qpid", "paper_questions.qid"],
            ondelete="CASCADE",
        ),
    )
