# app/chart/broadcaster.py
from app.chart.chart_hub import chart_hub

class IndicatorBroadcaster:
    def __init__(self, scheduler, hub):
        self.scheduler = scheduler
        self.hub = hub
    
    async def broadcast_last(self, symbol: str, timeframe: str):
        key = f"{symbol}:{timeframe}"
        if key not in self.scheduler.results_cache:
            return
        
        data = self.scheduler.results_cache[key]
        
        payload = {
            "type": "delta",
            "symbol": symbol,
            "timeframe": timeframe,
            "candle": data["last_candle"],
            "indicators": data["indicators"]
        }
        
        # استخدام الـ hub المحقن بدلاً من المتغير العام
        session = self.hub.get_session(symbol, timeframe)
        await session.broadcast(payload)