from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    model_validator,
)

from app.core.model import PaperStatus
from app.core.validation import (
    BodyDbId,
    CleanModel,
    SortOrder,
    check_reasonable_date,
)

# Marks: positive, at most two decimals, with a sane upper bound per question.
Marks = Annotated[Decimal, Field(gt=0, le=1000, decimal_places=2)]
NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
DurationMinutes = Annotated[int, Field(gt=0, le=24 * 60)]
StartDate = Annotated[datetime, AfterValidator(check_reasonable_date)]
# Generous limits that still keep one LLM request affordable
LongText = Annotated[str, StringConstraints(max_length=20_000)]


class QuestionCreate(CleanModel):
    question_text: Annotated[NonBlankText, StringConstraints(max_length=20_000)]
    model_answer: LongText | None = None
    rubric: LongText | None = None
    marks_assigned: Marks
    sort_order: SortOrder = 0


class QuestionUpdate(CleanModel):
    # Present: update that question. Absent: create a new question.
    qid: BodyDbId | None = None
    question_text: (
        Annotated[NonBlankText, StringConstraints(max_length=20_000)] | None
    ) = None
    model_answer: LongText | None = None
    rubric: LongText | None = None
    marks_assigned: Marks | None = None
    sort_order: SortOrder | None = None


# Question Base & Derived Schemas
class QuestionBase(BaseModel):
    qid: int
    qpid: int
    question_text: str
    marks_assigned: Decimal
    sort_order: int

    model_config = {"from_attributes": True}


class QuestionTeacherOut(QuestionBase):
    model_answer: str | None = None
    rubric: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class QuestionStudentOut(QuestionBase):
    # Deliberately has no model answer and no rubric.
    pass


class QuestionPaperCreate(CleanModel):
    title: Title
    start_date: StartDate
    duration_minutes: DurationMinutes | None = None
    is_published: bool = False
    questions: list[QuestionCreate] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _published_paper_needs_questions(self) -> "QuestionPaperCreate":
        if self.is_published and not self.questions:
            raise ValueError("A published paper needs at least one question")
        return self


class QuestionPaperUpdate(CleanModel):
    title: Title | None = None
    start_date: StartDate | None = None
    duration_minutes: DurationMinutes | None = None
    is_published: bool | None = None
    is_closed: bool | None = None
    # When given, this is the complete new list of questions.
    questions: list[QuestionUpdate] | None = Field(default=None, max_length=100)


# Paper Base & Derived Schemas
class QuestionPaperBase(BaseModel):
    qpid: int
    t_email: str
    title: str
    start_date: datetime
    duration_minutes: int | None = None
    total_marks: Decimal
    is_published: bool
    is_closed: bool = False
    status: PaperStatus

    model_config = {"from_attributes": True}


class QuestionPaperTeacherOut(QuestionPaperBase):
    created_at: datetime
    updated_at: datetime | None = None
    questions: list[QuestionTeacherOut] = Field(default_factory=list)


class QuestionPaperStudentOut(QuestionPaperBase):
    questions: list[QuestionStudentOut] = Field(default_factory=list)


# List output (no questions)
class QuestionPaperOut(QuestionPaperBase):
    created_at: datetime
    updated_at: datetime | None = None
    question_count: int = 0

    # Filled in for teachers
    submission_count: int | None = None
    evaluated_count: int | None = None

    # Filled in for students
    teacher_name: str | None = None
    attempted: bool | None = None
    evaluated: bool | None = None
    marks_obtained: Decimal | None = None
