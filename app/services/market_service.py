# app/services/market_service.py
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

from app.markets.candle_builder import CandleBuilder
from app.markets.candle_store import CandleStore
from app.markets.indicator_scheduler import IndicatorScheduler
from app.chart.chart_hub import ChartHub
from app.chart.broadcaster import IndicatorBroadcaster
from app.services.indicators import apply_indicators
from app.providers.binance_market_stream import stream_all_market
from app.chart.chart_session import ChartSession

class MarketService:
    """خدمة مركزية لإدارة السوق والرسوم البيانية"""
    
    def __init__(self, max_candles: int = 1000):
        # المكونات الأساسية
        self.candle_builder = CandleBuilder()
        self.candle_store = CandleStore(max_candles)
        self.indicator_scheduler = IndicatorScheduler(self.candle_store)
        self.chart_hub = ChartHub()
        self.broadcaster = IndicatorBroadcaster(self.indicator_scheduler, self.chart_hub)
        
        # الربط بين المكونات
        self.candle_builder.on_candle_close(self.indicator_scheduler.on_candle_close)
        self.indicator_scheduler.set_on_update(self.broadcaster.broadcast_last)
        
        # حالة النظام
        self.is_running = False
        
    def start_market_stream(self):
        """بدء استقبال بيانات السوق"""
        if not self.is_running:
            self.is_running = True
            asyncio.create_task(self._process_market_stream())
    
    async def _process_market_stream(self):
        """معالجة تدفق بيانات السوق"""
        async for msg in stream_all_market():
            for tick in msg["data"]:
                symbol = tick["symbol"]
                price = tick["price"]
                volume = tick["volume"]
                timestamp = datetime.utcnow()
                
                # معالجة التيك لجميع الأطر الزمنية المطلوبة
                for timeframe in ["1m", "5m", "15m", "1h", "4h", "1d"]:
                    self.candle_builder.process_tick(
                        symbol=symbol,
                        timeframe=timeframe,
                        price=price,
                        volume=volume,
                        timestamp=timestamp
                    )
    
    async def register_chart_client(
        self,
        symbol: str,
        timeframe: str,
        indicators: List[Dict]
    ) -> ChartSession:
        """تسجيل عميل للرسوم البيانية"""
        # تسجيل المؤشرات
        self.indicator_scheduler.register_indicators(
            symbol=symbol,
            timeframe=timeframe,
            indicators=indicators
        )
        
        # الحصول على الجلسة
        session = self.chart_hub.get_session(symbol, timeframe)
        
        # إرسال البيانات الحالية (إن وجدت)
        key = f"{symbol}:{timeframe}"
        if key in self.indicator_scheduler.results_cache:
            data = self.indicator_scheduler.results_cache[key]
            snapshot = {
                "type": "snapshot",
                "symbol": symbol,
                "timeframe": timeframe,
                "candle": data["last_candle"],
                "indicators": data["indicators"]
            }
            await session.broadcast(snapshot)
        
        return session
    
    def get_candles_dataframe(
        self,
        symbol: str,
        timeframe: str,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """الحصول على الشموع كـ DataFrame"""
        df = self.candle_store.to_dataframe(symbol, timeframe)
        if limit and not df.empty:
            return df.tail(limit)
        return df

# إنشاء نسخة وحيدة من الخدمة
market_service = MarketService()