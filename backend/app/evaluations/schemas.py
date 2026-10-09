from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, StringConstraints

from app.core.validation import CleanModel
from app.submissions.schemas import SubmissionDetailTeacherOut, SubmissionTeacherOut


class EvaluationMessageOut(BaseModel):
    message: str


class EvaluationResultOut(SubmissionDetailTeacherOut):
    """A submission after an evaluation run, plus what the run did."""

    # Answers graded in this run
    graded_count: int = 0
    # Answers the LLM could not grade (they can be retried)
    failed_count: int = 0
    # Answers that were not attempted (rate limit or token limit reached)
    pending_count: int = 0
    tokens_used: int = 0
    # Explains failed or pending answers, if there are any
    message: Optional[str] = None


class PaperEvaluationOut(BaseModel):
    """Summary of evaluating every submission of a paper."""

    qpid: int
    submission_count: int
    evaluated_count: int
    graded_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    tokens_used: int = 0
    message: Optional[str] = None
    submissions: List[SubmissionTeacherOut] = Field(default_factory=list)


class AnswerOverride(CleanModel):
    """A teacher's own mark (and optionally feedback) for one answer."""

    marks_obtained: Annotated[Decimal, Field(ge=0, decimal_places=2)]
    # Omit to keep the current feedback
    feedback: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
    ] = None
