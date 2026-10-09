from typing import List, Union

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_teacher, get_token_data
from app.auth.schemas import Token
from app.core.model import UserType
from app.core.validation import MAX_INT32, DbId
from app.database import get_db
from app.papers.schemas import (
    QuestionPaperCreate,
    QuestionPaperOut,
    QuestionPaperStudentOut,
    QuestionPaperTeacherOut,
    QuestionPaperUpdate,
)
from app.papers.service import PaperService

router = APIRouter(prefix="/api/papers", tags=["papers"])


@router.post(
    "/", response_model=QuestionPaperTeacherOut, status_code=status.HTTP_201_CREATED
)
@router.post(
    "",
    response_model=QuestionPaperTeacherOut,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_paper(
    paper_in: QuestionPaperCreate,
    db: AsyncSession = Depends(get_db),
    current_teacher: Token = Depends(get_current_teacher),
):
    """
    Create a new question paper along with questions. Limited to teachers.
    """
    paper = await PaperService.create_paper(paper_in, current_teacher, db)
    return QuestionPaperTeacherOut.model_validate(paper)


@router.get("/", response_model=List[QuestionPaperOut])
@router.get("", response_model=List[QuestionPaperOut], include_in_schema=False)
async def list_papers(
    skip: int = Query(0, ge=0, le=MAX_INT32),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: Token = Depends(get_token_data),
):
    """
    List question papers (without their questions).

    - Teachers get the papers they created, with submission counts.
    - Students get the published papers of their teachers, with their own
      attempt status and, once evaluated, their marks.
    """
    return await PaperService.get_papers(skip, limit, current_user, db)


@router.get(
    "/{qpid}", response_model=Union[QuestionPaperTeacherOut, QuestionPaperStudentOut]
)
async def get_paper(
    qpid: DbId,
    db: AsyncSession = Depends(get_db),
    current_user: Token = Depends(get_token_data),
):
    """
    Retrieve a specific question paper by ID, including its associated questions.
    Teachers also get the model answers and rubrics; students never do.
    """
    paper = await PaperService.get_paper(qpid, current_user, db)

    if current_user.role == UserType.teacher.value:
        return QuestionPaperTeacherOut.model_validate(paper)
    else:
        return QuestionPaperStudentOut.model_validate(paper)


@router.patch("/{qpid}", response_model=QuestionPaperTeacherOut)
async def update_paper(
    qpid: DbId,
    paper_in: QuestionPaperUpdate,
    db: AsyncSession = Depends(get_db),
    current_teacher: Token = Depends(get_current_teacher),
):
    """
    Update a question paper and its questions. Limited to the teacher who owns it.

    Use `is_published` to publish or unpublish, and `is_closed` to stop or
    resume accepting submissions.
    """
    paper = await PaperService.update_paper(qpid, paper_in, current_teacher, db)
    return QuestionPaperTeacherOut.model_validate(paper)


@router.delete("/{qpid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paper(
    qpid: DbId,
    db: AsyncSession = Depends(get_db),
    current_teacher: Token = Depends(get_current_teacher),
):
    """
    Delete a question paper with its submissions. Limited to the teacher who owns it.
    """
    await PaperService.delete_paper(qpid, current_teacher, db)
