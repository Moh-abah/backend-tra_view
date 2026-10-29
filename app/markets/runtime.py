# app/market/runtime.py
from app.markets.candle_builder import CandleBuilder
from app.markets.candle_store import CandleStore
from app.markets.indicator_scheduler import IndicatorScheduler
from app.chart.broadcaster import IndicatorBroadcaster

candle_builder = CandleBuilder()
candle_store = CandleStore()
indicator_scheduler = IndicatorScheduler(candle_store)


broadcaster = IndicatorBroadcaster(indicator_scheduler)


candle_builder.on_candle_close(
    indicator_scheduler.on_candle_close
)


indicator_scheduler.set_on_update(
    lambda symbol, timeframe:
        broadcaster.broadcast_last(symbol, timeframe)
)