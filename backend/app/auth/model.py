import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.config import settings
from app.core.model import UserType
from app.database import Base, UTCDateTime


class AppUser(Base):
    __tablename__ = "app_users"

    email: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    # Random id of this account, embedded in its access tokens. If an account
    # is deleted and the email is registered again, old tokens stop matching.
    uid: Mapped[str] = mapped_column(
        String(32), nullable=False, default=lambda: uuid.uuid4().hex
    )
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    user_type: Mapped[UserType] = mapped_column(SQLEnum(UserType), nullable=False)

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now()
    )


class UserUsage(Base):
    __tablename__ = "user_usage"

    email: Mapped[str] = mapped_column(
        String, ForeignKey("app_users.email", ondelete="CASCADE"), primary_key=True
    )

    total_papers_created: Mapped[int] = mapped_column(Integer, default=0)
    total_submissions_made: Mapped[int] = mapped_column(Integer, default=0)
    total_llm_tokens_used: Mapped[int] = mapped_column(Integer, default=0)

    papers_created_balance_monthly: Mapped[int] = mapped_column(
        Integer, default=settings.PAPERS_CREATED_MONTHLY_LIMIT
    )
    submissions_made_balance_monthly: Mapped[int] = mapped_column(
        Integer, default=settings.SUBMISSIONS_MADE_MONTHLY_LIMIT
    )
    llm_tokens_balance_monthly: Mapped[int] = mapped_column(
        Integer, default=settings.LLM_TOKEN_BALANCE_MONTHLY_LIMIT
    )

    # First day on which the monthly balances above were last refilled.
    last_reset_date: Mapped[date] = mapped_column(Date, default=date.today)

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now()
    )


class Association(Base):
    """Links a teacher to a student. A student sees the papers of their teachers."""

    __tablename__ = "associations"

    t_email: Mapped[str] = mapped_column(
        String, ForeignKey("app_users.email", ondelete="CASCADE"), primary_key=True
    )
    s_email: Mapped[str] = mapped_column(
        String, ForeignKey("app_users.email", ondelete="CASCADE"), primary_key=True
    )
