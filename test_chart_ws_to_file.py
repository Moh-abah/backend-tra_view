import asyncio
import json
import websockets
from datetime import datetime
import threading
import os

# الإعدادات
WS_URL = "ws://localhost:8000/ws/chart/ETHUSDT"
OUTPUT_FILE = "chart_data.json"

# قائمة المؤشرات المتاحة للتجربة
INDICATOR_MAP = {
    "1": {"name": "rsi", "type": "momentum", "params": {"period": 14}},
    "2": {"name": "ema", "type": "trend", "params": {"period": 20}},
    "3": {"name": "atr", "type": "volatility", "params": {"period": 14}}
}

active_indicators = set()

async def send_indicator(ws, choice: str):
    """إرسال طلب إضافة مؤشر بناءً على اختيار المستخدم"""
    indicator_config = INDICATOR_MAP.get(choice)
    if not indicator_config:
        return

    payload = {
        "action": "add_indicator",
        "indicator": indicator_config
    }
    await ws.send(json.dumps(payload))
    active_indicators.add(indicator_config["name"])
    print(f"\n🚀 [SENT] Request to add: {indicator_config['name'].upper()}")

async def chart_ws_to_file():
    # تنظيف ملف المخرجات عند البدء
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    async with websockets.connect(WS_URL) as ws:
        # 1. الاشتراك الأولي
        init_payload = {
            "timeframe": "1m",
            "market": "crypto",
            "indicators": []
        }
        await ws.send(json.dumps(init_payload))
        print("✅ Connected to WebSocket. Subscription sent.")
        print("--- Commands: Press 1 for RSI, 2 for EMA, 3 for ATR ---")

        loop = asyncio.get_running_loop()

        # 2. خيط (Thread) لقراءة مدخلات المستخدم دون تعطيل الاستقبال
        def input_thread(loop, ws):
            while True:
                user_input = input("\nEnter 1-3 to add indicator: ")
                if user_input in INDICATOR_MAP:
                    asyncio.run_coroutine_threadsafe(send_indicator(ws, user_input), loop)
                else:
                    print("❌ Invalid choice. Use 1, 2, or 3.")

        threading.Thread(target=input_thread, args=(loop, ws), daemon=True).start()

        # 3. حلقة استقبال البيانات
        try:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    
                    # حفظ في الملف
                    f.write(json.dumps(data) + "\n")
                    f.flush()

                    msg_type = data.get("type")
                    
                    # عرض النتائج في الكونسول بشكل مختصر وجميل
                    if msg_type == "price_update":
                        symbol = data.get("symbol")
                        price = data.get("live_candle", {}).get("close")
                        indicators = data.get("indicators", {})
                        
                        # سطر ملخص للثمن والمؤشرات
                        indicator_str = " | ".join([f"{k.upper()}: {v['values'][-1]:.2f}" 
                                                  for k, v in indicators.items() if v.get('values')])
                        
                        print(f"\r[LIVE] {symbol} @ {price:.2f} | {indicator_str}", end="", flush=True)

                    elif msg_type == "candle_close":
                        print(f"\n\n🔔 [CANDLE CLOSED] New Bar at {data['candle']['time']}")
                        # عرض نتائج المؤشرات عند الإغلاق
                        for name, res in data.get("indicators", {}).items():
                            val = res['values'][-1] if res.get('values') else 'N/A'
                            print(f"   ∟ {name.upper()}: {val}")
                        print("-" * 50)

        except websockets.ConnectionClosed:
            print("\n🔴 Connection closed by server.")
        except Exception as e:
            print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(chart_ws_to_file())
    except KeyboardInterrupt:
        print("\n👋 Client stopped.")