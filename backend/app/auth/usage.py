"""Monthly usage limits (papers created, submissions made, LLM tokens).

Balances are changed with single SQL UPDATE statements, never by reading a
value into Python and writing it back, so that simultaneous requests cannot
overspend a limit or lose a charge.
"""

from datetime import date
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.model import UserUsage
from app.config import settings

Allowance = Literal["papers", "submissions"]

_ALLOWANCE_COLUMNS = {
    "papers": (
        UserUsage.papers_created_balance_monthly,
        UserUsage.total_papers_created,
    ),
    "submissions": (
        UserUsage.submissions_made_balance_monthly,
        UserUsage.total_submissions_made,
    ),
}


def _full_balances() -> dict:
    return {
        UserUsage.papers_created_balance_monthly: settings.PAPERS_CREATED_MONTHLY_LIMIT,
        UserUsage.submissions_made_balance_monthly: settings.SUBMISSIONS_MADE_MONTHLY_LIMIT,
        UserUsage.llm_tokens_balance_monthly: settings.LLM_TOKEN_BALANCE_MONTHLY_LIMIT,
    }


async def get_usage(
    db: AsyncSession, email: str, *, today: date | None = None
) -> UserUsage:
    """Return the usage row for a user, refilling the balances on a new month.

    The row is created if it is missing. Nothing is committed here: the
    changes belong to the caller's transaction.
    """
    today = today or date.today()
    first_of_month = today.replace(day=1)

    # Refill once per calendar month. The WHERE clause makes this safe when
    # several requests arrive at the same time: only one of them matches.
    await db.execute(
        update(UserUsage)
        .where(UserUsage.email == email, UserUsage.last_reset_date < first_of_month)
        .values({**_full_balances(), UserUsage.last_reset_date: today})
        .execution_options(synchronize_session=False)
    )

    query = (
        select(UserUsage)
        .where(UserUsage.email == email)
        .execution_options(populate_existing=True)
    )
    usage = (await db.execute(query)).scalar_one_or_none()

    if usage is None:
        try:
            async with db.begin_nested():
                db.add(
                    UserUsage(
                        email=email,
                        total_papers_created=0,
                        total_submissions_made=0,
                        total_llm_tokens_used=0,
                        papers_created_balance_monthly=settings.PAPERS_CREATED_MONTHLY_LIMIT,
                        submissions_made_balance_monthly=settings.SUBMISSIONS_MADE_MONTHLY_LIMIT,
                        llm_tokens_balance_monthly=settings.LLM_TOKEN_BALANCE_MONTHLY_LIMIT,
                        last_reset_date=today,
                    )
                )
        except IntegrityError:
            # Another request created the row a moment ago
            pass
        usage = (await db.execute(query)).scalar_one()

    return usage


async def consume(db: AsyncSession, email: str, allowance: Allowance) -> bool:
    """Take one unit from a monthly allowance. False if none is left.

    Call `get_usage` first so the row exists and the monthly refill is applied.
    """
    balance, total = _ALLOWANCE_COLUMNS[allowance]
    result = await db.execute(
        update(UserUsage)
        .where(UserUsage.email == email, balance > 0)
        .values({balance: balance - 1, total: total + 1})
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


async def charge_tokens(db: AsyncSession, email: str, tokens: int) -> None:
    """Deduct LLM tokens from the monthly balance and add them to the total."""
    if tokens <= 0:
        return
    await db.execute(
        update(UserUsage)
        .where(UserUsage.email == email)
        .values(
            {
                UserUsage.llm_tokens_balance_monthly: UserUsage.llm_tokens_balance_monthly
                - tokens,
                UserUsage.total_llm_tokens_used: UserUsage.total_llm_tokens_used
                + tokens,
            }
        )
        .execution_options(synchronize_session=False)
    )
