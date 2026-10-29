# trading_backend\app\providers\binance_market_streamca.py
import json
import websockets
from datetime import datetime

BINANCE_ALL_TICKERS = "wss://stream.binance.com:9443/ws/!ticker@arr"

async def stream_all_marketca():
    async with websockets.connect(BINANCE_ALL_TICKERS) as ws:
        async for msg in ws:
            data = json.loads(msg)
            yield {
                "type": "market_overview",
                "time": int(datetime.utcnow().timestamp() * 1000), 
                "data": [
                    {
                        "symbol": d["s"],
                        "price": float(d["c"]),
                        "change24h": float(d["P"]),
                        "volume": float(d["v"]),
                    }
                    for d in data
                ]
            }
