"""Async SQLAlchemy engine / session management — single source of truth.

The engine is built from ``settings.DATABASE_URL`` (environment only — no
hardcoded credentials). Supported backends:

* PostgreSQL (asyncpg) — ``postgresql+asyncpg://user:pass@host/db?sslmode=require``

  IMPORTANT: SQLAlchemy's asyncpg dialect forwards URL query params verbatim
  as ``**kwargs`` to ``asyncpg.connect()``. asyncpg is NOT libpq — it does not
  accept ``sslmode=`` (a psycopg2/libpq parameter) as a keyword, and doing so
  raises ``TypeError: connect() got an unexpected keyword argument 'sslmode'``.
  Therefore we strip the ssl params from the URL here and translate them into
  asyncpg-native ``connect_args={"ssl": ...}``:

      sslmode=disable            -> ssl=False
      sslmode=require|prefer|allow -> ssl=True  (encrypt, no cert verification —
                                  identical semantics to libpq sslmode=require)
      sslmode=verify-ca          -> SSLContext (CA-validated, hostname skipped)
      sslmode=verify-full        -> SSLContext (CA-validated + hostname checked)

  Pooler endpoints (pgbouncer in transaction mode — e.g. Neon ``-pooler``
  hosts) break asyncpg server-side prepared statements, so when the host
  contains ``pooler`` (or ``?pgbouncer=true``) we set
  ``statement_cache_size=0`` automatically.

* SQLite (aiosqlite) — ``sqlite+aiosqlite:///./file.db``; any ``?ssl...``
  query params are stripped and ``check_same_thread=False`` is applied.

An empty DATABASE_URL aborts startup with a clear error (the app lifespan
logs the exception instead of crashing the process silently).
"""

import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

DATABASE_URL: str = settings.DATABASE_URL
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured. Set it in the environment/.env file, "
        "e.g. postgresql+asyncpg://user:pass@host/db?sslmode=require "
        "or sqlite+aiosqlite:///./trading.db"
    )


def build_asyncpg_connect_args(url_str: str) -> tuple[str, dict]:
    """Normalize a Postgres URL for the asyncpg driver.

    Pops ``sslmode`` / ``ssl`` / ``pgbouncer`` from the URL query and returns
    ``(clean_url, connect_args)`` ready for ``create_async_engine``. Keeping
    this as a pure function makes it unit-testable without a live database.
    """
    from sqlalchemy.engine import make_url

    url = make_url(url_str)

    # Accept bare ``postgresql://`` too — create_async_engine requires an
    # async driver; upgrade to asyncpg instead of failing at startup.
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")

    query = dict(url.query)
    raw_mode = query.pop("sslmode", None)
    if raw_mode is None:
        raw_mode = query.pop("ssl", None)
    pgbouncer = query.pop("pgbouncer", None)
    host = url.host or ""

    connect_args: dict = {}
    mode = str(raw_mode).strip().lower() if raw_mode is not None else None

    if mode in (None, "", "disable", "false", "none", "0"):
        if mode is not None:  # explicit disable → force SSL off
            connect_args["ssl"] = False
    elif mode in ("verify-ca", "verify-full"):
        ctx = ssl.create_default_context()
        if mode == "verify-ca":
            # CA-validated but hostname-agnostic (libpq verify-ca semantics).
            ctx.check_hostname = False
        connect_args["ssl"] = ctx
    else:
        # require / prefer / allow / true → encrypted, no cert verification.
        connect_args["ssl"] = True

    if "pooler" in host or str(pgbouncer).strip().lower() in ("true", "1", "yes"):
        # pgbouncer transaction pooling cannot handle server-side prepared
        # statements (Neon/Supabase poolers) → disable the statement cache.
        connect_args["statement_cache_size"] = 0

    clean_url = url.set(query=query)
    return clean_url.render_as_string(hide_password=False), connect_args


_IS_SQLITE = DATABASE_URL.startswith("sqlite")

if _IS_SQLITE:
    # aiosqlite neither understands nor needs ssl*/driver query params.
    DATABASE_URL = DATABASE_URL.split("?", 1)[0]
    engine = create_async_engine(
        DATABASE_URL,
        # SQL_ECHO افتراضياً مغلق حتى مع DEBUG — echo يطوف اللوق بـ BEGIN/ROLLBACK
        echo=bool(getattr(settings, "SQL_ECHO", False)),
        future=True,
        connect_args={"check_same_thread": False},
    )

    # app/models/signal.py uses postgresql.UUID (native on Postgres only).
    # Teach the SQLite dialect to render it as CHAR(36) so init_db can create
    # the full schema on the SQLite fallback. No-op on Postgres.
    from sqlalchemy.dialects.postgresql import UUID as _PgUUID
    from sqlalchemy.ext.compiler import compiles as _compiles

    @_compiles(_PgUUID, "sqlite")
    def _render_sqlite_uuid(element, compiler, **kw):
        return "CHAR(36)"
else:
    clean_url, _pg_connect_args = build_asyncpg_connect_args(DATABASE_URL)
    engine = create_async_engine(
        clean_url,
        echo=bool(getattr(settings, "SQL_ECHO", False)),
        future=True,
        pool_pre_ping=True,  # guards stale pooled conns (serverless DBs like Neon)
        connect_args=_pg_connect_args,
    )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Alias kept for callers that use the sessionmaker-style name.
async_session_maker = AsyncSessionLocal

Base = declarative_base()


async def get_db():
    """FastAPI dependency yielding an AsyncSession (always closed afterwards)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Create all ORM tables (no-op for tables that already exist)."""
    # Import models so every table is registered on Base.metadata.
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Dispose of the engine's connection pool."""
    await engine.dispose()
    