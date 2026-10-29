import asyncio
import websockets
import json
from datetime import datetime

async def test_market_overview():
    uri = "ws://localhost:8000/ws/market-overview"
    filename = "market_overview_stream.txt"

    # فتح الملف بشكل عادي خارج الـ async with
    file = open(filename, "a", encoding="utf-8")

    async with websockets.connect(uri) as ws:
        print("📊 Connected to Market Overview WebSocket")

        while True:
            try:
                msg = await ws.recv()
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # محاولة تحويله ل JSON
                try:
                    data = json.loads(msg)
                    line = f"[{timestamp}] {json.dumps(data)}\n"
                    print(f"[{timestamp}] {json.dumps(data, indent=2)}")
                except json.JSONDecodeError:
                    line = f"[{timestamp}] Raw: {msg}\n"
                    print(f"[{timestamp}] Raw message: {msg}")

                # اكتب السطر في الملف
                file.write(line)
                file.flush()  # يضمن الكتابة الفورية

            except websockets.ConnectionClosed:
                print("❌ Market overview WebSocket closed")
                break

    file.close()  # اغلق الملف بعد انتهاء الاتصال

asyncio.run(test_market_overview())
