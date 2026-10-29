# trading_backend/app/services/chart_manager.py
import asyncio
from typing import Dict, List, Optional
import pandas as pd
from app.services.indicators import apply_indicators, IndicatorConfig

class ChartManager:
    def __init__(self):
        # كل رمز لديه فريمات متعددة، وكل فريم يحوي قائمة الشموع وDataFrame
        self.candles: Dict[str, Dict[str, Dict]] = {}  # symbol -> timeframe -> {"data": [], "dataframe": pd.DataFrame}
        self.subscribers: List[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        """لـ WebSocket clients"""
        q = asyncio.Queue()
        self.subscribers.append(q)
        return q

    async def broadcast(self, message: dict):
        for q in self.subscribers:
            await q.put(message)

    async def update_candle(
        self,
        symbol: str,
        timeframe: str,
        candle: dict,
        indicators_config: Optional[List[Dict]] = None,
        parallel: bool = True,
        use_cache: bool = True
    ):
        # تهيئة البنية لكل رمز وفريم
        if symbol not in self.candles:
            self.candles[symbol] = {}
        if timeframe not in self.candles[symbol]:
            self.candles[symbol][timeframe] = {
                "data": [],
                "dataframe": pd.DataFrame()
            }

        candle_entry = self.candles[symbol][timeframe]
        candle_entry["data"].append(candle)

        # تحديث DataFrame لكل الفريم
        df = pd.DataFrame(candle_entry["data"])
        candle_entry["dataframe"] = df

        # تطبيق المؤشرات
        if indicators_config:
            indicators_result = apply_indicators(
                dataframe=df,
                indicators_config=indicators_config,
                parallel=parallel,
                use_cache=use_cache
            )
        else:
            indicators_result = {}

        # تجهيز الرسالة للبث
        message = {
            "type": "candle_update",
            "symbol": symbol,
            "timeframe": timeframe,
            "candle": candle,
            "indicators": indicators_result
        }

        # بث الرسالة لكل المشتركين
        await self.broadcast(message)

    def get_latest_dataframe(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """الحصول على DataFrame للفريم الأخير"""
        if symbol in self.candles and timeframe in self.candles[symbol]:
            return self.candles[symbol][timeframe]["dataframe"]
        return None
