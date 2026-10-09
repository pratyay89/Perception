from decimal import Decimal
from typing import List, Union

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_token_data
from app.auth.schemas import Token
from app.core.model import EvaluationStatus, UserType
from app.core.validation import MAX_INT32, DbId
from app.database import get_db
from app.submissions.model import Submission
from app.submissions.schemas import (
    SubmissionCreate,
    SubmissionDetailStudentOut,
    SubmissionDetailTeacherOut,
    SubmissionStudentOut,
    SubmissionTeacherOut,
)
from app.submissions.service import SubmissionService

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


def student_detail_view(submission: Submission) -> SubmissionDetailStudentOut:
    """What a student may see of their own submission.

    Marks and feedback stay hidden until the whole submission is evaluated,
    so a student never sees a half-graded paper.
    """
    out = SubmissionDetailStudentOut.model_validate(submission)
    if not out.evaluated:
        out.total_marks_obtained = Decimal("0")
        for answer in out.answers:
            answer.marks_obtained = Decimal("0")
            answer.feedback = None
            answer.status = EvaluationStatus.pending
            # The time of the last change would reveal which answers are graded
            answer.updated_at = None
        out.updated_at = None
    return out


def student_list_view(submission: Submission) -> SubmissionStudentOut:
    out = SubmissionStudentOut.model_validate(submission)
    if not out.evaluated:
        out.total_marks_obtained = Decimal("0")
        out.updated_at = None
    return out


@router.post(
    "/{qpid}",
    response_model=SubmissionDetailStudentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_submission(
    qpid: DbId,
    submission_in: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Token = Depends(get_token_data),
):
    """
    Submit answers for a particular question paper. Limited to students of the
    teacher who owns the paper, while the paper is open. One submission per paper.
    """
    submission = await SubmissionService.create_submission(
        qpid, submission_in, current_user, db
    )
    return student_detail_view(submission)


@router.get(
    "/{qpid}",
    response_model=Union[List[SubmissionTeacherOut], List[SubmissionStudentOut]],
)
async def list_submissions_for_paper(
    qpid: DbId,
    skip: int = Query(0, ge=0, le=MAX_INT32),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: Token = Depends(get_token_data),
):
    """
    Retrieve all submissions for a specific question paper.
    The teacher who owns the paper gets every submission; a student gets only their own.
    """
    submissions = await SubmissionService.get_submissions_for_paper(
        qpid, skip, limit, current_user, db
    )

    if current_user.role == UserType.teacher.value:
        return [SubmissionTeacherOut.model_validate(s) for s in submissions]
    else:
        return [student_list_view(s) for s in submissions]


@router.get(
    "/{qpid}/{s_email}",
    response_model=Union[SubmissionDetailTeacherOut, SubmissionDetailStudentOut],
)
async def get_submission(
    qpid: DbId,
    s_email: str,
    db: AsyncSession = Depends(get_db),
    current_user: Token = Depends(get_token_data),
):
    """
    Retrieve a specific submission and its answers.
    Students can only retrieve their own; teachers only those of their own papers.
    """
    submission = await SubmissionService.get_submission(qpid, s_email, current_user, db)

    if current_user.role == UserType.teacher.value:
        return SubmissionDetailTeacherOut.model_validate(submission)
    else:
        return student_detail_view(submission)


@router.delete("/{qpid}/{s_email}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_submission(
    qpid: DbId,
    s_email: str,
    db: AsyncSession = Depends(get_db),
    current_user: Token = Depends(get_token_data),
):
    """
    Delete a specific submission.
    Students can withdraw their own until it is evaluated.
    Teachers can delete any submission on their own question paper.
    """
    await SubmissionService.delete_submission(qpid, s_email, current_user, db)
