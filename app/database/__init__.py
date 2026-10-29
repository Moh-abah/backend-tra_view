"""Database package — clean re-exports only (no duplicate definitions).

The engine/session machinery lives in :mod:`app.database.session`; the Redis
helper lives in :mod:`app.database.redis_client`. Importing this package also
imports the ORM models so that ``Base.metadata`` is fully populated (needed
by ``init_db`` and Alembic-style create_all flows).
"""

# Import order matters: ``session`` must load before the models because the
# model modules do ``from app.database import Base`` (package attribute must
# already be bound when this package is the entry point of the import chain).
from .session import (
    DATABASE_URL,
    AsyncSessionLocal,
    Base,
    async_session_maker,
    close_db,
    engine,
    get_db,
    init_db,
)
from .redis_client import redis_client
import app.models  # noqa: F401,E402  (registers all ORM models on Base.metadata)

__all__ = [
    "DATABASE_URL",
    "AsyncSessionLocal",
    "Base",
    "async_session_maker",
    "close_db",
    "engine",
    "get_db",
    "init_db",
    "redis_client",
]
