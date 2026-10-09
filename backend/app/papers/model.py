from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.model import PaperStatus
from app.database import Base, UTCDateTime, utcnow


class QuestionPaper(Base):
    __tablename__ = "question_papers"

    qpid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    t_email: Mapped[str] = mapped_column(
        String,
        ForeignKey("app_users.email", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Students can open and attempt the paper from this moment on.
    start_date: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    # Suggested time limit for one attempt, shown to the student as a timer.
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    total_marks: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set by the teacher to stop accepting new submissions ("expired").
    is_closed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now()
    )

    questions: Mapped[List["Question"]] = relationship(
        "Question",
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="Question.sort_order, Question.qid",
    )

    @property
    def status(self) -> PaperStatus:
        if not self.is_published:
            return PaperStatus.draft
        if self.is_closed:
            return PaperStatus.closed
        if self.start_date > utcnow():
            return PaperStatus.scheduled
        return PaperStatus.open

    @property
    def accepting_submissions(self) -> bool:
        return self.status == PaperStatus.open


class Question(Base):
    __tablename__ = "paper_questions"

    __table_args__ = (
        UniqueConstraint("qpid", "qid", name="uq_paper_questions_qpid_qid"),
    )

    qid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    qpid: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("question_papers.qpid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    # What a full-marks answer contains. Never shown to students.
    model_answer: Mapped[Optional[str]] = mapped_column(Text)
    # How the marks are awarded. Never shown to students.
    rubric: Mapped[Optional[str]] = mapped_column(Text)
    marks_assigned: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now()
    )

    # A simple back-reference to the paper
    paper: Mapped["QuestionPaper"] = relationship(
        "QuestionPaper", back_populates="questions"
    )
