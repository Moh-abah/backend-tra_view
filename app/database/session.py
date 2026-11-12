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

import asyncio
import logging
import os
import sqlite3
import ssl

from sqlalchemy.exc import OperationalError as _SQLOperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from app.config import settings

_logger = logging.getLogger("app.database.session")

# ============================================================
# ✅ الجولة 44 — درع قفل قاعدة البيانات (SQLite Lock Shield)
# ============================================================
# المشكلة التي حلّتها هذه الجولة (من سجل الإنتاج الحرفي):
#   sqlite3.OperationalError: database is locked
#   - INSERT ضخم (chart_data ≈ 3.2MB) في backtest_runs من المهمة الموحدة
#   - SELECT ضخم (GET /get) في نفس اللحظة + كتابات متزامنة أخرى
#   SQLite بوضعه الافتراضي (journal_mode=DELETE) يحجب القرّاء أثناء
#   الكتابة والعكس، والمهلة الافتراضية 5 ثوانٍ فقط ← فشلت المهمة الموحدة
#   "رغم نجاح المحاكاة نفسها" (27.7% ربح / 23 صفقة ضاعت عند الحفظ)
#   وفشل GET /get بخطأ 500.
#
# الطبقات الثلاث للدرع (تُركّب تلقائياً على كل اتصال جديد):
#   1) WAL (journal_mode=WAL): القرّاء لا يحجبون الكاتب والكاتب لا يحجب
#      القرّاء. الوضع محفوظ داخل ملف القاعدة نفسه — يُثبَّت مرة ويبقى
#      للأبد لكل الاتصالات اللاحقة (حتى الخارجية منها).
#   2) busy_timeout=30s: بدل الفشل بعد 5 ثوانٍ، ينتظر الكاتب حتى 30 ثانية
#      حتى يفرغ القفل (في WAL فقط الكتّاب يتزاحمون فيما بينهم).
#   3) with_lock_retry / execute_with_lock_retry: إعادة محاولة تصاعدية
#      (0.35 ← 0.7 ← 1.4 ← 2.8 ← 5.6 ثانية) للنقاط الساخنة — حزام أمان
#      فوق الحزامين الأولين لأي قفل شاذ (سكربت صيانة خارجي مثلاً).
#
# الإعدادات اختيارية عبر البيئة وبقيم افتراضية آمنة (لا تحتاج أي .env):
#   SQLITE_BUSY_TIMEOUT_MS=30000 · SQLITE_LOCK_RETRIES=5
#   SQLITE_LOCK_BASE_DELAY=0.35  · SQLITE_LOCK_MAX_DELAY=6.0
#
# ملاحظات:
#   - كل هذا خاص بمسار SQLite فقط — مسار PostgreSQL لا يُمَس إطلاقاً.
#   - WAL يتطلب أن يكون ملف القاعدة على نظام ملفات محلي (حاويات Docker:
#     volume عادي = يعمل). لا يتطلب أي تغيير في المخطط أو البيانات.
#   - synchronous=NORMAL هو الإعداد الموصى به رسمياً مع WAL (آمن + أسرع).

SQLITE_BUSY_TIMEOUT_MS = int(getattr(settings, "SQLITE_BUSY_TIMEOUT_MS", 30000) or 30000)
SQLITE_LOCK_RETRIES = int(getattr(settings, "SQLITE_LOCK_RETRIES", 5) or 5)
SQLITE_LOCK_BASE_DELAY = float(getattr(settings, "SQLITE_LOCK_BASE_DELAY", 0.35) or 0.35)
SQLITE_LOCK_MAX_DELAY = float(getattr(settings, "SQLITE_LOCK_MAX_DELAY", 6.0) or 6.0)

_LOCKED_MARKERS = ("database is locked", "database table is locked")


def is_locked_error(exc: BaseException) -> bool:
    """هل هذا الاستثناء (أو سببه الجذري) خط قفل SQLite؟

    يفحص سلسلة الأسباب كاملة لأن sqlite3.OperationalError قد يظهر ملفوفاً
    داخل sqlalchemy.exc.OperationalError (orig) أو داخل asyncio — الرسالة
    الحرفية "database is locked" هي الفيصل في الطبقة التشغيلية.
    """
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, (_SQLOperationalError, sqlite3.Error)):
            orig = getattr(cur, "orig", None)
            msg = str(orig if orig is not None else cur).lower()
            if any(m in msg for m in _LOCKED_MARKERS):
                return True
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return False


def install_sqlite_lock_shield(target_async_engine) -> None:
    """تركيب PRAGMA الدرع على كل اتصال جديد يفتحه المحرك.

    يعمل مع المحرك الرئيسي ومع محركات ``build_isolated_session_maker`` —
    الحدث يُسجَّل على ``sync_engine`` (المحرك غير المتزامن يغلّف متزامناً
    داخلياً وهذا هو النمط الرسمي لأحداث connect مع aiosqlite).
    الترتيب مقصود: busy_timeout أولاً حتى يستطيع تبديل WAL الانتظار إن
    كان الملف مزدحماً لحظة التبديل (التبديل نفسه يحدث مرة واحدة فقط).
    """
    from sqlalchemy import event

    @event.listens_for(target_async_engine.sync_engine, "connect")
    def _r44_sqlite_lock_shield(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            try:
                cursor.close()
            except Exception:  # noqa: BLE001
                pass


def _lock_retry_delay(attempt: int) -> float:
    """مدة الانتظار قبل المحاولة رقم ``attempt`` (تصاعدية بسقف أقصى)."""
    return min(SQLITE_LOCK_BASE_DELAY * (2 ** (attempt - 1)), SQLITE_LOCK_MAX_DELAY)


async def with_lock_retry(action, *, what: str = "db-op", session=None):
    """تنفيذ عملية قاعدة بيانات مع إعادة محاولة تصاعدية عند قفل SQLite.

    - ``action``: كوروتين-فاكتوري — كل محاولة تستدعيه من جديد، لذا يجب أن
      يكون قابلاً لإعادة التنفيذ (يفتح جلسته الخاصة أو يعيد add بعد rollback).
    - ``session``: اختياري — إن مُرّر يُنفَّذ ``rollback`` قبل كل محاولة
      تالية لتفادي جلسة بحالة معاملة مكسورة.
    أي خطأ غير القفل (اتصال/صياغة/منطق) يُرفع فوراً بلا أي إعادة محاولة.
    """
    last_exc = None
    for attempt in range(1, SQLITE_LOCK_RETRIES + 1):
        try:
            return await action()
        except _SQLOperationalError as exc:
            if not is_locked_error(exc):
                raise
            last_exc = exc
            if attempt >= SQLITE_LOCK_RETRIES:
                break
            if session is not None:
                try:
                    await session.rollback()
                except Exception:  # noqa: BLE001
                    pass
            delay = _lock_retry_delay(attempt)
            _logger.warning(
                "⏳ [R44] SQLite busy/locked أثناء %s (محاولة %d/%d) — إعادة بعد %.1fs",
                what, attempt, SQLITE_LOCK_RETRIES, delay,
            )
            await asyncio.sleep(delay)
    _logger.error("🚨 [R44] القفل مستمر بعد %d محاولات (%s)", SQLITE_LOCK_RETRIES, what)
    raise last_exc


async def execute_with_lock_retry(session, statement, *, what: str = "query"):
    """تنفيذ استعلام على جلسة قائمة مع rollback + إعادة محاولة عند القفل.

    مصمم لنقاط القراءة الساخنة (GET /get · GET /list · _get_backtest_row)
    حيث الجلسة تُدار من FastAPI dependency ولا يمكن فتح بديلة لها.
    """
    for attempt in range(1, SQLITE_LOCK_RETRIES + 1):
        try:
            return await session.execute(statement)
        except _SQLOperationalError as exc:
            if not is_locked_error(exc) or attempt >= SQLITE_LOCK_RETRIES:
                raise
            try:
                await session.rollback()
            except Exception:  # noqa: BLE001
                pass
            delay = _lock_retry_delay(attempt)
            _logger.warning(
                "⏳ [R44] SQLite busy/locked أثناء %s (محاولة %d/%d) — إعادة بعد %.1fs",
                what, attempt, SQLITE_LOCK_RETRIES, delay,
            )
            await asyncio.sleep(delay)


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
        connect_args={
            "check_same_thread": False,
            # ✅ R44 — مهلة الانتظار على مستوى تعريف sqlite3 (بالثواني).
            # busy_timeout النهائي يثبّته PRAGMA الدرع أدناه بالمللي ثانية —
            # الاثنان من نفس الثابت حتى لا يتناقضا.
            "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000.0,
        },
    )
    # ✅ R44 — درع القفل على كل اتصال جديد للمحرك الرئيسي (WAL + busy_timeout)
    install_sqlite_lock_shield(engine)

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
    # ✅ R50 — مسبح اتصالات موسّع وقابل للضبط: الافتراضي القديم (5+10)
    # كان يستنزف تحت الضغط — الطلبات تنتظر وصلة حرة حتى pool_timeout
    # فيبدو النظام «مهنّقاً» وهو في الحقيقة يصطف على المسبح.
    # الأحجام من البيئة: DB_POOL_SIZE · DB_MAX_OVERFLOW · DB_POOL_TIMEOUT.
    _pool_size = int(os.getenv("DB_POOL_SIZE", "10") or 10)
    _max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20") or 20)
    _pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "15") or 15)
    engine = create_async_engine(
        clean_url,
        echo=bool(getattr(settings, "SQL_ECHO", False)),
        future=True,
        pool_pre_ping=True,  # guards stale pooled conns (serverless DBs like Neon)
        pool_size=_pool_size,
        max_overflow=_max_overflow,
        pool_timeout=_pool_timeout,
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

def build_isolated_session_maker():
    """✅ الجولة 14.1 — مصنع جلسات معزول لمسار التشغيل الداخلي للباك-تست.

    المسار الاحتياطي (بلا Celery) يشغّل المحرك على event loop مختلف عن حلقة
    الـAPI داخل خيط عامل — اتصالات المسبح المشترك مرتبطة بحلقة الـAPI ولا
    يجوز استخدامها من حلقة أخرى. هذا المصنع يبني محركاً جديداً بـ NullPool
    (اتصال جديد لكل جلسة، لا إعادة استخدام عبر الحلقات) على نفس قاعدة البيانات.
    يعيد (session_maker, engine) — المستدعي مسؤول عن engine.dispose() عند الانتهاء.
    """
    if _IS_SQLITE:
        iso_engine = create_async_engine(
            DATABASE_URL,
            future=True,
            connect_args={
                "check_same_thread": False,
                # ✅ R44 — نفس مهلة الانتظار للمحركات المعزولة (مسارات الحفظ)
                "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000.0,
            },
            poolclass=NullPool,
        )
        # ✅ R44 — نفس درع القفل للمحرك المعزول (هو من ينفّذ INSERT الضخم)
        install_sqlite_lock_shield(iso_engine)
    else:
        clean_url, _pg_connect_args = build_asyncpg_connect_args(DATABASE_URL)
        iso_engine = create_async_engine(
            clean_url,
            future=True,
            pool_pre_ping=True,
            connect_args=_pg_connect_args,
            poolclass=NullPool,
        )
    iso_session_maker = async_sessionmaker(
        iso_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return iso_session_maker, iso_engine
