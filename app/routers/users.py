"""User & authentication endpoints (fully async).

Covers registration, login (OAuth2 password flow), token refresh, the
``/me`` profile lifecycle, email verification / password reset (emails are
simulated via the logger) and superuser-only user administration.

All JWT handling goes through :class:`app.services.auth.AuthService`; all
database access uses async SQLAlchemy 2.0 style (``select`` + ``await
db.execute``).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    ChangePasswordRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    Token,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services.auth import AuthService

router = APIRouter(tags=["users"])
logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_TTL = timedelta(hours=48)
PASSWORD_RESET_TTL = timedelta(hours=24)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _send_welcome_email(email: str, username: str) -> None:
    """Simulated welcome email (no SMTP wiring in this project)."""
    logger.info("Welcome email sent to %s (user=%s) [simulated]", email, username)


def _log_email_verification_link(email: str, token: str) -> None:
    """Simulated verification email with the signed link."""
    logger.info(
        "Email verification link for %s: /api/v1/users/verify-email/%s [simulated]",
        email,
        token,
    )


def _log_password_reset_link(email: str, token: str) -> None:
    """Simulated password-reset email with the signed link."""
    logger.info(
        "Password reset link for %s: /reset-password?token=%s [simulated]",
        email,
        token,
    )


async def _get_user_by(db: AsyncSession, **filters) -> User | None:
    result = await db.execute(select(User).filter_by(**filters))
    return result.scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Registration / login / tokens
# --------------------------------------------------------------------------- #
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user (no tokens are issued here)."""
    if await _get_user_by(db, email=user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    if await _get_user_by(db, username=user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    db_user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=AuthService.get_password_hash(user_data.password),
        is_active=True,
        is_verified=False,
    )
    db.add(db_user)
    try:
        await db.commit()
        await db.refresh(db_user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered",
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user",
        )

    verification_token = AuthService.create_access_token(
        data={"sub": db_user.username, "user_id": db_user.id, "type": "email_verification"},
        expires_delta=EMAIL_VERIFICATION_TTL,
    )
    background_tasks.add_task(_send_welcome_email, db_user.email, db_user.username)
    background_tasks.add_task(_log_email_verification_link, db_user.email, verification_token)

    return db_user


@router.post("/login", response_model=Token)
async def login_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate and receive JWT tokens.

    Contract-compatibility (frontend parity) — accepts BOTH wire formats:

    1. JSON body  : {"email": "...", "password": "..."}   ← what the frontend sends
                    {"username": "...", "password": "..."} also accepted
    2. Form-encoded: username=...&password=...             ← OAuth2 password flow
                                                      (Swagger "Authorize" button)

    The identifier may be a username or an email (see AuthService.authenticate_user).
    """
    content_type = (request.headers.get("content-type") or "").lower()
    username: Optional[str] = None
    password: Optional[str] = None

    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            payload = None
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="JSON body must be an object with email/username and password",
            )
        username = payload.get("username") or payload.get("email")
        password = payload.get("password")
    else:
        form = await request.form()
        username = form.get("username") or form.get("email")
        password = form.get("password")

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide 'username' (or 'email') and 'password'",
        )

    try:
        user = await AuthService.authenticate_user(db, username, password)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed due to a database error",
        )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.last_login = datetime.now(timezone.utc)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("Could not update last_login for %s", user.username)

    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {"sub": user.username, "user_id": user.id}
    access_token = AuthService.create_access_token(token_data, expires_delta=expires_delta)
    refresh_token = AuthService.create_refresh_token(token_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int(expires_delta.total_seconds()),
    }


@router.post("/login-json", response_model=Token, include_in_schema=False)
async def login_user_json(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """JSON-only login alias (frontend parity): {"email"|"username", "password"}."""
    username = body.get("username") or body.get("email")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide 'username' (or 'email') and 'password'",
        )
    try:
        user = await AuthService.authenticate_user(db, username, password)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed due to a database error",
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user.last_login = datetime.now(timezone.utc)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("Could not update last_login for %s", user.username)

    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {"sub": user.username, "user_id": user.id}
    return {
        "access_token": AuthService.create_access_token(token_data, expires_delta=expires_delta),
        "refresh_token": AuthService.create_refresh_token(token_data),
        "token_type": "bearer",
        "expires_in": int(expires_delta.total_seconds()),
    }


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access token."""
    payload = AuthService.verify_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token data",
        )

    user = await _get_user_by(db, username=username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = AuthService.create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=expires_delta,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": int(expires_delta.total_seconds()),
        "refresh_token": body.refresh_token,
    }


# --------------------------------------------------------------------------- #
# Current user (/me)
# --------------------------------------------------------------------------- #
@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(AuthService.get_current_active_user),
):
    """Return the authenticated user's profile."""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate,
    current_user: User = Depends(AuthService.get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the authenticated user's profile."""
    update_data = user_data.model_dump(exclude_unset=True)

    if "email" in update_data and update_data["email"] != current_user.email:
        existing = await db.execute(
            select(User).where(User.email == update_data["email"], User.id != current_user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    if "username" in update_data and update_data["username"] != current_user.username:
        existing = await db.execute(
            select(User).where(User.username == update_data["username"], User.id != current_user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

    for field, value in update_data.items():
        setattr(current_user, field, value)
    current_user.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
        await db.refresh(current_user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered",
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating user",
        )
    return current_user


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(AuthService.get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the authenticated user's password."""
    if not AuthService.verify_password(body.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )

    current_user.hashed_password = AuthService.get_password_hash(body.new_password)
    current_user.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error changing password",
        )
    return {"message": "Password changed successfully"}


@router.delete("/me", response_model=MessageResponse)
async def delete_account(
    current_user: User = Depends(AuthService.get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the authenticated user's account."""
    try:
        await db.delete(current_user)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting account (associated resources may still exist)",
        )
    return {"message": "Account deleted successfully"}


# --------------------------------------------------------------------------- #
# Email verification / password reset (emails simulated via logger)
# --------------------------------------------------------------------------- #
@router.get("/verify-email/{token}", response_model=MessageResponse)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """Confirm an email address using the signed verification token."""
    payload = AuthService.verify_token(token)
    if not payload or payload.get("type") != "email_verification":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token data",
        )

    user = await _get_user_by(db, username=username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if user.is_verified:
        return {"message": "Email already verified"}

    user.is_verified = True
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Email verified successfully"}


@router.post("/request-password-reset", response_model=MessageResponse)
async def request_password_reset(
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Send (simulate) a password-reset email. Response is always generic."""
    user = await _get_user_by(db, email=body.email)
    if user is not None:
        reset_token = AuthService.create_access_token(
            data={"sub": user.username, "user_id": user.id, "type": "password_reset"},
            expires_delta=PASSWORD_RESET_TTL,
        )
        background_tasks.add_task(_log_password_reset_link, body.email, reset_token)

    return {"message": "If your email is registered, you will receive a reset link"}


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Reset the password using the signed reset token."""
    payload = AuthService.verify_token(body.token)
    if not payload or payload.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token data",
        )

    user = await _get_user_by(db, username=username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.hashed_password = AuthService.get_password_hash(body.new_password)
    user.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error resetting password",
        )
    return {"message": "Password reset successfully"}


# --------------------------------------------------------------------------- #
# Administration (superuser only)
# --------------------------------------------------------------------------- #
@router.get("/", response_model=List[UserResponse])
async def get_all_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(AuthService.get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """List users with pagination (superuser only)."""
    result = await db.execute(select(User).order_by(User.id).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: int,
    current_user: User = Depends(AuthService.get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a single user by id (superuser only)."""
    user = await _get_user_by(db, id=user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user_by_id(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(AuthService.get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Update any user by id (superuser only)."""
    user = await _get_user_by(db, id=user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    update_data = user_data.model_dump(exclude_unset=True)

    if "email" in update_data and update_data["email"] != user.email:
        existing = await db.execute(
            select(User).where(User.email == update_data["email"], User.id != user_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    if "username" in update_data and update_data["username"] != user.username:
        existing = await db.execute(
            select(User).where(User.username == update_data["username"], User.id != user_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

    for field, value in update_data.items():
        setattr(user, field, value)
    user.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered",
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating user",
        )
    return user


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user_by_id(
    user_id: int,
    current_user: User = Depends(AuthService.get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user by id (superuser only; cannot delete yourself)."""
    user = await _get_user_by(db, id=user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    try:
        await db.delete(user)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting user (associated resources may still exist)",
        )
    return {"message": "User deleted successfully"}
