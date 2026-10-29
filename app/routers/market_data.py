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
    timeframe: str = Query("1h", pattern="^(1m|3m|5m|15m|30m|1h|2h|4h|6h|8h|12h|1d|3d|1w)$"),
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

    # طول الشمعة بالملي ثانية لتحديد نافذة الطلب
    tf_ms = int(_tf_to_minutes(timeframe)) * 60 * 1000

    # end = قبل الشمعة المحمّلة الأقدم بفارق شمعة واحدة (لا تكرار ولا فجوات)
    if before is not None:
        end_dt = datetime.utcfromtimestamp(before / 1000.0)
    else:
        end_dt = datetime.utcnow()
    # نطلب نافذة أوسع قليلًا من limit لتغطية الفجوات (عطلات/توقف منصة)
    span_ms = tf_ms * int(limit * 1.25) + tf_ms * 10
    start_dt = end_dt - timedelta(milliseconds=span_ms)

    try:
        if normalized_market == "crypto":
            df = await provider.get_historicalcandl(
                symbol=symbol, timeframe=timeframe,
                start_date=start_dt, end_date=end_dt,
            )
        else:
            df = await provider.get_historical_data(
                symbol=symbol, timeframe=timeframe,
                period=f"{max(1, (end_dt - start_dt).days)}d",
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
            )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid market, symbol or no data available")
    except Exception:
        logger.exception("Paginated candles fetch failed for %s/%s", market, symbol)
        raise HTTPException(status_code=500, detail="Internal server error")

    if df is None or df.empty:
        return {
            "symbol": symbol.upper(),
            "market": normalized_market,
            "timeframe": timeframe,
            "candles": [],
            "count": 0,
            "oldest_time": None,
            "newest_time": None,
            "has_more": False,
            "next_before": before,
        }

    # توحيد عمود الوقت إلى epoch-ms
    if not isinstance(df.index, pd.DatetimeIndex) and "time" in df.columns:
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
        return {
            "time": int(r["_t"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r.get("volume", 0) or 0),
        }

    candles = [_row(r) for _, r in page.iterrows()]
    oldest = candles[0]["time"] if candles else None
    # إذا حصلنا على صفحة كاملة فالأغلب أن هناك مزيدًا؛ وإذا أقل فوصلنا لبداية التاريخ
    has_more = len(candles) >= limit
    if has_more and oldest is not None:
        # تأكيد إضافي: هل توجد شموع أقدم فعلًا في الإطار المطلوب؟
        has_more = bool((df["_t"] < oldest).any())

    return {
        "symbol": symbol.upper(),
        "market": normalized_market,
        "timeframe": timeframe,
        "candles": candles,
        "count": len(candles),
        "oldest_time": oldest,
        "newest_time": candles[-1]["time"] if candles else None,
        "has_more": has_more,
        "next_before": oldest,
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
