# import asyncio
# import json
# import websockets
# from datetime import datetime
# import threading
# import os

# # الإعدادات
# WS_URL = "ws://localhost:8000/ws/chart/ETHUSDT"
# OUTPUT_FILE = "chart_data.json"

# # قائمة جميع المؤشرات المتوفرة في مكتبتك
# INDICATOR_MAP = {
#     "1": {"name": "sma", "type": "trend", "params": {"period": 20, "source": "close"}},
#     "2": {"name": "ema", "type": "trend", "params": {"period": 20, "source": "close"}},
#     "3": {"name": "rsi", "type": "momentum", "params": {"period": 25, "source": "close", "overbought": 77, "oversold": 33}},
#     "4": {"name": "macd", "type": "trend", "params": {"fastPeriod": 12, "slowPeriod": 26, "signalPeriod": 9}},
#     "5": {"name": "bb", "type": "volatility", "params": {"period": 20, "stdDev": 2, "source": "close"}},
#     "6": {"name": "stochastic", "type": "oscillators", "params": {"kPeriod": 14, "dPeriod": 3, "slowing": 3}},
#     "7": {"name": "atr", "type": "volatility", "params": {"period": 14}},
#     "8": {"name": "volume", "type": "volume", "params": {"colorUp": "#26a69a", "colorDown": "#ef5350"}},
#     "9": {"name": "obv", "type": "volume", "params": {"color": "#2196F3"}},
# }

# active_indicators = set()

# async def send_indicator(ws, choice: str):
#     """إرسال طلب إضافة مؤشر بناءً على اختيار المستخدم"""
#     indicator_config = INDICATOR_MAP.get(choice)
#     if not indicator_config:
#         return

#     payload = {
#         "action": "add_indicator",
#         "indicator": indicator_config
#     }
#     await ws.send(json.dumps(payload))
#     active_indicators.add(indicator_config["name"])
#     print(f"\n🚀 [SENT] Request to add: {indicator_config['name'].upper()}")

# async def chart_ws_to_file():
#     # تنظيف ملف المخرجات عند البدء
#     if os.path.exists(OUTPUT_FILE):
#         os.remove(OUTPUT_FILE)

#     async with websockets.connect(WS_URL) as ws:
#         # 1. الاشتراك الأولي
#         init_payload = {
#             "timeframe": "1m",
#             "market": "crypto",
#             "indicators": []
#         }
#         await ws.send(json.dumps(init_payload))
#         print("✅ Connected to WebSocket. Subscription sent.")
#         print("--- Commands: Press 1-9 to add indicator ---")
#         print("1: SMA, 2: EMA, 3: RSI, 4: MACD, 5: Bollinger Bands")
#         print("6: Stochastic, 7: ATR, 8: Volume, 9: OBV")

#         loop = asyncio.get_running_loop()

#         # 2. خيط (Thread) لقراءة مدخلات المستخدم دون تعطيل الاستقبال
#         def input_thread(loop, ws):
#             while True:
#                 user_input = input("\nEnter 1-9 to add indicator (or 'all' to add all): ")
#                 if user_input in INDICATOR_MAP:
#                     asyncio.run_coroutine_threadsafe(send_indicator(ws, user_input), loop)
#                 elif user_input.lower() == 'all':
#                     # إضافة جميع المؤشرات تلقائياً
#                     for choice in INDICATOR_MAP.keys():
#                         asyncio.run_coroutine_threadsafe(send_indicator(ws, choice), loop)
#                 else:
#                     print("❌ Invalid choice. Use 1-9 or 'all'.")

#         threading.Thread(target=input_thread, args=(loop, ws), daemon=True).start()

#         # 3. حلقة استقبال البيانات
#         try:
#             with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
#                 while True:
#                     message = await ws.recv()
#                     data = json.loads(message)
                    
#                     # حفظ في الملف
#                     f.write(json.dumps(data) + "\n")
#                     f.flush()

#                     msg_type = data.get("type")
                    
#                     # عرض النتائج في الكونسول بشكل مختصر وجميل
#                     if msg_type == "price_update":
#                         symbol = data.get("symbol")
#                         price = data.get("live_candle", {}).get("close")
#                         indicators = data.get("indicators", {})
                        
#                         # سطر ملخص للثمن والمؤشرات
#                         if indicators:
#                             indicator_strs = []
#                             for k, v in indicators.items():
#                                 if v.get('values') and len(v['values']) > 0:
#                                     last_val = v['values'][-1]
#                                     if isinstance(last_val, (int, float)):
#                                         indicator_strs.append(f"{k.upper()}: {last_val:.2f}")
#                                     else:
#                                         indicator_strs.append(f"{k.upper()}: {last_val}")
                            
#                             indicator_str = " | ".join(indicator_strs)
#                             if indicator_str:
#                                 print(f"\r[LIVE] {symbol} @ {price:.2f} | {indicator_str}", end="", flush=True)

#                     elif msg_type == "candle_close":
#                         print(f"\n\n🔔 [CANDLE CLOSED] New Bar at {data['candle']['time']}")
#                         # عرض نتائج المؤشرات عند الإغلاق
#                         for name, res in data.get("indicators", {}).items():
#                             if res.get('values'):
#                                 val = res['values'][-1]
#                                 if isinstance(val, (int, float)):
#                                     print(f"   ∟ {name.upper()}: {val:.2f}")
#                                 else:
#                                     print(f"   ∟ {name.upper()}: {val}")
#                         print("-" * 50)
                        
#                     elif msg_type == "indicator_added":
#                         print(f"\n✅ [INDICATOR ADDED] {data.get('indicator')}")
#                         if data.get('indicators_results'):
#                             print(f"   Result has {len(data['indicators_results'])} indicators")

#         except websockets.ConnectionClosed:
#             print("\n🔴 Connection closed by server.")
#         except Exception as e:
#             print(f"\n❌ Error: {e}")

# if __name__ == "__main__":
#     try:
#         asyncio.run(chart_ws_to_file())
#     except KeyboardInterrupt:
#         print("\n👋 Client stopped.")

import asyncio
import json
import websockets
from datetime import datetime
import threading
import os

# الإعدادات
WS_URL = "ws://localhost:8000/ws/chart/ETHUSDT"
OUTPUT_FILE = "chart_data.json"

# قائمة جميع المؤشرات المحدثة (إضافة المؤشرات الجديدة 10-13)
INDICATOR_MAP = {
    "1": {"name": "sma", "type": "trend", "params": {"period": 20, "source": "close"}},
    "2": {"name": "ema", "type": "trend", "params": {"period": 20, "source": "close"}},
    "3": {"name": "rsi", "type": "momentum", "params": {"period": 25, "source": "close", "overbought": 77, "oversold": 33}},
    "4": {"name": "macd", "type": "trend", "params": {"fastPeriod": 12, "slowPeriod": 26, "signalPeriod": 9}},
    "5": {"name": "bb", "type": "volatility", "params": {"period": 20, "stdDev": 2, "source": "close"}},
    "6": {"name": "stochastic", "type": "oscillators", "params": {"kPeriod": 14, "dPeriod": 3, "slowing": 3}},
    "7": {"name": "atr", "type": "volatility", "params": {"period": 14}},
    "8": {"name": "volume", "type": "volume", "params": {"colorUp": "#26a69a", "colorDown": "#ef5350"}},
    "9": {"name": "obv", "type": "volume", "params": {"color": "#2196F3"}},
    # المؤشرات الجديدة المضافة
    "10": {"name": "supply_demand", "type": "support_resistance", "params": {"period": 20, "threshold": 2.0}},
    "11": {"name": "volume_climax", "type": "volume", "params": {"period": 20, "std_mult": 2.0}},
    "12": {"name": "harmonic_patterns", "type": "trend", "params": {"depth": 10}},
    "13": {"name": "hv_iv_analysis", "type": "volatility", "params": {"period": 20, "lookback": 252, "current_iv": 25.0}},
}

active_indicators = set()

async def send_indicator(ws, choice: str):
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
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    async with websockets.connect(WS_URL) as ws:
        init_payload = {
            "timeframe": "1m",
            "market": "crypto",
            "indicators": []
        }
        await ws.send(json.dumps(init_payload))
        
        print("✅ Connected to WebSocket.")
        print("--- Standard Indicators ---")
        print("1: SMA, 2: EMA, 3: RSI, 4: MACD, 5: BB, 6: Stoch, 7: ATR, 8: Vol, 9: OBV")
        print("--- New Advanced Indicators ---")
        print("10: Supply & Demand, 11: Volume Climax, 12: Harmonics, 13: HV/IV Analysis")
        print("-" * 50)

        loop = asyncio.get_running_loop()

        def input_thread(loop, ws):
            while True:
                user_input = input("\nEnter choice (1-13) or 'all': ")
                if user_input in INDICATOR_MAP:
                    asyncio.run_coroutine_threadsafe(send_indicator(ws, user_input), loop)
                elif user_input.lower() == 'all':
                    for choice in INDICATOR_MAP.keys():
                        asyncio.run_coroutine_threadsafe(send_indicator(ws, choice), loop)
                else:
                    print("❌ Invalid choice.")

        threading.Thread(target=input_thread, args=(loop, ws), daemon=True).start()

        try:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    
                    f.write(json.dumps(data) + "\n")
                    f.flush()

                    msg_type = data.get("type")
                    
                    if msg_type == "price_update":
                        indicators = data.get("indicators", {})
                        if indicators:
                            # طباعة قيم المؤشرات أو الـ Metadata إذا وجدت
                            for name, res in indicators.items():
                                if "metadata" in res and res["metadata"]:
                                    # تنبيه بوجود بيانات خاصة (مربعات، مثلثات، إلخ)
                                    meta_keys = list(res["metadata"].keys())
                                    print(f"\n✨ [DATA] {name.upper()} sent metadata: {meta_keys}")

                    elif msg_type == "candle_close":
                        print(f"\n🔔 [CANDLE CLOSED] at {data['candle']['time']}")
                        for name, res in data.get("indicators", {}).items():
                            # عرض عدد العناصر في الـ metadata للتأكد من وصولها
                            meta = res.get('metadata', {})
                            if meta:
                                for k, v in meta.items():
                                    count = len(v) if isinstance(v, list) else "1"
                                    print(f"   ∟ {name.upper()} Metadata [{k}]: {count} items found")

        except websockets.ConnectionClosed:
            print("\n🔴 Connection closed.")
        except Exception as e:
            print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(chart_ws_to_file())
    except KeyboardInterrupt:
        print("\n👋 Client stopped.")