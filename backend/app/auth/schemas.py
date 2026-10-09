from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.model import UserType
from app.core.validation import CleanModel


class Token(BaseModel):
    """The verified contents of an access token."""

    email: str
    role: str
    # Id of the account the token was issued to
    uid: str
    exp: datetime


class TokenOut(BaseModel):
    """Response of the login endpoint (OAuth2 password flow)."""

    access_token: str
    token_type: str = "bearer"
    email: str
    role: UserType
    full_name: str


class UserCreate(CleanModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    # Only students and teachers can register themselves.
    user_type: UserType

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        value = value.strip().lower()
        # The email is used in URLs such as /api/submissions/{qpid}/{email}
        if "/" in value or "\\" in value:
            raise ValueError("The email address must not contain slashes")
        return value

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("full_name must not be blank")
        return value

    @field_validator("user_type")
    @classmethod
    def _no_self_service_admin(cls, value: UserType) -> UserType:
        if value == UserType.admin:
            raise ValueError("user_type must be 'student' or 'teacher'")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    email: EmailStr
    full_name: str
    user_type: UserType
    is_verified: bool

    model_config = {"from_attributes": True}


class AssociatedUser(BaseModel):
    email: str
    full_name: str


class AssociationsOut(BaseModel):
    # Emails only (kept for backwards compatibility with earlier clients)
    associations: list[str]
    # Same people, with their display names
    users: list[AssociatedUser] = Field(default_factory=list)


class UsageOut(BaseModel):
    email: str
    papers_created_balance: int
    submissions_made_balance: int
    llm_tokens_balance: int
    papers_created_limit: int
    submissions_made_limit: int
    llm_tokens_limit: int
    total_papers_created: int
    total_submissions_made: int
    total_llm_tokens_used: int
    last_reset_date: date
