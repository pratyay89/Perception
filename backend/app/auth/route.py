from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    get_current_teacher,
    get_current_user,
    get_token_data,
)
from app.auth.model import AppUser
from app.auth.schemas import (
    AssociationsOut,
    Token,
    TokenOut,
    UsageOut,
    UserCreate,
    UserOut,
)
from app.auth.service import AuthService
from app.database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(user_in: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    """Register a new student or teacher account."""
    user = await AuthService.get_user_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    return await AuthService.create_user(db, user_in)


@router.post("/login", response_model=TokenOut)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Exchange email (sent as `username`) and password for an access token."""
    user = await AuthService.authenticate_user(
        db, form_data.username, form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    access_token = AuthService.create_access_token(
        email=user.email, role=user.user_type.value, uid=user.uid
    )

    return TokenOut(
        access_token=access_token,
        email=user.email,
        role=user.user_type,
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: AppUser = Depends(get_current_user)):
    """The account that owns the access token."""
    return current_user


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def delete_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Token = Depends(get_token_data),
):
    """Delete the current account and everything that belongs to it."""
    await AuthService.delete_user(db, email=current_user.email)


@router.get("/associations", response_model=AssociationsOut)
async def get_association(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Token = Depends(get_token_data),
):
    """A teacher gets their students; a student gets their teachers."""
    return await AuthService.get_associations(
        db, email=current_user.email, role=current_user.role
    )


@router.post("/associations", status_code=status.HTTP_200_OK)
async def create_association(
    s_email: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Token = Depends(get_current_teacher),
):
    """Add a registered student to the teacher's class."""
    await AuthService.create_association(
        db, t_email=current_user.email, s_email=s_email
    )
    return {"message": "Student added"}


@router.delete("/associations", status_code=status.HTTP_204_NO_CONTENT)
async def delete_association(
    s_email: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Token = Depends(get_current_teacher),
):
    """Remove a student from the teacher's class."""
    await AuthService.delete_association(
        db, t_email=current_user.email, s_email=s_email
    )


@router.get("/usage", response_model=UsageOut)
async def get_usage(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Token = Depends(get_token_data),
):
    """Remaining monthly allowance of the current user."""
    return await AuthService.get_usage(db, email=current_user.email)
