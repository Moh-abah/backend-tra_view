# app/routers/backtest1.py
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import List, Dict, Any, Optional
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
            task_id = uuid.uuid4().hex
            config_dict = config.model_dump(mode="json")
            _inprocess_tasks[task_id] = {
                "state": "PROGRESS",
                "status": "Unified Exit Engine: fetching candles...",
            }
            asyncio.create_task(_run_unified_exit_task(task_id, config_dict))
            dispatch = {
                "success": True,
                "message": "Unified backtest (exit-strategy engine) started. Processing in background.",
                "task_id": task_id,
                "status": "PROCESSING",
                "mode": "unified-exit",
            }
            logger.info(
                "🔁 [R42] backtest1/run unified-exit dispatch (task %s, symbol %s)",
                task_id, config.symbols[0] if config.symbols else "?",
            )
            if wait:
                return await _wait_for_result(db, dispatch, wait_timeout)
            return dispatch

        if not is_broker_available(timeout=2.0):
            # ✅ مسار احتياطي داخل العملية — بلا Redis/Celery
            from app.routers.backtest import _run_backtest_inprocess

            task_id = uuid.uuid4().hex
            config_dict = config.model_dump(mode="json")
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
                "status": "PROCESSING",
                "mode": "inprocess",
            }
        else:
            logger.info(f"📤 Dispatching Backtest task to Celery: {config.name}")

            # إرسال المهمة للـ Worker
            # ✅ model_dump(mode="json") يحول datetime إلى ISO strings —
            # dict() كان يفشل مع Celery JSON serializer (EncodeError)
            task = run_backtest_task.delay(config.model_dump(mode="json"))

            dispatch = {
                "success": True,
                "message": "Backtest started successfully. Processing in background.",
                "task_id": task.id,
                "status": "PROCESSING",
                "mode": "celery",
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
        try:
            from app.routers.backtest import _run_backtest_inprocess

            task_id = uuid.uuid4().hex
            config_dict = config.model_dump(mode="json")
            _inprocess_tasks[task_id] = {"state": "PROGRESS", "status": "Starting Backtest Engine..."}
            asyncio.create_task(_track_inprocess(task_id, config_dict))
            logger.warning("Celery dispatch failed (%s) → backtest1/run in-process (task %s)", e, task_id)
            return {
                "success": True,
                "message": "Backtest started in-process (broker dispatch failed). Processing in background.",
                "task_id": task_id,
                "status": "PROCESSING",
                "mode": "inprocess",
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


def _resolve_unified_days(config: BacktestConfig) -> int:
    """نافذة الجلب بالأيام للمنفذ الموحد: days إن أُرسلت وإلا من فرق
    التواريخ (start_date → end_date) — نفس نافذة المحرك الرئيسي."""
    if config.days:
        d = int(config.days)
    else:
        try:
            delta = (config.end_date - config.start_date).total_seconds()
            d = int(delta // 86400)
        except (TypeError, AttributeError):
            d = 30
    return max(1, min(365, d or 30))


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

        # 3) جلب الشموع (stateless — نفس مزوّد راوتر محرك الخروج)
        _inprocess_tasks[task_id] = {
            "state": "PROGRESS",
            "status": f"Unified Exit Engine: fetching {symbol} {timeframe} candles...",
        }
        from app.services.data_service import DataService

        data_service = DataService(None)
        days = _resolve_unified_days(config)
        dataframe = await data_service.get_historical(
            symbol=symbol, timeframe=timeframe, market=market, days=days,
        )
        if dataframe is None or getattr(dataframe, "empty", True):
            raise ValueError(
                f"لا توجد شموع للرمز {symbol} على فريم {timeframe} ({days} يوماً)"
            )

        # 4) التنفيذ الحسابي داخل خيط عامل (لا تجميد لحلقة الـAPI)
        _inprocess_tasks[task_id] = {
            "state": "PROGRESS",
            "status": "Unified Exit Engine: running simulation...",
        }
        from app.routers.exit_strategy import _df_to_candles
        from app.services.unified_backtest import run_unified_exit_backtest

        candles = _df_to_candles(dataframe)
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
        _inprocess_tasks[task_id] = {
            "state": "PROGRESS",
            "status": "Unified Exit Engine: saving result...",
        }
        from app.database.session import build_isolated_session_maker
        from app.models.backtest_run import BacktestRun as _BacktestRun
        from app.tasks.backtest_tasks import clean_for_db

        backtest_id = uuid.uuid4().hex
        clean_summary = clean_for_db(result["summary"])
        clean_chart = clean_for_db(result["chart_data"])
        clean_full_config = clean_for_db(config.model_dump(mode="json"))

        def _save_isolated() -> None:
            async def _inner() -> None:
                session_maker, iso_engine = build_isolated_session_maker()
                try:
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
                finally:
                    try:
                        await iso_engine.dispose()
                    except Exception:  # noqa: BLE001
                        pass

            import asyncio as _asyncio

            _asyncio.run(_inner())

        await asyncio.to_thread(_save_isolated)

        _inprocess_tasks[task_id] = {"state": "SUCCESS", "backtest_id": backtest_id}
        logger.info(
            "✅ [R42] unified-exit backtest %s completed (task %s, %.0f ms, strategy=%s)",
            backtest_id, task_id, (_time.perf_counter() - t0) * 1000, strategy,
        )
    except Exception as exc:  # noqa: BLE001
        _inprocess_tasks[task_id] = {
            "state": "FAILURE",
            "error": str(exc)[:400] or exc.__class__.__name__,
        }
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
    # بنفس منطق GET /backtest/get/{id} حرفياً — استدعاء مباشر لنفس الدالة.
    try:
        from app.routers.backtest import get_backtest_details
        doc = await get_backtest_details(backtest_id, db)
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
    task_result = AsyncResult(task_id, app=celery_app)
    response = {
        "task_id": task_id,
        "state": task_result.state
    }
    
    if task_result.state == 'PENDING':
        response['message'] = "Task is waiting to be processed."
    elif task_result.state == 'PROGRESS':
        response['message'] = task_result.info.get('status', 'Processing...')
    elif task_result.state == 'SUCCESS':
        response['message'] = "Backtest completed successfully."
        response['result'] = task_result.result
    elif task_result.state == 'FAILURE':
        response['message'] = "Task failed."
        response['error'] = str(task_result.info)
        
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
    """
    try:
        # الاستعلام عن الباك测试 مرتبة من الأحدث للأقدم
        query = select(BacktestRun).order_by(BacktestRun.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
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
    db: AsyncSession = Depends(get_db)
):
    """
    جلب تفاصيل باك测试 محدد مع بيانات الشارت (الشموع) بالكامل
    هذا هو البديل الدائم للـ storage المؤقت
    """
    try:
        # البحث في قاعدة البيانات
        query = select(BacktestRun).where(BacktestRun.id == backtest_id)
        result = await db.execute(query)
        backtest = result.scalar_one_or_none()
        
        if not backtest:
            # إذا لم يجد في قاعدة البيانات، يمكنه البحث في الذاكرة المؤقتة كاحتياطي (اختياري)
            mem_result = _backtest_storage.get(backtest_id)
            if mem_result:
                # منطق إرجاع البيانات من الذاكرة (كما كان كودك السابق)
                # سنكتفي هنا برفع خطأ 404 لأن الهدف هو التخزين الدائم
                pass
            raise HTTPException(status_code=404, detail="Backtest not found in database")
        
        # تجهيز البيانات للإرجاع بنفس الشكل الذي طلبه المستخدم
        response_data = {
            "success": True,
            "backtest_id": backtest.id,
            "name": backtest.name,
            "created_at": backtest.created_at.isoformat(),
            
            # إرجاع الملخص المحفوظ
            "summary": backtest.summary,
            
            # إرجاع بيانات الشارت (الشموع) - هذا هو الجزء المهم
            "chart_data": backtest.chart_data,

            "config": backtest.full_config
        }
        
        
        
    # ✅ معالجة وتنسيق بيانات الشارت (Processing)
        # ==========================================
         # ==========================================
        
        # نسخة عميقة لتجنب تعديل البيانات الأصلية في الذاكرة إذا لزم الأمر
        chart_data = backtest.chart_data.copy() if backtest.chart_data else {}
        
        # التأكد من وجود الشموع
        if "visual_candles" in chart_data and isinstance(chart_data["visual_candles"], list):
            processed_candles = []
                   

            for candle in chart_data["visual_candles"]:
                # إنشاء نسخة من الشمعة للتعديل عليها
                formatted_candle = candle.copy()
                
                # 1. استخراج المؤشرات المتداخلة (nested)
                indicators_data = formatted_candle.pop("indicators", {})
                
                # 2. تسطيح المؤشرات (Flattening) باستخدام الدالة المساعدة الموجودة
                # تحول { "bb": { "upper": 3000 } } إلى { "bb_upper": 3000 }
                flat_indicators = flatten_dict(indicators_data)
                
                # 3. دمج المؤشرات المسطحة في الشمعة وإضافة البادئة ind_
                # ✅ الجولة 12.1 (إصلاح 0-أ): لا بادئة مزدوجة — ind_ind_zz_pivot كان
                # يظهر من هذه النقطة تحديداً (أعمدة العقد تأتي مسبقة ind_ من المحرك).
                for key, value in flat_indicators.items():
                    _k = str(key)
                    formatted_candle[_k if _k.startswith("ind_") else f"ind_{_k}"] = value
                
                processed_candles.append(formatted_candle)
            
            # تحديث قائمة الشموع بالنسخة المنسقة
            chart_data["visual_candles"] = processed_candles

        # إضافة البيانات المعدلة للاستجابة
        response_data["chart_data"] = chart_data
        
        return response_data
        
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

@router.get("/metrics")
async def get_available_metrics():
    """الحصول على مقاييس متاحة"""
    return {
        "return_metrics": ["total_pnl", "sharpe_ratio", "win_rate"],
        "risk_metrics": ["max_drawdown", "volatility"],
        "trade_metrics": ["total_trades", "avg_win", "avg_loss"]
    }
