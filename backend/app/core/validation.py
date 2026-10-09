"""Input checks shared by all request schemas and routes.

They exist so that bad client input is answered with a 4xx response instead of
reaching the database and surfacing as a 500.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import HTTPException, Path
from pydantic import BaseModel, Field, model_validator

# Largest value of a PostgreSQL INTEGER column
MAX_INT32 = 2_147_483_647

# Identifiers in the URL path and in request bodies
DbId = Annotated[int, Path(ge=1, le=MAX_INT32)]
BodyDbId = Annotated[int, Field(ge=1, le=MAX_INT32)]
SortOrder = Annotated[int, Field(ge=0, le=100_000)]

MIN_YEAR, MAX_YEAR = 2000, 2100


def has_unsafe_chars(value: str) -> bool:
    """True for text PostgreSQL cannot store: NUL bytes and lone surrogates."""
    return "\x00" in value or any(0xD800 <= ord(ch) <= 0xDFFF for ch in value)


def _find_unsafe(value: Any) -> bool:
    if isinstance(value, str):
        return has_unsafe_chars(value)
    if isinstance(value, dict):
        return any(_find_unsafe(k) or _find_unsafe(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_find_unsafe(item) for item in value)
    return False


class CleanModel(BaseModel):
    """Base class for request bodies: rejects text that cannot be stored."""

    @model_validator(mode="before")
    @classmethod
    def _reject_unsafe_text(cls, data: Any) -> Any:
        if _find_unsafe(data):
            raise ValueError("Text contains characters that are not allowed")
        return data


def check_reasonable_date(value: datetime) -> datetime:
    """Keeps dates in a range that survives time zone conversion."""
    if not MIN_YEAR <= value.year <= MAX_YEAR:
        raise ValueError(f"The year must be between {MIN_YEAR} and {MAX_YEAR}")
    return value


def clean_email_param(value: str) -> str:
    """Normalise an email taken from the URL (path or query string)."""
    value = value.strip().lower()
    if not value or len(value) > 320 or has_unsafe_chars(value):
        raise HTTPException(status_code=422, detail="Invalid email address")
    return value
