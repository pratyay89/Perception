from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import usage as usage_service
from app.auth.model import AppUser, Association
from app.auth.schemas import UserCreate
from app.config import settings
from app.core.model import UserType
from app.core.validation import clean_email_param, has_unsafe_chars

# bcrypt only looks at the first 72 bytes of a password.
_BCRYPT_MAX_BYTES = 72


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    ALGORITHM = "HS256"

    @staticmethod
    def _password_bytes(password: str) -> bytes:
        return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(
                cls._password_bytes(plain_password), hashed_password.encode("utf-8")
            )
        except ValueError:
            # Stored hash is not a valid bcrypt hash
            return False

    @classmethod
    def get_password_hash(cls, password: str) -> str:
        return bcrypt.hashpw(cls._password_bytes(password), bcrypt.gensalt()).decode(
            "utf-8"
        )

    @classmethod
    def create_access_token(cls, email: str, role: str, uid: str) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        to_encode = {"exp": expires_at, "email": email, "role": role, "uid": uid}
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=cls.ALGORITHM)

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> AppUser | None:
        if has_unsafe_chars(email):
            return None
        result = await db.execute(
            select(AppUser).where(AppUser.email == normalize_email(email))
        )
        return result.scalar_one_or_none()

    @classmethod
    async def create_user(cls, db: AsyncSession, user_input: UserCreate) -> AppUser:
        email = normalize_email(user_input.email)
        new_user = AppUser(
            email=email,
            password_hash=cls.get_password_hash(user_input.password),
            full_name=user_input.full_name,
            user_type=user_input.user_type,
        )
        db.add(new_user)

        try:
            # The user row must exist before the usage row that points at it.
            await db.flush()
            await usage_service.get_usage(db, email)
            await db.commit()
        except IntegrityError:
            # Two sign-ups for the same email raced each other.
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        await db.refresh(new_user)
        return new_user

    @classmethod
    async def authenticate_user(
        cls, db: AsyncSession, email: str, password: str
    ) -> AppUser | None:
        user = await cls.get_user_by_email(db, email)
        if not user:
            return None
        if has_unsafe_chars(password):
            return None
        if not cls.verify_password(password, user.password_hash):
            return None
        return user

    @staticmethod
    async def delete_user(db: AsyncSession, email: str) -> None:
        user = await AuthService.get_user_by_email(db, email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        await db.delete(user)
        await db.commit()

    @staticmethod
    async def get_associations(db: AsyncSession, email: str, role: str) -> dict:
        """Students of a teacher, or teachers of a student."""
        if role == UserType.teacher.value:
            stmt = (
                select(AppUser.email, AppUser.full_name)
                .join(Association, Association.s_email == AppUser.email)
                .where(Association.t_email == email)
            )
        elif role == UserType.student.value:
            stmt = (
                select(AppUser.email, AppUser.full_name)
                .join(Association, Association.t_email == AppUser.email)
                .where(Association.s_email == email)
            )
        else:
            return {"associations": [], "users": []}

        rows = (await db.execute(stmt.order_by(AppUser.email))).all()
        return {
            "associations": [row.email for row in rows],
            "users": [{"email": row.email, "full_name": row.full_name} for row in rows],
        }

    @staticmethod
    async def create_association(db: AsyncSession, t_email: str, s_email: str) -> None:
        s_email = clean_email_param(s_email)
        teacher = await AuthService.get_user_by_email(db, t_email)
        student = await AuthService.get_user_by_email(db, s_email)

        if not teacher or teacher.user_type != UserType.teacher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found"
            )
        if not student or student.user_type != UserType.student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
            )

        existing = await db.execute(
            select(Association).where(
                Association.t_email == teacher.email,
                Association.s_email == student.email,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student is already in your class",
            )

        db.add(Association(t_email=teacher.email, s_email=student.email))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student is already in your class",
            )

    @staticmethod
    async def delete_association(db: AsyncSession, t_email: str, s_email: str) -> None:
        result = await db.execute(
            delete(Association).where(
                Association.t_email == normalize_email(t_email),
                Association.s_email == clean_email_param(s_email),
            )
        )
        if result.rowcount == 0:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student is not in your class",
            )
        await db.commit()

    @staticmethod
    async def get_usage(db: AsyncSession, email: str) -> dict:
        usage = await usage_service.get_usage(db, email)
        # Persists a monthly refill if one was due
        await db.commit()
        return {
            "email": usage.email,
            "papers_created_balance": usage.papers_created_balance_monthly,
            "submissions_made_balance": usage.submissions_made_balance_monthly,
            "llm_tokens_balance": usage.llm_tokens_balance_monthly,
            "papers_created_limit": settings.PAPERS_CREATED_MONTHLY_LIMIT,
            "submissions_made_limit": settings.SUBMISSIONS_MADE_MONTHLY_LIMIT,
            "llm_tokens_limit": settings.LLM_TOKEN_BALANCE_MONTHLY_LIMIT,
            "total_papers_created": usage.total_papers_created,
            "total_submissions_made": usage.total_submissions_made,
            "total_llm_tokens_used": usage.total_llm_tokens_used,
            "last_reset_date": usage.last_reset_date,
        }
