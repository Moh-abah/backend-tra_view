# 🚑 ترقيع الجولة 6.5 — بث نظرة السوق (ملف واحد)

**التاريخ:** 2026-10-30
**الحالة:** ✅ مُصلَّح ومُختبر بالقياس الحي (تفاصيل تحت)

---

## 1) المشكلة المكتشفة بالإنتاج اليوم (دليل الاختبار)

اختبار `ws://161.97.73.254:8000/ws/market-overview` لمدة 90 ثانية:
```
message_types: {'connection_established': 1, 'ping': 3}
VERDICT: FAIL   ← صفر رسائل market_overview في 90 ثانية
```
بينما قياس الروابط من شبكة خارجية بنفس اللحظة:
```
✅ wss://data-stream.binance.vision/ws/!miniTicker@arr   → أول إطار 1.29ث (14KB)
✅ wss://stream.binance.com:9443/ws/!miniTicker@arr      → أول إطار 1.03ث (18KB)
⚠️ wss://stream.binance.com:9443/ws/!ticker@arr          → فُتح ثم لا إطار في 20ث (تعلق صامت)
```

## 2) السبب الجذري (ثغرة معمارية دقيقة)

- ترقية الجولة 6 جعلت الروابط تدور **عند إعادة إنشاء المولّد فقط** (اتصال عميل جديد).
- لكن راوتر `/ws/market-overview` يستهلك مولّداً **واحداً** بـ `async for`:
  لو علِق الرابط **بعد الفتح الناجح** (وهذا بالضبط ما تفعله `!ticker@arr`):
  المولّد ينتظر أول إطار **للأبد**، ولا يوجد من يدير الرابط داخلياً.
- النتيجة: العميل يتصل → رسالة ترحيب → صمت مطلق مهما انتظر.

## 3) الإصلاح (ملف واحد: `app/providers/binance_market_stream.py`)

1. **Watchdog أول إطار داخل المولّد نفسه (12 ثانية):** إن لم يصل إطار نغلق
   وننتقل للرابط التالي تلقائياً — بلا تدخل من أي مستهلك.
2. **الدوران الداخلي مستمر للأبد:** انقطاع بعد بث ناجح → ندير للرابط التالي
   أيضاً (لا نعيد الرابط الذي انقطع للتو).
3. **كل المستهلكين الأربعة يستفيدون فوراً:** websocket.py / live_stream.py /
   market_pipeline.py / market_service.py — التوقيع وشكل الرسائل كما هما حرفياً.
4. توافق كامل مع شبكة الأمان الخارجية في live_stream (15ث > 12ث داخلي —
   الداخلي يشتغل أولاً، والخارجي يبقى احتياطاً).

## 4) أدلة الاختبار بعد الإصلاح (محلي على نفس ظروف الشبكة)

| الاختبار | النتيجة |
|---|---|
| بث حقيقي عادي | أول payload خلال **0.54 ث** — 125 رمزاً (BTCUSDT ضمنها)، `time` بالملي ثانية ✅ |
| محاكاة التعليق الصامت (الرابط العالق أولاً ثم الرابط الصحيح) | "no first frame in 12s — rotating endpoint" → انتقال تلقائي → أول payload خلال **18 ث** إجمالاً (كان: للأبد) ✅ |
| توافق الواجهة لكل المستهلكين (stream_all_market / last_endpoint / last_open_ok) | ✅ |

## 5) النشر (ملف واحد + إعادة تشغيل)

```bash
# على الخادم 161.97.73.254:
docker cp binance_market_stream.py trading-backend:/app/app/providers/binance_market_stream.py
docker restart trading-backend

# أو إذا كان المشروع من مجلد على الخادم:
cp app/providers/binance_market_stream.py /path/to/trading-backend/app/providers/
cd /path/to/trading-backend && docker compose restart backend
```

## 6) تحقق فوري بعد النشر

```bash
# في السجل — المتوقع خلال ثوانٍ من أول اتصال عميل:
docker logs --tail 30 trading-backend | grep -E "Market ticker"
# 🟢 Market ticker WS connected: wss://data-stream.binance.vision/ws/!miniTicker@arr
# 📡 Market ticker first frame: 125 symbols (14KB)
```
وأي عميل يتصل بـ `/ws/market-overview` يستقبل أول دفعة خلال ~1-2 ثانية.

## 7) رسالة لوكيل الفرونت

- لا شيء يتغير عندك إطلاقاً: نفس نقطة `/ws/market-overview` ونفس شكل الرسائل.
- بعد نشر هذا الملف، نظرة السوق ستعود للبث الحي (~تحديث كل 7 ثوانٍ كما هو مضبوط).
- إن ظهرت قائمة الرموز أصغر من السوق الكامل فهذا طبيعي (miniTicker يبث المتغير فعلياً).

— وكيل الباكند، الجولة 6.5.
