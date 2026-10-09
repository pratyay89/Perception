import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.model import AppUser
from app.auth.schemas import Token
from app.config import settings
from app.core.model import UserType
from app.database import get_db

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def decode_access_token(token: str) -> Token:
    """Verify the signature and expiry of a token and return its contents."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["exp", "email", "role", "uid"]},
        )
        return Token(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.PyJWTError, ValidationError):
        raise _CREDENTIALS_ERROR


async def get_current_user(
    token: str = Depends(reusable_oauth2),
    db: AsyncSession = Depends(get_db),
) -> AppUser:
    """The account behind the token. Fails if the account no longer exists."""
    token_data = decode_access_token(token)

    result = await db.execute(select(AppUser).where(AppUser.email == token_data.email))
    user = result.scalar_one_or_none()

    # A token must stop working when its account is deleted, when the role
    # changes, or when the same email is later registered as a new account.
    if (
        user is None
        or user.uid != token_data.uid
        or user.user_type.value != token_data.role
    ):
        raise _CREDENTIALS_ERROR

    return user


async def get_token_data(
    token: str = Depends(reusable_oauth2),
    user: AppUser = Depends(get_current_user),
) -> Token:
    """The verified token of an existing user (email + role)."""
    return decode_access_token(token)


async def get_current_teacher(
    token_data: Token = Depends(get_token_data),
) -> Token:
    if token_data.role != UserType.teacher.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher privileges required",
        )
    return token_data


async def get_current_student(
    token_data: Token = Depends(get_token_data),
) -> Token:
    if token_data.role != UserType.student.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student privileges required",
        )
    return token_data
