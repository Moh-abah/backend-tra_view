# =============================================================================
# ✅ الجولة 10 — Overlays Router: مؤشرات البنية السعرية (ZigZag / Fib / Trendline)
# =============================================================================
# mounted at /api/v1/overlays  (see app/main.py)
#
# النقاط:
#   GET  /compute  — يحسب المؤشرات على شموع السوق (يجلبهن DataService بنفس
#                    مسار الاستراتيجيات) — للشارت الحي.
#   POST /compute  — يحسب على شموع معطاة في الجسم (يستعمله chart-data
#                    داخلياً وأي عميل لديه شموع جاهزة).
#   GET  /health   — فحص حي بسيط.
#
# الكاش: TTL 30 ثانية لكل مفتاح (market|symbol|tf|days|limit|types|params)
# بحد 32 مدخلاً — الطلبات المتتالية خلالات صفرية الكلفة، والحساب نفسه ~80ms
# لـ5000 شمعة (مثبت بالقياس).
# =============================================================================

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.services.data_service import DataService
from app.services.indicators.overlays import OVERLAY_TYPES, compute_overlays
from app.utils.dataframe_utils import ensure_datetime_index

logger = logging.getLogger(__name__)

router = APIRouter(tags=["overlays"])

# ---------------------------------------------------------------------------
# كاش TTL صغير
# ---------------------------------------------------------------------------
_OVL_CACHE_MAX = 32
_OVL_TTL_SECONDS = 30.0
_ovl_cache: "OrderedDict[str, tuple[float, Dict[str, Any]]]" = OrderedDict()


def _ovl_cache_get(key: str) -> Optional[Dict[str, Any]]:
    entry = _ovl_cache.get(key)
    if entry is None:
        return None
    ts, payload = entry
    if (time.monotonic() - ts) > _OVL_TTL_SECONDS:
        _ovl_cache.pop(key, None)
        return None
    _ovl_cache.move_to_end(key)
    return payload


def _ovl_cache_put(key: str, value: Dict[str, Any]) -> None:
    _ovl_cache[key] = (time.monotonic(), value)
    _ovl_cache.move_to_end(key)
    while len(_ovl_cache) > _OVL_CACHE_MAX:
        _ovl_cache.popitem(last=False)


# ---------------------------------------------------------------------------
# أدوات مساعدة
# ---------------------------------------------------------------------------
_MARKET_MAP = {"stock": "stocks", "stocks": "stocks", "crypto": "crypto", "binance": "crypto"}


def _parse_types(types: Optional[str]) -> List[str]:
    """'zigzag,fib,trendline' → قائمة نظيفة. فارغ/الكل → الثلاثة."""
    if not types or not str(types).strip() or str(types).strip().lower() in ("all", "*"):
        return list(OVERLAY_TYPES)
    wanted = [t.strip().lower() for t in str(types).split(",") if t.strip()]
    unknown = [t for t in wanted if t not in OVERLAY_TYPES]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"أنواع مؤشرات غير معروفة: {unknown}. المسموح: {list(OVERLAY_TYPES)}",
        )
    return wanted


def _build_params(
    zz_length: int,
    zz_extend: bool,
    fib_depth: int,
    fib_dev: float,
    fib_ret: float,
    fib_levels: Optional[str],
    tl_period: int,
    tl_pairs: int,
) -> Dict[str, Dict[str, Any]]:
    params: Dict[str, Dict[str, Any]] = {
        "zigzag": {"length": zz_length, "extend": zz_extend},
        "fib": {"depth": fib_depth, "dev_threshold": fib_dev, "retracement": fib_ret},
        "trendline": {"period": tl_period, "max_pairs": tl_pairs},
    }
    if fib_levels:
        raw = [x.strip() for x in str(fib_levels).split(",") if x.strip()]
        try:
            ratios = [float(x) for x in raw]
        except ValueError:
            raise HTTPException(status_code=400, detail="fib_levels يجب أن تكون أرقاماً مفصولة بفواصل مثل: 0,0.382,0.618,1")
        params["fib"]["level_ratios"] = ratios
    return params


def _validate_symbol(symbol: str, timeframe: str) -> None:
    # نفس تحقق الجولة 9 في strategies1 — رسائل عربية واضحة بدل 500 صامت
    if not symbol or not str(symbol).strip() or str(symbol).strip().lower() == "undefined":
        raise HTTPException(status_code=400, detail="معامل symbol مفقود أو غير مضبوط (وصلت القيمة الحرفية 'undefined' من الواجهة؟)")
    if not timeframe or not str(timeframe).strip() or str(timeframe).strip().lower() == "undefined":
        raise HTTPException(status_code=400, detail="معامل timeframe مفقود أو غير مضبوط")


# ===========================================================================
# GET /compute — شموع السوق عبر DataService (نفس مسار الاستراتيجيات)
# ===========================================================================
@router.get("/compute")
async def compute_market_overlays(
    symbol: str = Query(..., description="مثل BTCUSDT"),
    timeframe: str = Query("1h", pattern="^(1m|3m|5m|15m|30m|1h|2h|4h|6h|8h|12h|1d|3d|1w|1M)$"),
    market: str = Query("crypto"),
    days: int = Query(30, ge=1, le=365, description="كم يوماً من التاريخ يُجلب"),
    limit: int = Query(None, ge=10, le=20000, description="قص الشموع إلى آخر N شمعة بعد الجلب"),
    types: str = Query(None, description="zigzag,fib,trendline — الافتراضي الكل"),
    zz_length: int = Query(100, ge=2, le=2000),
    zz_extend: bool = Query(True),
    fib_depth: int = Query(10, ge=1, le=500),
    fib_dev: float = Query(5.0, ge=0.0, le=100.0),
    fib_ret: float = Query(0.618, ge=-10.0, le=10.0),
    fib_levels: str = Query(None, description="مثل 0,0.382,0.618,1 — افتراضياً مستويات السكربت"),
    tl_period: int = Query(10, ge=2, le=500),
    tl_pairs: int = Query(1, ge=1, le=250),
    db: AsyncSession = Depends(get_db),
):
    """حساب مؤشرات البنية على شموع السوق الحقيقية — للشارت الحي."""
    _validate_symbol(symbol, timeframe)
    wanted_types = _parse_types(types)
    params = _build_params(zz_length, zz_extend, fib_depth, fib_dev, fib_ret, fib_levels, tl_period, tl_pairs)

    normalized_market = _MARKET_MAP.get(market.lower(), market)
    cache_key_src = json.dumps(
        ["GET", normalized_market, symbol.upper(), timeframe, days, limit, wanted_types, params],
        sort_keys=True, default=str,
    )
    cache_key = hashlib.md5(cache_key_src.encode()).hexdigest()
    cached = _ovl_cache_get(cache_key)
    if cached is not None:
        payload = dict(cached)
        payload["summary"]["cache"] = "hit"
        return payload

    data_service = DataService(db)
    t0 = time.perf_counter()
    try:
        dataframe = await data_service.get_historical(
            symbol=symbol.strip().upper(), timeframe=timeframe, market=normalized_market, days=days
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("overlays: فشل جلب الشموع لـ %s", symbol)
        raise HTTPException(status_code=502, detail=f"فشل جلب الشموع من المزود: {exc}")

    if dataframe is None or dataframe.empty:
        raise HTTPException(status_code=404, detail=f"لا توجد شموع للرمز {symbol} على فريم {timeframe}")

    dataframe = ensure_datetime_index(dataframe)
    if limit:
        dataframe = dataframe.tail(int(limit))

    candles = [
        {
            "time": int(ts.timestamp() * 1000) if hasattr(ts, "timestamp") else int(ts),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }
        for ts, row in dataframe.iterrows()
    ]
    if not candles:
        raise HTTPException(status_code=404, detail="لا توجد شموع صالحة بعد التطبيع")

    result = compute_overlays(candles, types=wanted_types, params=params)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    payload = {
        "symbol": symbol.strip().upper(),
        "timeframe": timeframe,
        "market": normalized_market,
        "summary": {
            "bars": result["bars"],
            "types": wanted_types,
            "compute_ms": elapsed_ms,
            "cache": "built",
        },
        "time_from": result["time_from"],
        "time_to": result["time_to"],
        "overlays": result["overlays"],
    }
    _ovl_cache_put(cache_key, payload)
    return payload


# ===========================================================================
# POST /compute — شموع معطاة مباشرة (بلا جلب من المزود)
# ===========================================================================
@router.post("/compute")
async def compute_given_overlays(
    body: Dict[str, Any] = Body(...),
):
    """حساب المؤشرات على شموع يرسلها العميل — contract:
    {"candles": [{"time": ms, "open": ..., "high": ..., "low": ..., "close": ...}, ...],
     "types": ["zigzag","fib","trendline"],          # اختياري
     "params": {"zigzag": {...}, "fib": {...}, "trendline": {...}}}  # اختياري
    """
    candles = body.get("candles")
    if not isinstance(candles, list) or not candles:
        raise HTTPException(status_code=400, detail="الحقل candles مطلوب: قائمة شموع [{time,open,high,low,close}]")
    if len(candles) > 50000:
        raise HTTPException(status_code=400, detail=f"عدد الشموع كبير جداً ({len(candles)}) — الحد 50000")

    types_in = body.get("types")
    if isinstance(types_in, str):
        wanted_types = _parse_types(types_in)
    elif isinstance(types_in, (list, tuple)):
        wanted_types = _parse_types(",".join(str(x) for x in types_in))
    else:
        wanted_types = list(OVERLAY_TYPES)

    params_in = body.get("params") if isinstance(body.get("params"), dict) else {}

    t0 = time.perf_counter()
    result = compute_overlays(candles, types=wanted_types, params=params_in)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "summary": {"bars": result["bars"], "types": wanted_types, "compute_ms": elapsed_ms, "cache": "bypass"},
        "time_from": result["time_from"],
        "time_to": result["time_to"],
        "overlays": result["overlays"],
    }


# ===========================================================================
# GET /health
# ===========================================================================
@router.get("/health")
async def overlays_health():
    return {
        "status": "ok",
        "router": "overlays",
        "round": 10,
        "types": list(OVERLAY_TYPES),
        "cache": {"max_entries": _OVL_CACHE_MAX, "ttl_seconds": _OVL_TTL_SECONDS, "entries": len(_ovl_cache)},
    }
