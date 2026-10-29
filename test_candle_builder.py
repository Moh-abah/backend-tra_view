# import asyncio
# import json
# import websockets

# WS_URL = "ws://localhost:8000/ws/chart/BTCUSDT"

# async def test_chart_ws():
#     async with websockets.connect(WS_URL) as ws:
#         # إرسال الاشتراك بدون مؤشرات أولاً
#         init_payload = {
#             "timeframe": "1m",
#             "market": "crypto",
#             "indicators": []
#         }
#         await ws.send(json.dumps(init_payload))
#         print("✅ تم إرسال بيانات الاشتراك بدون مؤشرات، في انتظار الرسائل...")

#         try:
#             while True:
#                 message = await ws.recv()
#                 data = json.loads(message)
#                 # نطبع كل تحديث للشارت
#                 print(f"📥 رسالة: {data.get('type')} | الوقت: {data.get('time')} | سعر آخر: {data.get('data', {}).get('live_candle', {}).get('close')}")
#         except websockets.ConnectionClosed:
#             print("🔴 تم إغلاق الاتصال")

# asyncio.run(test_chart_ws())













# import asyncio
# import json
# import websockets

# WS_URL = "ws://localhost:8000/ws/chart/BTCUSDT"

# async def test_chart_ws():
#     async with websockets.connect(WS_URL) as ws:
#         # 1️⃣ إرسال بيانات الاشتراك
#         init_payload = {
#             "timeframe": "1m",
#             "market": "crypto",
#             "indicators": []
#         }
#         await ws.send(json.dumps(init_payload))
#         print("✅ تم إرسال بيانات الاشتراك بدون مؤشرات، في انتظار الرسائل...")

#         try:
#             while True:
#                 message = await ws.recv()
#                 data = json.loads(message)

#                 msg_type = data.get("type")
#                 time = data.get("time")
                
#                 # نحاول الحصول على سعر الشمعة الحية إذا موجود
#                 live_candle = data.get("data", {}).get("live_candle") or data.get("candle")
#                 last_price = live_candle.get("close") if live_candle else None

#                 print(f"📥 رسالة: {msg_type} | الوقت: {time} | سعر آخر: {last_price}")

#         except websockets.ConnectionClosed:
#             print("🔴 تم إغلاق الاتصال")

#         except Exception as e:
#             print(f"❌ خطأ أثناء استقبال الرسائل: {e}")

# # تشغيل الاختبار
# asyncio.run(test_chart_ws())




import asyncio
import json
import websockets

WS_URL = "ws://localhost:8000/ws/chart/BTCUSDT"

async def test_chart_ws():
    async with websockets.connect(WS_URL) as ws:
        # 1️⃣ إرسال بيانات الاشتراك
        init_payload = {
            "timeframe": "1m",
            "market": "crypto",
            "indicators": []
        }
        await ws.send(json.dumps(init_payload))
        print("✅ تم إرسال بيانات الاشتراك بدون مؤشرات، في انتظار الرسائل...")

        try:
            while True:
                message = await ws.recv()
                data = json.loads(message)

                # اطبع الرسالة كاملة كما هي
                print("📥 رسالة كاملة:", json.dumps(data, indent=2, ensure_ascii=False))

        except websockets.ConnectionClosed:
            print("🔴 تم إغلاق الاتصال")

        except Exception as e:
            print(f"❌ خطأ أثناء استقبال الرسائل: {e}")

# تشغيل الاختبار
asyncio.run(test_chart_ws())
