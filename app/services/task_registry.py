# app/services/task_registry.py
"""✅ الجولة 45 — سجل العمليات المؤسساتي (Task Registry Service).

المصدر الوحيد للحقيقة لكل عملية باك-تست: التخصيص، دورة الحياة، التقدّم،
المدد، والاسترجاع — كله في قاعدة البيانات (يبقى بعد إعادة التشغيل)،
يعمل تحت درع قفل R44 (WAL + busy_timeout + إعادة محاولة).

التصميم:
  * allocate_id(): عدّاد ذرّي 10000001 → 99999999 بعبارة واحدة
    UPDATE ... RETURNING — آمن للتخصيص المتزامن من API + Worker، ولا
    يعيد الأرقام حتى بعد حذف صفوف السجل.
  * register/update/finish_*: دورة حياة كاملة (progress% + phase + message
    + مدد) — تحديثات التقدّم «لا تقتل التشغيل أبداً» (فشلها يُسجَّل فقط).
  * get(): يعيد الصف الحي + elapsed/ETA محسوبين لحظياً — ETA من متوسط
    آخر 10 عمليات ناجحة لنفس الرمز/الفريم، وإلا استقراء من نسبة التقدم.
  * list_tasks(): قائمة المكتبة (سطحي + إحصاءات جاهزة للواجهة).
  * reap_stale(): تنظيف المهام الميتة (سقوط العملية) بعد مهلة قابلة
    للضبط — والاكتمال المتأخر يشفى تلقائياً (الكتابة اللاحقة تغلب).

كل الدوال تستقبل session_maker اختيارياً: الافتراضي للمحرك الرئيسي
(حلقة الـAPI)، ومسارات الخيوط العاملة تمرّر مصنعها المعزول (R14.1).
"""
from __future__ import annotations

import logging
import threading
import time as _time_mod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text, update

from app.config import settings
from app.database.session import AsyncSessionLocal, with_lock_retry

logger = logging.getLogger("app.services.task_registry")

TASK_ID_START = int(getattr(settings, "TASK_ID_START", 10000001) or 10000001)
TASK_ID_MAX = int(getattr(settings, "TASK_ID_MAX", 99999999) or 99999999)
REAP_SECONDS = int(getattr(settings, "TASK_REGISTRY_REAP_SECONDS", 1800) or 0)

# مذكرة ضمان الجداول لكل خيط (كل حلقة أحداث تعيش في خيط) — الإنشاء نفسه
# idempotent (checkfirst) فلا حاجة لقفل عبر await (خطر انسداد ميت).
_ensured_threads: set = set()
_ensured_lock = threading.Lock()


def utcnow_naive() -> datetime:
    """الاسم العام للتوقيت الموحد الساذج — تستورده وحدات R45 الأخرى."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


_now = utcnow_naive


def _iso(v: Optional[datetime]) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else None


# ==========================================================================
# ضمان الجداول (CREATE TABLE IF NOT EXISTS) — عبر محرك معزول آمن لأي حلقة
# ==========================================================================
async def ensure_registry_tables() -> None:
    """إنشاء جدولي السجل والكاش إن لم يوجدا — مرة لكل خيط، بأمان تام.

    يعمل بمحرك NullPool معزول (نفس نمط R14.1) فيصح استدعاؤه من حلقة
    الـAPI أو من خيط عامل داخل asyncio.run دون ربط اتصالات بحلقة غريبة.
    """
    tid = threading.get_ident()
    if tid in _ensured_threads:
        return

    from sqlalchemy import MetaData

    from app.database.session import Base, build_isolated_session_maker
    from app.models.backtest_task import BacktestTask, TaskIdCounter
    from app.models.candle_cache import CandleCache

    session_maker, iso_engine = build_isolated_session_maker()
    try:
        tables = [
            BacktestTask.__table__,
            TaskIdCounter.__table__,
            CandleCache.__table__,
        ]
        async with iso_engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, tables=tables, checkfirst=True
                )
            )
        if REAP_SECONDS > 0:
            await _reap_stale(session_maker)
    finally:
        try:
            await iso_engine.dispose()
        except Exception:  # noqa: BLE001
            pass

    with _ensured_lock:
        _ensured_threads.add(tid)


async def _reap_stale(session_maker) -> int:
    """تحويل المهام PROGRESS المتوقفة عن التنفس (سقوط العملية) إلى FAILURE.

    شرط التنفيذ: لم تُحدَّث منذ REAP_SECONDS. أي اكتمال متأخر لاحق من
    عامل حي يكتب SUCCESS فوقها فيُشفى الصف تلقائياً — لذا التنظيف آمن
    حتى مع عامل بطيء شرعياً طالما يُحدّث تقدمه.
    """
    from app.models.backtest_task import BacktestTask

    cutoff_dt = datetime.fromtimestamp(
        _now().timestamp() - REAP_SECONDS, tz=timezone.utc
    ).replace(tzinfo=None)
    try:
        async with session_maker() as db:
            stmt = (
                update(BacktestTask)
                .where(
                    BacktestTask.state == "PROGRESS",
                    BacktestTask.updated_at < cutoff_dt,
                )
                .values(
                    state="FAILURE",
                    phase="reaped",
                    message="انقطعت العملية (سقوط/إعادة تشغيل) ولم تُحدَّث — نُظِّفت تلقائياً",
                    error=f"stale: no heartbeat for {REAP_SECONDS}s (reaped by registry)",
                    finished_at=_now(),
                    updated_at=_now(),
                )
            )
            result = await db.execute(stmt)
            await db.commit()
            n = result.rowcount or 0
            if n:
                logger.warning("🧹 [R45] reap: %d مهمة متوقفة نُظِّفت", n)
            return n
    except Exception:  # noqa: BLE001
        logger.exception("[R45] reap failed (non-fatal)")
        return 0


# ==========================================================================
# الخدمة
# ==========================================================================
class TaskRegistry:
    """واجهة سجل العمليات — تُنشأ لكل سياق تشغيل (API أو خيط عامل)."""

    def __init__(self, session_maker=None):
        self._sm = session_maker or AsyncSessionLocal

    # ------------------------------------------------------------------
    # 1) التخصيص الذرّي
    # ------------------------------------------------------------------
    async def allocate_id(self) -> int:
        """الرقم التسلسلي التالي (10000001...) — بلا إعادة استخدام أبداً.

        عبارة واحدة ذرّية: UPDATE counter SET last_id=last_id+1 RETURNING —
        التزامن بين العمليات متسلسل طبيعياً عبر قفل الكتابة في SQLite/PG.
        ملاحظة معيارية: قد تظهر فجوة نادرة عند إعادة محاولة بعد قفل عابر
        (نفس سلوك sequences في PostgreSQL) — الرقم يظل تسلسلياً وفريداً.
        """
        await ensure_registry_tables()

        async def _do() -> int:
            async with self._sm() as db:
                is_pg = (db.bind.dialect.name == "postgresql") if db.bind else False
                seed = TASK_ID_START - 1
                if is_pg:
                    await db.execute(
                        text(
                            "INSERT INTO task_id_counter (id, last_id) "
                            "VALUES (1, :seed) ON CONFLICT (id) DO NOTHING"
                        ),
                        {"seed": seed},
                    )
                else:
                    await db.execute(
                        text(
                            "INSERT OR IGNORE INTO task_id_counter (id, last_id) "
                            "VALUES (1, :seed)"
                        ),
                        {"seed": seed},
                    )
                row = await db.execute(
                    text(
                        "UPDATE task_id_counter SET last_id = last_id + 1 "
                        "WHERE id = 1 RETURNING last_id"
                    )
                )
                new_id = row.scalar()
                await db.commit()
                return int(new_id)

        new_id = await with_lock_retry(_do, what="R45 task-id allocate")
        if new_id > TASK_ID_MAX:
            raise RuntimeError(
                f"نفد عدّاد أرقام العمليات: آخر رقم مسموح {TASK_ID_MAX} "
                f"وقد طُلب {new_id}. السجل محفوظ بالكامل — صدِّر الأرشيف "
                "وارفع TASK_ID_START بعد أرشفة الجدول القديم."
            )
        if new_id < TASK_ID_START:
            # عدّاد قديم مُدار يدوياً تحت البداية — نتجاوزه فوراً
            async with self._sm() as db:
                await db.execute(
                    text(
                        "UPDATE task_id_counter SET last_id = :floor "
                        "WHERE id = 1 AND last_id < :floor"
                    ),
                    {"floor": TASK_ID_START - 1},
                )
                await db.commit()
            return await self.allocate_id()
        return new_id

    # ------------------------------------------------------------------
    # 2) التسجيل ودورة الحياة
    # ------------------------------------------------------------------
    async def register(
        self,
        task_id: int,
        *,
        name: Optional[str],
        mode: str,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        market: Optional[str] = None,
        strategy: Optional[str] = None,
        days: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
        message: str = "تم استلام العملية وبدء التشغيل",
    ) -> None:
        from app.models.backtest_task import BacktestTask

        await ensure_registry_tables()
        now = _now()
        async with self._sm() as db:
            db.add(
                BacktestTask(
                    id=int(task_id),
                    state="PROGRESS",
                    progress=2.0,
                    phase="register",
                    message=message[:500],
                    mode=mode,
                    name=(name or f"backtest-{task_id}")[:255],
                    symbol=(symbol or "")[:32] or None,
                    timeframe=(timeframe or "")[:16] or None,
                    market=(market or "")[:16] or None,
                    strategy=(strategy or "")[:64] or None,
                    days=days,
                    meta=meta or {},
                    created_at=now,
                    started_at=now,
                    updated_at=now,
                )
            )
            await db.commit()

    async def update(
        self,
        task_id: int,
        *,
        progress: Optional[float] = None,
        phase: Optional[str] = None,
        message: Optional[str] = None,
        meta_patch: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """تحديث تقدّم غير حرج — أي فشل يُسجَّل فقط ولا يوقف العملية."""
        from app.models.backtest_task import BacktestTask

        try:
            values: Dict[str, Any] = {"updated_at": _now()}
            if progress is not None:
                values["progress"] = max(0.0, min(100.0, float(progress)))
            if phase is not None:
                values["phase"] = str(phase)[:32]
            if message is not None:
                values["message"] = str(message)[:500]
            if meta_patch:
                current = await self._meta_of(task_id)
                values["meta"] = {**(current or {}), **meta_patch}
            async with self._sm() as db:
                await db.execute(
                    update(BacktestTask).where(BacktestTask.id == int(task_id)),
                    values,
                )
                await db.commit()
            return True
        except Exception:  # noqa: BLE001
            logger.exception("[R45] registry update %s failed (non-fatal)", task_id)
            return False

    async def finish_success(
        self,
        task_id: int,
        *,
        backtest_id: Optional[str],
        total_pnl_percent: Optional[float] = None,
        win_rate: Optional[float] = None,
        total_trades: Optional[int] = None,
        meta_patch: Optional[Dict[str, Any]] = None,
    ) -> bool:
        from app.models.backtest_task import BacktestTask

        try:
            now = _now()
            started = await self._started_at_of(task_id)
            duration_ms = (
                max(0, int((now - started).total_seconds() * 1000))
                if started
                else None
            )
            values: Dict[str, Any] = {
                "state": "SUCCESS",
                "progress": 100.0,
                "phase": "done",
                "message": "اكتملت العملية بنجاح وحُفظت النتيجة",
                "backtest_id": backtest_id,
                "finished_at": now,
                "updated_at": now,
                "duration_ms": duration_ms,
            }
            if total_pnl_percent is not None:
                values["total_pnl_percent"] = float(total_pnl_percent)
            if win_rate is not None:
                values["win_rate"] = float(win_rate)
            if total_trades is not None:
                values["total_trades"] = int(total_trades)
            if meta_patch:
                current = await self._meta_of(task_id)
                values["meta"] = {**(current or {}), **meta_patch}
            async with self._sm() as db:
                await db.execute(
                    update(BacktestTask).where(BacktestTask.id == int(task_id)),
                    values,
                )
                await db.commit()
            return True
        except Exception:  # noqa: BLE001
            logger.exception("[R45] registry finish_success %s failed", task_id)
            return False

    async def finish_failure(self, task_id: int, *, error: Any) -> bool:
        from app.models.backtest_task import BacktestTask

        try:
            now = _now()
            started = await self._started_at_of(task_id)
            duration_ms = (
                max(0, int((now - started).total_seconds() * 1000))
                if started
                else None
            )
            async with self._sm() as db:
                await db.execute(
                    update(BacktestTask).where(BacktestTask.id == int(task_id)),
                    {
                        "state": "FAILURE",
                        "phase": "error",
                        "message": "فشلت العملية — التفاصيل في حقل error",
                        "error": str(error)[:1000] or "unknown error",
                        "finished_at": now,
                        "updated_at": now,
                        "duration_ms": duration_ms,
                    },
                )
                await db.commit()
            return True
        except Exception:  # noqa: BLE001
            logger.exception("[R45] registry finish_failure %s failed", task_id)
            return False

    # ------------------------------------------------------------------
    # 3) القراءة
    # ------------------------------------------------------------------
    async def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        from app.models.backtest_task import BacktestTask

        await ensure_registry_tables()
        async with self._sm() as db:
            result = await db.execute(
                select(BacktestTask).where(BacktestTask.id == int(task_id))
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._row_to_dict(row)

    async def list_tasks(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """قائمة المكتبة — ✅ R50: ترقيم صفحات على مستوى SQL.

        كان الاستعلام يحمّل **كل** صفوف السجل ثم يقطّع الصفحة في بايثون
        — مع نمو السجل (مئات العمليات) يصبح كل استطلاع من الفرونت
        حمولة كاملة بلا داع. الآن: COUNT + LIMIT/OFFSET في قاعدة البيانات.
        """
        from app.models.backtest_task import BacktestTask

        await ensure_registry_tables()
        async with self._sm() as db:
            base_q = select(BacktestTask)
            if state:
                base_q = base_q.where(BacktestTask.state == state.strip().upper())
            total = (
                await db.execute(
                    select(func.count()).select_from(base_q.subquery())
                )
            ).scalar() or 0
            stats_q = select(BacktestTask.state, func.count(BacktestTask.id)).group_by(
                BacktestTask.state
            )
            stats_rows = (await db.execute(stats_q)).all()
            stats = {s: c for s, c in stats_rows}
            stats["total"] = total
            page = (
                (
                    await db.execute(
                        base_q.order_by(BacktestTask.id.desc())
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return {
                "success": True,
                "count": len(page),
                "limit": limit,
                "offset": offset,
                "stats": {
                    "total": stats.get("total", 0),
                    "running": stats.get("PROGRESS", 0),
                    "success": stats.get("SUCCESS", 0),
                    "failure": stats.get("FAILURE", 0),
                },
                "data": [self._row_to_dict(r) for r in page],
            }

    # ------------------------------------------------------------------
    # 4) أدوات داخلية
    # ------------------------------------------------------------------
    async def _meta_of(self, task_id: int) -> Optional[Dict[str, Any]]:
        from app.models.backtest_task import BacktestTask

        async with self._sm() as db:
            result = await db.execute(
                select(BacktestTask.meta).where(BacktestTask.id == int(task_id))
            )
            return result.scalar_one_or_none()

    async def _started_at_of(self, task_id: int) -> Optional[datetime]:
        from app.models.backtest_task import BacktestTask

        async with self._sm() as db:
            result = await db.execute(
                select(BacktestTask.started_at).where(BacktestTask.id == int(task_id))
            )
            return result.scalar_one_or_none()

    async def _avg_duration_ms(self, symbol: str, timeframe: str) -> Optional[float]:
        """متوسط مدة آخر 10 عمليات ناجحة لنفس الرمز/الفريم — لتقدير ETA."""
        from app.models.backtest_task import BacktestTask

        try:
            async with self._sm() as db:
                sub = (
                    select(BacktestTask.duration_ms)
                    .where(
                        BacktestTask.state == "SUCCESS",
                        BacktestTask.duration_ms.isnot(None),
                        BacktestTask.symbol == symbol,
                        BacktestTask.timeframe == timeframe,
                    )
                    .order_by(BacktestTask.id.desc())
                    .limit(10)
                    .subquery()
                )
                avg = (
                    await db.execute(select(func.avg(sub.c.duration_ms)))
                ).scalar()
                return float(avg) if avg else None
        except Exception:  # noqa: BLE001
            return None

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """تحويل الصف إلى القاموس الحي المعروض — مع elapsed/ETA لحظياً."""
        now_ts = _time_mod.time()
        d: Dict[str, Any] = {
            "task_id": str(row.id),
            "task_number": int(row.id),
            "state": row.state,
            "mode": row.mode,
            "name": row.name,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "market": row.market,
            "strategy": row.strategy,
            "days": row.days,
            "progress": float(row.progress or 0.0),
            "phase": row.phase,
            "message": row.message,
            "backtest_id": row.backtest_id,
            "total_pnl_percent": row.total_pnl_percent,
            "win_rate": row.win_rate,
            "total_trades": row.total_trades,
            "duration_ms": row.duration_ms,
            "error": row.error,
            "meta": row.meta or {},
            "created_at": _iso(row.created_at),
            "started_at": _iso(row.started_at),
            "finished_at": _iso(row.finished_at),
            "updated_at": _iso(row.updated_at),
            "eta_seconds": None,
            "elapsed_seconds": None,
            "stale_seconds": None,
        }
        if row.started_at is not None:
            started_ts = row.started_at.replace(tzinfo=timezone.utc).timestamp()
            if row.state == "PROGRESS":
                elapsed = max(0.0, now_ts - started_ts)
                d["elapsed_seconds"] = round(elapsed, 2)
                if row.updated_at is not None:
                    upd_ts = row.updated_at.replace(tzinfo=timezone.utc).timestamp()
                    d["stale_seconds"] = round(max(0.0, now_ts - upd_ts), 1)
            elif row.duration_ms is not None:
                d["elapsed_seconds"] = round(row.duration_ms / 1000.0, 2)
        return d

    async def enrich_live(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """إضافة ETA لحظي للمهام الجارية.

        الأولوية: متوسط آخر 10 عمليات ناجحة لنفس الرمز/الفريم؛ فإن غاب
        أو أصبح سالباً (هذا التشغيل أبطأ من تاريخه) نستقرئ من نسبة التقدم.
        كلاهما تعطيل مشروط — لا نخترع رقماً كاذباً أبداً."""
        if d.get("state") != "PROGRESS":
            return d
        eta: Optional[float] = None
        avg_ms = await self._avg_duration_ms(
            str(d.get("symbol") or ""), str(d.get("timeframe") or "")
        )
        elapsed = d.get("elapsed_seconds") or 0.0
        if avg_ms and avg_ms > 0:
            eta = avg_ms / 1000.0 - elapsed
        if (eta is None or eta < 0) and (d.get("progress") or 0.0) >= 10.0 and elapsed > 0:
            p = float(d["progress"])
            eta = elapsed * (100.0 - p) / p
        if eta is not None and eta >= 0:
            d["eta_seconds"] = round(eta, 1)
        return d


# ==========================================================================
# عقد الحالة الموحد (توافق كامل مع الواجهة الحالية + حقول R45 الجديدة)
# ==========================================================================
def status_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """بناء استجابة /status من صف السجل — بنفس شكل العقد القديم حرفياً
    للمفاتيح القديمة (state/message/backtest_id/result/error/error_detail)
    مع إضافة عقد R45 الكامل (task_number/progress/eta/duration/meta)."""
    state = row.get("state")
    p: Dict[str, Any] = {
        "task_id": row.get("task_id"),
        "task_number": row.get("task_number"),
        "state": state,
        "mode": row.get("mode"),
        "name": row.get("name"),
        "symbol": row.get("symbol"),
        "timeframe": row.get("timeframe"),
        "progress": {
            "percent": row.get("progress"),
            "phase": row.get("phase"),
            "message": row.get("message"),
        },
        "elapsed_seconds": row.get("elapsed_seconds"),
        "eta_seconds": row.get("eta_seconds"),
        "duration_ms": row.get("duration_ms"),
        "stale_seconds": row.get("stale_seconds"),
        "created_at": row.get("created_at"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "backtest_id": row.get("backtest_id"),
        "summary_stats": None,
        "meta": row.get("meta") or {},
    }
    if row.get("total_trades") is not None or row.get("win_rate") is not None:
        p["summary_stats"] = {
            "total_pnl_percent": row.get("total_pnl_percent"),
            "win_rate": row.get("win_rate"),
            "total_trades": row.get("total_trades"),
        }
    if state == "PROGRESS":
        p["message"] = row.get("message") or "Processing..."
    elif state == "SUCCESS":
        p["message"] = "Backtest completed successfully."
        p["result"] = {"status": "SUCCESS", "backtest_id": row.get("backtest_id")}
    elif state == "FAILURE":
        p["message"] = "Task failed."
        p["error"] = row.get("error") or "Backtest execution failed."
        p["error_detail"] = row.get("error") or ""
    return p


async def get_registry_status(task_id: str) -> Optional[Dict[str, Any]]:
    """قراءة حالة مهمة رقمية من السجل + شفاء celery المتأخر إن لزم.

    يعيد None إذا لم يوجد صف — المتصل يقرر الرد (404 أو مسار قديم).
    """
    if not str(task_id).isdigit():
        return None
    numeric = int(task_id)
    if numeric < TASK_ID_START or numeric > TASK_ID_MAX:
        return None

    reg = TaskRegistry()
    row = await reg.get(numeric)
    if row is None:
        return None
    row = await reg.enrich_live(row)

    # --- شفاء celery المتأخر: سجل يقول PROGRESS بينما العامل أنهى فعلاً ----
    if row.get("state") == "PROGRESS" and (row.get("meta") or {}).get("celery_task_id"):
        celery_id = row["meta"]["celery_task_id"]
        try:
            import asyncio as _asyncio

            from celery.result import AsyncResult

            from app.celery_app import celery_app

            def _peek_celery():
                """✅ R50 — قراءة حالة celery (شبكة Redis متزامنة) داخل خيط
                عامل — كانت تثبّت حلقة الأحداث مع كل استطلاع /status لمهمة
                جارية (الفرونت يستطلع كل ثانيتين)."""
                res = AsyncResult(celery_id, app=celery_app)
                state = res.state
                info = res.result if state == "SUCCESS" else (
                    str(res.info)[:400] if state == "FAILURE" else None
                )
                return state, info

            celery_state, celery_info = await _asyncio.to_thread(_peek_celery)
            if celery_state == "SUCCESS" and isinstance(celery_info, dict):
                bid = celery_info.get("backtest_id")
                await reg.finish_success(
                    numeric,
                    backtest_id=bid,
                    meta_patch={"healed_from": "celery"},
                )
                row = await reg.get(numeric)
                row = await reg.enrich_live(row)
            elif celery_state == "FAILURE":
                await reg.finish_failure(
                    numeric, error=celery_info or "celery failure"
                )
                row = await reg.get(numeric)
                row = await reg.enrich_live(row)
        except Exception:  # noqa: BLE001 — الشفاء أفضل-جهد فقط
            pass

    return status_payload(row)
