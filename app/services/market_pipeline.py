# trading_backend/app/services/market_pipeline.py
import asyncio
from datetime import datetime
from app.providers.binance_market_stream import stream_all_market
from app.services.candle_aggregator import CandleAggregator

aggregator = CandleAggregator()

async def process_market_stream():
    async for msg in stream_all_market():
        for tick in msg["data"]:
            symbol = tick["symbol"]
            price = tick["price"]
            volume = tick["volume"]
            timestamp = datetime.utcnow()  # يمكن استخدام الوقت من الباينانس إذا متاح

            # توليد الشمعة لكل فريم نريده، مثلا 1m و 5m
            for timeframe in ["1m", "5m"]:
                candle = aggregator.add_tick(symbol, price, volume, timestamp, timeframe)
                if candle:
                    # هنا ترسل الشمعة المكتملة للـ ChartManager
                    print(f"New candle: {symbol} {timeframe} {candle}")
