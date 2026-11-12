# app/tasks/backtest_tasks.py
"""
مهمة Celery لتشغيل الباك-تست في الخلفية (Worker منفصل تماماً عن السيرفر).

- تبقى sync def (متوافقة مع Celery prefork) وتنشئ event loop خاصاً بها.
- تنشئ جلستها الخاصة من async_session_maker (لا تعتمد على جلسة الـ API).
- تستقبل config_dict كاملاً JSON-آمن (قادم من الراوتر عبر model_dump(mode="json")).
"""
import asyncio
import json
import logging
import math
from datetime import datetime

import numpy as np
import pandas as pd

from app.celery_app import celery_app
from app.database import async_session_maker
from app.backtest.engine1 import BacktestEngine
from app.services.data_service import DataService
from app.backtest.schemas import BacktestConfig
from app.models.backtest_run import BacktestRun

logger = logging.getLogger(__name__)


async def _dispose_worker_async_state() -> None:
    """✅ R56 — كسر تلوث حلقات الأحداث بين مهام Celery المتتالية.

    كل مهمة تنشئ event loop خاصاً بها ثم تغلقه في finally — لكن مسبح
    اتصالات المحرك المشترك (asyncpg) والعميل المشترك لـ Redis يبقيان
    اتصالات مرتبطة بالحلقة المغلقة. المهمة التالية (على حلقة جديدة)
    تسحب تلك الاتصالات من المسبح فتفشل بـ:
      RuntimeError: Task ... got Future ... attached to a different loop
      RuntimeError: Event loop is closed
    (سجل الإنتاج: [R45] registry update failed + Redis get_cached failed
    في كل مهمة بعد الأولى — فتبدو المهمة عالقة PROGRESS في الواجهة
    ويَموت كاش الشموع داخل العامل).

    الإغلاق هنا في نهاية كل مهمة — على حلقة المهمة نفسها قبل إغلاقها —
    يضمن أن المهمة التالية تبدأ باتصالات جديدة على حلقتها الخاصة.
    العميل مستقل داخل عملية العامل فقط (عملية الـAPI لا تتأثر إطلاقاً).
    """
    try:
        from app.database.session import engine as _shared_engine
        await _shared_engine.dispose()
    except Exception:  # noqa: BLE001 — التنظيف لا يُفشل مهمة نجحت
        pass
    try:
        from app.database.redis_client import redis_client as _rc
        await _rc.disconnect()  # يردّها None ← إعادة اتصال نظيفة على حلقة المهمة التالية
    except Exception:  # noqa: BLE001
        pass


def _sanitize_nonfinite(obj):
    """✅ R49 — إصلاح «Token "Infinity" is invalid»:

    json.dumps يكتب قيم float اللانهائية/NaN كنصوص حرفية (Infinity/NaN)
    **دون المرور بـ JSONEncoder.default** — فهي float أصلية وليست نوعاً
    مجهولاً. PostgreSQL يرفضها: invalid input syntax for type json،
    فتضيع نتيجة محاكاة ناجحة كاملة عند الحفظ (ثبت حياً في R49 على
    SOLUSDT 1m: sharpe/calmar = inf عند drawdown صفري).
    المعالجة المسبقة التكرارية تحوّل ±inf/NaN → None (JSON null) قبل
    أي dumps — وهو سلوك الافتراضيات السليمة في كل العقد.
    """
    if isinstance(obj, dict):
        return {k: _sanitize_nonfinite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nonfinite(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


def clean_for_db(data):
    """
    تحويل جميع أنواع البيانات المعقدة (Datetime, Numpy, NaN, ±Infinity) إلى
    JSON عادي عبر roundtrip: dumps ثم loads.
    """
    class CleanEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (datetime, pd.Timestamp)):
                return obj.isoformat()
            if isinstance(obj, (np.integer, np.floating)):
                return float(obj) if not math.isnan(obj) else None  # حماية من NaN
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    try:
        # ✅ R49: المعالجة المسبقة إلزامية — default وحده لا يُستدعى أصلاً
        # لقيم float العادية (Infinity/NaN تمر كما هي إلى المخرجات النصية)
        data = _sanitize_nonfinite(data)
        return json.loads(json.dumps(data, cls=CleanEncoder, allow_nan=False))
    except Exception:
        logger.warning("Failed to clean data for JSON, returning raw")
        return {}


@celery_app.task(bind=True)
def run_backtest_task(self, config_dict: dict):
    """
    مهمة Celery لتشغيل الباك-تست في الخلفية.

    config_dict يجب أن يكون JSON-آمن (التواريخ ISO strings) — الراوتر يرسله
    عبر BacktestConfig.model_dump(mode="json").

    عند النجاح يرجع: {"status": "SUCCESS", "backtest_id": <id>} — الـ backtest_id
    يُنشأ داخل المهمة نفسها (سجل BacktestRun في قاعدة البيانات)، لذا يمكن
    استرجاعه عبر GET /status/{task_id} بعد انتهاء المهمة.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    self.update_state(state='PROGRESS', meta={'status': 'Starting Backtest Engine...'})

    try:
        result = loop.run_until_complete(_execute_backtest(config_dict, self))
        return {"status": "SUCCESS", "backtest_id": result}
    except Exception as e:
        # ✅ نرفع الاستثناء حتى يسجّل Celery الحالة FAILURE فعلياً
        # (النسخة السابقة كانت تُرجع dict وتبدو المهمة ناجحة).
        # ✅ R56 — أُزيل update_state(state="FAILURE") اليدوي: كان يكتب
        # نتيجة FAILURE بلا exc_type/exc_message ثم يتعثر celery نفسه في
        # mark_as_failure عند فكّها:
        #   ValueError: Exception information must include the exception type
        # (Pool callback raised exception — سجل الإنتاج 11:50:30).
        # الاستثناء المرفوع يوثّق السبب كاملاً في نتيجة المهمة، والسجل
        # الدائم يُقفله finish_failure داخل _execute_backtest.
        reason = str(e)[:400] or e.__class__.__name__
        logger.exception(f"❌ Backtest Task Failed: {reason}")
        raise
    finally:
        # ✅ R56 — التنظيف على حلقة المهمة نفسها قبل إغلاقها (انظر الدالة)
        try:
            loop.run_until_complete(_dispose_worker_async_state())
        except Exception:  # noqa: BLE001
            pass
        loop.close()


async def _execute_backtest(config_dict: dict, task_ref=None, session_maker=None):
    """تنفيذ الباك-تست كاملاً وحفظ النتيجة في BacktestRun

    ✅ الجولة 14.1: session_maker اختياري — مسار التشغيل الداخلي (بلا Celery)
    يمرّر مصنع جلسات معزول (محرك NullPool خاص بحلقة الخيط) لأن اتصالات
    المسبح المشترك مرتبطة بحلقة الـAPI. الافتراضي = المصنع المشترك كما هو.

    ✅ الجولة 45 — سجل العمليات + كاش الشموع:
    * ``config_dict["_r45_task_id"]`` (اختياري): رقم العملية التسلسلي الذي
      خصّصه الراوتر — عند وجوده تُحدَّث نسبة التقدم والمدة في جدول
      backtest_tasks طوال دورة الحياة (وينبثق قبل تحليل BacktestConfig
      حتى لا يرى pydantic مفتاحاً غريباً).
    * DataService يُغلَّف بـ CachedDataService: شموع الرمز/الفريم تُقرأ
      من قاعدة البيانات عند التغطية ويُجلب فقط الرأس الناقص فوقها —
      «اختبار سنة لبيتكوين بفريم الدقيقة» لا يعيد جلب 500 ألف شمعة
      مع كل استراتيجية جديدة. أي فشل داخل الكاش ⇦ جلب مباشر (سلوك
      اليوم) — لا كسر أبداً.
    """
    # ✅ R45: انبثاق رقم العملية قبل تحليل المخطط (مفتاح داخلي ليس من العقد)
    reg_id = config_dict.pop("_r45_task_id", None)
    reg = None
    if reg_id:
        try:
            from app.services.task_registry import TaskRegistry
            reg = TaskRegistry(session_maker=session_maker)
            await reg.update(
                int(reg_id), progress=8.0, phase="fetch",
                message="تحضير الشموع (كاش قاعدة البيانات)",
            )
        except Exception:  # noqa: BLE001 — السجل لا يوقف التشغيل أبداً
            reg = None

    _session_maker = session_maker or async_session_maker
    async with _session_maker() as db:
        try:
            # 1. تجهيز البيئة (config JSON-آمن → pydantic يحلل التواريخ ISO)
            config = BacktestConfig(**config_dict)
            data_service = DataService(db)

            # ✅ R45 — كاش الشموع الدائم: وكيل شفاف حول جلب التاريخ
            cached_service = data_service
            _CachedDS = None
            try:
                from app.services.candle_cache import CachedDataService as _CachedDS
                cached_service = _CachedDS(
                    data_service, session_maker=_session_maker
                )
            except Exception:  # noqa: BLE001 — الكاش رفاهية لا شرط بقاء
                cached_service = data_service
                _CachedDS = None

            engine = BacktestEngine(cached_service)

            strategy_name = config.strategy_config.get('name', 'Unknown') if config.strategy_config else 'Default'
            logger.info(f"🚀 [Worker] Starting Backtest for strategy: {strategy_name}")

            # 2. تشغيل المحرك
            if reg:
                await reg.update(
                    int(reg_id), progress=25.0, phase="simulate",
                    message=f"تنفيذ المحاكاة (استراتيجية {strategy_name})",
                )
            result = await engine.run_backtest(config)

            if reg:
                _ds_stats = (
                    dict(cached_service.stats)
                    if _CachedDS is not None
                    and isinstance(cached_service, _CachedDS)
                    else None
                )
                await reg.update(
                    int(reg_id), progress=80.0, phase="compute",
                    message="حساب المقاييس المتقدمة",
                    meta_patch=_ds_stats,
                )
            if task_ref:
                task_ref.update_state(state='PROGRESS', meta={'status': 'Calculating Metrics & Saving...'})

            # 3. الملخص والمقاييس المتقدمة
            response_summary = {
                "name": config.name,
                "timeframe": config.timeframe,
                # ✅ الجولة 14.0 — صدى التوقيت لتحقق الواجهة من المحاذاة المطبّقة
                "timezone": str(getattr(config, "timezone", "UTC") or "UTC"),
                "tz_offset_minutes": int(getattr(config, "tz_offset_minutes", 0) or 0),
                "initial_capital": result.initial_capital,
                "final_capital": result.final_capital,
                "total_pnl": result.total_pnl,
                "total_pnl_percent": result.total_pnl_percent,
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "win_rate": result.win_rate,
                "max_drawdown_percent": result.max_drawdown_percent,
                "sharpe_ratio": result.sharpe_ratio,
                "sortino_ratio": result.sortino_ratio,
                "calmar_ratio": result.calmar_ratio,
                "profit_factor": result.profit_factor,
                "expectancy": result.expectancy,
                "annual_return_percent": result.annual_return_percent,
                "execution_time_seconds": result.execution_time_seconds,
                "architecture_mode": "Strategy-Decision-Driven",
                # ✅ الجولة 12: الشفافية الحسابية الكاملة
                "fees_applied": float(getattr(result, "fees_applied", 0.0) or 0.0),
                "fill_model": str(getattr(result, "fill_model", "next_open") or "next_open"),
                "math_audit": getattr(result, "math_audit", {}) or {},
                # ✅ الجولة 14.1: ما طبّقه المحرك فعلاً من إعدادات المخاطر — شفافية تعاقدية
                "effective_config": getattr(result, "effective_config", None) or {},
            }

            advanced_metrics = {
                "volatility_annual": result.volatility_annual,
                "var_95": result.var_95,
                "cvar_95": result.cvar_95,
                "system_quality_number": result.system_quality_number,
                "kelly_criterion": result.kelly_criterion
            }

            clean_summary = clean_for_db(response_summary)
            clean_advanced_metrics = clean_for_db(advanced_metrics)

            # 4. تجهيز بيانات الشارت (الشموع + نقاط التداول + المنحنيات)
            #    model_dump(mode="json") يحوّل التواريخ تلقائياً — ثم clean_for_db
            #    يضمن خلوّ كل شيء من numpy/NaN.
            candles_as_dicts = [
                candle.model_dump(mode="json") for candle in result.visual_candles
            ]

            clean_chart_data = clean_for_db({
                "visual_candles": candles_as_dicts,
                "trade_points": result.trade_points,
                "equity_curve": result.equity_curve,
                "drawdown_curve": result.drawdown_curve,
            })

            # ✅ JSON-آمن بالكامل (كان config.dict() يحتوي datetime objects)
            clean_full_config = config.model_dump(mode="json")

            db_backtest = BacktestRun(
                id=result.id,
                name=config.name,
                summary={**clean_summary, **clean_advanced_metrics},
                chart_data=clean_chart_data,
                full_config=clean_full_config,
                total_pnl_percent=result.total_pnl_percent,
                win_rate=result.win_rate,
                total_trades=result.total_trades,
                timeframe=config.timeframe,
                symbol=config.symbols[0] if config.symbols else "Unknown"
            )

            # ✅ R44 — الحفظ عبر درع القفل: كل محاولة تعيد add (بعد rollback
            # يعود الكائن transient) ثم commit — بلا فقدان نتيجة محاكاة
            # ناجحة بخط قفل عابر كان يضيعها كاملة في الإنتاج.
            if reg:
                await reg.update(
                    int(reg_id), progress=92.0, phase="save",
                    message="حفظ النتيجة في قاعدة البيانات",
                )
            from app.database.session import with_lock_retry

            async def _commit_save() -> None:
                db.add(db_backtest)
                await db.commit()

            await with_lock_retry(
                _commit_save, what=f"save backtest {result.id}", session=db
            )
            logger.info(f"✅ [Worker] Backtest {result.id} saved to DB successfully.")

            # ✅ R45 — إقفال صف السجل بالمدة واللقطة السطحية
            if reg:
                _cache_meta = (
                    cached_service.last_meta.get("cache")
                    if _CachedDS is not None
                    and isinstance(cached_service, _CachedDS)
                    and isinstance(cached_service.last_meta, dict)
                    else None
                )
                await reg.finish_success(
                    int(reg_id),
                    backtest_id=result.id,
                    total_pnl_percent=float(result.total_pnl_percent or 0.0),
                    win_rate=float(result.win_rate or 0.0),
                    total_trades=int(result.total_trades or 0),
                    meta_patch={"cache": _cache_meta} if _cache_meta else None,
                )

            return result.id

        except Exception as e:
            await db.rollback()
            if reg:
                await reg.finish_failure(int(reg_id), error=e)
            logger.exception(f"Error during backtest execution: {e}")
            raise


# =============================================================================
# ✅ R49 — المسار الموحد (exit_strategy) داخل عامل Celery بدل عملية الـAPI
# -----------------------------------------------------------------------------
# المشكلة المُثبتة: backtest1/run بمسار exit_strategy كان يشغل المحاكاة دائماً
# داخل عملية الـAPI (asyncio.to_thread). الخيط لا يوقف الحلقة لكنه يسرق GIL
# طوال المحاكاة (127 ثانية في إنتاج المستخدم على SOLUSDT 1m) فتتجمد بقية
# النقاط ويهلك healthcheck ثم تعاد تشغيل الحاوية.
# الحل: نفس الجسم (دورة الحياة/التقدم/الحفظ) لكن داخل العامل المنفصل —
# والراوتر يرسل إليه عند توفر الـ broker ويبقى المسار الداخلي درعاً عند غيابه.
# =============================================================================

@celery_app.task(bind=True)
def run_unified_exit_task(self, config_dict: dict):
    """
    مهمة Celery للمسار الموحد (محرك الخروج ج41 + استراتيجية zzfib*).

    نفس عقد _run_unified_exit_task داخل العملية حرفياً:
    PROGRESS (10/25/92%) → SUCCESS/FAILURE + حفظ BacktestRun + إقفال السجل
    عبر config_dict["_r45_task_id"].
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_execute_unified_exit(config_dict, self))
        return {"status": "SUCCESS", "backtest_id": result}
    except Exception as e:
        # ✅ R56 — نفس إصلاح run_backtest_task: بلا update_state(FAILURE)
        # يدوي (كان يكسر mark_as_failure في backend الـ celery) —
        # الاستثناء المرفوع يوثّق السبب بنفسه.
        reason = str(e)[:400] or e.__class__.__name__
        logger.exception("❌ Unified-exit task failed: %s", reason)
        raise
    finally:
        # ✅ R56 — التنظيف على حلقة المهمة نفسها قبل إغلاقها (انظر الدالة)
        try:
            loop.run_until_complete(_dispose_worker_async_state())
        except Exception:  # noqa: BLE001
            pass
        loop.close()


async def _execute_unified_exit(config_dict: dict, task_ref=None) -> str:
    """جسم المسار الموحد داخل العامل — منقول حرفياً من
    app.routers.backtest1._run_unified_exit_task (R42/R45) بلا أي تغيير عقد."""  # noqa: E501

    reg_id = config_dict.pop("_r45_task_id", None)

    async def _set_progress(percent: float, phase: str, message: str) -> None:
        if not reg_id:
            return
        try:
            from app.services.task_registry import TaskRegistry

            await TaskRegistry().update(int(reg_id), progress=percent,
                                        phase=phase, message=message)
        except Exception:  # noqa: BLE001 — التقدم غير حرج
            pass

    import time as _time
    import uuid

    t0 = _time.perf_counter()
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

    # 2) إعدادات الخروج — المنظّمة من المخطط إن توفرت
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

    # 3) ✅ R55 — جلب الشموع بنافذة الجذر الحرفية (نفس مصدر المحرك الرئيسي
    #    ونفس فضاء كاش d) — انتهى «آخر N يوم من الآن» الذي كان يتجاهل
    #    start_date/end_date من الجذر (#10000016).
    await _set_progress(
        10.0, "fetch",
        f"تحضير شموع {symbol} {timeframe} بنافذة الجذر "
        f"({config.start_date:%Y-%m-%d} → {config.end_date:%Y-%m-%d})",
    )
    from app.routers.backtest1 import _fetch_unified_candles

    candles, _cache_meta = await _fetch_unified_candles(
        config, symbol, timeframe, market,
    )
    if not candles:
        raise ValueError(
            f"لا توجد شموع للرمز {symbol} على فريم {timeframe} بين "
            f"{config.start_date:%Y-%m-%d} و{config.end_date:%Y-%m-%d}"
        )

    # ✅ R55 — تمرير سقف المراكز الرقمي من جذر الطلب لمحرك الخروج
    if config.max_positions is not None:
        exit_cfg["max_concurrent_positions"] = int(config.max_positions)

    # ✅ R64 — وراثة الستوب لوز من جذر الطلب عند تعطيل خروج الفيبو:
    # fibo_floor_exit=false ولم يُرسل stop_loss_pct صراحةً في كتلة الخروج
    # ⇒ يُورَث stop_loss_percent من جذر الكونفيق إن كان مفعلاً (0 < x < 100).
    # الأولوية الموثقة: stop_loss_pct الصريح في الكتلة > جذر الكونفيق > معطّل
    # (نفس فلسفة تمرير max_positions أعلاه — الجذر يغذي المحرك المنعزل).
    if exit_cfg.get("fibo_floor_exit") is False and "stop_loss_pct" not in (block.config or {}):
        _root_sl_r64 = config.stop_loss_percent
        if _root_sl_r64 is not None and 0.0 < float(_root_sl_r64) < 100.0:
            exit_cfg["stop_loss_pct"] = float(_root_sl_r64)

    # 4) التنفيذ الحسابي (داخل العامل المنفصل — الـAPI لا يتأثر إطلاقاً)
    _cache_hit = bool(((_cache_meta or {}).get("cache") or {}).get("hit"))
    await _set_progress(
        25.0, "simulate",
        f"تنفيذ المحاكاة (استراتيجية {strategy}) — "
        f"{'من الكاش' if _cache_hit else 'جلب كامل'}: "
        f"{len(candles)} شمعة",
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

    # 5) الحفظ في BacktestRun — جلسة عادية داخل العامل
    await _set_progress(
        92.0, "save", "حفظ النتيجة في قاعدة البيانات"
    )
    backtest_id = uuid.uuid4().hex
    clean_summary = clean_for_db(result["summary"])
    clean_chart = clean_for_db(result["chart_data"])
    clean_full_config = clean_for_db(config.model_dump(mode="json"))

    from app.database import async_session_maker
    from app.database.session import with_lock_retry

    async def _do_save() -> None:
        async with async_session_maker() as db:
            db.add(BacktestRun(
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

    await with_lock_retry(_do_save, what=f"unified-exit save {backtest_id}")

    if reg_id:
        try:
            from app.services.task_registry import TaskRegistry

            await TaskRegistry().finish_success(
                int(reg_id),
                backtest_id=backtest_id,
                total_pnl_percent=float(clean_summary.get("total_pnl_percent") or 0.0),
                win_rate=float(clean_summary.get("win_rate") or 0.0),
                total_trades=int(clean_summary.get("total_trades") or 0),
                meta_patch=_cache_meta,
            )
        except Exception:  # noqa: BLE001 — إقفال السجل لا يفسد نتيجة ناجحة
            logger.exception("[R49] finish_success %s failed", reg_id)
    logger.info(
        "✅ [R49] unified-exit (celery) backtest %s completed (task %s, %.0f ms, strategy=%s)",
        backtest_id, reg_id, (_time.perf_counter() - t0) * 1000, strategy,
    )
    return backtest_id
