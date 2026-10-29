# app/websocket/signals_ws.py
"""
WebSocket لبث إشارات التداول اللحظية.

- جلسة قاعدة بيانات واحدة لكل اتصال تُغلق دائماً (async with).
- تقييم كل رمز داخل try/except مستقل حتى لا يُسقط رمز واحد الحلقة.
- حد أقصى 10 رموز لكل اتصال.
"""

import asyncio
import logging

import pandas as pd
from fastapi import WebSocket, WebSocketDisconnect

from app.database import AsyncSessionLocal
from app.services.data_service import DataService
from app.services.signals.candle_tracker import CandleStateTracker
from app.services.signals.engine import SignalEngine
from app.services.signals.state import SignalStateManager

logger = logging.getLogger(__name__)

MAX_SYMBOLS = 10
POLL_INTERVAL_SECONDS = 30
CANDLE_LIMIT = 50

signal_engine = SignalEngine()
candle_tracker = CandleStateTracker()
signal_state = SignalStateManager()


def _last_candle_time(df: pd.DataFrame):
    """استخراج وقت آخر شمعة من DataFrame بشكل دفاعي."""
    if "time" in df.columns:
        raw = df.iloc[-1]["time"]
    else:
        raw = df.index[-1]
    try:
        return pd.to_datetime(raw)
    except Exception:
        return raw


async def signals_websocket(websocket: WebSocket):
    await websocket.accept()

    try:
        # 1) استقبال التكوين من العميل
        config = await websocket.receive_json()

        symbols = [str(s).upper() for s in (config.get("symbols") or [])][:MAX_SYMBOLS]
        timeframe = str(config.get("timeframe", "1m"))
        market = str(config.get("market", "crypto"))
        indicators = config.get("indicators") or []
        strategy = config.get("strategy")

        if not symbols:
            await websocket.send_json({"type": "error", "message": "No symbols provided"})
            return

        logger.info("Signals WS: %d symbols | timeframe=%s | market=%s",
                    len(symbols), timeframe, market)
        await websocket.send_json({
            "type": "subscribed",
            "symbols": symbols,
            "timeframe": timeframe,
            "market": market,
        })

        # 2) جلسة DB واحدة تُغلق دائماً
        async with AsyncSessionLocal() as db:
            data_service = DataService(db)

            # 3) حلقة الاستقصاء
            while True:
                for symbol in symbols:
                    try:
                        df = await data_service.get_latest_candles(
                            symbol=symbol,
                            timeframe=timeframe,
                            market=market,
                            limit=CANDLE_LIMIT,
                        )

                        if df is None or df.empty:
                            continue

                        last_time = _last_candle_time(df)
                        if not candle_tracker.is_new_candle(symbol, timeframe, last_time):
                            continue  # لم تغلق شمعة جديدة بعد

                        signals = await signal_engine.evaluate(
                            symbol=symbol,
                            timeframe=timeframe,
                            dataframe=df,
                            indicators_config=indicators,
                            strategy_config=strategy,
                        )

                        for sig in signals:
                            signal_type = sig.get("signal_type")
                            if signal_type and signal_state.should_emit(
                                symbol, signal_type, sig.get("timestamp")
                            ):
                                await websocket.send_json(sig)

                    except WebSocketDisconnect:
                        raise
                    except Exception:
                        # رمز واحد لا يُسقط باقي الرموز
                        logger.exception("Signals WS: خطأ أثناء تقييم %s", symbol)
                        continue

                await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except WebSocketDisconnect:
        logger.info("Signals WS: client disconnected")
    except Exception:
        logger.exception("Signals WS: خطأ غير متوقع")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
