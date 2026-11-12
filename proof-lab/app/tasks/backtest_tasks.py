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


def clean_for_db(data):
    """
    تحويل جميع أنواع البيانات المعقدة (Datetime, Numpy, NaN) إلى JSON عادي
    عبر roundtrip: dumps ثم loads.
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
        return json.loads(json.dumps(data, cls=CleanEncoder))
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
        # (النسخة السابقة كانت تُرجع dict وتبدو المهمة ناجحة)
        # ✅ Bugfix: كنا نخفي السبب الحقيقي عن /status ("رسالة فاشلة عامة") —
        # الآن نحفظ السبب في meta ليقرأه /status ويعرضه عند DEBUG.
        reason = str(e)[:400] or e.__class__.__name__
        try:
            self.update_state(state="FAILURE", meta={"error": reason})
        except Exception:  # noqa: BLE001 — فشل تحديث الحالة لا يخفي الخطأ الأصلي
            pass
        logger.exception(f"❌ Backtest Task Failed: {e}")
        raise
    finally:
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
