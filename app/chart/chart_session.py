# app/chart/chart_session.py
from typing import List
from fastapi import WebSocket

class ChartSession:
    def __init__(self, symbol: str, timeframe: str):
        self.symbol = symbol
        self.timeframe = timeframe
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, payload: dict):
        for ws in self.connections.copy():
            try:
                await ws.send_json(payload)
            except:
                self.disconnect(ws)
