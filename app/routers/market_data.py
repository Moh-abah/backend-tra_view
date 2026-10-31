"""Market data router: symbols, historical candles, live price and live WS stream.

Mounted at /api/v1/market (see app/main.py).
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, get_db
from app.database.redis_client import redis_client
from app.routers.websocket import initialize_websocket_services
from app.services.data_service import DataService
from app.utils.dataframe_utils import (
    composite_base_tf,
    is_composite_tf,
    resample_candles,
    sanitize_candle_time_ms,
)
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["market-data"])


# ---------------------------------------------------------------------------
# Shared real health-check helpers (mirror of api.py)
# ---------------------------------------------------------------------------
async def _check_database() -> Dict[str, Any]:
    """Probe the PostgreSQL connection with a real `SELECT 1`. Never raises."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "up", "detail": "SELECT 1 OK"}
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return {"status": "down", "detail": "Database connection failed"}


async def _check_redis() -> Dict[str, Any]:
    """Probe Redis with a real PING. Never raises."""
    try:
        if await redis_client.ping():
            return {"status": "up", "detail": "PING OK"}
        return {"status": "down", "detail": "PING returned False"}
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return {"status": "down", "detail": "PING failed"}


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/status",
    summary="صحة النظام الحقيقية (قاعدة البيانات + Redis)",
)
async def system_status():
    """Real system status: probes the database and Redis, degrades if any is down.

    الاستجابة:
        {"status": "ok"|"degraded", "services": {"database": {...}, "redis": {...}}, "timestamp": ...}
    استخدمها للتحقق الجانبي قبل الاتصال بالبيانات.
    """
    try:
        services = {
            "database": await _check_database(),
            "redis": await _check_redis(),
        }
        overall = "ok" if all(s["status"] == "up" for s in services.values()) else "degraded"
        return {
            "status": overall,
            "services": services,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception:
        logger.exception("Status payload construction failed")
        return {"status": "degraded", "services": {}, "timestamp": datetime.utcnow().isoformat()}


@router.get(
    "/symbols",
    summary="قائمة الرموز المتاحة لسوق (crypto=774 / stocks=5222)",
    responses={
        200: {
            "description": "قائمة الرموز",
            "content": {
                "application/json": {
                    "example": {
                        "market": "crypto",
                        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                        "count": 774,
                        "timestamp": "2026-01-02T12:00:00",
                    }
                }
            },
        }
    },
)
async def get_available_symbols(
    market: str = Query("crypto", description="crypto | stocks"),
    db: AsyncSession = Depends(get_db),
):
    """List available symbols for a market.

    يُستخدم لتعبئة قوائم تغيير الرمز في الواجهة. الرموز بصيغة
    BTCUSDT (كريبتو) أو AAPL (أسهم).
    """
    try:
        service = DataService(db)
        symbols = await service.get_symbols(market)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list symbols for market=%s", market)
        raise HTTPException(status_code=500, detail="Internal server error")

    if not symbols:
        return {
            "market": market,
            "symbols": [],
            "message": f"No symbols found for market: {market}",
            "count": 0,
        }

    return {
        "market": market,
        "symbols": symbols,
        "count": len(symbols),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Cursor-paginated candles (TradingView-style infinite scroll)
# ---------------------------------------------------------------------------
# يبني الفرونت الشارت ويطلب صفحة شموع، وعند تمرير المستخدم لليسار يطلب الصفحة
# الأقدم بتمرير before=<أقدم وقت محمّل بالملي ثانية>. التاريخ الكامل متاح —
# لا يوجد حد إجمالي على عدد الشموع إطلاقًا (الحجم الأقصى هو حجم الصفحة الواحدة).
_CANDLE_PAGE_DEFAULT = 2000
_CANDLE_PAGE_MAX = 5000


@router.get(
    "/candles/{market}/{symbol}",
    summary="⭐ نقطة الشارت الأساسية — صفحة شموع مع ترقيم cursor للتمرير اللانهائي",
    responses={
        200: {
            "description": "صفحة شموع مغلقة تصاعدية + مؤشر استمرارية",
            "content": {
                "application/json": {
                    "example": {
                        "symbol": "BTCUSDT",
                        "market": "crypto",
                        "timeframe": "1h",
                        "candles": [
                            {
                                "time": 1767139200000,
                                "open": 80216.01,
                                "high": 80310.5,
                                "low": 80190.2,
                                "close": 80285.4,
                                "volume": 1234.56,
                            },
                            {
                                "time": 1767142800000,
                                "open": 80285.4,
                                "high": 80400.0,
                                "low": 80270.1,
                                "close": 80372.96,
                                "volume": 987.65,
                            },
                        ],
                        "count": 2,
                        "oldest_time": 1767139200000,
                        "newest_time": 1767142800000,
                        "has_more": True,
                        "next_before": 1767139200000,
                    }
                }
            },
        }
    },
)
async def get_candles_paginated(
    market: str,
    symbol: str,
    timeframe: str = Query("1h", pattern="^(1m|2m|3m|5m|10m|15m|30m|1h|2h|4h|6h|8h|12h|1d|2d|3d|1w|2w|1M)$"),
    limit: int = Query(_CANDLE_PAGE_DEFAULT, ge=10, le=_CANDLE_PAGE_MAX),
    before: Optional[int] = Query(
        None, ge=0,
        description="epoch-ms — يجلب الشموع الأقدم من هذا الوقت (للتمرير للخلف). اتركه فارغًا لآخر الشموع",
    ),
    db: AsyncSession = Depends(get_db),
):
    """صفحة شموع مغلقة للشارت مع مؤشر استمرارية (has_more/next_before).

    مصممة خصيصًا للتمرير اللانهائي بنمط TradingView:
      - الطلب الأول:  ?timeframe=1h&limit=2000            → آخر 2000 شمعة مغلقة
      - التمرير يسار: ?timeframe=1h&limit=2000&before=<oldest_time> → 2000 شمعة أقدم
    الشموع تعود بترتيب تصاعدي (الأقدم أولًا) وجاهزة للدمج مباشرة في الشارت.
    """
    # توحيد أسماء السوق (مطابق لنقطة /historical)
    market_map = {"stock": "stocks", "stocks": "stocks", "crypto": "crypto", "binance": "crypto"}
    normalized_market = market_map.get(market.lower(), market)

    data_service = DataService(db)
    provider = data_service.providers.get(normalized_market)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unsupported market: {market}")

    # فريم مركّب (2m/10m/2d/2w/1M)؟ نجلب الفريم الأساسي ثم نجمّع محلياً
    composite = is_composite_tf(timeframe)
    fetch_tf = composite_base_tf(timeframe)[0] if composite else timeframe

    # طول الشمعة المُجلب بها بالملي ثانية لتحديد نافذة الطلب
    tf_ms = int(_tf_to_minutes(fetch_tf)) * 60 * 1000

    # end = قبل الشمعة المحمّلة الأقدم بفارق شمعة واحدة (لا تكرار ولا فجوات)
    if before is not None:
        end_dt = datetime.utcfromtimestamp(before / 1000.0)
    else:
        end_dt = datetime.utcnow()

    try:
        if normalized_market == "crypto":
            # نطلب نافذة أوسع من limit لتغطية الفجوات (عطلات/توقف منصة).
            # للمركّبات: factor = عدد شموع الأساس داخل bucket الواحد
            # (2m×2 | 10m×2 | 2d×2 | 2w×14 | 1M×31) × 1.3 هامش أمان
            if composite:
                _, factor = composite_base_tf(timeframe)
                span_ms = tf_ms * int(limit * factor * 1.3) + tf_ms * 10
            else:
                span_ms = tf_ms * int(limit * 1.25) + tf_ms * 10
            start_dt = end_dt - timedelta(milliseconds=span_ms)
            df = await provider.get_historicalcandl(
                symbol=symbol, timeframe=fetch_tf,
                start_date=start_dt, end_date=end_dt,
            )
            if composite and df is not None and not df.empty:
                # تجميع الفريم الأساسي إلى المركّب — ثم كل المنطق أدناه يعمل كما هو
                df = resample_candles(df, timeframe, time_col="time")
        else:
            # أسهم: إطار كامل من كاش التاريخ الكامل (يستبقى العقد الدقيقة
            # 1m/5m وعمق 17+ سنة يومي) — تقسيم صفحات محلي سريع وhas_more دقيق
            df = await provider.get_full_history(symbol, timeframe)
            if df is not None and not df.empty and isinstance(df.index, pd.DatetimeIndex):
                idx_ms = df.index.astype("int64") // 10**6
                df = df.reset_index(drop=True).assign(_t=idx_ms)
                # تطبيق الـ cursor محلياً — الإطار الكامل يجب تقطيعه هنا
                # (كريبتو يطبقه داخل نافذة المزود، لكن الأسهم تخدم من إطار كامل)
                if before is not None:
                    df = df[df["_t"] < int(before)]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid market, symbol or no data available")
    except Exception:
        logger.exception("Paginated candles fetch failed for %s/%s", market, symbol)
        raise HTTPException(status_code=500, detail="Internal server error")

    # ⚠️ وسم الجلب الناقص (حظر/تهدئة Binance مؤقتة): إن وُجد لا نعلن نهاية
    # التاريخ زوراً — نُعيد ما توفر مع has_more=true ليستمر التمرير، والفجوات
    # تُملأ تلقائياً في الطلبات التالية بعد انتهاء التهدئة (كاش يُصلح نفسه).
    _df_attrs = getattr(df, "attrs", {}) or {}
    fetch_incomplete = bool(_df_attrs.get("fetch_incomplete", False)) if df is not None else False

    if df is None or df.empty:
        return {
            "symbol": symbol.upper(),
            "market": normalized_market,
            "timeframe": timeframe,
            "candles": [],
            "count": 0,
            "oldest_time": None,
            "newest_time": None,
            "has_more": fetch_incomplete,
            "next_before": before,
        }

    # توحيد عمود الوقت إلى epoch-ms (مسار الأسهم يجهّز _t مباشرة أعلاه)
    if "_t" in df.columns:
        pass  # محوّل مسبقاً
    elif not isinstance(df.index, pd.DatetimeIndex) and "time" in df.columns:
        time_series = df["time"]
        if pd.api.types.is_numeric_dtype(time_series):
            # epoch-ms صريح (مسار العملات)
            df = df.assign(_t=time_series.astype("int64"))
        else:
            df = df.assign(_t=pd.to_datetime(time_series).astype("int64") // 10**6)
    elif isinstance(df.index, pd.DatetimeIndex):
        idx_ms = df.index.astype("int64") // 10**6
        df = df.reset_index(drop=True).assign(_t=idx_ms)
    else:
        raise HTTPException(status_code=500, detail="Unexpected candle payload shape")

    df = df.sort_values("_t").drop_duplicates(subset=["_t"], keep="last")

    page = df.tail(limit)

    def _row(r) -> Dict[str, Any]:
        # ✅ الجولة 4: طابع موحّد — epoch-ms محاذاة الفريم تماماً (بلا بقايا ±tz)
        t_clean = sanitize_candle_time_ms(int(r["_t"]), timeframe)
        return {
            "time": t_clean,
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r.get("volume", 0) or 0),
        }

    candles = [_row(r) for _, r in page.iterrows()]
    # إزالة التكرار الناتج عن تقريب المحاذاة (نادر — bucket واحد يلتقط صفين)
    if candles:
        _seen = set()
        _uniq = []
        for c in candles:
            if c["time"] not in _seen:
                _seen.add(c["time"])
                _uniq.append(c)
        candles = _uniq
    oldest = candles[0]["time"] if candles else None
    # إذا حصلنا على صفحة كاملة فالأغلب أن هناك مزيدًا؛ وإذا أقل فوصلنا لبداية التاريخ
    has_more = len(candles) >= limit
    if has_more and oldest is not None:
        # تأكيد إضافي: هل توجد شموع أقدم فعلًا في الإطار المطلوب؟
        has_more = bool((df["_t"] < oldest).any())
    # صفحة ناقصة بسبب حظر/تهدئة مؤقتة: نُبقي التمرير حياً بدل إيقافه زوراً
    if fetch_incomplete and candles:
        has_more = True

    # ✅ الجولة 4: حالة سوق الأسهم مع استجابة الشموع (open/closed/pre_market/...)
    resp_market_status = None
    if normalized_market in ("stocks", "stock"):
        try:
            from app.providers.us_stock_provider import get_market_status
            resp_market_status = get_market_status()
        except Exception:  # noqa: BLE001
            resp_market_status = None

    return {
        "symbol": symbol.upper(),
        "market": normalized_market,
        "timeframe": timeframe,
        "market_status": resp_market_status,
        "candles": candles,
        "count": len(candles),
        "oldest_time": oldest,
        "newest_time": candles[-1]["time"] if candles else None,
        "has_more": has_more,
        "next_before": oldest,
    }


# ---------------------------------------------------------------------------
# ✅ الجولة 6: نطاق زمني واحد (Range) — بدل حلقات before عند القفزات العميقة
# ---------------------------------------------------------------------------
# طلب الفرونت (تقرير الجولة 5، تحسين #1): قفزة "الانتقال إلى تاريخ" عميقة
# (>100 ألف شمعة) تتطلب حالياً حلقات before متكررة. هذه النقطة تعيد نطاقاً
# كاملاً بطلب واحد: /range?timeframe=&from=&to= (epoch-ms شامل الطرفين).
# العقد الثابت محفوظ: نفس حقول الشموع time|open|high|low|close|volume،
# ونفس مفاتيح has_more/next_before ليعمل التمرير الرجعي إن لزم.
_CANDLE_RANGE_MAX = 20000   # حد limit لنقطة النطاق (أكبر من صفحة التمرير)


@router.get(
    "/candles/{market}/{symbol}/range",
    summary="⭐ الجولة 6: شموع نطاق زمني بطلب واحد — from/to بالملي ثانية (للقفزات العميقة)",
    responses={
        200: {
            "description": "شموع النطاق [from, to] (آخر limit شمعة داخل النطاق) + مؤشرات الاستمرارية",
            "content": {
                "application/json": {
                    "example": {
                        "symbol": "BTCUSDT",
                        "market": "crypto",
                        "timeframe": "1h",
                        "from": 1698796800000,
                        "to": 1700000000000,
                        "candles": [
                            {
                                "time": 1699986000000,
                                "open": 36500.0,
                                "high": 36620.0,
                                "low": 36410.0,
                                "close": 36580.0,
                                "volume": 512.3,
                            }
                        ],
                        "count": 1,
                        "oldest_time": 1699986000000,
                        "newest_time": 1699986000000,
                        "has_more": True,
                        "next_before": 1699986000000,
                        "truncated": False,
                        "limit": 5000,
                    }
                }
            },
        }
    },
)
async def get_candles_range(
    market: str,
    symbol: str,
    timeframe: str = Query("1h", pattern="^(1m|2m|3m|5m|10m|15m|30m|1h|2h|4h|6h|8h|12h|1d|2d|3d|1w|2w|1M)$"),
    from_ms: int = Query(..., ge=0, alias="from",
                         description="بداية النطاق epoch-ms (شاملة)"),
    to_ms: int = Query(..., ge=0, alias="to",
                       description="نهاية النطاق epoch-ms (شاملة)"),
    limit: int = Query(_CANDLE_PAGE_DEFAULT, ge=10, le=_CANDLE_RANGE_MAX,
                       description=f"أقصى عدد شموع معاد (نُبقي الأحدث). الحد الأقصى {_CANDLE_RANGE_MAX}"),
    db: AsyncSession = Depends(get_db),
):
    """شموع نطاق زمني [from, to] بطلب واحد — تسريع "الانتقال إلى تاريخ".

    العقد الثابت كما في نقطة /candles:
      - الشموع تصاعدية بحقول time|open|high|low|close|volume وtime بالملي ثانية.
      - has_more/next_before بنفس دلالات التمرير الرجعي (next_before = أقدم شمعة
        معادة؛ مرّرها إلى /candles?before= إن أردت ما هو أقدم).
    سلوك النطاق:
      - يُعاد آخر `limit` شمعة داخل النطاق (الأحدث عند `to`)؛ إن كان النطاق
        أوسع من `limit` تُضبط truncated=true وتستمر بالتمرير الرجعي عند الحاجة.
      - جلب العملات يُقيَّد بنافذة تكفي `limit` شمعة فقط (سريع دائماً حتى لو
        طُلب نطاق 10 سنوات — لأن الأحدث داخل النطاق هو المُعاد على أي حال).
    الترويسة: X-Max-Limit: 20000 على كل استجابات هذه النقطة.
    """
    if from_ms > to_ms:
        raise HTTPException(status_code=400, detail="from must be <= to (epoch-ms)")

    market_map = {"stock": "stocks", "stocks": "stocks", "crypto": "crypto", "binance": "crypto"}
    normalized_market = market_map.get(market.lower(), market)

    data_service = DataService(db)
    provider = data_service.providers.get(normalized_market)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unsupported market: {market}")

    composite = is_composite_tf(timeframe)
    fetch_tf = composite_base_tf(timeframe)[0] if composite else timeframe
    tf_ms = int(_tf_to_minutes(fetch_tf)) * 60 * 1000

    to_dt = datetime.utcfromtimestamp(to_ms / 1000.0)
    # نافذة الجلب: النطاق المطلوب مقيّداً بما يكفي limit شمعة فقط (×1.3 هامش فجوات)
    if composite:
        _, factor = composite_base_tf(timeframe)
        cap_ms = tf_ms * int(limit * factor * 1.3) + tf_ms * 10
    else:
        cap_ms = tf_ms * int(limit * 1.3) + tf_ms * 10
    span_ms = min(to_ms - from_ms, cap_ms)
    clamped_fetch = span_ms < (to_ms - from_ms)
    start_dt = to_dt - timedelta(milliseconds=span_ms)

    try:
        if normalized_market == "crypto":
            df = await provider.get_historicalcandl(
                symbol=symbol, timeframe=fetch_tf,
                start_date=start_dt, end_date=to_dt,
            )
            if composite and df is not None and not df.empty:
                df = resample_candles(df, timeframe, time_col="time")
        else:
            # أسهم: كاش التاريخ الكامل محلياً — تقطيع [from, to] فوري
            df = await provider.get_full_history(symbol, timeframe)
            if df is not None and not df.empty and isinstance(df.index, pd.DatetimeIndex):
                idx_ms = df.index.astype("int64") // 10**6
                df = df.reset_index(drop=True).assign(_t=idx_ms)
                df = df[(df["_t"] >= int(from_ms)) & (df["_t"] <= int(to_ms))]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid market, symbol or no data available")
    except Exception:
        logger.exception("Range candles fetch failed for %s/%s", market, symbol)
        raise HTTPException(status_code=500, detail="Internal server error")

    _df_attrs = getattr(df, "attrs", {}) or {}
    fetch_incomplete = bool(_df_attrs.get("fetch_incomplete", False)) if df is not None else False

    empty_resp = {
        "symbol": symbol.upper(),
        "market": normalized_market,
        "timeframe": timeframe,
        "from": from_ms,
        "to": to_ms,
        "candles": [],
        "count": 0,
        "oldest_time": None,
        "newest_time": None,
        "has_more": fetch_incomplete,
        "next_before": None,
        "truncated": False,
        "limit": limit,
    }
    if df is None or df.empty:
        return empty_resp

    # توحيد الوقت إلى epoch-ms (نفس منطق نقطة الترقيم)
    if "_t" in df.columns:
        pass
    elif not isinstance(df.index, pd.DatetimeIndex) and "time" in df.columns:
        time_series = df["time"]
        if pd.api.types.is_numeric_dtype(time_series):
            df = df.assign(_t=time_series.astype("int64"))
        else:
            df = df.assign(_t=pd.to_datetime(time_series).astype("int64") // 10**6)
    elif isinstance(df.index, pd.DatetimeIndex):
        idx_ms = df.index.astype("int64") // 10**6
        df = df.reset_index(drop=True).assign(_t=idx_ms)
    else:
        raise HTTPException(status_code=500, detail="Unexpected candle payload shape")

    df = df.sort_values("_t").drop_duplicates(subset=["_t"], keep="last")
    # النطاق المطلوب فقط (للمسار الكريبتو: نافذة الجلب تقريبه أصلاً — تأكيد الحدود)
    df = df[(df["_t"] >= int(from_ms)) & (df["_t"] <= int(to_ms))]

    if df.empty:
        return empty_resp

    in_window = len(df)
    page = df.tail(limit)  # الأحدث داخل النطاق

    def _row(r) -> Dict[str, Any]:
        t_clean = sanitize_candle_time_ms(int(r["_t"]), timeframe)
        return {
            "time": t_clean,
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r.get("volume", 0) or 0),
        }

    candles = [_row(r) for _, r in page.iterrows()]
    if candles:
        _seen = set()
        _uniq = []
        for c in candles:
            if c["time"] not in _seen:
                _seen.add(c["time"])
                _uniq.append(c)
        candles = _uniq
    oldest = candles[0]["time"] if candles else None

    # has_more بنفس دلالات التمرير الرجعي: هل توجد شموع أقدم من المُعاد؟
    has_more = bool((df["_t"] < oldest).any()) if oldest is not None else False
    if fetch_incomplete and candles:
        has_more = True
    # truncated: النطاق كان أوسع من limit فاقتُعت الأحدث فقط
    truncated = bool(clamped_fetch and len(candles) >= limit and in_window >= limit)

    resp_market_status = None
    if normalized_market in ("stocks", "stock"):
        try:
            from app.providers.us_stock_provider import get_market_status
            resp_market_status = get_market_status()
        except Exception:  # noqa: BLE001
            resp_market_status = None

    return {
        "symbol": symbol.upper(),
        "market": normalized_market,
        "timeframe": timeframe,
        "market_status": resp_market_status,
        "from": from_ms,
        "to": to_ms,
        "candles": candles,
        "count": len(candles),
        "oldest_time": oldest,
        "newest_time": candles[-1]["time"] if candles else None,
        "has_more": has_more,
        "next_before": oldest,
        "truncated": truncated,
        "limit": limit,
    }


def _tf_to_minutes(timeframe: str) -> int:
    """Fallback converter (m/h/d/w) used when TimeframeConverter lacks to_minutes."""
    tf = timeframe.strip().lower()
    try:
        if tf.endswith("m"):
            return int(tf[:-1])
        if tf.endswith("h"):
            return int(tf[:-1]) * 60
        if tf.endswith("d"):
            return int(tf[:-1]) * 1440
        if tf.endswith("w"):
            return int(tf[:-1]) * 10080
    except ValueError:
        pass
    return 60


@router.get(
    "/historical/{market}/{symbol}",
    summary="تاريخ كامل حتى 10 سنوات (استجابة كبيرة — للتصدير/التحليل)",
)
async def get_historical_data(
    market: str,
    symbol: str,
    timeframe: str = "1h",
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Historical OHLCV data for a symbol (capped at 10 years)."""
    if days > 3650:
        raise HTTPException(status_code=400, detail="Days parameter cannot exceed 3650")

    # Market aliases
    market_map = {
        "stock": "stocks",
        "stocks": "stocks",
        "crypto": "crypto",
        "binance": "crypto",
    }
    normalized_market = market_map.get(market.lower(), market)

    try:
        data_service = DataService(db)
        df = await data_service.get_historical(
            symbol=symbol,
            timeframe=timeframe,
            market=normalized_market,
            days=days,
        )
    except HTTPException:
        raise
    except ValueError:
        logger.warning("Historical lookup rejected for %s/%s (market=%s)", symbol, timeframe, normalized_market)
        raise HTTPException(status_code=400, detail="Invalid market, symbol or no data available")
    except Exception:
        logger.exception("Historical data fetch failed for %s/%s", market, symbol)
        raise HTTPException(status_code=500, detail="Internal server error")

    if df is None or df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No historical data found for {symbol} in {market}",
        )

    # Single vectorized conversion instead of row-by-row iteration: reset the
    # index once, normalize the time column in one shot, then emit records via
    # one DataFrame -> JSON pass (handles NaN/Inf and numpy types safely).
    # NOTE: for a year of 1m candles (~527k rows) this is seconds of CPU — run
    # it in a worker thread so the event loop keeps serving /health and other
    # requests while the big payload is prepared.
    import asyncio as _asyncio

    def _frame_to_records() -> list:
        frame = df.reset_index()
        time_col = next(
            (c for c in ("timestamp", "time", "date", "index") if c in frame.columns),
            frame.columns[0],
        )
        if pd.api.types.is_datetime64_any_dtype(frame[time_col]):
            frame[time_col] = frame[time_col].dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
        else:
            frame[time_col] = frame[time_col].astype(str)
        if time_col != "timestamp":
            frame = frame.rename(columns={time_col: "timestamp"})
        return json.loads(frame.to_json(orient="records", date_format="iso"))

    records = await _asyncio.to_thread(_frame_to_records)

    def _index_to_iso(value: Any) -> Optional[str]:
        try:
            return value.isoformat()
        except AttributeError:
            pass
        if value is None:
            return None
        # Bugfix: كان يعيد str(int) مثل "0" عندما يكون الفهرس RangeIndex
        # (بيانات بدون فهرس زمني) — نعيد None بدل تاريخ وهمي.
        # ملاحظة: عمود "time" في مسار العملات (crypto) قيمه epoch بالمللي ثانية
        # (numpy.int64 أو int) — نحوّلها إلى تاريخ ISO حقيقي.
        try:
            ms = float(value)  # يدعم int/float و numpy scalars معًا
        except (TypeError, ValueError):
            ms = None
        if ms is not None:
            if ms > 1e11:  # عتبة معقولة لأزمنة epoch-ms (بعد 1973)
                try:
                    return datetime.utcfromtimestamp(ms / 1000.0).isoformat()
                except (OverflowError, OSError, ValueError):
                    return None
            return None  # رقم وليس تاريخًا
        s = str(value)
        # نصوص رقمية صرفة ليست تواريخ
        return None if s.isdigit() else s

    def _first_last_iso(frame) -> tuple:
        """أول/آخر طابع زمني حقيقي: من الفهرس إن كان DatetimeIndex،
        وإلا من عمود timestamp/date إن وُجد، وإلا (None, None)."""
        idx = frame.index
        if len(frame) and hasattr(idx, "dtype") and str(idx.dtype).startswith("datetime"):
            return _index_to_iso(idx[0]), _index_to_iso(idx[-1])
        # ملاحظة: مسار العملات يعيد عمود "time" (epoch ms) — أُضيف هنا
        # ليُعاد start_date/end_date حقيقيان بدل None.
        for col in ("timestamp", "time", "date", "open_time"):
            if col in getattr(frame, "columns", []):
                series = frame[col].dropna()
                if len(series):
                    first = series.iloc[0]
                    last = series.iloc[-1]
                    return _index_to_iso(first), _index_to_iso(last)
        if len(frame):
            first, last = _index_to_iso(idx[0]), _index_to_iso(idx[-1])
            # قيم فهرس رقمية ليست تواريخ → None (أدق من "0")
            if isinstance(idx[0], (int, float)):
                return None, None
            return first, last
        return None, None

    start_iso, end_iso = _first_last_iso(df)

    payload = {
        "symbol": symbol,
        "market": normalized_market,
        "timeframe": timeframe,
        "days": days,
        "row_count": len(df),
        "start_date": start_iso,
        "end_date": end_iso,
        "data": records,
    }
    # Pre-serialize in a worker thread and return raw Response bytes — letting
    # FastAPI walk 500k+ dicts through jsonable_encoder would block the event
    # loop for seconds (the "backend freezes" symptom).
    content = await _asyncio.to_thread(
        json.dumps, payload, ensure_ascii=False, separators=(",", ":"), default=str
    )
    from fastapi.responses import Response as _Response

    return _Response(content=content, media_type="application/json")


@router.get(
    "/price/{market}/{symbol}",
    summary="السعر الحي لرمز واحد",
    responses={
        200: {
            "description": "السعر وإحصائيات 24 ساعة",
            "content": {
                "application/json": {
                    "example": {
                        "symbol": "BTCUSDT",
                        "price": 80248.55,
                        "change_24h": -1.12,
                        "high_24h": 81200.0,
                        "low_24h": 79900.0,
                        "volume_24h": 5250000000.0,
                        "timestamp": "2026-01-02T12:00:00",
                    }
                }
            },
        }
    },
)
async def get_current_price(
    market: str,
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    """Current price for one symbol."""
    try:
        data_service = DataService(db)
        price = await data_service.get_live_price(symbol, market)
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported market: {market}")
    except Exception:
        logger.exception("Live price fetch failed for %s/%s", market, symbol)
        raise HTTPException(status_code=500, detail="Internal server error")

    if not price:
        raise HTTPException(status_code=502, detail="Price provider returned no data")
    return price


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@router.websocket("/ws/live/{market}/{symbol}")
async def websocket_live_data(
    websocket: WebSocket,
    market: str,
    symbol: str,
    timeframe: str = Query("1m", pattern="^(1m|5m|15m|1h|4h|1d)$"),
):
    """Live data stream for one symbol, delegated to the shared WebSocket manager.

    بث حي للشارت — رسائل الخادم:
        {"type": "connection_established"}        ← عند القبول
        {"type": "kline", "kline": {...}}          ← تحديث الشمعة الحية (is_closed=false)
        {"type": "kline_closed", "kline": {...}}   ← إغلاق شمعة — أضفها للتاريخ
        {"type": "pong"}                          ← رد على {"type": "ping"}
    الشكل الكامل موثق في /agent/contract.json ← websocket_protocol.
    """
    initialize_websocket_services()
    try:
        await manager.handle_stream_connection(
            websocket,
            symbol=symbol,
            timeframe=timeframe,
            market=market,
        )
    except WebSocketDisconnect:
        logger.info("Live WS disconnected: %s/%s", market, symbol)
    except Exception:
        logger.exception("Live WS error: %s/%s", market, symbol)
