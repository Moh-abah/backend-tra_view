# app/routers/backtest1.py
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Request
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import asyncio
import logging
import math
import time
import uuid
from app.backtest.engine1 import BacktestEngine
from app.backtest.reports import ReportGenerator
from app.backtest.schemas import BacktestConfig, BacktestResult
from app.services.data_service import DataService
from app.database import get_db
from app.metrics.normalizer import MetricsNormalizer
from app.models.backtest_run import BacktestRun
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sqlalchemy_delete
from app.celery_app import celery_app
from celery.result import AsyncResult
from app.tasks.backtest_tasks import run_backtest_task 

router = APIRouter(tags=["backtest1"])
logger = logging.getLogger(__name__)

_backtest_engine = None
_report_generator = ReportGenerator()
_backtest_storage = {}  # {backtest_id: BacktestResult}
_engine_cache = None

# ✅ الجولة 12 (هوت-فكس): سجل المهام داخل العملية — يُستخدم عند سقوط
# Celery/Redis حتى لا يفشل backtest1/run بخطأ Error 111 (broker down).
_inprocess_tasks: Dict[str, Dict[str, Any]] = {}

async def get_backtest_from_db(backtest_id: str) -> Optional[BacktestResult]:
    """استرجاع نتيجة الباك-تست من التخزين المؤقت"""
    return _backtest_storage.get(backtest_id)


def get_backtest_engine(db) -> BacktestEngine:
    """Get or Create BacktestEngine"""
    global _backtest_engine
    if _backtest_engine is None:
        data_service = DataService(db)
        _backtest_engine = BacktestEngine(data_service)
    return _backtest_engine




def log_invalid_numbers(data, path="root"):
    if isinstance(data, dict):
        for k, v in data.items():
            log_invalid_numbers(v, f"{path}.{k}")
    elif isinstance(data, list):
        for i, v in enumerate(data):
            log_invalid_numbers(v, f"{path}[{i}]")
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            logger.error(f"❌ INVALID NUMBER FOUND | path={path} | value={data}")





# ==========================================
# ✅ الجولة 42.1 — درع الصراحة (لا تجاهل صامت)
# ==========================================

def _reject_exit_strategy_r421(config: BacktestConfig, where: str) -> None:
    """كتلة exit_strategy يُنفّذها المحرك الموحّد ج42 في /run فقط — المسارات
    الأخرى (walk-forward/monte-carlo) تتقبلها من المخطط المشترك ثم تتجاهلها
    بصمت. ممنوع: 422 فوري برسالة صريحة."""
    if getattr(config, "exit_strategy", None) is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"كتلة exit_strategy تُنفّذ فقط في POST /api/v1/backtest1/run "
                f"(المسار الموحّد ج42) — {where} لا ينفّذها ولن يتجاهلها بصمت. "
                f"أرسل الطلب إلى /run أو احذف اللكتلة."
            ),
        )


@router.post("/run")
async def run_backtest(
    config: BacktestConfig = Body(...),
    wait: bool = Query(False, description="true = انتظر انتهاء التشغيل وأعد النتيجة الكاملة (summary + chart_data) في نفس الرد"),
    wait_timeout: int = Query(280, ge=5, le=900, description="أقصى انتظار بالثواني عند wait=true"),
    # نتجاهل generate_report و save_to_file لأنها ستتم معالجتها داخل الـ worker أو لاحقاً
    db = Depends(get_db)
):
    """
    يرسل طلب الباك-تست إلى Celery Worker ويعود فوراً بـ task_id.

    ✅ الجولة 42 — التوحيد الكامل: عند وجود كتلة `exit_strategy` في الحمولة
    يُنفَّذ التشغيل بمحرك الخروج الج41 (التريلينق الحرفي، جني الربح، DCA،
    كسر الفيبو) من داخل هذا المسار نفسه — لا مسار موازٍ إطلاقاً:

        POST /backtest1/run  (exit_strategy: {...})
          → GET /backtest1/status/{task_id}     (نفس العقد)
          → GET /backtest1/get/{backtest_id}    (نفس العقد + إثراءات ج42)

    وغياب الكتلة = نفس سلوك المحرك الرئيسي بت-بت (لا يتغير شيء لأي
    مستخدم حالي).

    ✅ الجولة 12 (هوت-فكس): عندما يكون الـ broker (Redis) متوقفاً كان هذا
    المسار يفشل كلياً بخطأ "Error 111 connecting to localhost:6379" —
    الآن نتحقق من توفر الـ broker أولاً وعند عدم توفره تُنفَّذ نفس المهمة
    داخل عملية الـ API (نفس محرك app.routers.backtest._run_backtest_inprocess
    ونفس الحفظ في BacktestRun) ويعيد /backtest1/status نفس العقد تماماً —
    فلا يبقى أي مسار تشغيل معتمداً على Redis حيّاً.
    """
    try:
        from app.celery_app import is_broker_available

        dispatch: Dict[str, Any]

        # ✅ الجولة 42 — المنفذ الموحد: محرك الخروج ج41 داخل backtest1/run
        # نفسها. التنفيذ داخل العملية مباشرة (المحرك خفيف وسريع) بنفس
        # دورة الحياة ونفس التخزين في BacktestRun — الفرونت يرى نفس
        # /status و /get بلا أي فرق شكلي.
        if config.exit_strategy is not None:
            # ✅ R45 — رقم عملية تسلسلي مؤسساتي (10000001 ثم 10000002 ...)
            # من عدّاد ذرّي في قاعدة البيانات + صف سجل دائم كامل
            from app.services.task_registry import TaskRegistry

            reg = TaskRegistry()
            task_number = await reg.allocate_id()
            task_id = str(task_number)
            config_dict = config.model_dump(mode="json")
            await reg.register(
                task_number,
                name=config.name,
                mode="unified-exit",
                symbol=str((config.symbols[0] if config.symbols else "") or "?").strip().upper()[:32],
                timeframe=str(config.timeframe or "1d")[:16],
                market=str(config.market or "crypto").strip().lower()[:16],
                strategy=_unified_strategy_name(config),
                days=_resolve_unified_days(config),
            )
            # ✅ R49 — إصلاح التجميد أثناء الباك تست الثقيل نفسه:
            # المسار الموحد كان يعمل دائماً داخل عملية الـAPI (خيط عامل).
            # الخيط لا يجمّد الحلقة لكنه يسرق GIL طوال المحاكاة (127 ثانية
            # في إنتاج المستخدم) فتتجمد بقية النقاط ويهلك healthcheck.
            # الآن: عند توفر الـ broker تُرسل المهمة إلى عامل Celery المنفصل
            # (نفس دورة الحياة ونفس العقد تماماً — /status يقرأ من السجل
            # الدائم ويشفي المتأخر تلقائياً)، وعند غيابه يبقى مسار العملية
            # الداخلية كما هو (درع بلا Redis).
            _use_celery = False
            try:
                # ✅ R50: فحص الـ broker شبكة متزامنة — داخل خيط عامل حتى لا
                # يثبّت حلقة الأحداث حتى ثانيتين عند سقوط Redis
                _use_celery = await asyncio.to_thread(is_broker_available, 2.0)
            except Exception:  # noqa: BLE001
                _use_celery = False

            if _use_celery:
                from app.tasks.backtest_tasks import run_unified_exit_task

                config_dict["_r45_task_id"] = task_number
                task = run_unified_exit_task.delay(config_dict)
                # ✅ R56 — درع مضاد للتوائم: المهمة سبق أن أُرسلت للعامل بنجاح.
                # كان السطر التالي يستدعي update(meta=...) والتوقيع يقبل
                # meta_patch فقط ← TypeError يُمسكه المقبض العام فيُظن أن
                # الإرسال فشل فتُشغّل نفس المحاكاة مرة ثانية داخل عملية
                # الـAPI (توأم: موت عامل uvicorn بحمولة 1.3M شمعة + إعادة
                # تهيئة دائمة — سجل الإنتاج 2026-11-08 11:45). الآن:
                # (1) الاسم الصحيح meta_patch، و(2) أي فشل في تحديث السجل
                # بعد نجاح delay() يُسجّل فقط ولا يُفشل الإرسال أبدًا.
                try:
                    await reg.update(
                        task_number,
                        meta_patch={"celery_task_id": task.id},  # شفاء المتأخر + الانتقال السلس
                    )
                except Exception:  # noqa: BLE001 — السجل لا يُفشل إرسالاً تمّ بنجاح
                    logger.exception(
                        "[R56] registry update after unified dispatch failed (non-fatal, task %s)",
                        task_number,
                    )
                dispatch = {
                    "success": True,
                    "message": "Unified backtest (exit-strategy engine) started. Processing in background.",
                    "task_id": task_id,
                    "task_number": task_number,
                    "status": "PROCESSING",
                    "mode": "unified-exit-celery",
                    "celery_task_id": task.id,
                    "progress": {"percent": 2.0, "phase": "register", "message": "تم استلام العملية"},
                    "poll": f"/api/v1/backtest1/status/{task_id}",
                }
                logger.info(
                    "📤 [R49] unified-exit → Celery worker (task %s, symbol %s, celery %s)",
                    task_id, config.symbols[0] if config.symbols else "?", task.id,
                )
            else:
                _inprocess_tasks[task_id] = {
                    "state": "PROGRESS",
                    "status": "Unified Exit Engine: fetching candles...",
                }
                asyncio.create_task(_run_unified_exit_task(task_id, config_dict))
                dispatch = {
                    "success": True,
                    "message": "Unified backtest (exit-strategy engine) started. Processing in background.",
                    "task_id": task_id,
                    "task_number": task_number,
                    "status": "PROCESSING",
                    "mode": "unified-exit",
                    "progress": {"percent": 2.0, "phase": "register", "message": "تم استلام العملية"},
                    "poll": f"/api/v1/backtest1/status/{task_id}",
                }
                logger.info(
                    "🔁 [R42/R45] backtest1/run unified-exit dispatch (task %s, symbol %s)",
                    task_id, config.symbols[0] if config.symbols else "?",
                )
            if wait:
                return await _wait_for_result(db, dispatch, wait_timeout)
            return dispatch

        # ✅ R45 — تخصيص رقم العملية مرة واحدة لأي مسار تسليم لاحق
        from app.services.task_registry import TaskRegistry

        reg = TaskRegistry()
        task_number = await reg.allocate_id()
        task_id = str(task_number)
        _symbol0 = str((config.symbols[0] if config.symbols else "") or "?").strip().upper()[:32]
        _tf0 = str(config.timeframe or "1d")[:16]
        _mk0 = str(config.market or "crypto").strip().lower()[:16]
        _st0 = (
            (config.strategy_config or {}).get("name")
            if config.strategy_config
            else None
        )

        if not await asyncio.to_thread(is_broker_available, 2.0):
            # ✅ مسار احتياطي داخل العملية — بلا Redis/Celery
            from app.routers.backtest import _run_backtest_inprocess

            config_dict = config.model_dump(mode="json")
            config_dict["_r45_task_id"] = task_number  # ✅ R45: رقم العملية للمُنفّذ
            await reg.register(
                task_number, name=config.name, mode="inprocess",
                symbol=_symbol0, timeframe=_tf0, market=_mk0,
                strategy=str(_st0 or "")[:64] or None,
            )
            _inprocess_tasks[task_id] = {"state": "PROGRESS", "status": "Starting Backtest Engine..."}
            asyncio.create_task(_track_inprocess(task_id, config_dict))
            logger.warning(
                "Celery broker unavailable → backtest1/run in-process (task %s, strategy '%s')",
                task_id, config.name,
            )
            dispatch = {
                "success": True,
                "message": "Backtest started in-process (broker unavailable). Processing in background.",
                "task_id": task_id,
                "task_number": task_number,
                "status": "PROCESSING",
                "mode": "inprocess",
                "progress": {"percent": 2.0, "phase": "register", "message": "تم استلام العملية"},
                "poll": f"/api/v1/backtest1/status/{task_id}",
            }
        else:
            logger.info(f"📤 Dispatching Backtest task to Celery: {config.name}")

            # إرسال المهمة للـ Worker
            # ✅ model_dump(mode="json") يحول datetime إلى ISO strings —
            # dict() كان يفشل مع Celery JSON serializer (EncodeError)
            config_dict = config.model_dump(mode="json")
            config_dict["_r45_task_id"] = task_number  # ✅ R45: رقم العملية للعامل
            task = run_backtest_task.delay(config_dict)
            await reg.register(
                task_number, name=config.name, mode="celery",
                symbol=_symbol0, timeframe=_tf0, market=_mk0,
                strategy=str(_st0 or "")[:64] or None,
                meta={"celery_task_id": task.id},  # شفاء المتأخر + الانتقال السلس
            )
            dispatch = {
                "success": True,
                "message": "Backtest started successfully. Processing in background.",
                "task_id": task_id,
                "task_number": task_number,
                "status": "PROCESSING",
                "mode": "celery",
                "celery_task_id": task.id,
                "progress": {"percent": 2.0, "phase": "register", "message": "تم استلام العملية"},
                "poll": f"/api/v1/backtest1/status/{task_id}",
            }

        # ✅ الجولة 12: wait=true — انتظر النتيجة وأعدها في نفس الرد
        # (يُسهّل اختبارات القبول الحرفية: chart_data.visual_candles[0].close
        # متاحة مباشرة من استجابة POST واحدة).
        if wait:
            return await _wait_for_result(db, dispatch, wait_timeout)
        return dispatch
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to dispatch task: {e}")
        # ✅ محاولة أخيرة داخل العملية قبل الفشل — الزر يعمل بأي حال
        # ✅ R45: حتى المسار الطارئ يحصل على رقم عملية مسجَّل في السجل
        try:
            from app.routers.backtest import _run_backtest_inprocess
            from app.services.task_registry import TaskRegistry

            reg = TaskRegistry()
            task_number = await reg.allocate_id()
            task_id = str(task_number)
            config_dict = config.model_dump(mode="json")
            config_dict["_r45_task_id"] = task_number
            await reg.register(
                task_number, name=config.name, mode="inprocess",
                symbol=str((config.symbols[0] if config.symbols else "") or "?").strip().upper()[:32],
                timeframe=str(config.timeframe or "1d")[:16],
                market=str(config.market or "crypto").strip().lower()[:16],
            )
            _inprocess_tasks[task_id] = {"state": "PROGRESS", "status": "Starting Backtest Engine..."}
            asyncio.create_task(_track_inprocess(task_id, config_dict))
            logger.warning("Celery dispatch failed (%s) → backtest1/run in-process (task %s)", e, task_id)
            return {
                "success": True,
                "message": "Backtest started in-process (broker dispatch failed). Processing in background.",
                "task_id": task_id,
                "task_number": task_number,
                "status": "PROCESSING",
                "mode": "inprocess",
                "progress": {"percent": 2.0, "phase": "register", "message": "تم استلام العملية"},
                "poll": f"/api/v1/backtest1/status/{task_id}",
            }
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e))


async def _track_inprocess(task_id: str, config_dict: dict) -> None:
    """غلاف ينسخ حالة المهمة داخل العملية إلى سجل backtest1 المحلي."""
    from app.routers.backtest import _run_backtest_inprocess, _inprocess_tasks as _bt_inprocess

    await _run_backtest_inprocess(task_id, config_dict)
    # انسخ الحالة النهائية إلى سجلنا المحلي (نفس المرجع يكفي عملياً لكن
    # النسخ يضمن استقلالية السجل عن أي إعادة تحميل للوحدة)
    state = _bt_inprocess.get(task_id)
    if state is not None:
        _inprocess_tasks[task_id] = dict(state)


def _unified_strategy_name(config: BacktestConfig) -> Optional[str]:
    """اسم الاستراتيجية الموحدة كما يحلّها المنفّذ (للسجل والعرض)."""
    sc_name = ""
    if config.strategy_config and isinstance(config.strategy_config, dict):
        sc_name = str(config.strategy_config.get("name") or "").strip().lower()
    block = getattr(config, "exit_strategy", None)
    strategy = str(getattr(block, "strategy", "") or sc_name or "zzfib").strip().lower()
    return strategy[:64] or None


async def _set_registry_progress(
    task_id: str, percent: float, phase: str, message: str
) -> None:
    """✅ R45 — تحديث السجل الدائم + المرآة المحلية معاً.

    تحديث التقدّم «غير حرج» بتعريف عقد هذه الجولة: أي فشل فيه يُسجَّل
    فقط ولا يمس التشغيل نفسه — الشريط قد يتجمد لكن الباك-تست يكتمل.
    """
    _inprocess_tasks[task_id] = {"state": "PROGRESS", "status": message}
    if not task_id.isdigit():
        return
    try:
        from app.services.task_registry import TaskRegistry

        await TaskRegistry().update(
            int(task_id), progress=percent, phase=phase, message=message
        )
    except Exception:  # noqa: BLE001
        logger.debug("[R45] progress update skipped for %s", task_id)


def _resolve_unified_days(config: BacktestConfig) -> int:
    """نافذة الجلب بالأيام للمنفذ الموحد: days إن أُرسلت وإلا من فرق
    التواريخ (start_date → end_date) — نفس نافذة المحرك الرئيسي.
    ✅ R55: أُلغي سقف 365 — كان يقصّ نافذة 478 يوم (اختبار مقارنة ال580)
    إلى سنة واحدة بصمت. الحد الأقصى الآن 3650 (نفس حد days بالمخطط)."""
    if config.days:
        d = int(config.days)
    else:
        try:
            delta = (config.end_date - config.start_date).total_seconds()
            d = int(delta // 86400)
        except (TypeError, AttributeError):
            d = 30
    return max(1, min(3650, d or 30))


async def _fetch_unified_candles(
    config: BacktestConfig, symbol: str, timeframe: str, market: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """✅ R55 — جلب شموع المسار الموحد بنافذة الجذر الحرفية.

    المشكلة القديمة: كان الجلب «آخر N يوم من الآن» عبر get_historical(days)
    فتشغيل بنافذة 2023-10-14 → 2025-02-02 كان ينفّذ 2025-11 → 2026-11
    فعلياً (#10000016). الآن: نفس مصدر المحرك الرئيسي بت-بت
    (get_historical_last_version بتواريخ صريحة) ونفس فضاء كاش d —
    فنافذة 478 يوم المحفوظة من تشغيل #10000001 المرجعي تُقرأ فوراً
    بلا أي إعادة جلب.

    يعيد (candles, cache_meta).
    """
    from datetime import datetime, timezone as _tz

    from app.services.data_service import DataService
    from app.services.candle_cache import CandleCacheService
    from app.routers.exit_strategy import _df_to_candles_range

    data_service = DataService(None)
    cache_svc = CandleCacheService()

    def _to_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=_tz.utc)
        return dt.astimezone(_tz.utc)

    start_dt = _to_utc(config.start_date)
    end_dt = _to_utc(config.end_date)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    tz_off = int(getattr(config, "tz_offset_minutes", 0) or 0)

    async def _fetch_range(range_start_ts: int, range_end_ts: int):
        return await data_service.get_historical_last_version(
            symbol=symbol, timeframe=timeframe, market=market,
            start_date=datetime.fromtimestamp(int(range_start_ts), tz=_tz.utc),
            end_date=datetime.fromtimestamp(int(range_end_ts), tz=_tz.utc),
            use_cache=True,
            tz_offset_minutes=tz_off,
        )

    df = await cache_svc.get_dataframe_range(
        symbol=symbol, timeframe=timeframe, market=market,
        start_ts=start_ts, end_ts=end_ts,
        fetch_range_df=_fetch_range,
    )
    candles = _df_to_candles_range(df)
    meta = dict(cache_svc.last_meta or {})
    # نفس شكل CacheResult.as_meta() القديم تقريباً — للسجل وشفافية الجلب
    cache_meta = {
        "cache": meta.get("cache") or {"hit": False, "note": "range-fetch"},
        "total": len(candles),
        "window": {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "bars": len(candles),
        },
    }
    return candles, cache_meta


async def _run_unified_exit_task(task_id: str, config_dict: dict) -> None:
    """✅ الجولة 42 — المنفذ الموحد: محرك الخروج ج41 من داخل backtest1/run.

    نفس دورة الحياة (PROGRESS → SUCCESS/FAILURE) ونفس التخزين (BacktestRun)
    ونفس عقد /status و /get — بلا أي مسار موازٍ للفرونت:

      1) جلب الشموع من نفس المزوّد (DataService — stateless)
      2) استراتيجية البطل (zzfib*) → إشارات الدخول + أرضيات الفيبو
      3) محرك الخروج ج41 (التريلينق الحرفي / TP / DCA / كسر الفيبو)
      4) بناء (summary + chart_data) بنفس عقد المحرك الرئيسي
      5) الحفظ في نفس جدول BacktestRun → /get و /chart-data يعملان فوراً

    الحساب الثقيل داخل خيط عامل (نفس درس الجولة 14.1 — لا تجميد للحلقة)
    والجلسة معزولة (NullPool خاص بحلقة الخيط).
    """
    import time as _time

    t0 = _time.perf_counter()
    try:
        config = BacktestConfig(**config_dict)
        block = config.exit_strategy

        symbol = (config.symbols[0] if config.symbols else "").strip().upper()
        timeframe = str(config.timeframe or "1d")
        market = str(config.market or "crypto").strip().lower()

        # 1) حلّ الاستراتيجية: block.strategy ← strategy_config.name ← zzfib
        sc_name = ""
        if config.strategy_config and isinstance(config.strategy_config, dict):
            sc_name = str(config.strategy_config.get("name") or "").strip().lower()
        strategy = str(block.strategy or sc_name or "zzfib").strip().lower()

        # 2) إعدادات الخروج — المنظّمة من المخطط إن توفرت (لا إعادة حساب)،
        #    وإلا تطبيع نهائي هنا (تحقق مزدوج رخيص مقابل أمان مطلق).
        from app.services.unified_backtest import validate_exit_block

        normalized = getattr(block, "_normalized_block", None)
        if normalized is None:
            normalized, v_errors = validate_exit_block(
                block.strategy, block.strategy_params, block.config,
            )
            if v_errors:
                raise ValueError("؛ ".join(v_errors))
        exit_cfg = dict(normalized["config"])
        strategy_params = dict(normalized.get("strategy_params") or {})

        # 3) ✅ R55 — جلب الشموع بنافذة الجذر الحرفية (start_date → end_date):
        #    نفس مصدر المحرك الرئيسي get_historical_last_version ونفس فضاء
        #    كاش d — انتهى عصر «آخر N يوم من الآن» الذي نفّذ تشغيل #10000016
        #    على 2025-11 → 2026-11 بدل 2023-10-14 → 2025-02-02.
        await _set_registry_progress(
            task_id, 10.0, "fetch",
            f"تحضير شموع {symbol} {timeframe} بنافذة الجذر "
            f"({config.start_date:%Y-%m-%d} → {config.end_date:%Y-%m-%d})",
        )

        candles, _cache_meta = await _fetch_unified_candles(
            config, symbol, timeframe, market,
        )
        if not candles:
            raise ValueError(
                f"لا توجد شموع للرمز {symbol} على فريم {timeframe} بين "
                f"{config.start_date:%Y-%m-%d} و{config.end_date:%Y-%m-%d}"
            )

        # ✅ R55 — تمرير سقف المراكز الرقمي من جذر الطلب لمحرك الخروج:
        # max_positions (None/1 = تاريخي · 2..10 = سقف رقمي فعّال)
        if config.max_positions is not None:
            exit_cfg["max_concurrent_positions"] = int(config.max_positions)

        # ✅ R64 — وراثة الستوب لوز من جذر الطلب عند تعطيل خروج الفيبو:
        # fibo_floor_exit=false ولم يُرسل stop_loss_pct صراحةً في كتلة الخروج
        # ⇒ يُورَث stop_loss_percent من جذر الكونفيق إن كان مفعلاً (0 < x < 100).
        # الأولوية الموثقة: stop_loss_pct الصريح في الكتلة > جذر الكونفيق > معطّل
        # (نفس منطق مسار العامل Celery حرفياً — المساران متطابقان دائماً).
        if exit_cfg.get("fibo_floor_exit") is False and "stop_loss_pct" not in (block.config or {}):
            _root_sl_r64 = config.stop_loss_percent
            if _root_sl_r64 is not None and 0.0 < float(_root_sl_r64) < 100.0:
                exit_cfg["stop_loss_pct"] = float(_root_sl_r64)

        # 4) التنفيذ الحسابي داخل خيط عامل (لا تجميد لحلقة الـAPI)
        _cache_note = str(((_cache_meta or {}).get("cache") or {}).get("note") or "")
        _cache_hit = bool(((_cache_meta or {}).get("cache") or {}).get("hit"))
        await _set_registry_progress(
            task_id, 25.0, "simulate",
            f"تنفيذ المحاكاة (استراتيجية {strategy}) — "
            f"{'من الكاش' if _cache_hit else 'جلب كامل'}: "
            f"{len(candles)} شمعة {_cache_note[:60]}",
        )
        from app.services.unified_backtest import run_unified_exit_backtest

        result = await asyncio.to_thread(
            run_unified_exit_backtest,
            candles, strategy, strategy_params, exit_cfg,
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "market": market,
                "initial_capital": float(config.initial_capital),
                "timezone": str(config.timezone),
                "tz_offset_minutes": int(config.tz_offset_minutes or 0),
                "name": config.name,
            },
        )

        # 5) الحفظ في BacktestRun — نفس جدول التخزين، جلسة معزولة
        await _set_registry_progress(
            task_id, 92.0, "save", "حفظ النتيجة في قاعدة البيانات",
        )
        from app.database.session import build_isolated_session_maker
        from app.models.backtest_run import BacktestRun as _BacktestRun
        from app.tasks.backtest_tasks import clean_for_db

        backtest_id = uuid.uuid4().hex
        clean_summary = clean_for_db(result["summary"])
        clean_chart = clean_for_db(result["chart_data"])
        clean_full_config = clean_for_db(config.model_dump(mode="json"))

        def _save_isolated() -> None:
            from app.database.session import with_lock_retry

            async def _inner() -> None:
                session_maker, iso_engine = build_isolated_session_maker()
                try:
                    # ✅ R44 — الحفظ عبر درع القفل: كل محاولة تفتح جلسة
                    # جديدة (إعادة المحاولة على جلسة فاشلة غير آمنة) —
                    # انتظار/إعادة تصاعدية بدل الفشل بخط database is locked
                    # الذي أضاع نتائج محاكاة ناجحة كاملة في الإنتاج.
                    async def _do_save() -> None:
                        async with session_maker() as db:
                            db.add(_BacktestRun(
                                id=backtest_id,
                                name=config.name,
                                summary=clean_summary,
                                chart_data=clean_chart,
                                full_config=clean_full_config,
                                total_pnl_percent=float(clean_summary.get("total_pnl_percent") or 0.0),
                                win_rate=float(clean_summary.get("win_rate") or 0.0),
                                total_trades=int(clean_summary.get("total_trades") or 0),
                                timeframe=timeframe,
                                symbol=symbol,
                            ))
                            await db.commit()

                    await with_lock_retry(
                        _do_save, what=f"unified-exit save {backtest_id}"
                    )
                finally:
                    try:
                        await iso_engine.dispose()
                    except Exception:  # noqa: BLE001
                        pass

            import asyncio as _asyncio

            _asyncio.run(_inner())

        await asyncio.to_thread(_save_isolated)

        _inprocess_tasks[task_id] = {"state": "SUCCESS", "backtest_id": backtest_id}
        # ✅ R45 — إقفال صف السجل: مدة فعلية + لقطة سطحية للمكتبة
        if task_id.isdigit():
            try:
                from app.services.task_registry import TaskRegistry

                await TaskRegistry().finish_success(
                    int(task_id),
                    backtest_id=backtest_id,
                    total_pnl_percent=float(clean_summary.get("total_pnl_percent") or 0.0),
                    win_rate=float(clean_summary.get("win_rate") or 0.0),
                    total_trades=int(clean_summary.get("total_trades") or 0),
                    meta_patch=_cache_meta,
                )
            except Exception:  # noqa: BLE001 — إقفال السجل لا يفسد نتيجة ناجحة
                logger.exception("[R45] finish_success %s failed", task_id)
        logger.info(
            "✅ [R42/R45] unified-exit backtest %s completed (task %s, %.0f ms, strategy=%s)",
            backtest_id, task_id, (_time.perf_counter() - t0) * 1000, strategy,
        )
    except Exception as exc:  # noqa: BLE001
        _inprocess_tasks[task_id] = {
            "state": "FAILURE",
            "error": str(exc)[:400] or exc.__class__.__name__,
        }
        if task_id.isdigit():
            try:
                from app.services.task_registry import TaskRegistry

                await TaskRegistry().finish_failure(int(task_id), error=exc)
            except Exception:  # noqa: BLE001
                pass
        logger.exception("❌ [R42] unified-exit task %s failed: %s", task_id, exc)


async def _wait_for_result(db: AsyncSession, dispatch: Dict[str, Any], wait_timeout: int) -> Dict[str, Any]:
    """
    ✅ الجولة 12: عند wait=true — يستطلع حالة المهمة حتى النجاح/الفشل/انتهاء
    المهلة ثم يجلب المستند الكامل (summary + chart_data) من BacktestRun ويُعيده
    في نفس استجابة POST — فأوامر القبول الحرفية تقرأ chart_data مباشرة.
    """
    task_id = dispatch.get("task_id")
    if not task_id:
        return dispatch

    deadline = time.time() + max(5, int(wait_timeout))
    state = None
    status_resp: Dict[str, Any] = {}
    while time.time() < deadline:
        status_resp = await get_task_status(task_id)
        state = status_resp.get("state")
        if state in ("SUCCESS", "FAILURE"):
            break
        await asyncio.sleep(1.0)

    if state != "SUCCESS":
        out = dict(dispatch)
        out["status"] = "WAIT_TIMEOUT" if state not in ("FAILURE",) else "FAILURE"
        if state == "FAILURE":
            out["error"] = status_resp.get("error") or status_resp.get("error_detail") or "Backtest failed"
        elif state != "SUCCESS":
            out["message"] = f"Still processing after {wait_timeout}s — استخدم /backtest1/status/{task_id} لاحقاً"
        return out

    backtest_id = status_resp.get("backtest_id") or (status_resp.get("result") or {}).get("backtest_id")
    if not backtest_id:
        return {**dispatch, "status": "COMPLETED"}

    # ✅ نُعيد المستند المُثرى (metadata + ind_* مسطّحة + chart_data_by_symbol)
    # بنفس منطق GET /backtest/get/{id} حرفياً — عبر نفس البنية الداخلية
    # (R49: get_backtest_details أصبحت تعيد Response جاهزة bytes للتسريع،
    # لذا نبني الـ dict هنا من نفس الأساس المشترك بلا تسلسل مزدوج).
    try:
        from app.routers.backtest import (
            _get_or_build_base, _build_get_payload, _fetch_backtest_doc,
        )

        # ✅ R50: جلب خفيف بلا فك JSON ضخم داخل الحلقة
        bt_row = await _fetch_backtest_doc(db, backtest_id)
        base = await _get_or_build_base(db, backtest_id, bt_row)
        doc = await asyncio.to_thread(_build_get_payload, base, bt_row)
        return {
            "success": True,
            "task_id": task_id,
            "status": "COMPLETED",
            "mode": dispatch.get("mode"),
            "backtest_id": backtest_id,
            "name": doc.get("name"),
            "summary": doc.get("summary"),
            "chart_data": doc.get("chart_data"),
            "config": doc.get("config"),
        }
    except Exception:
        logger.exception("wait=true: failed to fetch enriched document")
        result = await db.execute(select(BacktestRun).where(BacktestRun.id == backtest_id))
        bt = result.scalar_one_or_none()
        if bt is None:
            return {**dispatch, "status": "COMPLETED", "backtest_id": backtest_id}
        return {
            "success": True,
            "task_id": task_id,
            "status": "COMPLETED",
            "mode": dispatch.get("mode"),
            "backtest_id": bt.id,
            "summary": bt.summary,
            "chart_data": bt.chart_data,
            "config": bt.full_config,
        }

# ==========================================
# 2. نقطة لفحص حالة المهمة
# ==========================================
@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    حالة المهمة — يدعم المهام داخل العملية (وضع inprocess) و Celery معاً.

    ✅ الجولة 12 (هوت-فكس): كان يعتمد Celery فقط، فكانت مهام inprocess
    تبدو PENDING للأبد. الآن: السجل المحلي أولاً ثم Celery.
    """
    # 0) ✅ R45 — المعرّفات الرقمية التسلسلية: السجل الدائم أولاً.
    #    الحالة والتقدّم والمدة وETA من قاعدة البيانات — صحيحة حتى بعد
    #    إعادة تشغيل الخدمة، مع شفاء صفوف celery المتأخرة تلقائياً.
    if task_id.isdigit():
        from app.services.task_registry import get_registry_status

        payload = await get_registry_status(task_id)
        if payload is not None:
            return payload

    # 1) المهام داخل العملية (وضع بلا Redis) — لها الأولوية
    local = _inprocess_tasks.get(task_id)
    if local is not None:
        response = {"task_id": task_id, "state": local.get("state", "PENDING"), "mode": "inprocess"}
        state = local.get("state")
        if state == "PROGRESS":
            response["message"] = local.get("status", "Processing...")
        elif state == "SUCCESS":
            response["message"] = "Backtest completed successfully."
            response["backtest_id"] = local.get("backtest_id")
            response["result"] = {"status": "SUCCESS", "backtest_id": local.get("backtest_id")}
        elif state == "FAILURE":
            response["message"] = "Task failed."
            response["error"] = local.get("error", "Backtest execution failed.")
            response["error_detail"] = local.get("error", "")
        else:
            response["message"] = "Task is waiting to be processed."
        return response

    # 2) مهام Celery (الوضع الطبيعي)
    # ✅ R50 — قراءة حالة celery (شبكة Redis متزامنة) داخل خيط عامل
    def _read_celery():
        tr = AsyncResult(task_id, app=celery_app)
        st = tr.state
        if st == "PROGRESS":
            return st, (tr.info if isinstance(tr.info, dict) else {}), None, None
        if st == "SUCCESS":
            return st, None, tr.result, None
        if st == "FAILURE":
            return st, None, None, tr.info
        return st, None, None, None

    try:
        state, progress_info, success_result, failure_info = await asyncio.to_thread(_read_celery)
    except Exception:  # noqa: BLE001 — broker ساقط: تحلّل آمن بدل 500
        return {
            "task_id": task_id,
            "state": "PENDING",
            "message": "Task state temporarily unavailable (broker offline) — retry shortly.",
        }
    response = {
        "task_id": task_id,
        "state": state
    }
    
    if state == 'PENDING':
        response['message'] = "Task is waiting to be processed."
    elif state == 'PROGRESS':
        response['message'] = (progress_info or {}).get('status', 'Processing...')
    elif state == 'SUCCESS':
        response['message'] = "Backtest completed successfully."
        response['result'] = success_result
    elif state == 'FAILURE':
        response['message'] = "Task failed."
        response['error'] = str(failure_info)
        
    return response


# @router.post("/run")
# async def run_backtest(
#     config: BacktestConfig = Body(...),
#     generate_report: bool = Query(True),
#     save_to_file: bool = Query(False),
#     db = Depends(get_db)
# ):
#     """
#     تشغيل باك-تيست كامل (يعمل الآن كمحرك تنفيذ للقرارات)
#     """
#     try:
#         engine = get_backtest_engine(db)
        
#         strategy_name = config.strategy_config.get('name', 'Unknown') if config.strategy_config else 'Default'
#         logger.info(f"🚀 Starting Backtest for strategy: {strategy_name}")
        
#         # تشغيل المحرك (الذي سيقوم بإنشاء StrategyEngine داخلياً وتنفيذ القرارات)
#         result = await engine.run_backtest(config)

#         _backtest_storage[result.id] = result

        
#         response = {
#             "success": True,
#             "backtest_id": result.id,
#             "summary": {
#                 "name": config.name,
#                 "timeframe": config.timeframe,
#                 "initial_capital": result.initial_capital,
#                 "final_capital": result.final_capital,
#                 "total_pnl": result.total_pnl,
#                 "total_pnl_percent": result.total_pnl_percent,  # ★ الاسم الجديد
#                 "total_trades": result.total_trades,
#                 "winning_trades": result.winning_trades,
#                 "losing_trades": result.losing_trades,
#                 "win_rate": result.win_rate,
#                 "max_drawdown_percent": result.max_drawdown_percent,
#                 "sharpe_ratio": result.sharpe_ratio,
#                 "sortino_ratio": result.sortino_ratio,
#                 "calmar_ratio": result.calmar_ratio,
#                 "profit_factor": result.profit_factor,
#                 "expectancy": result.expectancy,
#                 "annual_return_percent": result.annual_return_percent,
#                 "execution_time_seconds": result.execution_time_seconds,
#                 "architecture_mode": "Strategy-Decision-Driven"
#             },
#             # بيانات إضافية يمكن استخدامها لاحقاً
#             "advanced_metrics": {
#                 "volatility_annual": result.volatility_annual,
#                 "var_95": result.var_95,
#                 "cvar_95": result.cvar_95,
#                 "system_quality_number": result.system_quality_number,
#                 "kelly_criterion": result.kelly_criterion
#             }
#         }
        
#         if hasattr(result, 'visual_candles'):
#             response["visual_candles_count"] = len(result.visual_candles)
#         if hasattr(result, 'trade_points'):
#             response["trade_points_count"] = len(result.trade_points)
        
#         # ==========================================
#         # ✅ إضافة كود الحفظ في قاعدة البيانات
#         # ==========================================
#         # ==========================================
#         # ✅ كود الحفظ المعدل (تعديل في السيف)
#         # ==========================================
#         try:
#             import json
#             from datetime import datetime
#             import pandas as pd
#             import numpy as np

#             # دالة مساعدة قوية لتنظيف البيانات قبل الحفظ
#             def clean_for_db(data):
#                 """
#                 تحويل البيانات إلى JSON ثم عودتها لقاموس.
#                 هذا يحل مشكلة datetime, timestamp, و numpy types المخفية.
#                 """
#                 class CleanEncoder(json.JSONEncoder):
#                     def default(self, obj):
                        
#                         # تحويل جميع أنواع التواريخ إلى نص ISO
#                         if isinstance(obj, (datetime, pd.Timestamp)):
                            
#                             return obj.isoformat()
#                         # تحويل أرقام numpy إلى float/int عادي
#                         if isinstance(obj, (np.integer, np.floating)):
#                             return float(obj)
                        

                        
#                         if isinstance(obj, np.ndarray):
#                             return obj.tolist()
#                         # للباقي
#                         return super().default(obj)
                
#                 # Roundtrip: dumps then loads
#                 return json.loads(json.dumps(data, cls=CleanEncoder))

#             # 1. تنظيف Summary
#             clean_summary = clean_for_db(response["summary"])

#             # 2. تجهيز وتنظيف Chart Data (الشموع + نقاط التداول)
#             # تحويل كائنات الشموع إلى قواميس أولاً
#             candles_as_dicts = []
#             for candle in result.visual_candles:
#                 if hasattr(candle, 'dict'):
#                     candles_as_dicts.append(candle.dict())
#                 elif hasattr(candle, '__dict__'):
#                     candles_as_dicts.append(candle.__dict__)
#                 else:
#                     candles_as_dicts.append(candle)
            
#             raw_chart_data = {
#                 "visual_candles": candles_as_dicts,
#                 "trade_points": result.trade_points
#             }
#             # تنظيف البيانات بالكامل
#             clean_chart_data = clean_for_db(raw_chart_data)

#             # 3. تنظيف Config (لأنه يحتوي على start_date و end_date)
#             clean_full_config = clean_for_db(config.dict())

#             # ✅ الحفظ الآن باستخدام البيانات المنظفة تماماً
#             db_backtest = BacktestRun(
#                 id=result.id,
#                 name=config.name,
#                 summary=clean_summary,          # ✅ تم التنظيف
#                 chart_data=clean_chart_data,    # ✅ تم التنظيف
#                 full_config=clean_full_config,  # ✅ تم التنظيف
#                 total_pnl_percent=result.total_pnl_percent,
#                 win_rate=result.win_rate,
#                 total_trades=result.total_trades,
#                 timeframe=config.timeframe,
#                 symbol=config.symbols[0] if config.symbols else "Unknown"
#             )
            
#             db.add(db_backtest)
#             await db.commit()
#             logger.error(f"DB state before commit | is_active={db.is_active} | in_transaction={db.in_transaction()} | bind={db.get_bind()}")

#             logger.info(f"✅ Backtest {result.id} saved to database successfully.")
            
#         except Exception as db_err:
#             logger.error(f"❌ Failed to save backtest to DB: {db_err}")
#             # لا نوقف العملية


#         if generate_report:
#             # التأكد من وجود دالة التوليد
#             try:
#                 report = _report_generator.generate_full_report(result, include_charts=True)
#                 response["report"] = report
                
#                 if save_to_file:
#                     filepath = _report_generator.save_report_to_file(result)
#                     response["report_file"] = filepath
#             except Exception as report_err:
#                 logger.warning(f"Failed to generate detailed report: {report_err}")
#                 response["report_note"] = "Report generation failed, but data is available in summary."


#         normalizer = MetricsNormalizer()
#         safe_response = normalizer.normalize(response)  # تمرير dict فقط
#         return safe_response        
#         # return response
        
#     except Exception as e:
#         logger.exception("Backtest execution failed")
#         raise HTTPException(status_code=500, detail=str(e))


























# ✅ 1. دالة مساعدة لتفكيك القواميس المتداخلة (مثل Bollinger Bands)
def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
    """
    يحول قاموس متداخل مثل: {"bb": {"upper": 3000, "lower": 2900}}
    إلى قاموس مسطح مثل: {"bb_upper": 3000, "bb_lower": 2900}
    """
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items

@router.get("/{backtest_id}/chart-data")
async def get_chart_data(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    start_index: int = Query(None),
    limit: int = Query(None),
    include_indicators: Optional[List[str]] = Query(None)
):
    """
    جلب كامل بيانات الرسم البياني (Full Dump).

    ✅ الجولة 12.1 (إصلاح جذري): كانت هذه النقطة تقرأ backtest.visual_candles
    — وهو حقل غير موجود في ORM BacktestRun (البيانات الفعلية في عمود
    chart_data JSON) — فكانت تُعيد 404 "No chart data available" **دائماً**
    حتى مع وجود بيانات. الآن تُفوَّض مباشرة إلى التنفيذ الصحيح والكامل في
    app.routers.backtest.get_chart_data (نفس مصدر الحقيقة: عمود chart_data
    + كاش + include_indicators=true + chart_data_by_symbol + overlays) —
    بلا أي ازدواجية منطق يمكن أن يتفكك مستقبلاً.
    """
    from app.routers.backtest import get_chart_data as _correct_chart_data

    # ✅ ملاحظة: استدعاء مباشر (ليس عبر FastAPI) — لذلك نمرّر كل معاملات
    # الدالة الداخلية صراحة (الافتراضيات Query(None) تبقى FieldInfo عند
    # الاستدعاء المباشر فلا تُقرأ تلقائياً كـ None).
    return await _correct_chart_data(
        backtest_id=backtest_id,
        db=db,
        request=request,
        start_index=start_index,
        limit=limit,
        include_indicators=include_indicators,
        overlays=None,
        zz_length=100,
        fib_depth=10,
        fib_dev=5.0,
        fib_ret=0.618,
        tl_period=10,
        tl_pairs=1,
    )


@router.get("/list")
async def list_backtests(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    جلب قائمة بجميع عمليات الباك测试 المخزنة (مفيد للوحة التحكم)

    ✅ R50 — قائمة خفيفة: كان الاستعلام يحمّل كامل الكيان بما فيه
    chart_data (52-208MB لكل صف!) — الآن أعمدة العرض فقط (نفس الرد
    بالضبط). القياس الفعلي قبل الإصلاح: 2.9 ثانية لكل استدعاء مع
    تجميد كامل للنظام خلفه.
    """
    try:
        # الاستعلام عن الباك测试 مرتبة من الأحدث للأقدم
        # ✅ R44 — قراءة عبر درع القفل (rollback + إعادة محاولة تصاعدية)
        from app.database.session import execute_with_lock_retry
        from sqlalchemy.orm import load_only

        query = (
            select(BacktestRun)
            .options(load_only(
                BacktestRun.id, BacktestRun.name, BacktestRun.created_at,
                BacktestRun.total_pnl_percent, BacktestRun.win_rate,
                BacktestRun.total_trades, BacktestRun.timeframe, BacktestRun.symbol,
            ))
            .order_by(BacktestRun.created_at.desc()).offset(offset).limit(limit)
        )
        result = await execute_with_lock_retry(db, query, what="backtest1/list")
        backtests = result.scalars().all()
        
        backtests_list = []
        for bt in backtests:
            backtests_list.append({
                "id": bt.id,
                "name": bt.name,
                "created_at": bt.created_at.isoformat() if bt.created_at else None,
                "summary_stats": {
                    "total_pnl_percent": bt.total_pnl_percent,
                    "win_rate": bt.win_rate,
                    "total_trades": bt.total_trades,
                    "timeframe": bt.timeframe,
                    "symbol": bt.symbol
                }
            })
            
        return {
            "success": True,
            "count": len(backtests_list),
            "data": backtests_list
        }
    except Exception as e:
        logger.error(f"Error listing backtests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/{backtest_id}")
async def get_backtest_details(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    جلب تفاصيل باك-test محدد مع بيانات الشارت (الشموع) بالكامل
    هذا هو البديل الدائم للـ storage المؤقت

    ✅ R49 — إصلاح التجميد:
    - كان كل طلب يعيد تحميل عمود chart_data الضخم (87MB+ للمستندات الثقيلة)
      ويعيد تسطيح 129,600 شمعة **داخل حلقة الأحداث وبلا أي كاش** — 10.6 ثانية
      لكل فتح من المكتبة والنظام كله متجمد خلفه، ثم timeout عند الفرونت.
    - الآن: كاش R49 (مفتاح |get1) + بناء مشترك مع أساس /chart-data
      (نسخة شموع واحدة في الذاكرة) + كل المعالجة داخل خيط عامل.
    - العقد حرفيًا كما كان: نفس الحقول، visual_candles مسطحة ind_*،
      trade_points الخام، وبقية حقول chart_data كما خزنها المحرك.
    """
    try:
        from app.routers.backtest import (
            _get_or_build_base, _serve_heavy_doc, _bt_cache_get,
        )

        response_data = None
        cache_key = f"{backtest_id}|get1bytes"

        # ✅ R50.1 (تدقيق الرئيس): فحص كاش البايتات **المبكر** — إعادة الهيكلة
        # كانت قد نقلت الفحص إلى _serve_heavy_doc الذي يُستدعى بعد جلب
        # المستند وتفكيكه وبناء الأساس والحمولة كاملة → كل طلب دافئ دفع
        # ~2.4s + ~500MB ذاكرة عابرة بلا داعٍ. الآن: الفحص أول شيء —
        # الطلب المتكرر يُعاد فورًا من البايتات المضغوطة (نفس مسار
        # /backtest/get الحرفي).
        _cached = _bt_cache_get(cache_key)
        if _cached is not None:
            import gzip as _gz

            from starlette.responses import Response
            if isinstance(_cached, tuple):
                _tag, _data = _cached
                if _tag == "gz":
                    if request is not None and "gzip" in (request.headers.get("accept-encoding") or ""):
                        return Response(
                            content=_data, media_type="application/json",
                            headers={"Content-Encoding": "gzip"},
                        )
                    _raw = await asyncio.to_thread(_gz.decompress, _data)
                    return Response(content=_raw, media_type="application/json")
                # ✅ R56 — زوج ("raw", bytes): أول طلب جاء من عميل بلا
                # accept-encoding: gzip فخُزّنت البايتات غير المضغوطة.
                # كان السقوط إلى الأسفل يمرّر الزوج كاملًا لـ Response
                # فينفجر starlette بـ 'tuple' object has no attribute
                # 'encode' → 500 دائم لكل طلب لاحق على نفس الباك تست
                # (سجل الإنتاج 2026-11-08 11:54 — 41d9a610).
                if _tag == "raw":
                    return Response(content=_data, media_type="application/json")
            return Response(content=_cached, media_type="application/json")

        # ✅ R44 — قراءة عبر درع القفل (rollback + إعادة محاولة تصاعدية)
        from app.routers.backtest import _fetch_backtest_doc as _fetch_doc

        backtest = await _fetch_doc(db, backtest_id)

        # ✅ R49: الأساس المشترك (كاش + بناء داخل خيط عامل)
        base = await _get_or_build_base(db, backtest_id, backtest)

        def _build_payload():
            chart_data = dict(base["get_extras"])
            chart_data["visual_candles"] = base["flat_candles"]
            chart_data["trade_points"] = base["trade_points_raw"]
            return {
                "success": True,
                "backtest_id": backtest.id,
                "name": backtest.name,
                "created_at": backtest.created_at.isoformat(),
                "summary": backtest.summary,
                "chart_data": chart_data,
                "config": backtest.full_config,
            }

        response_data = await asyncio.to_thread(_build_payload)
        # ✅ R50: تسلسل + ضغط gzip داخل خيط عامل + كاش البايتات المضغوطة
        # (7MB بدل 52MB) — _serve_heavy_doc يفحص الكاش ويعيد المضغوط فوراً.
        return await _serve_heavy_doc(request, response_data, cache_key=cache_key)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting backtest details: {e}")
        raise HTTPException(status_code=500, detail=str(e))







@router.delete("/delete/{backtest_id}")
async def delete_backtest_run(
    backtest_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    حذف نتيجة باك-تست محددة من قاعدة البيانات
    """
    try:
        # البحث عن السجل
        query = select(BacktestRun).where(BacktestRun.id == backtest_id)
        result = await db.execute(query)
        backtest = result.scalar_one_or_none()
        
        if not backtest:
            raise HTTPException(status_code=404, detail="Backtest not found")
        
        # حذف السجل
        await db.delete(backtest)
        await db.commit()

        # ✅ R50.1 (تدقيق الرئيس): إبطال كاش الباك-تست المحذوف — هذا المسار
        # لم يُبطِل الكاش أصلًا (عيب موروث): بعد الحذف كان /get يعيد
        # المستند المحذوف من كاش البايتات. نفس سلوك /backtest/delete.
        from app.routers.backtest import _bt_cache_drop

        _bt_cache_drop(backtest_id)

        return {
            "success": True,
            "message": f"Backtest '{backtest.name}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/walk-forward")
async def run_walk_forward_analysis(
    config: BacktestConfig = Body(...),
    periods: int = Query(5, ge=2, le=20),
    db = Depends(get_db)
):
    """
    تشغيل تحليل مشي للأمام (يدعمه المحرك الجديد)
    """
    _reject_exit_strategy_r421(config, "/walk-forward")  # ✅ ج42.1: درع الصراحة
    try:
        engine = get_backtest_engine(db)
        logger.info(f"Starting Walk-Forward Analysis ({periods} periods)...")
        
        results = await engine.run_walk_forward_analysis(config, periods)
        
        periods_summary = []
        for i, res in enumerate(results):
            periods_summary.append({
                "period": i + 1,
                "start_date": res.config.start_date.isoformat(),
                "end_date": res.config.end_date.isoformat(),
                "pnl_percent": res.total_pnl_percent,
                "win_rate": res.win_rate
            })
        
        return {
            "success": True,
            "periods_summary": periods_summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/monte-carlo")
async def run_monte_carlo_simulation(
    config: BacktestConfig = Body(...),
    simulations: int = Query(1000, ge=100, le=10000),
    db = Depends(get_db)
):
    """
    تشغيل محاكاة مونت كارلو
    """
    _reject_exit_strategy_r421(config, "/monte-carlo")  # ✅ ج42.1: درع الصراحة
    try:
        engine = get_backtest_engine(db)
        results = await engine.run_monte_carlo_simulation(config, simulations)
        
        return {
            "success": True,
            "results": results,
            "interpretation": {
                "probability_of_profit": f"{results['probability_profit'] * 100:.1f}%"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# ✅ الجولة 45 — سجل العمليات: المكتبة المؤسساتية
# ==========================================
@router.get("/tasks")
async def list_task_registry(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: Optional[str] = Query(None, description="فلترة: PROGRESS | SUCCESS | FAILURE"),
):
    """قائمة كل عمليات الباك-تست (المنتهية والجارية) من السجل الدائم.

    هذا مصدر شاشة Library في الواجهة: لكل عملية رقمها التسلسلي الظاهر
    (10000001...) واسمها وحالتها ونسبة تقدمها الحية (للجارية) ومدتها
    ولقطتها السطحية (نسبة الربح/النجاح/عدد الصفقات) — كلها من قاعدة
    البيانات، تبقى بعد إعادة التشغيل، وتُسترجع أي عملية سابقة عبر
    GET /get/{backtest_id} بحقل backtest_id المرتبط.
    """
    from app.services.task_registry import TaskRegistry

    reg = TaskRegistry()
    result = await reg.list_tasks(limit=limit, offset=offset, state=state)
    # إثراء الجارية بـ ETA (متوسط تاريخي أو استقراء تقدم)
    enriched = []
    for row in result.get("data", []):
        enriched.append(await reg.enrich_live(row))
    result["data"] = enriched
    return result


@router.get("/tasks/{task_id}")
async def get_task_registry_entry(task_id: str):
    """تفاصيل عملية واحدة من السجل الدائم — نفس عقد /status الرقمي."""
    if not task_id.isdigit():
        raise HTTPException(
            status_code=422,
            detail="معرّف العملية في السجل رقمي تسلسلي (مثل 10000001) — "
            "للمعرّفات السداسية القديمة استخدم /status/{task_id}",
        )
    from app.services.task_registry import get_registry_status

    payload = await get_registry_status(task_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"لا توجد عملية برقم {task_id} في السجل",
        )
    return payload


@router.get("/candle-cache")
async def list_candle_cache(limit: int = Query(100, ge=1, le=500)):
    """شفافية كاش الشموع: ما المخزون لكل رمز/فريم وحدوده الزمنية.

    لكل مفتاح: عدد الشموع المخزنة دائماً في قاعدة البيانات + أول وآخر
    شمعة + ملاحظة آخر جلب — حتى يعرف الفرونت والمراقبة من أين تأتي
    البيانات دون تخمين.
    """
    from app.services.candle_cache import CandleCacheService

    entries = await CandleCacheService().list_entries(limit=limit)
    return {"success": True, "count": len(entries), "data": entries}


@router.delete("/candle-cache/{cache_key:path}")
async def clear_candle_cache(cache_key: str):
    """حذف مخزون كاش لمفتاح واحد (يعاد جلبه كاملاً عند أول طلب تالٍ)."""
    from app.services.candle_cache import CandleCacheService

    deleted = await CandleCacheService().delete_entry(cache_key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cache key not found")
    return {"success": True, "message": f"candle cache '{cache_key}' cleared"}


@router.get("/metrics")
async def get_available_metrics():
    """الحصول على مقاييس متاحة"""
    return {
        "return_metrics": ["total_pnl", "sharpe_ratio", "win_rate"],
        "risk_metrics": ["max_drawdown", "volatility"],
        "trade_metrics": ["total_trades", "avg_win", "avg_loss"]
    }
