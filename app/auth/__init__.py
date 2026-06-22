import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import (
    TokenCreateRequest,
    TokenResponse,
    UserCreateRequest,
    UserResponse,
)
from app.auth.utils import generate_api_token, hash_password
from app.core.database import get_db
from app.models.api_token import ApiToken
from app.models.user import User

router = APIRouter(prefix="/api", tags=["auth"])


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    body: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user (admin / internal use only)."""
    # email is already lowercased by the schema validator
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{body.email}' already exists",
        )

    password_hash = await asyncio.to_thread(hash_password, body.password)
    user = User(
        email=body.email,
        password_hash=password_hash,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{body.email}' already exists",
        )
    await db.refresh(user)
    return user


@router.post(
    "/tokens",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_token(
    body: TokenCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create (or rotate) a permanent API token for a user.

    Each user can have at most one token.  Creating a new token invalidates
    the previous one.
    """
    result = await db.execute(select(User).where(User.id == body.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id '{body.user_id}' not found",
        )

    raw_token, token_hash, token_prefix = generate_api_token()

    # Remove any existing token for this user (one-token policy).
    result = await db.execute(select(ApiToken).where(ApiToken.user_id == user.id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.flush()  # flush the DELETE before INSERT to avoid UNIQUE violation

    api_token = ApiToken(
        user_id=user.id,
        token_hash=token_hash,
        token_prefix=token_prefix,
    )
    db.add(api_token)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A token already exists for user '{body.user_id}'",
        )
    await db.refresh(api_token)

    return TokenResponse(
        token=raw_token,
        created_at=api_token.created_at,
        expires_at=api_token.expires_at,
    )
