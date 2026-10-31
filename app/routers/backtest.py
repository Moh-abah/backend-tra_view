# app/routers/backtest.py
"""
Backtest router — Celery-backed.

- POST /run            : يرسل مهمة الباك-تست إلى Celery (config JSON-آمن) ويعيد task_id
- GET  /status/{id}    : حالة المهمة من Celery Result Backend
- GET  /list           : قائمة الباك-تستات المخزنة (BacktestRun)
- GET  /get/{id}       : تفاصيل باك-تست كاملة من قاعدة البيانات
- GET  /{id}/chart-data: بيانات الرسم البياني من عمود chart_data في BacktestRun
- DELETE /delete/{id}  : حذف باك-تست
- POST /walk-forward   : تحليل مشي للأمام (محرك لكل طلب — بلا cache عالمي)
- POST /monte-carlo    : محاكاة مونت كارلو (محرك لكل طلب)
- GET  /metrics        : قائمة المقاييس المتاحة
"""
import asyncio
import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.backtest.engine1 import BacktestEngine, MAX_MONTE_CARLO_SIMULATIONS, MAX_WALK_FORWARD_WINDOWS
from app.backtest.schemas import BacktestConfig
from app.celery_app import celery_app
from app.database import get_db, async_session_maker
from app.models.backtest_run import BacktestRun
from app.services.data_service import DataService
from app.services.indicators.overlays import OVERLAY_TYPES as _OVL_TYPES, compute_overlays as _compute_overlays  # ✅ الجولة 10
from app.tasks.backtest_tasks import run_backtest_task

router = APIRouter(tags=["backtest"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process fallback registry (when Celery/Redis broker is unavailable).
#
# POST /run normally enqueues a Celery task and the client polls /status.
# Without a broker the old code hard-failed 503 and the dashboard backtest
# button was dead. Now: the same engine runs **inside the API process** as a
# background asyncio task, and /status serves its state from this registry
# with the exact same response contract ({task_id, state, backtest_id, ...}).
# ---------------------------------------------------------------------------
_inprocess_tasks: Dict[str, Dict[str, Any]] = {}

# ===========================================================================
# ✅ الجولة 9: كاش باكند لنتائج الباك-تست (بيانات تاريخية ثابتة لا تتغير أبداً)
# ---------------------------------------------------------------------------
# قياس الإنتاج: chart-data?include_indicators=true كان يأخذ 109-231 ثانية
# في كل طلب لنفس البيانات الثابتة. السبب: إعادة تحميل عمود JSON الضخم
# وإعادة حساب كل شيء في كل طلب بلا أي تخزين بيني.
#
# التصميم:
# - بناء **أساس معالج واحد** لكل backtest_id عند أول طلب (شموع مسطحة بكل
#   مفاتيح ind_* + نقاط تداول + منحنيات + metadata) ثم كل طلب لاحق
#   مجرد تقطيع/نسخ خفيف من الأساس — أداء ثابت مهما تعددت المعاملات.
# - LRU محدود (12 باك-تست) لضبط الذاكرة؛ الأحدث استخداماً يبقى.
# - الإبطال عند الحذف + عند إعادة تشغيل نفس المعرف (run جديد على نفس id).
# ===========================================================================
from collections import OrderedDict as _OrderedDict

_BT_CACHE_MAX = 12
_bt_cache: "_OrderedDict[str, Dict[str, Any]]" = _OrderedDict()


def _bt_cache_get(key: str) -> Optional[Dict[str, Any]]:
    if key in _bt_cache:
        _bt_cache.move_to_end(key)
        return _bt_cache[key]
    return None


def _bt_cache_put(key: str, value: Dict[str, Any]) -> None:
    _bt_cache[key] = value
    _bt_cache.move_to_end(key)
    while len(_bt_cache) > _BT_CACHE_MAX:
        _bt_cache.popitem(last=False)
    logger.info("💾 Backtest cache stored [%s] (entries=%d)", key[:12], len(_bt_cache))


def _bt_cache_drop(backtest_id: str) -> None:
    dropped = [k for k in list(_bt_cache.keys()) if k == backtest_id or k.startswith(f"{backtest_id}|")]
    for k in dropped:
        _bt_cache.pop(k, None)
    if dropped:
        logger.info("🧹 Backtest cache invalidated for %s (%d entries)", backtest_id, len(dropped))


def _inprocess_status_payload(task_id: str) -> Dict[str, Any]:
    state_entry = _inprocess_tasks.get(task_id)
    if not state_entry:
        return {"task_id": task_id, "state": "PENDING", "message": "Task is waiting to be processed."}
    state = state_entry["state"]
    response: Dict[str, Any] = {"task_id": task_id, "state": state}
    if state == "PENDING":
        response["message"] = "Task is waiting to be processed."
    elif state == "PROGRESS":
        response["message"] = state_entry.get("status", "Processing...")
    elif state == "SUCCESS":
        response["message"] = "Backtest completed successfully."
        response["backtest_id"] = state_entry.get("backtest_id")
        response["result"] = {"status": "SUCCESS", "backtest_id": state_entry.get("backtest_id")}
    else:  # FAILURE
        response["message"] = "Task failed."
        response["error"] = "Backtest execution failed. See server logs for details."
        if state_entry.get("error"):
            response["error_detail"] = state_entry["error"]
    return response


async def _run_backtest_inprocess(task_id: str, config_dict: dict) -> None:
    """Execute the same celery task body inside the API process."""
    from app.tasks.backtest_tasks import _execute_backtest

    _inprocess_tasks[task_id] = {"state": "PROGRESS", "status": "Starting Backtest Engine..."}
    try:
        backtest_id = await _execute_backtest(config_dict, None)
        _inprocess_tasks[task_id] = {
            "state": "SUCCESS",
            "backtest_id": backtest_id,
        }
        logger.info(f"✅ [in-process] Backtest {backtest_id} completed (task {task_id})")
    except Exception as exc:  # noqa: BLE001
        _inprocess_tasks[task_id] = {
            "state": "FAILURE",
            "error": str(exc)[:400] or exc.__class__.__name__,
        }
        logger.exception(f"❌ [in-process] Backtest task {task_id} failed: {exc}")



# ==========================================
# Helpers
# ==========================================

def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
    """
    يحول قاموساً متداخلاً مثل: {"bb": {"upper": 3000, "lower": 2900}}
    إلى قاموس مسطح مثل: {"bb_upper": 3000, "bb_lower": 2900}
    """
    items: Dict[str, Any] = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def _compute_drawdown_curve(equity_curve: List[float]) -> List[float]:
    """منحنى الانخفاض (نفس منطق PerformanceMetrics._calculate_drawdown_curve)"""
    if not equity_curve:
        return []
    peak = equity_curve[0]
    drawdowns: List[float] = []
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        drawdowns.append((peak - equity) / peak * 100 if peak > 0 else 0.0)
    return drawdowns


async def _get_backtest_row(db: AsyncSession, backtest_id: str) -> BacktestRun:
    """جلب سجل BacktestRun أو رفع 404"""
    result = await db.execute(select(BacktestRun).where(BacktestRun.id == backtest_id))
    backtest = result.scalar_one_or_none()
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return backtest


# ==========================================
# 1. تشغيل باك-تست عبر Celery
# ==========================================

@router.post("/run")
async def run_backtest(config: BacktestConfig = Body(...)):
    """
    يرسل طلب الباك-تست إلى Celery Worker ويعيد task_id فوراً.

    ✅ Fallback بدون Redis/Celery: إذا لم يكن الـ broker متاحاً تُنفَّذ نفس
    المهمة داخل عملية الـ API كخلفية asyncio (نفس المحرك ونفس الحفظ في
    BacktestRun) ويعيد /status نفس العقد تماماً — زر الباك تست في اللوحة
    يعمل بلا Redis.

    ملاحظة: backtest_id يُنشأ داخل المهمة عند حفظ النتيجة في BacktestRun —
    استرجعه من GET /status/{task_id} بعد نجاح المهمة (حقل backtest_id).
    """
    # ✅ فحص سريع لتوفر الـ broker قبل النشر — كان الطلب يعلّق لِدقائق
    # بإعادة محاولة kombu الافتراضية عندما يكون Redis/Celery غير متاح.
    from app.celery_app import is_broker_available
    if not is_broker_available(timeout=2.0):
        # ✅ مسار احتياطي داخل العملية — لا 503 بعد اليوم
        task_id = uuid.uuid4().hex
        config_dict = config.model_dump(mode="json")
        _inprocess_tasks[task_id] = {"state": "PROGRESS", "status": "Starting Backtest Engine..."}
        asyncio.create_task(_run_backtest_inprocess(task_id, config_dict))
        logger.warning(
            "Celery broker unavailable → running backtest in-process (task %s, strategy '%s')",
            task_id, config.name,
        )
        return {
            "task_id": task_id,
            "status": "queued",
            "mode": "inprocess",
        }
    try:
        # ✅ model_dump(mode="json") يحول datetime إلى ISO strings —
        # dict()/json.dumps كان يفشل مع Celery JSON serializer (EncodeError)
        task = run_backtest_task.delay(config.model_dump(mode="json"))
        logger.info(f"Dispatched backtest task {task.id} for '{config.name}'")
    except Exception:
        logger.exception("Failed to enqueue backtest task")
        raise HTTPException(
            status_code=503,
            detail="Failed to queue backtest task. The task broker may be unavailable."
        )

    return {
        "task_id": task.id,
        "status": "queued",
    }


# ==========================================
# 2. حالة المهمة
# ==========================================

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """فحص حالة مهمة Celery أو مهمة داخلية (fallback بلا broker) — JSON-آمن"""
    # ✅ مهام المسار الاحتياطي داخل العملية تُدار من السجل المحلي أولاً
    if task_id in _inprocess_tasks:
        return _inprocess_status_payload(task_id)
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        state = task_result.state
        response: Dict[str, Any] = {"task_id": task_id, "state": state}

        if state == 'PENDING':
            response['message'] = "Task is waiting to be processed."
        elif state == 'STARTED':
            response['message'] = "Task has started."
        elif state == 'PROGRESS':
            info = task_result.info if isinstance(task_result.info, dict) else {}
            response['message'] = info.get('status', 'Processing...')
        elif state == 'SUCCESS':
            result = task_result.result
            if isinstance(result, dict) and result.get("status") == "FAILURE":
                # (مهمة قديمة أرجعت FAILURE كقيمة نجاح — نتعامل معها)
                logger.warning(f"Task {task_id} returned embedded FAILURE: {result.get('error')}")
                response['state'] = 'FAILURE'
                response['message'] = "Task failed."
                response['error'] = "Backtest execution failed. See server logs for details."
            else:
                response['message'] = "Backtest completed successfully."
                if isinstance(result, dict):
                    response['backtest_id'] = result.get("backtest_id")
                response['result'] = result
        elif state == 'FAILURE':
            # نسجّل الاستثناء الحقيقي server-side ولا نكشفه للعميل،
            # ✅ لكن عند DEBUG نعرض السبب الحقيقي (Bugfix: كان الفشل يظهر
            # برسالة عامة بلا تفاصيل فيصعب تشخيصه مثل تعطل قاعدة البيانات).
            logger.error(f"Task {task_id} failed: {task_result.info}")
            response['message'] = "Task failed."
            response['error'] = "Backtest execution failed. See server logs for details."
            from app.config import settings as _settings
            if _settings.DEBUG:
                info = task_result.info
                if isinstance(info, dict) and info.get("error"):
                    response['error_detail'] = info["error"]
                elif isinstance(info, Exception):
                    response['error_detail'] = str(info)[:400]
                elif info:
                    response['error_detail'] = str(info)[:400]
        else:  # RETRY, REVOKED, ...
            response['message'] = f"Task state: {state}"

        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to read status for task {task_id}")
        raise HTTPException(status_code=500, detail="Failed to read task status.")


# ==========================================
# 3. قائمة الباك-تستات
# ==========================================

@router.get("/list")
async def list_backtests(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """جلب قائمة عمليات الباك-تست المخزنة (الأحدث أولاً)"""
    try:
        query = (
            select(BacktestRun)
            .order_by(BacktestRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        backtests = result.scalars().all()

        backtests_list = [
            {
                "id": bt.id,
                "name": bt.name,
                "created_at": bt.created_at.isoformat() if bt.created_at else None,
                "summary_stats": {
                    "total_pnl_percent": bt.total_pnl_percent,
                    "win_rate": bt.win_rate,
                    "total_trades": bt.total_trades,
                    "timeframe": bt.timeframe,
                    "symbol": bt.symbol,
                },
            }
            for bt in backtests
        ]

        return {
            "success": True,
            "count": len(backtests_list),
            "data": backtests_list,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error listing backtests")
        raise HTTPException(status_code=500, detail="Failed to list backtests.")


# ==========================================
# 4. تفاصيل باك-تست محدد
# ==========================================

@router.get("/get/{backtest_id}")
async def get_backtest_details(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
):
    """جلب تفاصيل باك-تست محدد مع بيانات الشارت بالكامل (من قاعدة البيانات)
    ✅ الجولة 9: الكاش — البيانات ثابتة فلا إعادة حساب بعد أول طلب."""
    try:
        cached = _bt_cache_get(f"{backtest_id}|get")
        if cached is not None:
            return cached

        backtest = await _get_backtest_row(db, backtest_id)

        chart_data = dict(backtest.chart_data) if backtest.chart_data else {}

        # تسطيح المؤشرات المتداخلة داخل كل شمعة (ind_ prefix)
        if isinstance(chart_data.get("visual_candles"), list):
            processed_candles = []
            for candle in chart_data["visual_candles"]:
                if not isinstance(candle, dict):
                    continue
                formatted_candle = dict(candle)
                indicators_data = formatted_candle.pop("indicators", {}) or {}
                flat_indicators = flatten_dict(indicators_data) if isinstance(indicators_data, dict) else {}
                for key, value in flat_indicators.items():
                    formatted_candle[f"ind_{key}"] = value
                processed_candles.append(formatted_candle)
            chart_data["visual_candles"] = processed_candles

        payload = {
            "success": True,
            "backtest_id": backtest.id,
            "name": backtest.name,
            "created_at": backtest.created_at.isoformat() if backtest.created_at else None,
            "summary": backtest.summary,
            "chart_data": chart_data,
            "config": backtest.full_config,
        }
        _bt_cache_put(f"{backtest_id}|get", payload)
        return payload
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Error getting backtest details for {backtest_id}")
        raise HTTPException(status_code=500, detail="Failed to get backtest details.")


# ==========================================
# 5. بيانات الرسم البياني (من عمود chart_data في ORM)
# ==========================================

@router.get("/{backtest_id}/chart-data")
async def get_chart_data(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
    start_index: int = Query(None, ge=0),
    limit: int = Query(None, ge=1),
    include_indicators: Optional[List[str]] = Query(None),
    # ✅ الجولة 10: مؤشرات البنية — overlays=zigzag,fib,trendline (اختياري)
    overlays: Optional[str] = Query(None, description="zigzag,fib,trendline — يضيف حقل overlays للاستجابة"),
    zz_length: int = Query(100, ge=2, le=2000),
    fib_depth: int = Query(10, ge=1, le=500),
    fib_dev: float = Query(5.0, ge=0.0, le=100.0),
    fib_ret: float = Query(0.618, ge=-10.0, le=10.0),
    tl_period: int = Query(10, ge=2, le=500),
    tl_pairs: int = Query(1, ge=1, le=250),
):
    """
    جلب بيانات الرسم البياني من BacktestRun.chart_data (JSON column).

    الاستجابة: {metadata, equity_curve, drawdown_curve, visual_candles, trade_points}
    - equity_curve/drawdown_curve: من chart_data إن وُجدت، وإلا تُشتق من
      account_balance في الشموع، وإلا None (بدون انهيار).
    - 404 أنيق عندما لا توجد بيانات رسم على الإطلاق.

    ✅ الجولة 9:
    - كاش الأساس المعالج لكل backtest_id — كل طلب لاحق تقطيع خفيف (أداء ثابت).
    - `include_indicators=true` (قيمة منطقية حرفية) تعني **تضمين كل المؤشرات**
      بدل تفسيرها كاسم مؤشر اسمه "true" — هذا كان يُسقط حقول ind_* بالخطأ.
    - `include_indicators=true` يعمل الآن مع limit معاً (حقل ind_* لا يُسقط).
    """
    try:
        # ---- تطبيع معامل المؤشرات (قبل الكاش — الرموز المنطقية ليست أسماء) ----
        inc_norm: Optional[List[str]]
        if isinstance(include_indicators, (list, tuple, set)) and include_indicators:
            flags = {str(x).strip().lower() for x in include_indicators}
            if flags & {"true", "1", "yes", "all", "full"}:
                inc_norm = None          # "true" → كل المؤشرات
            elif flags & {"false", "0", "no", "none"}:
                inc_norm = []            # "false" → بلا مؤشرات
            else:
                inc_norm = [str(x) for x in include_indicators]
        else:
            inc_norm = None if not include_indicators else [str(x) for x in include_indicators]

        # ---- الأساس المعالج (يُبنى مرة واحدة لكل باك-تست) ----
        cache_key = f"{backtest_id}|chart"
        base = _bt_cache_get(cache_key)
        was_cached = base is not None
        if base is None:
            backtest = await _get_backtest_row(db, backtest_id)

            chart = backtest.chart_data if isinstance(backtest.chart_data, dict) else {}
            summary = backtest.summary if isinstance(backtest.summary, dict) else {}
            full_config = backtest.full_config if isinstance(backtest.full_config, dict) else {}

            raw_candles = chart.get("visual_candles") or []
            raw_trade_points = chart.get("trade_points") or []

            if not raw_candles and not raw_trade_points:
                raise HTTPException(status_code=404, detail="No chart data available for this backtest")

            # فهرس زمني سريع لربط نقاط التداول بمواقعها
            timestamp_index = {
                c.get("timestamp"): idx for idx, c in enumerate(raw_candles) if isinstance(c, dict)
            }

            # شموع مسطحة بكل مفاتيح ind_* (الشكل الشامل — التقطيع والفلترة لاحقاً)
            flat_candles: List[Dict[str, Any]] = []
            for candle in raw_candles:
                if not isinstance(candle, dict):
                    continue
                formatted_candle = dict(candle)
                indicators_data = formatted_candle.pop("indicators", {}) or {}
                flat = flatten_dict(indicators_data) if isinstance(indicators_data, dict) else {}
                for ind_name, ind_value in flat.items():
                    formatted_candle[f"ind_{ind_name}"] = ind_value
                flat_candles.append(formatted_candle)

            # نقاط التداول (مع index داخل الشموع)
            trade_points: List[Dict[str, Any]] = []
            for tp in raw_trade_points:
                if not isinstance(tp, dict):
                    continue
                marker = dict(tp)
                marker["index"] = timestamp_index.get(tp.get("timestamp"))
                trade_points.append(marker)

            # منحنى رأس المال (من chart_data أو مشتق من الشموع)
            initial_capital = summary.get("initial_capital", full_config.get("initial_capital"))
            equity_curve = chart.get("equity_curve")
            if not equity_curve:
                derived = [c.get("account_balance") for c in raw_candles if isinstance(c, dict)]
                derived = [float(v) for v in derived if isinstance(v, (int, float))]
                if derived:
                    equity_curve = (
                        ([float(initial_capital)] if isinstance(initial_capital, (int, float)) else [])
                        + derived
                    )
                else:
                    equity_curve = None

            # منحنى الانخفاض (من chart_data أو مشتق)
            drawdown_curve = chart.get("drawdown_curve")
            if not drawdown_curve and equity_curve:
                drawdown_curve = _compute_drawdown_curve(equity_curve)

            # Metadata
            timestamps = [c.get("timestamp") for c in raw_candles if isinstance(c, dict) and c.get("timestamp")]
            metadata = {
                "backtest_id": backtest.id,
                "name": backtest.name or summary.get("name", "Backtest"),
                "symbol": backtest.symbol or (full_config.get("symbols") or [None])[0],
                "timeframe": backtest.timeframe or summary.get("timeframe"),
                "initial_capital": initial_capital,
                "final_capital": summary.get("final_capital"),
                "total_pnl": summary.get("total_pnl"),
                "total_pnl_percent": backtest.total_pnl_percent if backtest.total_pnl_percent is not None else summary.get("total_pnl_percent"),
                "total_trades": backtest.total_trades if backtest.total_trades is not None else summary.get("total_trades"),
                "win_rate": backtest.win_rate if backtest.win_rate is not None else summary.get("win_rate"),
                "max_drawdown_percent": summary.get("max_drawdown_percent"),
                "sharpe_ratio": summary.get("sharpe_ratio"),
                "start_date": timestamps[0] if timestamps else None,
                "end_date": timestamps[-1] if timestamps else None,
                "created_at": backtest.created_at.isoformat() if backtest.created_at else None,
            }

            # أسماء المؤشرات المتاحة (من أول شمعة كاملة)
            available_indicators: List[str] = []
            for candle in raw_candles:
                if isinstance(candle, dict) and isinstance(candle.get("indicators"), dict):
                    available_indicators = sorted(flatten_dict(candle["indicators"]).keys())
                    break

            base = {
                "raw_len": len(raw_candles),
                "flat_candles": flat_candles,
                "trade_points": trade_points,
                "equity_curve": equity_curve,
                "drawdown_curve": drawdown_curve,
                "metadata": metadata,
                "available_indicators": available_indicators,
            }
            _bt_cache_put(cache_key, base)

        # ---- تجهيز الاستجابة من الأساس (تقطيع/نسخ خفيف فقط) ----
        flat_candles = base["flat_candles"]
        trade_points = base["trade_points"]
        metadata = base["metadata"]
        available_indicators = base["available_indicators"]
        raw_len = base["raw_len"]

        offset = start_index or 0
        if start_index is not None or limit is not None:
            window = flat_candles[offset: offset + limit] if limit else flat_candles[offset:]
        else:
            window = flat_candles

        if inc_norm is None:
            formatted_candles = window                      # الشكل الشامل كما هو
        else:
            wanted = {str(n) for n in inc_norm}
            formatted_candles = [
                {k: v for k, v in c.items() if not k.startswith("ind_") or k[4:] in wanted}
                for c in window
            ]

        visible_range_start = offset
        visible_range_end = visible_range_start + len(formatted_candles)

        # ✅ الجولة 10: مؤشرات البنية — تُحسب مرة واحدة على كامل الشموع (لا النافذة)
        # وتُخزن بكاش مستقل بمعاملاتها — الطلبات المتتالية خلالات فورية.
        overlays_payload: Optional[Dict[str, Any]] = None
        if overlays and str(overlays).strip():
            wanted_ovl = [t.strip().lower() for t in str(overlays).split(",") if t.strip()]
            if not wanted_ovl or "all" in wanted_ovl or "*" in wanted_ovl:
                wanted_ovl = list(_OVL_TYPES)
            unknown = [t for t in wanted_ovl if t not in _OVL_TYPES]
            if unknown:
                raise HTTPException(status_code=400, detail=f"أنواع overlays غير معروفة: {unknown}. المسموح: {list(_OVL_TYPES)}")
            ovl_params: Dict[str, Dict[str, Any]] = {
                "zigzag": {"length": zz_length},
                "fib": {"depth": fib_depth, "dev_threshold": fib_dev, "retracement": fib_ret},
                "trendline": {"period": tl_period, "max_pairs": tl_pairs},
            }
            ovl_key_src = json.dumps([wanted_ovl, ovl_params, base["raw_len"]], sort_keys=True, default=str)
            ovl_key = f"{backtest_id}|ovl|{hashlib.md5(ovl_key_src.encode()).hexdigest()}"
            overlays_payload = _bt_cache_get(ovl_key)
            ovl_cached = overlays_payload is not None
            if overlays_payload is None:
                ovl_candles = [
                    {"time": c.get("timestamp"), "open": c.get("open"), "high": c.get("high"),
                     "low": c.get("low"), "close": c.get("close")}
                    for c in flat_candles if isinstance(c, dict)
                ]
                ovl_result = _compute_overlays(ovl_candles, types=wanted_ovl, params=ovl_params)
                overlays_payload = {
                    "types": wanted_ovl,
                    "bars": ovl_result["bars"],
                    "time_from": ovl_result["time_from"],
                    "time_to": ovl_result["time_to"],
                    "overlays": ovl_result["overlays"],
                }
                _bt_cache_put(ovl_key, overlays_payload)
            overlays_payload = dict(overlays_payload)
            overlays_payload["cache"] = "hit" if ovl_cached else "built"

        return {
            "backtest_id": metadata["backtest_id"],
            "metadata": metadata,
            "equity_curve": base["equity_curve"],
            "drawdown_curve": base["drawdown_curve"],
            "visual_candles": formatted_candles,
            "trade_points": trade_points,
            **({"overlays": overlays_payload} if overlays_payload is not None else {}),
            "summary": {
                "total_candles": raw_len,
                "total_trades": len(trade_points),
                "win_rate": metadata["win_rate"],
                "total_pnl": metadata["total_pnl"],
                "total_pnl_percent": metadata["total_pnl_percent"],
                "max_drawdown_percent": metadata["max_drawdown_percent"],
                "sharpe_ratio": metadata["sharpe_ratio"],
                "available_indicators": available_indicators,
                "visible_range": f"{visible_range_start}-{visible_range_end}",
                "has_more_data": visible_range_end < raw_len,
                # ✅ الجولة 9: شفافية الكاش للتشخيص
                "cache": "hit" if was_cached else "built",
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Error building chart data for {backtest_id}")
        raise HTTPException(status_code=500, detail="Failed to build chart data.")


# ==========================================
# 6. حذف باك-تست
# ==========================================

@router.delete("/delete/{backtest_id}")
async def delete_backtest_run(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
):
    """حذف نتيجة باك-تست محددة من قاعدة البيانات"""
    try:
        backtest = await _get_backtest_row(db, backtest_id)
        name = backtest.name

        await db.delete(backtest)
        await db.commit()

        # ✅ الجولة 9: إبطال كاش الباك-تست المحذوف
        _bt_cache_drop(backtest_id)

        return {
            "success": True,
            "message": f"Backtest '{name}' deleted successfully",
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception(f"Error deleting backtest {backtest_id}")
        raise HTTPException(status_code=500, detail="Failed to delete backtest.")


# ==========================================
# 7. Walk-Forward Analysis (محرك لكل طلب)
# ==========================================

@router.post("/walk-forward")
async def run_walk_forward_analysis(
    config: BacktestConfig = Body(...),
    train_days: Optional[int] = Query(None, ge=1, description="طول نافذة التدريب بالأيام (افتراضي: 3× test_days)"),
    test_days: Optional[int] = Query(None, ge=1, description="طول نافذة الاختبار بالأيام (افتراضي: تقسيم الفترة)"),
    max_windows: int = Query(5, ge=1, le=MAX_WALK_FORWARD_WINDOWS, description="أقصى عدد نوافذ"),
):
    """
    تشغيل تحليل المشي للأمام (Anchored Walk-Forward).

    المحرك يُنشأ لكل طلب (بدون cache عالمي يحتفظ بجلسة DB قديمة) ويُغلق مع الجلسة.
    """
    try:
        async with async_session_maker() as db:
            engine = BacktestEngine(DataService(db))
            result = await engine.run_walk_forward_analysis(
                config,
                train_days=train_days,
                test_days=test_days,
                max_windows=max_windows,
            )

        overall = result.get("overall", {})
        return {
            "success": True,
            "method": result.get("method"),
            "train_days": result.get("train_days"),
            "test_days": result.get("test_days"),
            "windows": result.get("windows", []),
            "periods_summary": [
                {
                    "period": w.get("window"),
                    "start_date": w.get("test_start"),
                    "end_date": w.get("test_end"),
                    "pnl_percent": (w.get("out_of_sample") or {}).get("total_pnl_percent"),
                    "win_rate": (w.get("out_of_sample") or {}).get("win_rate"),
                }
                for w in result.get("windows", [])
            ],
            "overall": overall,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Walk-forward analysis failed")
        raise HTTPException(
            status_code=500,
            detail="Walk-forward analysis failed. Check server logs for details."
        )


# ==========================================
# 8. Monte Carlo Simulation (محرك لكل طلب)
# ==========================================

@router.post("/monte-carlo")
async def run_monte_carlo_simulation(
    config: BacktestConfig = Body(...),
    n_simulations: int = Query(100, ge=1, le=MAX_MONTE_CARLO_SIMULATIONS, description="عدد المحاكاات (1-500)"),
    random_seed: Optional[int] = Query(None, ge=0, description="بذرة عشوائية للتكرارية"),
):
    """
    تشغيل محاكاة مونت كارلو (bootstrap على صفقات باك-تست أساسي واحد).
    المحرك يُنشأ لكل طلب ويُغلق مع الجلسة.
    """
    try:
        async with async_session_maker() as db:
            engine = BacktestEngine(DataService(db))
            results = await engine.run_monte_carlo_simulation(
                config,
                n_simulations=n_simulations,
                random_seed=random_seed,
            )

        prob_of_profit = results.get("probability_of_profit")
        return {
            "success": True,
            "results": results,
            "interpretation": {
                "probability_of_profit": (
                    f"{prob_of_profit * 100:.1f}%" if isinstance(prob_of_profit, (int, float)) else None
                )
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Monte Carlo simulation failed")
        raise HTTPException(
            status_code=500,
            detail="Monte Carlo simulation failed. Check server logs for details."
        )


# ==========================================
# 9. المقاييس المتاحة
# ==========================================

@router.get("/metrics")
async def get_available_metrics():
    """الحصول على المقاييس المتاحة"""
    return {
        "return_metrics": ["total_pnl", "sharpe_ratio", "win_rate"],
        "risk_metrics": ["max_drawdown", "volatility"],
        "trade_metrics": ["total_trades", "avg_win", "avg_loss"],
    }
