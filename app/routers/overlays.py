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
#
# ✅ الجولة 12 — POST /compute يقبل أيضاً صيغة الواجهة الحرفية
#    {"symbol","timeframe","days","overlays"} بلا شموع فيُجلب من المزود،
#    ويقبل "overlays" كمرادف لـ "types".
# ✅ الجولة 13 (بند 3-ب) — رفع المستويات الفعلية + out_of_range إلى summary.
# ✅ الجولة 19 — معاملات زقزاق TV الكلاسيكي لرسم zzfib على الشارت الحي
#    (zz_mode/zz_depth/zz_deviation/zz_backstep) مطابقة للبريسِت الحي ZLF.
# ✅ الجولة 28 — تمرير الحجم (volume) مع الشموع في كل مسارات جلب الشموع
#    (GET /compute + POST /compute بصيغة الواجهة): بدون الحجم لا يُبنى المرجع R
#    ولا تُصنَّف حالات S1/S2/S3 في zzfib / zzfib_e2e — هذا كان الجذر المُثبت
#    لعدم ظهور إشارات E2E الحية على الشارت الحي. NaN/غياب العمود → None بأمان.
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


def _volume_series_from_dataframe(dataframe) -> List[Any]:
    """✅ ROUND28 — استخراج عمود الحجم من الداتافريم بأمان (لأجل محركات السيولة).

    الخلفية (الجذر المُثبت): GET /compute كان يبني شموع {time,open,high,low,close}
    **بدون volume** — فيتعذّر على zzfib/zzfib_e2e بناء المرجع R (يشترط حجم الشموع)
    فيعود ref=null وsignals=[] على الشارت الحي — بينما الباك تست سليم لأن مساره
    يمرر الحجم. هذه الدالة تعيد قائمة طولها = عدد الصفوف، كل عنصر float أو None،
    بأي من الأسماء الشائعة (volume/Volume/vol/Vol/v) وبلا استثناءات عند غياب العمود.
    """
    try:
        cols = {str(c).lower(): c for c in dataframe.columns}
    except Exception:
        return [None] * len(dataframe)
    vcol = cols.get("volume") or cols.get("vol") or cols.get("v")
    if vcol is None:
        return [None] * len(dataframe)
    out: List[Any] = []
    try:
        import math
        for v in dataframe[vcol].tolist():
            try:
                fv = float(v)
                out.append(None if (fv is None or math.isnan(fv) or math.isinf(fv)) else fv)
            except (TypeError, ValueError):
                out.append(None)
    except Exception:
        return [None] * len(dataframe)
    return out


def _parse_types(types: Optional[str]) -> List[str]:
    """'zigzag,fib,trendline' → قائمة نظيفة. فارغ/الكل → الثلاثة."""
    # ✅ ROUND29 — لف دفاعي str() (نفس نسخة الاستعادة المرجعية)
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
    zz_mode: str = "tradingview",
    zz_depth: int = 12,
    zz_deviation: float = 20.0,
    zz_backstep: int = 3,
    # ✅ ROUND31 — نافذة مرجع السيولة R: كانت تسقط على افتراض الخدمة (20)
    # بينما محرك البث الحي والبريسِت يعملان 240 منذ j21-v2 — فكان مرجع R
    # في طبقة الرسم مختلفاً عن مرجع محرك القرار (تشخيص ROUND31 الجذر 2).
    zz_liq_lookback: int = 240,
) -> Dict[str, Dict[str, Any]]:
    params: Dict[str, Dict[str, Any]] = {
        "zigzag": {"length": zz_length, "extend": zz_extend},
        "fib": {"depth": fib_depth, "dev_threshold": fib_dev, "retracement": fib_ret},
        "trendline": {"period": tl_period, "max_pairs": tl_pairs},
        # ✅ ROUND19: رسم zzfib على الشارت الحي بوضع زقزاق TV الكلاسيكي —
        # نفس معاملات البريسِت الحي (ZLF) حتى يطابق الرسم المرسوم الإشارات
        # والأطراف المرسومة على TradingView (طلب صاحب القرار).
        # ✅ ROUND31: إضافة liq_lookback=240 (البطل j21-v2) لاتساق مرجع R.
        "zzfib": {"mode": zz_mode, "depth": zz_depth,
                  "deviation": zz_deviation, "backstep": zz_backstep,
                  "liq_lookback": max(1, int(zz_liq_lookback))},
    }
    if fib_levels:
        raw = [x.strip() for x in str(fib_levels).split(",") if x.strip()]
        try:
            ratios = [float(x) for x in raw]
        except ValueError:
            raise HTTPException(status_code=400, detail="fib_levels يجب أن تكون أرقاماً مفصولة بفواصل مثل: 0,0.382,0.618,1")
        params["fib"]["level_ratios"] = ratios
    return params


def _apply_zzfib_defaults(params: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    """✅ ROUND31 — حقن افتراضيات البطل لـ zzfib في المفاتيح الغائبة فقط.

    تُطبّق على مسارات POST (حمولات الواجهة) حتى لا تسقط أي نداء zzfib على
    افتراضات الخدمة (luxalgo + liq_lookback=20) المختلفة عن محرك البث الحي
    (tradingview + liq_lookback=240). المفاتيح الصريحة من العميل تفوز دائماً.
    zzfib_e2e خارج هذا كلياً (luxalgo مواصفته التعاقدية).
    """
    p = dict(params or {})
    zf = dict(p.get("zzfib") or {})
    zf.setdefault("mode", "tradingview")
    zf.setdefault("depth", 12)
    zf.setdefault("deviation", 20.0)
    zf.setdefault("backstep", 3)
    zf.setdefault("liq_lookback", 240)
    p["zzfib"] = zf
    return p


def _validate_symbol(symbol: str, timeframe: str) -> None:
    # نفس تحقق الجولة 9 في strategies1 — رسائل عربية واضحة بدل 500 صامت
    if not symbol or not str(symbol).strip() or str(symbol).strip().lower() == "undefined":
        raise HTTPException(status_code=400, detail="معامل symbol مفقود أو غير مضبوط (وصلت القيمة الحرفية 'undefined' من الواجهة؟)")
    if not timeframe or not str(timeframe).strip() or str(timeframe).strip().lower() == "undefined":
        raise HTTPException(status_code=400, detail="معامل timeframe مفقود أو غير مضبوط")


def _overlay_levels_summary(result: Dict[str, Any], wanted_types: List[str]) -> Dict[str, Any]:
    """✅ الجولة 13 (بند 3-ب): رفع المستويات الفعلية المستخدمة + out_of_range
    إلى summary ليتحقق الواجهة آلياً (تحصين — ليس عيباً)."""
    extra: Dict[str, Any] = {}
    ovl = result.get("overlays") if isinstance(result, dict) else None
    if not isinstance(ovl, dict):
        return extra
    if "zzfib" in wanted_types and isinstance(ovl.get("zzfib"), dict):
        zzf = ovl["zzfib"]
        extra["zzfib_levels"] = (zzf.get("params") or {}).get("levels")
        extra["zzfib_out_of_range"] = zzf.get("out_of_range")
    if "fib" in wanted_types and isinstance(ovl.get("fib"), dict):
        fb = ovl["fib"]
        extra["fib_levels"] = fb.get("levels") if fb.get("levels") is not None else (fb.get("current") or {}).get("levels")
        extra["fib_out_of_range"] = fb.get("out_of_range")
    return extra


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
    # ✅ ROUND19 — معاملات زقزاق TV الكلاسيكي لرسم zzfib (الافتراضي مطابق للبريسِت الحي)
    zz_mode: str = Query("tradingview", pattern="^(tradingview|luxalgo)$"),
    zz_depth: int = Query(12, ge=2, le=500),
    zz_deviation: float = Query(20.0, ge=0.0, le=1000.0),
    zz_backstep: int = Query(3, ge=1, le=100),
    # ✅ ROUND31 — نافذة مرجع السيولة R (الافتراضي = قالب البطل j21-v2 = 240)
    zz_liq_lookback: int = Query(240, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """حساب مؤشرات البنية على شموع السوق الحقيقية — للشارت الحي."""
    _validate_symbol(symbol, timeframe)
    wanted_types = _parse_types(types)
    params = _build_params(zz_length, zz_extend, fib_depth, fib_dev, fib_ret, fib_levels,
                           tl_period, tl_pairs, zz_mode, zz_depth, zz_deviation, zz_backstep,
                           zz_liq_lookback)
    # ✅ ROUND31 — تحصين إضافي: إن طلب العميل params=[] عبر صيغة أخرى فلا سقوط
    # على افتراضات الخدمة (idempotent — المفاتيح الموجودة لا تُمس)
    params = _apply_zzfib_defaults(params)

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

    # ✅ ROUND28 — الحجم يجب أن يمر مع الشموع: بدونها لا يُبنى المرجع R ولا
    # تُصنّف حالات S1/S2/S3 في zzfib / zzfib_e2e (الجذر المُثبت لعدم ظهور
    # إشارات E2E الحية على الشارت الحي). NaN/غياب العمود → None بأمان.
    _vols = _volume_series_from_dataframe(dataframe)

    candles = [
        {
            "time": int(ts.timestamp() * 1000) if hasattr(ts, "timestamp") else int(ts),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            # ✅ ROUND28 — تمرير الحجم (None بأمان إن غاب)
            "volume": _vols[_i] if _i < len(_vols) else None,
        }
        for _i, (ts, row) in enumerate(dataframe.iterrows())
    ]
    if not candles:
        raise HTTPException(status_code=404, detail="لا توجد شموع صالحة بعد التطبيع")

    result = compute_overlays(candles, types=wanted_types, params=params)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    # ✅ الجولة 13 (بند 3-ب): رفع المستويات الفعلية المستخدمة + out_of_range
    # إلى الملخص ليتحقق الواجهة آلياً دون تنقيب جسم الاستجابة.
    _summary_extra = _overlay_levels_summary(result, wanted_types)

    payload = {
        "symbol": symbol.strip().upper(),
        "timeframe": timeframe,
        "market": normalized_market,
        "summary": {
            "bars": result["bars"],
            "types": wanted_types,
            "compute_ms": elapsed_ms,
            "cache": "built",
            # ✅ ROUND28 — علم تشخيصي: هل وصل الحجم لمحركات السيولة فعلاً؟
            "volume_available": any(v is not None for v in _vols),
            **_summary_extra,
        },
        "time_from": result["time_from"],
        "time_to": result["time_to"],
        "overlays": result["overlays"],
    }
    _ovl_cache_put(cache_key, payload)
    return payload


# ===========================================================================
# POST /compute — شموع معطاة مباشرة (بلا جلب من المزود)
# ✅ الجولة 12: يقبل أيضاً صيغة الواجهة الحرفية —
#    {"symbol":"BTCUSDT","timeframe":"1h","days":180,"overlays":["fib"]}
#    (بدون candles) فيُجلب الشموع من المزود نفسه مثل GET، ويقبل "overlays"
#    كمرادف لـ "types" — لا مزيد من 400 "الحقل candles مطلوب".
# ===========================================================================
@router.post("/compute")
async def compute_given_overlays(
    body: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """حساب المؤشرات على شموع يرسلها العميل — contract:
    {"candles": [{"time": ms, "open": ..., "high": ..., "low": ..., "close": ...}, ...],
     "types": ["zigzag","fib","trendline"],          # اختياري (أو "overlays" كمرادف)
     "params": {"zigzag": {...}, "fib": {...}, "trendline": {...}}}  # اختياري

    ✅ الجولة 12 — صيغة الواجهة البديلة (بلا شموع):
    {"symbol":"BTCUSDT","timeframe":"1h","market":"crypto","days":180,
     "overlays":["fib"], "limit": 2000}
    """
    candles = body.get("candles")
    if not isinstance(candles, list) or not candles:
        # ✅ الجولة 12: لا شموع؟ جرّب صيغة الواجهة (symbol + overlays)
        symbol = body.get("symbol")
        if symbol and str(symbol).strip() and str(symbol).strip().lower() != "undefined":
            timeframe = body.get("timeframe") or "1h"
            market = body.get("market") or "crypto"
            days = int(body.get("days") or 30)
            limit = body.get("limit")
            types_in_alt = body.get("types") if body.get("types") is not None else body.get("overlays")
            if isinstance(types_in_alt, str):
                wanted_types_alt = _parse_types(types_in_alt)
            elif isinstance(types_in_alt, (list, tuple)):
                wanted_types_alt = _parse_types(",".join(str(x) for x in types_in_alt))
            else:
                wanted_types_alt = list(OVERLAY_TYPES)
            params_alt = body.get("params") if isinstance(body.get("params"), dict) else {}
            # ✅ ROUND31 — افتراضيات البطل لـ zzfib في صيغة الواجهة أيضاً
            params_alt = _apply_zzfib_defaults(params_alt)

            _validate_symbol(str(symbol), str(timeframe))
            normalized_market_alt = _MARKET_MAP.get(str(market).lower(), str(market))
            data_service = DataService(db)
            t0_alt = time.perf_counter()
            try:
                dataframe = await data_service.get_historical(
                    symbol=str(symbol).strip().upper(), timeframe=str(timeframe),
                    market=normalized_market_alt, days=days,
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
                try:
                    dataframe = dataframe.tail(int(limit))
                except Exception:  # noqa: BLE001
                    pass
            # ✅ ROUND28 — تمرير الحجم هنا أيضاً (نفس منطق GET /compute):
            # صيغة الواجهة تجلب من المزود فيجب أن يصل الحجم لمحركات السيولة.
            _vols_alt = _volume_series_from_dataframe(dataframe)
            candles = [
                {
                    "time": int(ts.timestamp() * 1000) if hasattr(ts, "timestamp") else int(ts),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    # ✅ ROUND28 — تمرير الحجم (None بأمان إن غاب)
                    "volume": _vols_alt[_i] if _i < len(_vols_alt) else None,
                }
                for _i, (ts, row) in enumerate(dataframe.iterrows())
            ]
            if not candles:
                raise HTTPException(status_code=404, detail="لا توجد شموع صالحة بعد التطبيع")
            result = compute_overlays(candles, types=wanted_types_alt, params=params_alt)
            elapsed_alt = round((time.perf_counter() - t0_alt) * 1000, 1)
            # ✅ الجولة 13 (بند 3-ب): نفس رفع المستويات إلى الملخص
            _summary_extra_alt = _overlay_levels_summary(result, wanted_types_alt)
            return {
                "symbol": str(symbol).strip().upper(),
                "timeframe": str(timeframe),
                "market": normalized_market_alt,
                "summary": {"bars": result["bars"], "types": wanted_types_alt,
                            "compute_ms": elapsed_alt, "cache": "built-provider",
                            # ✅ ROUND28 — علم تشخيصي للحجم في صيغة الواجهة
                            "volume_available": any(v is not None for v in _vols_alt),
                            **_summary_extra_alt},
                "time_from": result["time_from"],
                "time_to": result["time_to"],
                "overlays": result["overlays"],
            }
        raise HTTPException(status_code=400, detail=(
            "الحقل candles مطلوب: قائمة شموع [{time,open,high,low,close}] — "
            "أو صيغة الواجهة: {symbol, timeframe, days, overlays} فيُجلب من المزود"
        ))
    if len(candles) > 50000:
        raise HTTPException(status_code=400, detail=f"عدد الشموع كبير جداً ({len(candles)}) — الحد 50000")

    types_in = body.get("types") if body.get("types") is not None else body.get("overlays")
    if isinstance(types_in, str):
        wanted_types = _parse_types(types_in)
    elif isinstance(types_in, (list, tuple)):
        wanted_types = _parse_types(",".join(str(x) for x in types_in))
    else:
        wanted_types = list(OVERLAY_TYPES)

    params_in = body.get("params") if isinstance(body.get("params"), dict) else {}
    # ✅ ROUND31 — افتراضيات البطل لـ zzfib في مسار الشموع المباشر أيضاً
    params_in = _apply_zzfib_defaults(params_in)

    t0 = time.perf_counter()
    result = compute_overlays(candles, types=wanted_types, params=params_in)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    # ✅ الجولة 13 (بند 3-ب): نفس رفع المستويات إلى الملخص
    _summary_extra_direct = _overlay_levels_summary(result, wanted_types)

    return {
        "summary": {"bars": result["bars"], "types": wanted_types, "compute_ms": elapsed_ms, "cache": "bypass",
                    **_summary_extra_direct},
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
        "round": 39,
        "round_note": "ROUND39: إتمام عقد الحمولة لوكيل الفرونت (ج38) — إضافات صرفة بلا أي تغيير سلوك: pivots[] لمحاور الزقزاق (نفس نقاط النواة المؤكدة، عقد رسم موحد مع legs)، display (تسمية TV = 1−ratio بعقد ROUND18) وis_launch (علم خط الانطلاقة) في كل مستوى فيبو، وwindow (هوية النافذة) — السابق ROUND34: المحرك الموحد zigzag_fib_core وإصلاح أزمنة ISO ومستويات كل نطاق من الولادة للنهاية،",
        "types": list(OVERLAY_TYPES),
        "cache": {"max_entries": _OVL_CACHE_MAX, "ttl_seconds": _OVL_TTL_SECONDS, "entries": len(_ovl_cache)},
    }
