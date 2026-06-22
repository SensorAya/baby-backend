import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserCreateRequest(BaseModel):
    """Payload for registering a new user."""

    email: str = Field(..., max_length=255, examples=["admin@example.com"])
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,  # bcrypt 72-byte limit
    )

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v.lower()  # normalize to lowercase


class TokenCreateRequest(BaseModel):
    """Payload for creating / rotating a user's permanent API token."""

    user_id: UUID


class UserResponse(BaseModel):
    """Public user representation returned by the API."""

    id: UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Returned once when a token is created — the raw token is NOT stored."""

    token: str
    created_at: datetime
    expires_at: datetime | None = None
