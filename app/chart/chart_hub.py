# app/chart/chart_hub.py
from typing import Dict
from app.chart.chart_session import ChartSession

class ChartHub:
    def __init__(self):
        self.sessions: Dict[str, ChartSession] = {}
    
    def get_session(self, symbol: str, timeframe: str) -> ChartSession:
        key = f"{symbol}:{timeframe}"
        if key not in self.sessions:
            self.sessions[key] = ChartSession(symbol, timeframe)
        return self.sessions[key]