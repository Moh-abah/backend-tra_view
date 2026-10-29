"""Authentication service — JWT issuing/validation, password hashing and
FastAPI auth dependencies (all async).

Contract exposed (used as FastAPI dependencies):

* ``get_current_user_or_bypass`` / ``get_current_active_user_or_bypass``
  dev-friendly: when ``DEBUG`` and ``DISABLE_AUTH`` are on, resolves (or
  creates) the dev user; falls back to an in-memory stub if the DB is down.
* ``get_current_user`` / ``get_current_active_user`` / ``get_current_superuser``
  production dependencies — a valid Bearer token is mandatory.
* ``authenticate_user``, ``create_access_token``, ``create_refresh_token``,
  ``verify_token`` — token/user primitives.

All database access is fully async (``select`` + ``await db.execute(...)``).
"""

import logging
import secrets as secrets_module
import types
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

# passlib 1.7.4 cannot initialize its bcrypt backend with bcrypt>=4.1/5.0
# (its backend self-test hashes a >72-byte probe which bcrypt 5.0 rejects).
# Silence the trapped-version noise and probe once; fall back to direct
# bcrypt (hash-format compatible) when passlib cannot initialize.
logging.getLogger("passlib").setLevel(logging.ERROR)
try:
    from passlib.context import CryptContext

    _pwd_context: Optional[CryptContext] = CryptContext(schemes=["bcrypt"], deprecated="auto")
    _pwd_context.hash("backend-init-probe")  # force backend initialization
except Exception:  # noqa: BLE001 — any backend failure means "use bcrypt directly"
    _pwd_context = None

_BCRYPT_ROUNDS = 12
_BCRYPT_MAX_BYTES = 72  # bcrypt operates on at most 72 bytes of password

# JWT configuration comes exclusively from settings (env / .env).
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

pwd_context = _pwd_context
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login", auto_error=False)

logger = logging.getLogger(__name__)
_dev_fallback_warned = False

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _require_signing_secret() -> None:
    """Abort with a clear error if JWTs are requested without a SECRET_KEY."""
    if not SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SECRET_KEY not configured — set it in the environment/.env file",
        )


class AuthService:
    """Authentication and user-resolution primitives (all async)."""

    # ------------------------------------------------------------------ #
    # Password hashing
    # ------------------------------------------------------------------ #
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            if pwd_context is not None:
                return pwd_context.verify(plain_password, hashed_password)
            return bcrypt.checkpw(
                plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES],
                hashed_password.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False

    @staticmethod
    def get_password_hash(password: str) -> str:
        if pwd_context is not None:
            return pwd_context.hash(password)
        return bcrypt.hashpw(
            password.encode("utf-8")[:_BCRYPT_MAX_BYTES],
            bcrypt.gensalt(rounds=_BCRYPT_ROUNDS),
        ).decode("utf-8")

    # ------------------------------------------------------------------ #
    # Tokens
    # ------------------------------------------------------------------ #
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create an access JWT: ``sub`` + ``type=access`` + ``exp``."""
        _require_signing_secret()
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta
            if expires_delta is not None
            else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire})
        # Default to an access token, but let callers (email verification,
        # password reset) issue purpose-typed tokens via the same signer.
        to_encode.setdefault("type", "access")
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """Create a refresh JWT: ``sub`` + ``type=refresh`` + ``exp``."""
        _require_signing_secret()
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """Return the decoded payload, or None if invalid/expired."""
        if not SECRET_KEY:
            return None
        try:
            return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            return None

    # ------------------------------------------------------------------ #
    # User resolution
    # ------------------------------------------------------------------ #
    @staticmethod
    async def authenticate_user(
        db: AsyncSession, username: str, password: str
    ) -> Optional[User]:
        """Return the user if ``username``/``password`` are valid, else None.

        Contract-compatibility (frontend parity): the identifier may be a
        username OR an email address. When it looks like an email we try the
        email column first, then fall back to username lookup — so both the
        legacy form login and the JSON email login work unchanged.
        """
        identifier = (username or "").strip()
        user: Optional[User] = None

        if "@" in identifier:
            result = await db.execute(select(User).where(User.email == identifier))
            user = result.scalar_one_or_none()
            if user is None:
                result = await db.execute(select(User).where(User.username == identifier))
                user = result.scalar_one_or_none()
        else:
            result = await db.execute(select(User).where(User.username == identifier))
            user = result.scalar_one_or_none()

        if user is None or not AuthService.verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    async def _get_or_create_dev_user(db: AsyncSession) -> User:
        """Find (or create) the well-known dev user used when auth is bypassed."""
        result = await db.execute(select(User).where(User.email == "dev@example.com"))
        user = result.scalar_one_or_none()
        if user is not None:
            return user

        user = User(
            email="dev@example.com",
            username="devuser",
            full_name="Development User",
            hashed_password=AuthService.get_password_hash(secrets_module.token_urlsafe(32)),
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
        except Exception:  # noqa: BLE001 — concurrent creation race
            await db.rollback()
            result = await db.execute(select(User).where(User.email == "dev@example.com"))
            user = result.scalar_one_or_none()
            if user is None:
                raise
        return user

    @staticmethod
    def _dev_fallback_user() -> types.SimpleNamespace:
        """In-memory stand-in for the dev user when the DB is unreachable."""
        global _dev_fallback_warned
        if not _dev_fallback_warned:
            logger.warning(
                "Auth bypass active and database unavailable — "
                "returning in-memory dev user stub"
            )
            _dev_fallback_warned = True
        return types.SimpleNamespace(
            id=1,
            email="dev@example.com",
            username="devuser",
            full_name="Development User",
            is_active=True,
            is_verified=True,
            is_superuser=True,
            hashed_password="",
            created_at=None,
        )

    @staticmethod
    async def get_current_user_or_bypass(
        db: AsyncSession = Depends(get_db),
        token: Optional[str] = Depends(oauth2_scheme),
    ) -> User:
        """Resolve the current user; bypasses auth in dev when enabled."""
        if settings.DEBUG and settings.DISABLE_AUTH:
            try:
                return await AuthService._get_or_create_dev_user(db)
            except Exception:  # noqa: BLE001 — DB down must not kill dev flow
                return AuthService._dev_fallback_user()
        return await AuthService.get_current_user(db, token)

    @staticmethod
    async def get_current_user(
        db: AsyncSession = Depends(get_db),
        token: Optional[str] = Depends(oauth2_scheme),
    ) -> User:
        """Resolve the current user from a mandatory, valid Bearer token."""
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload = AuthService.verify_token(token)
        if payload is None:
            raise _CREDENTIALS_EXCEPTION

        username = payload.get("sub")
        if username is None:
            raise _CREDENTIALS_EXCEPTION

        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None:
            raise _CREDENTIALS_EXCEPTION

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled",
            )
        return user

    @staticmethod
    async def get_current_active_user_or_bypass(
        current_user: User = Depends(get_current_user_or_bypass),
    ) -> User:
        """Same as the bypass resolver, but also enforces ``is_active``."""
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled",
            )
        return current_user

    @staticmethod
    async def get_current_active_user(
        current_user: User = Depends(get_current_user),
    ) -> User:
        """Enforce that the authenticated user is active."""
        if not current_user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        return current_user

    @staticmethod
    async def get_current_superuser(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        """Enforce superuser privileges."""
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return current_user
