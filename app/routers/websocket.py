"""WebSocket routers: market overview, indicator monitoring, filters and streams.

Mounted at /ws (see app/main.py). This module holds the ONE canonical
implementation of each WebSocket endpoint:

- /ws/market-overview          live Binance !ticker@arr stream (USDT/USDC, capped)
- /ws/indicators/{symbol}      historical snapshot + live indicator monitoring
- /ws/filter                   streaming filtered symbols (+prices)
- /ws/signals                  delegated to app.websocket.signals_ws
- /ws/stream/{symbol}/{tf}     TradingView-like stream via WebSocketManager
- /ws/chart/{symbol}           provided by app.websocket.chart_ws (included below)

The former duplicates (/market-overviewalls, /market-data_overview, /stream,
/ws/filters and the copy in api.py) were removed.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.providers.binance_indicators_stream import indicators_manager
from app.providers.binance_market_stream import stream_all_market
from app.providers.binance_provider import BinanceProvider
from app.database.session import AsyncSessionLocal
from app.services.data_service import DataService
from app.services.filtering import FilterCriteria, FilteringEngine, get_filtering_engine
from app.websocket.chart_ws import router as chart_router
from app.websocket.manager import manager
from app.websocket.signals_ws import signals_websocket

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])
router.include_router(chart_router)

# Limits / intervals
MAX_OVERVIEW_SYMBOLS = 50
MAX_FILTER_PRICES = 50
KEEPALIVE_TIMEOUT = 30.0          # seconds without a client message before we ping
MARKET_OVERVIEW_INTERVAL = 7.0    # seconds between overview pushes
FILTER_INTERVAL = 10.0            # seconds between filter pushes


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def initialize_websocket_services():
    """Ensure the shared real-time stream handler exists (idempotent).

    Keeps only the manager.initialize() call — no module-level service globals.
    The stream handler's data paths (stream_live / get_historical) go through
    providers and Redis, never through the DB session, so a sessionless
    DataService(None) is sufficient here (DataService is being made db=None
    tolerant).
    """
    if manager.stream_handler is None:
        manager.initialize(DataService(None), FilteringEngine())


async def _keepalive_listener(websocket: WebSocket, timeout: float = KEEPALIVE_TIMEOUT) -> None:
    """Background receive loop: answers client pings, surfaces disconnects.

    Runs as a task next to a sending loop. `asyncio.wait_for` guarantees a
    silent client still receives a periodic server ping so intermediaries do
    not idle the connection out. Raises WebSocketDisconnect (or any send
    error) out of the task when the client goes away.
    """
    while True:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
        except asyncio.TimeoutError:
            await websocket.send_json({"type": "ping", "timestamp": _utcnow_iso()})
            continue
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(message, dict) and message.get("type") == "ping":
            await websocket.send_json({"type": "pong", "timestamp": _utcnow_iso()})


# ---------------------------------------------------------------------------
# Market overview (canonical)
# ---------------------------------------------------------------------------
@router.websocket("/market-overview")
async def websocket_market_overview(websocket: WebSocket):
    """Stream live Binance 24h tickers (USDT/USDC only, max ~50 symbols)."""
    await websocket.accept()
    logger.info("Market overview WS connected")
    try:
        await websocket.send_json({
            "type": "connection_established",
            "message": "Connected to market data stream",
            "timestamp": _utcnow_iso(),
        })
    except Exception:
        logger.warning("Failed to send market-overview welcome message")
        return

    listener = asyncio.create_task(_keepalive_listener(websocket))
    try:
        async for payload in stream_all_market():
            tickers = [
                d for d in payload.get("data", [])
                if str(d.get("symbol", "")).endswith(("USDT", "USDC"))
            ][:MAX_OVERVIEW_SYMBOLS]
            await websocket.send_json({
                "type": payload.get("type", "market_overview"),
                "timestamp": payload.get("timestamp") or _utcnow_iso(),
                "data": tickers,
                "count": len(tickers),
            })
            if listener.done():
                listener.result()  # re-raise client disconnect / listener error
            await asyncio.sleep(MARKET_OVERVIEW_INTERVAL)
    except WebSocketDisconnect:
        logger.info("Market overview WS disconnected")
    except Exception:
        logger.exception("Market overview WS error")
        await websocket.close(code=1011, reason="Internal server error")
    finally:
        listener.cancel()
        logger.info("Market overview WS closed")


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------
# NOTE: this router is mounted at "/ws" in app/main.py — the decorator path is
# "/indicators/{symbol}" so the FINAL path is /ws/indicators/{symbol} (the old
# "/ws/indicators/..." decorator produced a double-prefixed /ws/ws/... route).
@router.websocket("/indicators/{symbol}")
async def indicators_websocket(websocket: WebSocket, symbol: str):
    """Historical indicator snapshot + live monitoring for one symbol.

    The client may send a first JSON message:
        {"indicators": [...], "timeframe": "1m", "days": 1}
    Live candle/indicator updates are pushed by the indicators manager.
    """
    await websocket.accept()
    logger.info("Indicators WS connected: %s", symbol)
    timeframe = "1m"
    registered = False
    try:
        # 1. Optional client configuration (first message, default after timeout)
        try:
            config = await asyncio.wait_for(websocket.receive_json(), timeout=KEEPALIVE_TIMEOUT)
        except asyncio.TimeoutError:
            config = {}
        if not isinstance(config, dict):
            config = {}
        indicators_config = config.get("indicators") or []
        timeframe = str(config.get("timeframe") or "1m")
        try:
            days = int(config.get("days") or 1)
        except (TypeError, ValueError):
            days = 1

        # 2. Historical snapshot through a real DB session
        async with AsyncSessionLocal() as db:
            data_service = DataService(db)
            historical_data = await data_service.get_data_with_indicators(
                symbol=symbol,
                timeframe=timeframe,
                market="crypto",
                indicators_config=indicators_config,
                days=days,
            )
        await websocket.send_json({
            "type": "historical_data",
            "data": historical_data,
            "timestamp": _utcnow_iso(),
        })

        # 3. Register the symbol for live monitoring, attach this client
        await indicators_manager.add_symbol_monitoring(symbol, timeframe)
        registered = True
        try:
            entry = indicators_manager.active_symbols.setdefault(symbol, {"clients": []})
            clients = entry.get("clients") if isinstance(entry, dict) else None
            if clients is not None and websocket not in clients:
                clients.append(websocket)
        except Exception:
            logger.warning("Could not attach client to %s monitoring", symbol, exc_info=True)

        # 4. Hold the connection open; updates arrive from indicators_manager
        while True:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=KEEPALIVE_TIMEOUT)
            if raw == "ping":
                await websocket.send_json({"type": "pong", "timestamp": _utcnow_iso()})

    except asyncio.TimeoutError:
        logger.info("Indicators WS idle timeout: %s", symbol)
        await websocket.close(code=1001, reason="Idle timeout")
    except WebSocketDisconnect:
        logger.info("Indicators WS disconnected: %s", symbol)
    except Exception:
        logger.exception("Indicators WS error for %s", symbol)
        await websocket.close(code=1011, reason="Internal server error")
    finally:
        try:
            entry = indicators_manager.active_symbols.get(symbol)
            if isinstance(entry, dict):
                clients = entry.get("clients")
                if clients and websocket in clients:
                    clients.remove(websocket)
        except Exception:
            logger.debug("Failed to detach client from %s", symbol, exc_info=True)
        if registered:
            try:
                await indicators_manager.remove_symbol_monitoring(symbol)
            except Exception:
                logger.warning("remove_symbol_monitoring failed for %s", symbol, exc_info=True)


# ---------------------------------------------------------------------------
# Signals (delegated)
# ---------------------------------------------------------------------------
@router.websocket("/signals")
async def ws_signals(websocket: WebSocket):
    """Delegate to the signals streaming module."""
    try:
        await signals_websocket(websocket)
    except WebSocketDisconnect:
        logger.info("Signals WS disconnected")
    except Exception:
        logger.exception("Signals WS error")
        await websocket.close(code=1011, reason="Internal server error")


# ---------------------------------------------------------------------------
# Filters (merged: old /filter + /filters)
# ---------------------------------------------------------------------------
@router.websocket("/filter")
async def websocket_filter_stream(websocket: WebSocket):
    """Stream filtered symbols (with prices) for client-supplied criteria.

    Expected first message: {"criteria": {...}, "markets": ["crypto", ...]}
    Invalid criteria closes the socket with code 1008 (policy violation).
    """
    await websocket.accept()
    logger.info("Filter WS connected")
    try:
        try:
            body = await asyncio.wait_for(websocket.receive_json(), timeout=KEEPALIVE_TIMEOUT)
        except asyncio.TimeoutError:
            await websocket.close(code=1008, reason="Missing filter criteria")
            return
        if not isinstance(body, dict) or not isinstance(body.get("criteria"), dict):
            await websocket.close(code=1008, reason='Body must be {"criteria": {...}, "markets": [...]}')
            return
        markets = body.get("markets") or ["crypto"]
        if not isinstance(markets, list):
            markets = ["crypto"]
        try:
            criteria = FilterCriteria(**body["criteria"])
        except ValidationError:
            logger.info("Rejected invalid filter criteria")
            await websocket.close(code=1008, reason="Invalid filter criteria")
            return

        filtering_engine = get_filtering_engine()
        provider = BinanceProvider()  # created ONCE, reused every iteration

        listener = asyncio.create_task(_keepalive_listener(websocket))
        try:
            while True:
                for market in markets:
                    result = await filtering_engine.filter_symbols(
                        market=market, criteria=criteria
                    )
                    symbols = list(result.symbols)[:MAX_FILTER_PRICES]
                    prices = []
                    for sym in symbols:
                        try:
                            price_data = await provider.get_live_price(sym)
                        except Exception:
                            logger.debug("Price lookup failed for %s", sym, exc_info=True)
                            continue
                        if price_data:
                            prices.append({
                                "symbol": sym,
                                "current": price_data.get("price", 0),
                                "timestamp": _utcnow_iso(),
                            })
                    await websocket.send_json({
                        "type": "filter_result",
                        "timestamp": _utcnow_iso(),
                        "market": market,
                        "criteria": criteria.model_dump(mode="json"),
                        "data": {"symbols": symbols, "prices": prices, "count": len(symbols)},
                    })
                    if listener.done():
                        listener.result()
                await asyncio.sleep(FILTER_INTERVAL)
        finally:
            listener.cancel()
    except WebSocketDisconnect:
        logger.info("Filter WS disconnected")
    except Exception:
        logger.exception("Filter WS error")
        await websocket.close(code=1011, reason="Internal server error")


# ---------------------------------------------------------------------------
# Real-time streams (TradingView-like, via WebSocketManager)
# ---------------------------------------------------------------------------
@router.websocket("/stream/{symbol}/{timeframe}")
async def websocket_stream_endpoint(
    websocket: WebSocket,
    symbol: str,
    timeframe: str,
    market: str = Query("crypto"),
    indicators: Optional[str] = Query(None),
    strategy: Optional[str] = Query(None),
):
    """Live stream for one symbol/timeframe (price, indicators, signals, status)."""
    initialize_websocket_services()
    try:
        await manager.handle_stream_connection(
            websocket,
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            indicators_config=indicators,
            strategy_config=strategy,
        )
    except WebSocketDisconnect:
        logger.info("Stream WS disconnected: %s (%s)", symbol, timeframe)
    except Exception:
        logger.exception("Stream WS error: %s (%s)", symbol, timeframe)


@router.get("/stream/active")
async def get_active_streams():
    """List currently active real-time streams."""
    initialize_websocket_services()

    if manager.stream_handler:
        return {
            "success": True,
            "data": manager.stream_handler.get_stream_info(),
            "timestamp": _utcnow_iso(),
        }

    return {
        "success": False,
        "message": "Stream handler not initialized",
        "data": {},
    }


@router.post("/stream/start")
async def start_stream(
    symbol: str,
    timeframe: str,
    market: str = "crypto",
    indicators: Optional[str] = None,
    strategy: Optional[str] = None,
):
    """Start a real-time stream via REST."""
    initialize_websocket_services()

    if not manager.stream_handler:
        return {"success": False, "message": "Stream handler not initialized"}

    try:
        indicators_config = json.loads(indicators) if indicators else []
        strategy_config = json.loads(strategy) if strategy else None

        stream_id = await manager.stream_handler.start_stream(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            indicators_config=indicators_config,
            strategy_config=strategy_config,
        )
        return {
            "success": True,
            "message": f"Stream started for {symbol} ({timeframe})",
            "stream_id": stream_id,
            "info": manager.stream_handler.get_stream_info(stream_id),
        }
    except json.JSONDecodeError:
        logger.warning("Invalid JSON indicators/strategy passed to /stream/start")
        return {"success": False, "message": "Invalid JSON in indicators/strategy parameters"}
    except Exception:
        logger.exception("Failed to start stream for %s", symbol)
        return {"success": False, "message": "Failed to start stream"}


@router.post("/stream/stop/{stream_id}")
async def stop_stream(stream_id: str):
    """Stop a specific stream."""
    initialize_websocket_services()

    if not manager.stream_handler:
        return {"success": False, "message": "Stream handler not initialized"}

    try:
        success = await manager.stream_handler.stop_stream(stream_id)
    except Exception:
        logger.exception("Failed to stop stream %s", stream_id)
        return {"success": False, "message": "Failed to stop stream", "stream_id": stream_id}

    return {
        "success": success,
        "message": f"Stream {stream_id} {'stopped' if success else 'not found'}",
        "stream_id": stream_id,
    }
