from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.model import EvaluationStatus
from app.core.validation import BodyDbId, CleanModel

# Long enough for an essay, short enough to keep one LLM call affordable.
MAX_ANSWER_LENGTH = 20_000


class AnswerCreate(CleanModel):
    qid: BodyDbId
    student_answer: str = Field(max_length=MAX_ANSWER_LENGTH)


class SubmissionCreate(CleanModel):
    # Questions that are left out are stored as blank answers.
    answers: List[AnswerCreate] = Field(default_factory=list, max_length=100)


# Central Base Models
class AnswerBase(BaseModel):
    qpid: int
    s_email: str
    qid: int
    student_answer: Optional[str] = None
    marks_obtained: Decimal = Decimal("0.0")
    feedback: Optional[str] = None
    status: EvaluationStatus = EvaluationStatus.pending
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SubmissionBase(BaseModel):
    qpid: int
    s_email: str
    evaluated: bool = False
    total_marks_obtained: Decimal = Decimal("0.0")
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# Teacher Schemas
class AnswerTeacherOut(AnswerBase):
    pass


class SubmissionTeacherOut(SubmissionBase):
    student_name: Optional[str] = None


class SubmissionDetailTeacherOut(SubmissionTeacherOut):
    answers: List[AnswerTeacherOut] = Field(default_factory=list)


# Student Schemas
class AnswerStudentOut(AnswerBase):
    pass


class SubmissionStudentOut(SubmissionBase):
    pass


class SubmissionDetailStudentOut(SubmissionStudentOut):
    answers: List[AnswerStudentOut] = Field(default_factory=list)
