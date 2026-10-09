from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_teacher
from app.auth.schemas import Token
from app.core.validation import DbId
from app.database import get_db
from app.evaluations.schemas import (
    AnswerOverride,
    EvaluationMessageOut,
    EvaluationResultOut,
    PaperEvaluationOut,
)
from app.evaluations.service import SubEvaluationService
from app.submissions.schemas import SubmissionDetailTeacherOut, SubmissionTeacherOut

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.post("/{qpid}", response_model=PaperEvaluationOut)
async def evaluate_paper(
    qpid: DbId,
    force: bool = Query(
        False, description="Re-grade answers that already have a mark as well"
    ),
    db: AsyncSession = Depends(get_db),
    current_teacher: Token = Depends(get_current_teacher),
):
    """
    Evaluate every submission of a question paper using the AI evaluator.
    Limited to the teacher who created the question paper.

    Submissions that are already evaluated are skipped unless `force` is set.
    """
    submissions, run = await SubEvaluationService.evaluate_paper(
        qpid, current_teacher, db, force=force
    )
    return PaperEvaluationOut(
        qpid=qpid,
        submission_count=len(submissions),
        evaluated_count=sum(1 for s in submissions if s.evaluated),
        graded_count=run.graded,
        failed_count=run.failed,
        pending_count=run.pending,
        tokens_used=run.tokens_used,
        message=run.message(),
        submissions=[SubmissionTeacherOut.model_validate(s) for s in submissions],
    )


@router.delete("/{qpid}", response_model=EvaluationMessageOut)
async def reset_paper_evaluation(
    qpid: DbId,
    db: AsyncSession = Depends(get_db),
    current_teacher: Token = Depends(get_current_teacher),
):
    """
    Discard the marks and feedback of every submission of a question paper.
    The students' answers are kept.
    """
    count = await SubEvaluationService.reset_paper(qpid, current_teacher, db)
    return EvaluationMessageOut(message=f"Evaluation reset for {count} submission(s)")


@router.post(
    "/{qpid}/{s_email}",
    response_model=EvaluationResultOut,
    status_code=status.HTTP_200_OK,
)
async def evaluate_submission(
    qpid: DbId,
    s_email: str,
    force: bool = Query(
        False, description="Re-grade answers that already have a mark as well"
    ),
    db: AsyncSession = Depends(get_db),
    current_teacher: Token = Depends(get_current_teacher),
):
    """
    Evaluate a specific student's submission for a question paper using the AI Evaluator.
    Limited to the teacher who created the question paper.
    """
    submission, run = await SubEvaluationService.evaluate_submission(
        qpid, s_email, current_teacher, db, force=force
    )
    detail = SubmissionDetailTeacherOut.model_validate(submission)
    return EvaluationResultOut(
        **detail.model_dump(),
        graded_count=run.graded,
        failed_count=run.failed,
        pending_count=run.pending,
        tokens_used=run.tokens_used,
        message=run.message(),
    )


@router.delete("/{qpid}/{s_email}", response_model=SubmissionDetailTeacherOut)
async def reset_submission_evaluation(
    qpid: DbId,
    s_email: str,
    db: AsyncSession = Depends(get_db),
    current_teacher: Token = Depends(get_current_teacher),
):
    """
    Discard the marks and feedback of one submission. The answers are kept.
    """
    submission = await SubEvaluationService.reset_submission(
        qpid, s_email, current_teacher, db
    )
    return SubmissionDetailTeacherOut.model_validate(submission)


@router.patch("/{qpid}/{s_email}/{qid}", response_model=SubmissionDetailTeacherOut)
async def override_answer_evaluation(
    qpid: DbId,
    s_email: str,
    qid: DbId,
    override: AnswerOverride,
    db: AsyncSession = Depends(get_db),
    current_teacher: Token = Depends(get_current_teacher),
):
    """
    Review step: the teacher sets the final mark (and optionally the feedback)
    of one answer, replacing what the AI gave.
    """
    submission = await SubEvaluationService.override_answer(
        qpid, s_email, qid, override, current_teacher, db
    )
    return SubmissionDetailTeacherOut.model_validate(submission)
