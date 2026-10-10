from decimal import Decimal

from pydantic import BaseModel


class PaperLeaderboardEntry(BaseModel):
    rank: int
    full_name: str
    # Only teachers see the email addresses of other students
    s_email: str | None
    is_you: bool
    marks_obtained: Decimal
    percentage: float


class PaperLeaderboardOut(BaseModel):
    qpid: int
    title: str
    total_marks: Decimal
    # Submitted, but not evaluated yet, so not ranked
    pending_count: int
    entries: list[PaperLeaderboardEntry]


class ClassLeaderboardEntry(BaseModel):
    rank: int
    full_name: str
    s_email: str | None
    is_you: bool
    papers_evaluated: int
    marks_obtained: Decimal
    total_marks: Decimal
    percentage: float


class ClassLeaderboardOut(BaseModel):
    t_email: str
    teacher_name: str
    papers_count: int
    entries: list[ClassLeaderboardEntry]
