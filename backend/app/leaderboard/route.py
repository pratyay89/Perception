from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_token_data
from app.auth.schemas import Token
from app.core.validation import DbId
from app.database import get_db
from app.leaderboard.schemas import ClassLeaderboardOut, PaperLeaderboardOut
from app.leaderboard.service import LeaderboardService

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("/", response_model=List[ClassLeaderboardOut])
@router.get("", response_model=List[ClassLeaderboardOut], include_in_schema=False)
async def class_leaderboards(
    db: AsyncSession = Depends(get_db),
    current_user: Token = Depends(get_token_data),
):
    """
    Overall class standings, ranked by percentage across evaluated papers.

    - Teachers get the standings of their own class.
    - Students get one table per class they are in. Other students' email
      addresses are hidden.
    """
    return await LeaderboardService.class_leaderboards(current_user, db)


@router.get("/papers/{qpid}", response_model=PaperLeaderboardOut)
async def paper_leaderboard(
    qpid: DbId,
    db: AsyncSession = Depends(get_db),
    current_user: Token = Depends(get_token_data),
):
    """
    Ranking of the evaluated submissions of one paper, best first. Visible to
    the paper's teacher and to the students who can see the paper.
    """
    return await LeaderboardService.paper_leaderboard(qpid, current_user, db)
