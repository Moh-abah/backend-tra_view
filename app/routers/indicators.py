"""Indicator endpoints: apply, pine transpile, signals and registry metadata.

Mounted at /api/v1/indicators (see app/main.py).
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.managers import chart_manager, indicator_id as compute_indicator_id
from app.database.session import get_db
from app.schemas.signals import SignalRequest
from app.services.data_service import DataService
from app.services.indicators import (
    IndicatorRegistry,
    IndicatorType,
    create_indicator_from_pine,
    get_available_indicators,
    transpile_pine_script,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["indicators"])


def _slice_indicators_payload(result: Dict[str, Any], limit: int) -> Dict[str, Any]:
    """✅ الجولة 4: قص آخر N قيمة من كل مصفوفات المؤشرات (ومن الشموع) — للجوال."""
    if not limit or limit <= 0 or not isinstance(result, dict):
        return result

    data = result.get("data")
    if isinstance(data, list) and len(data) > limit:
        result["data"] = data[-limit:]

    indicators = result.get("indicators")
    if isinstance(indicators, dict):
        trimmed: Dict[str, Any] = {}
        for name, res in indicators.items():
            if isinstance(res, dict):
                res = dict(res)
                values = res.get("values")
                if isinstance(values, dict):
                    values = dict(values)
                    for k in ("data", "index"):
                        arr = values.get(k)
                        if isinstance(arr, list) and len(arr) > limit:
                            values[k] = arr[-limit:]
                    res["values"] = values
                elif isinstance(values, list) and len(values) > limit:
                    res["values"] = values[-limit:]
                sig = res.get("signals")
                if isinstance(sig, dict):
                    sig = dict(sig)
                    for k in ("data", "index"):
                        arr = sig.get(k)
                        if isinstance(arr, list) and len(arr) > limit:
                            sig[k] = arr[-limit:]
                    res["signals"] = sig
                trimmed[name] = res
            else:
                trimmed[name] = res
        result["indicators"] = trimmed

    meta = result.get("metadata")
    if isinstance(meta, dict):
        meta = dict(meta)
        meta["limit_applied"] = limit
        result["metadata"] = meta
    return result


class IndicatorSpec(BaseModel):
    """One indicator configuration (flat dict, e.g. {"name": "rsi", "period": 14}).

    Extra keys (id/label/params/...) are preserved so the calculator receives
    the exact configuration shape clients already send.
    """

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., min_length=1, description="Registered indicator name, e.g. rsi, macd, bb")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/available",
    summary="قائمة المؤشرات الحية (54+) بالفئات — اكتشفها ديناميكياً",
)
async def list_available_indicators(
    category: Optional[str] = Query(None, description="Filter by category, e.g. momentum, trend, volatility"),
):
    """List all registered indicators with defaults and required columns."""
    try:
        category_enum = None
        if category:
            try:
                category_enum = IndicatorType(category)
            except ValueError:
                raise HTTPException(status_code=400, detail="Unknown indicator category")
        indicators = jsonable_encoder(get_available_indicators(category_enum))
        return {"count": len(indicators), "indicators": indicators}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list available indicators")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/apply",
    summary="حساب مؤشرات على بيانات رمز وإرجاع القيم جاهزة للرسم",
)
async def apply_indicators_to_data(
    symbol: str,
    timeframe: str,
    market: str = "crypto",
    indicators: List[IndicatorSpec] = Body(..., description="List of indicator configurations"),
    days: int = 30,
    limit: int = Query(0, ge=0, le=50000, description="✅ الجولة 4: أعِد آخر N قيمة فقط (0 = الكل)"),
    db: AsyncSession = Depends(get_db),
):
    """Apply indicators to market data and return the series alongside the candles.

    - **symbol**: stock or crypto symbol
    - **timeframe**: candle interval (1m, 5m, 1h, ...)
    - **market**: market type (crypto, stocks)
    - **body**: list of indicator configurations
    - **days**: historical lookback in days
    - **limit**: ✅ الجولة 4 — يعيد آخر N قيمة فقط (متوافق مع نافذة الشموع المعروضة؛ 0 = الكل)
    """
    indicators_config = [spec.model_dump(exclude_none=True) for spec in indicators]
    try:
        data_service = DataService(db)
        result = await data_service.get_data_with_indicators(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            indicators_config=indicators_config,
            days=days,
        )
        return _slice_indicators_payload(result, limit)
    except HTTPException:
        raise
    except ValueError:
        logger.warning("Indicator apply rejected for %s/%s (market=%s)", symbol, timeframe, market)
        raise HTTPException(status_code=400, detail="Invalid symbol, market or timeframe")
    except Exception:
        logger.exception("Failed to apply indicators for %s", symbol)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/pine/transpile")
async def transpile_pine_code(
    pine_code: str = Body(..., embed=True),
    execute: bool = False,
):
    """Transpile Pine Script code to Python.

    - **pine_code**: full Pine Script source
    - **execute**: optionally build the indicator class from the code
    """
    try:
        python_code = transpile_pine_script(pine_code)
    except Exception:
        logger.exception("Pine Script transpilation failed")
        raise HTTPException(status_code=400, detail="Could not transpile the provided Pine Script")

    result: Dict[str, Any] = {
        "success": True,
        "python_code": python_code,
        "message": "تم التحويل بنجاح",
    }

    if execute:
        try:
            indicator_class = create_indicator_from_pine(pine_code)
            result["indicator_created"] = True
            result["indicator_name"] = indicator_class.__name__
        except Exception:
            logger.warning("Indicator creation from Pine failed", exc_info=True)
            result["indicator_created"] = False
            result["error"] = "Could not build an indicator from the provided code"

    return result


@router.post("/signals")
async def get_trading_signals(request: SignalRequest, db: AsyncSession = Depends(get_db)):
    """Trading signals derived from indicator configurations.

    - **symbol**: stock or crypto symbol
    - **timeframe**: candle interval
    - **market**: market type
    - **indicators**: list of indicator configurations
    - **days**: historical lookback in days
    """
    try:
        data_service = DataService(db)
        signals = await data_service.get_trading_signals(
            symbol=request.symbol,
            timeframe=request.timeframe,
            market=request.market,
            indicators_config=request.indicators,
            days=request.days,
        )
        return signals
    except HTTPException:
        raise
    except ValueError:
        logger.warning("Signal request rejected for %s", request.symbol)
        raise HTTPException(status_code=400, detail="Invalid symbol, market or timeframe")
    except Exception:
        logger.exception("Failed to compute trading signals for %s", request.symbol)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# ✅ الجولة 4: REST fallback لإدارة المؤشرات (تعمل بدون WS) + إعادة المزامنة
# ---------------------------------------------------------------------------
class ManageIndicatorRequest(BaseModel):
    """طلب إدارة مؤشر عبر REST — يعمل حتى عند انقطاع WS."""
    symbol: str = Field(..., description="رمز التداول، مثل BTCUSDT أو AAPL")
    timeframe: str = Field("1m", description="الإطار الزمني")
    market: str = Field("crypto", description="crypto | stocks")
    indicator: Optional[Dict[str, Any]] = Field(
        None, description='تكوين المؤشر {"name": "rsi", "type": "momentum", "params": {...}}')
    indicator_id: Optional[str] = Field(None, description="معرف المؤشر (للحذف/التعديل)")
    params: Optional[Dict[str, Any]] = Field(None, description="معاملات جديدة (للتعديل)")


class _SavedIndicatorsStore:
    """الوصول لقاعدة المؤشرات المحفوظة (نفس chart_states.db المستخدمة في WS)."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            from app.websocket.chart_ws import ChartStateDB
            cls._instance = ChartStateDB("chart_states.db")
        return cls._instance


def _resolve_target_name(identifier: str, live_indicators: List[Dict], saved: List[Dict]) -> Optional[str]:
    """حلّ indicator_id أو الاسم إلى اسم المؤشر الفعلي."""
    for ind in list(live_indicators) + list(saved):
        if isinstance(ind, dict) and (
            str(ind.get("name")) == identifier or compute_indicator_id(ind) == identifier
        ):
            return str(ind.get("name"))
    return None


@router.post(
    "/manage/add",
    summary="✅ REST: إضافة مؤشر (مكافئ لـ WS add_indicator — يعمل عند انقطاع WS)",
)
async def rest_add_indicator(req: ManageIndicatorRequest, db: AsyncSession = Depends(get_db)):
    if not req.indicator or not req.indicator.get("name"):
        raise HTTPException(status_code=400, detail="indicator.name is required")
    ind = dict(req.indicator)
    ind.setdefault("type", "trend")
    ind.setdefault("params", {})

    key = chart_manager.get_chart_key(req.symbol, req.timeframe)
    chart = chart_manager.charts.get(key)
    if chart is None:
        chart = await chart_manager.get_or_create_chart(
            req.symbol, req.timeframe, market=req.market)

    success = await chart_manager.add_indicator(req.symbol, req.timeframe, ind)
    results = await chart_manager.calculate_full_indicators(req.symbol, req.timeframe)
    # حفظ دائم في القائمة العامة
    if chart is not None:
        await asyncio_get_loop_save(chart.indicators)

    ind_id = compute_indicator_id(ind)
    return {
        "success": bool(success or results),
        "indicator": ind.get("name"),
        "indicator_id": ind_id,
        "indicators_count": len(chart.indicators) if chart else 0,
        "values_available": bool(results),
        "note": "استخدم POST /api/v1/indicators/apply للحصول على القيم كاملة بدون WS",
    }


async def asyncio_get_loop_save(live_indicators: List[Dict]):
    """حفظ المؤشرات الحية إلى المخزن الدائم (بشكل آمن خارج event loop)."""
    import asyncio as _asyncio
    store = _SavedIndicatorsStore()
    await _asyncio.to_thread(store.save_global_indicators, list(live_indicators))


@router.post(
    "/manage/remove",
    summary="✅ REST: حذف مؤشر دائمًا (من الشارت الحي ومن المحفوظات)",
)
async def rest_remove_indicator(req: ManageIndicatorRequest):
    identifier = req.indicator_id or (req.indicator or {}).get("name")
    if not identifier:
        raise HTTPException(status_code=400, detail="indicator_id or indicator.name is required")
    identifier = str(identifier)
    store = _SavedIndicatorsStore()
    saved = await _load_saved(store)

    key = chart_manager.get_chart_key(req.symbol, req.timeframe)
    chart = chart_manager.charts.get(key)
    target = _resolve_target_name(
        identifier, chart.indicators if chart else [], saved)

    removed_live = False
    if chart is not None and target:
        removed_live = await chart_manager.remove_indicator(
            req.symbol, req.timeframe, target)

    kept, removed_saved = [], 0
    for ind in saved:
        if isinstance(ind, dict) and (
            str(ind.get("name")) == (target or identifier)
            or compute_indicator_id(ind) == identifier
        ):
            removed_saved += 1
        else:
            kept.append(ind)
    if removed_saved:
        import asyncio as _asyncio
        await _asyncio.to_thread(store.save_global_indicators, kept)

    if not removed_live and not removed_saved:
        raise HTTPException(status_code=404, detail=f"Indicator '{identifier}' not found")

    return {
        "success": True,
        "indicator": target or identifier,
        "indicator_id": identifier,
        "removed_from_live": removed_live,
        "removed_from_saved": removed_saved,
    }


async def _load_saved(store) -> List[Dict]:
    import asyncio as _asyncio
    return await _asyncio.to_thread(store.load_global_indicators) or []


@router.post(
    "/manage/update",
    summary="✅ REST: تعديل معاملات مؤشر موجود (بالاسم أو بالمعرف)",
)
async def rest_update_indicator(req: ManageIndicatorRequest):
    identifier = req.indicator_id or (req.indicator or {}).get("name")
    if not identifier or not req.params:
        raise HTTPException(status_code=400, detail="indicator_id/name and params are required")
    identifier = str(identifier)
    store = _SavedIndicatorsStore()
    saved = await _load_saved(store)
    key = chart_manager.get_chart_key(req.symbol, req.timeframe)
    chart = chart_manager.charts.get(key)
    target = _resolve_target_name(identifier, chart.indicators if chart else [], saved)
    if not target:
        raise HTTPException(status_code=404, detail=f"Indicator '{identifier}' not found")

    success = await chart_manager.update_indicator(req.symbol, req.timeframe, target, req.params)
    # تحديث المحفوظات بنفس التغيير
    for ind in saved:
        if isinstance(ind, dict) and str(ind.get("name")) == target:
            ind["params"] = req.params
    import asyncio as _asyncio
    await _asyncio.to_thread(store.save_global_indicators, saved)

    new_id = compute_indicator_id({"name": target, "params": req.params})
    return {
        "success": bool(success),
        "indicator": target,
        "indicator_id": new_id,
        "params": req.params,
    }


@router.get(
    "/values/{indicator_id}",
    summary="✅ إعادة مزامنة قيم مؤشر بعد انقطاع WS — من الذاكرة أو بإعادة حساب كامل",
)
async def get_indicator_values_resync(
    indicator_id: str,
    symbol: str = Query(..., description="رمز التداول"),
    timeframe: str = Query("1m", description="الإطار الزمني"),
    market: str = Query("crypto", description="crypto | stocks"),
    from_ms: Optional[int] = Query(None, description="بداية النطاق (epoch-ms)"),
    to_ms: Optional[int] = Query(None, description="نهاية النطاق (epoch-ms)"),
    limit: int = Query(5000, ge=1, le=50000, description="آخر N قيمة عند غياب from/to"),
    db: AsyncSession = Depends(get_db),
):
    """يعيد قيم المؤشر لملء الفجوات بعد reconnect طويل.

    1) إن كان الشارت حياً في الذاكرة → يعيد من نتائجه المخزنة فوراً.
    2) إن لا → يجلب الشموع ويحسب المؤشر من جديد (نفس شكل /apply).
    القيم تُقص إلى آخر `limit` قيمة (أو النطاق from/to عند تحديده)."""
    store = _SavedIndicatorsStore()
    saved = await _load_saved(store)
    key = chart_manager.get_chart_key(symbol, timeframe)
    chart = chart_manager.charts.get(key)

    # 1) من الشارت الحي
    if chart is not None:
        target = _resolve_target_name(indicator_id, chart.indicators, saved)
        if target:
            results = chart_manager.get_chart_indicators_results(symbol, timeframe) or \
                await chart_manager.calculate_full_indicators(symbol, timeframe)
            entry = results.get(target) or results.get(indicator_id)
            if entry:
                # ✅ الجولة 5: نتائج الذاكرة قائمة مجردة بلا طوابع زمنية — كان
                # from_ms/to_ms يتجاهلان بصمت والفرونت يتلقى قيماً بلا أزمنة.
                # نعيد الحساب على الشموع الحالية ثم نبني index من أزمنة الشموع
                # (محاذاة من النهاية) حتى يعمل النطاق والرصّ على الشموع مباشرة.
                try:
                    def _flat(v):
                        if isinstance(v, dict):
                            return list(v.get("data") or []), list(v.get("index") or [])
                        if isinstance(v, list):
                            return list(v), []
                        return [], []

                    data_arr, index_arr = _flat(entry.get("values") if isinstance(entry, dict) else entry)
                    if data_arr and not index_arr:
                        fresh = await chart_manager.calculate_full_indicators(symbol, timeframe)
                        fresh_entry = (fresh or {}).get(target) or (fresh or {}).get(indicator_id)
                        if fresh_entry:
                            entry = fresh_entry
                            data_arr, index_arr = _flat(
                                entry.get("values") if isinstance(entry, dict) else entry)
                        times = [int(c["time"]) for c in getattr(chart, "candles", []) or []
                                 if isinstance(c, dict) and c.get("time")]
                        if data_arr and len(times) >= len(data_arr):
                            entry = dict(entry) if isinstance(entry, dict) else {"values": entry}
                            entry["values"] = {"data": data_arr, "index": times[-len(data_arr):]}
                except Exception:
                    logger.warning("resync: failed to build time index for live results", exc_info=True)
                return _finalize_resync(target, indicator_id, entry, from_ms, to_ms, limit)

    # 2) إعادة حساب كاملة من بيانات السوق
    cfg = None
    for ind in saved:
        if isinstance(ind, dict) and (
            str(ind.get("name")) == indicator_id or compute_indicator_id(ind) == indicator_id
        ):
            cfg = {"name": ind.get("name"), "type": ind.get("type", "trend"),
                   "params": ind.get("params") or {}}
            break
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail=f"Indicator '{indicator_id}' not found in saved indicators — "
                   f"استخدم /indicators/manage/add أولاً أو مرّر الاسم كاملاً")

    data_service = DataService(db)
    result = await data_service.get_data_with_indicators(
        symbol=symbol, timeframe=timeframe, market=market,
        indicators_config=[cfg], days=30)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    entry = (result.get("indicators") or {}).get(cfg["name"])
    if not entry:
        raise HTTPException(status_code=404, detail="Indicator computed but returned no values")
    return _finalize_resync(cfg["name"], indicator_id, entry, from_ms, to_ms, limit)


def _finalize_resync(
    name: str, requested_id: str, entry: Dict[str, Any],
    from_ms: Optional[int], to_ms: Optional[int], limit: int,
) -> Dict[str, Any]:
    """قص قيم الـ resync حسب النطاق/الحد وتوحيد شكل الاستجابة."""
    entry = dict(entry) if isinstance(entry, dict) else {"values": entry}
    values = entry.get("values")
    data_arr, index_arr = [], []
    if isinstance(values, dict):
        data_arr = list(values.get("data") or [])
        index_arr = list(values.get("index") or [])
    elif isinstance(values, list):
        data_arr = list(values)

    def _to_ms(v: Any) -> Optional[int]:
        try:
            if isinstance(v, (int, float)):
                x = float(v)
                return int(x if x > 1e11 else x * 1000)
            s = str(v)
            from datetime import datetime as _dt
            return int(_dt.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:  # noqa: BLE001
            return None

    if from_ms is not None and index_arr:
        pairs = [(d, i) for d, i in zip(data_arr, index_arr)]
        ms_list = [(_to_ms(i), d, i) for d, i in pairs]
        sel = [(d, i) for (ms, d, i) in ms_list if ms is not None and ms >= from_ms
               and (to_ms is None or ms <= to_ms)]
        data_arr = [d for d, _ in sel]
        index_arr = [i for _, i in sel]
    elif limit and len(data_arr) > limit:
        data_arr = data_arr[-limit:]
        if index_arr:
            index_arr = index_arr[-limit:]

    return {
        "indicator": name,
        "indicator_id": requested_id,
        "values": {"data": data_arr, "index": index_arr},
        "count": len(data_arr),
        "range": {"from_ms": from_ms, "to_ms": to_ms, "limit": limit},
    }


@router.get(
    "/{indicator_name}/params",
    summary="الإعدادات الافتراضية لمؤشر (rsi, macd, bb...) — لبناء لوحة الإعدادات",
)
async def get_indicator_parameters(indicator_name: str):
    """Default parameters for a registered indicator (e.g. rsi, macd, bb)."""
    info = IndicatorRegistry.get_indicator_info(indicator_name)

    if not info:
        raise HTTPException(status_code=404, detail="Indicator not found")

    return {
        "name": indicator_name,
        "display_name": info.display_name,
        "description": info.description,
        "category": info.category.value,
        "default_params": info.default_params,
        "required_columns": info.required_columns,
    }
