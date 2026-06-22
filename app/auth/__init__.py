import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    LoginRequest,
    TokenCreateRequest,
    TokenResponse,
    TokenVerifyResponse,
    UserCreateRequest,
    UserResponse,
)
from app.auth.utils import generate_api_token, hash_password, verify_password
from app.core.database import get_db
from app.models.api_token import ApiToken
from app.models.user import User

router = APIRouter(prefix="/api", tags=["auth"])


async def _create_token_for_user(
    user: User,
    db: AsyncSession,
) -> TokenResponse:
    """Create (or rotate) a permanent API token for the given user.

    Each user can have at most one token — creating a new one invalidates
    the previous one.  Returns the raw token in the response (only shown once).
    """
    raw_token, token_hash, token_prefix = generate_api_token()

    # Remove any existing token for this user (one-token policy).
    result = await db.execute(select(ApiToken).where(ApiToken.user_id == user.id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.flush()

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
            detail=f"A token already exists for user '{user.id}'",
        )
    await db.refresh(api_token)

    return TokenResponse(
        token=raw_token,
        created_at=api_token.created_at,
        expires_at=api_token.expires_at,
    )


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
    """Create (or rotate) a permanent API token for a user by user ID.

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

    return await _create_token_for_user(user, db)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Log in with email and password to obtain an API token.

    Creates a new token for the user (invalidating any previous one).
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    password_ok = await asyncio.to_thread(
        verify_password, body.password, user.password_hash or ""
    )
    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return await _create_token_for_user(user, db)


@router.get("/verify-token", response_model=TokenVerifyResponse)
async def verify_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify that the Bearer API token is valid and return the associated user.

    Uses the ``Authorization: Bearer <token>`` header.  Returns 401 if the
    token is missing, malformed, unknown, or expired.
    """
    result = await db.execute(
        select(ApiToken).where(ApiToken.user_id == current_user.id)
    )
    api_token = result.scalar_one_or_none()

    return TokenVerifyResponse(
        user=UserResponse.model_validate(current_user),
        token_created_at=api_token.created_at if api_token else current_user.created_at,
        token_expires_at=api_token.expires_at if api_token else None,
    )
