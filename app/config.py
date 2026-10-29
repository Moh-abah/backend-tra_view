"""Application settings (pydantic-settings v2).

Single source of truth for configuration. Values are loaded from the
environment with a `.env` file fallback (development). Secrets are NEVER
hardcoded here — they must come from the environment (.env / env vars).

Fail-fast rule (module level): when running with DEBUG=False, a real
SECRET_KEY must be present, otherwise startup aborts with a clear error.
"""

from typing import List, Optional

import json

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application ------------------------------------------------------
    PROJECT_NAME: str = "Trading Backend"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Declared exactly once. Dev convenience flags — never enable in prod.
    DEBUG: bool = False
    DISABLE_AUTH: bool = False

    LOG_LEVEL: str = "INFO"

    # --- Data stores (secrets come from env ONLY; empty by default) --------
    # Postgres example: postgresql+asyncpg://user:pass@host/db?sslmode=require
    # SQLite fallback example: sqlite+aiosqlite:///./trading.db
    DATABASE_URL: str = ""
    REDIS_URL: str = ""

    # Disk (parquet) cache for historical klines — makes repeat dashboard
    # requests for the same window ~instant (only the new tail is fetched).
    # Mount this path as a Docker volume so the cache survives restarts.
    DATA_CACHE_DIR: str = "data/history"

    # --- CORS ---------------------------------------------------------------
    # Accepts either CORS_ORIGINS or the legacy ALLOWED_ORIGINS env var, as a
    # JSON list string or a comma-separated string.
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000"],
        validation_alias=AliasChoices("CORS_ORIGINS", "ALLOWED_ORIGINS"),
    )

    # --- Market data sources -------------------------------------------------
    BINANCE_WS_URL: str = "wss://stream.binance.com:9443/ws"
    BINANCE_API_URL: str = "https://api.binance.com"
    ALPACA_API_KEY: Optional[str] = None
    ALPACA_SECRET_KEY: Optional[str] = None
    POLYGON_API_KEY: Optional[str] = None
    ALPHA_VANTAGE_API_KEY: Optional[str] = None

    # --- Security / JWT -------------------------------------------------------
    # Defaults to empty on purpose: token creation refuses to work when it is
    # not configured, and the module-level validator below aborts startup for
    # non-DEBUG deployments.
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENCRYPTION_KEY: str = ""

    # --- Email (optional) -------------------------------------------------------
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None

    # --- Validators ---------------------------------------------------------------
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value):
        """Coerce bare filesystem paths / ``file:`` URIs into async SQLite URLs.

        Accepts ``/path/to.db``, ``./path/to.db`` and ``file:/path/to.db`` so a
        plain SQLite location can be supplied via the environment without
        remembering SQLAlchemy's URL syntax.
        """
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.startswith("file:"):
                candidate = candidate[len("file:"):]
            if candidate.startswith("/") or candidate.startswith("./"):
                return f"sqlite+aiosqlite:///{candidate}"
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value):
        """Accept a JSON list string, a comma-separated string, or a list."""
        if value is None:
            return ["http://localhost:3000"]
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()


# Module-level fail-fast validation (runs once at import time).
if not settings.DEBUG and (
    not settings.SECRET_KEY or settings.SECRET_KEY.startswith("your-")
):
    raise RuntimeError(
        "Insecure configuration: SECRET_KEY is missing or still a placeholder "
        '(starts with "your-"). Set a real SECRET_KEY in the environment/.env '
        "before running with DEBUG=false. Generate one with: "
        'python -c "import secrets; print(secrets.token_urlsafe(48))"'
    )
