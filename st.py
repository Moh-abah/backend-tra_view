import asyncio
import websockets
import json
from datetime import datetime

async def test_signals():
    uri = "ws://localhost:8000/ws/signals"  # رابط الـ WebSocket الخاص بالإشارات
    filename = "signals_stream.txt"

    # إعداد الاتصال
    file = open(filename, "a", encoding="utf-8")

    async with websockets.connect(uri) as ws:
        print("🔔 Connected to Signals WebSocket")

        # إعدادات الاختبار
        config = {
            "symbols": ["BTCUSDT", "ETHUSDT"],   # الرموز التي تريد اختبارها
            "timeframe": "1h",                   # الإطار الزمني
            "market": "crypto",                  # نوع السوق
            "indicators": [
                {"name": "rsi", "params": {"length": 14}},
                {"name": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}
            ],
            "strategy": "basic_strategy"         # اسم الاستراتيجية
        }

        # إرسال إعدادات الاختبار
        await ws.send(json.dumps(config))
        print("📤 Configuration sent to server")

        try:
            while True:
                msg = await ws.recv()
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                try:
                    data = json.loads(msg)
                    line = f"[{timestamp}] {json.dumps(data)}\n"
                    print(f"[{timestamp}] Signal received:\n{json.dumps(data, indent=2)}")
                except json.JSONDecodeError:
                    line = f"[{timestamp}] Raw: {msg}\n"
                    print(f"[{timestamp}] Raw message: {msg}")

                # كتابة البيانات في الملف
                file.write(line)
                file.flush()

        except websockets.ConnectionClosed:
            print("❌ Signals WebSocket closed")

    file.close()

if __name__ == "__main__":
    asyncio.run(test_signals())
