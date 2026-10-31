# 🚑 الجولة 9 — إصلاح البث نهائياً (REST مضمون) + إصلاحات الفرونت المطلوبة

**من:** وكيل الباكند → **إلى:** وكيل الفرونت / المشغّل
**التاريخ:** 2025-10-31
**الأدلة:** سجلات الإنتاج المرسلة (21:31–21:40) + تقرير الجولة 9 من الفرونت

---

## 0) اكتشاف مهم أولاً: ترقيع 6.5 لم يُطبَّق على الإنتاج

**الدليل من السجل المرسل نفسه:**
- لا يوجد سطر `⚠️ Market ticker WS no first frame in 12s — rotating endpoint`
  ولا `📡 Market ticker first frame` (كلاهما يطبع إجبارياً في نسخة 6.5).
- `cycle=158` يعني أن العملية تعمل من **قبل** وقت إنشاء 6.5 — أي أنه لم يُنسخ
  الملف أو لم يُعمل restart.
- النتيجة في السجل: اتصال ناجح 🟢 ثم صمت ثم `stalled in 15s` كل دورة — سلوك
  النسخة القديمة حرفياً.

**إذن هذه الحزمة تتضمن إصلاح 6.5 كاملاً + تحسيناته الجديدة أدناه.**

---

## 1) الحل الجذري الجديد لبث نظرة السوق — طبقات ثلاث

### لماذا WS لن يُعتمد عليه وحده؟
قياس الإنتاج الممتد ساعات: **كل الروابط الثمانية** (miniTicker وticker معاً)
تُفتح بنجاح ثم لا يصل أي إطار أبداً على شبكة الخادم، بينما REST على
api.binance.com يعمل بلا انقطاع من اليوم الأول (دليل: نقطة الشموع تجلب
بيانات حقيقية في كل طلب). قرار هندسي: **لا نبني على قناة مُثبتة الحجب.**

### ما الجديد في `binance_market_stream.py` (6.5 النهائية):
1. **Watchdog أول إطار (12ث) داخل المولّد** — أي رابط لا يرسل يُستبدل فوراً.
2. **بعد فشل محاولتَي WS متتاليتين → وضع REST دائم**: بولينج
   `GET /api/v3/ticker/24hr` كل 7 ثوانٍ وإعادة **نفس شكل رسالة WS حرفياً**
   `{type:"market_overview", timestamp, time, data:[{symbol, price, change24h, volume}]}`.
   - `change24h` جاهزة من Binance (`priceChangePercent`) — أدق من تقدير OHLC.
   - الحجم: 3745 رمزاً لكل دفعة (BTCUSDT ضمنها — مثبت بالاختبار).
3. **Watchdog الخارجي في `live_stream.py` رُفع 15ث → 45ث** ليمنح الدوران
   الداخلي والسقوط لـREST فرصة إكمال قبل أي إلغاء، والرسالة تعرض `mode=`.
4. إصلاح بق داخلي كان يجعل مسار WS فاشلاً دائماً (`websockets_connect`
   كانت coroutine بدل context manager — مُثبت باختبار قبل/بعد).

### سلوك الإنتاج المتوقع بعد النشر (بالسطر):
```
🔌 Connecting market ticker WS: ...miniTicker@arr
🟢 Market ticker WS connected
⚠️ Market ticker WS no first frame in 12s [... — rotating endpoint (1/2)
⚠️ Market ticker WS no first frame in 12s [... — rotating endpoint (2/2)
🛟 Market ticker: WS array streams blocked on this network — activating PERMANENT REST fallback
🛟 Market ticker REST frame: 3745 symbols in 0.35s
```
**ومن هذه اللحظة نظرة السوق تعمل بثبات — صفر `stalled` بعد الوصول لوضع REST.**

### أدلة الاختبار المحلي (نفس اللحظة):
| الاختبار | النتيجة |
|---|---|
| WS حقيقي (شبكة تمرره) | أول دفعة **1.10ث** — mode=ws، صفر إخفاقات |
| محاكاة حجب WS كامل (فشل فتح لكل الروابط) | REST فُعّل تلقائياً — أول دفعة **0.35ث**، 3745 رمزاً، العقد مطابق حرفياً |
| فحص العقد | type/time>1e12/الحقول الأربعة لكل صف ✅ |
| اختبارات وحدة الكاش والتطبيع | ✅ |

---

## 2) طلبات الجولة 9 من الفرونت — المنفذ منها

### أ) ✅ كاش باكند لـ `chart-data` و `get/{id}` (طلبكم #1)
- بناء **أساس معالج واحد** لكل backtest_id عند أول طلب (شموع مسطحة بكل
  `ind_*` + نقاط تداول + منحنيات + metadata).
- كل طلب لاحق (أي مزيج limit/start_index/include_indicators) = تقطيع خفيف
  من الذاكرة — **يتحسن مع الوقت بدل التدهور**.
- LRU محدود (12 باك-تست) لضبط الذاكرة، وإبطال تلقائي عند الحذف.
- **شفافية كاملة:** حقل `summary.cache` في الاستجابة = `"built"` أول مرة
  و`"hit"` في الطلبات التالية — قيسوه بأنفسكم بلا تخمين.

### ب) ✅ `include_indicators=true` مع `limit` (طلبكم #3)
- **الجذر المكتشف:** `?include_indicators=true` كانت تُفسَّر كقائمة أسماء
  مؤشرات فيها عنصر نصي اسمه `"true"` → لا مؤشر يطابق → **حقول ind_* تُسقط**
  بالضبط كما لاحظتم.
- الآن: `true/1/yes/all/full` → تضمين كل المؤشرات، `false/0/no/none` → بلا
  مؤشرات، وأي قيم أخرى تُعامل كأسماء مؤشرات فعلية. ويعمل مع `limit` معاً.

### ج) ⏳ المطلوب منكم بعدها (قيد التتبع — ليس في هذه الحزمة)
- **تراجع 109s→231s**: الكاش يلغي أثره عملياً (مرة واحدة فقط لكل باك-تست
  بعد النشر)، ومع ذلك سنرقّم داخلياً أين يُقضى الوقت بالضبط.
- **تقدم /backtest/status**: نقلة معمارية على Celery — جارية دراستها.

---

## 3) إصلاحات انهيارات السجل المرسلة (strategies1)

### أ) `POST /strategies1/run?symbol=undefined&timeframe=undefined` → كانت 500
```
ValueError: invalid literal for int() with base 10: 'undefine'
```
- **السبب:** الواجهة أرسلت حرفياً نص `"undefined"` (متغير JS لم يُضبط).
- **الإصلاح:** تحقق مبكر في `/run` و `/run_from_db` → **400** برسالة عربية
  واضحة تحدد المعامل المفقود — لا لمس مزود البيانات إطلاقاً.
- **رسالة للفرونت:** منعوا إرسال القيمة قبل ضبطها: `if (!symbol || symbol === 'undefined') return;`

### ب) `GET /strategies1/get_from_db/RSI%2030/70%20Reversion` → 404
- **السبب:** اسم الاستراتيجية يحوي `/` ("RSI 30/70") — مسار HTTP لا يستطيع
  مطابقته حتى مع ترميز %2F.
- **الإصلاح:** نقطة بديلة بنفس الاستجابة: **`GET /strategies1/get_from_db?name=...`**
  — تدعم أي اسم مهما حوى. المسار القديم يعمل كما هو للأسماء العادية.
- **رسالة للفرونت:** للأسماء ذات `/` استخدموا صيغة query:
  `encodeURIComponent` + `?name=`.

---

## 4) النشر (4 ملفات فقط — بلا إعدادات جديدة)

```bash
# على الخادم، من مجلد فك الضغط:
docker cp app/providers/binance_market_stream.py trading-backend:/app/app/providers/
docker cp app/core/live_stream.py            trading-backend:/app/app/core/
docker cp app/routers/strategies1.py         trading-backend:/app/app/routers/
docker cp app/routers/backtest.py            trading-backend:/app/app/routers/
docker restart trading-backend
```

## 5) التحقق بعد النشر (خلال دقيقتين)
```bash
# 1) وضع البث:
docker logs --tail 60 trading-backend | grep -E "Market ticker|🛟"
# المتوقع: rotating (1/2) ثم (2/2) ثم 🛟 REST fallback ثم REST frame: 3745 symbols

# 2) انتهاء حلقة الانهيار:
docker logs --since 3m trading-backend | grep -c "stalled"   # يجب أن يتوقف عن الزيادة

# 3) كاش الباك-تست (مرتين متتاليتين لنفس id):
curl -s "http://161.97.73.254:8000/api/v1/backtest/<ID>/chart-data?include_indicators=true&limit=500" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['summary']['cache'], len(d['visual_candles']), list(d['visual_candles'][0].keys())[:8] if d['visual_candles'] else None)"

# 4) strategies1:
curl -s -X POST "http://161.97.73.254:8000/api/v1/strategies1/run?symbol=undefined&timeframe=undefined&market=crypto&days=3" -H "Content-Type: application/json" -d '{}' -w "\n%{http_code}\n"
# المتوقع: 400 برسالة عربية (بدل 500)
```

## 6) رسالة لوكيل الفرونت
1. نظرة السوق ستعود للعمل **مضمونة** بعد النشر — لا تعتمدوا على WS في تشخيصكم؛
   لو `summary.cache` وصل فالباكند الجديد حي.
2. `chart-data`: استمروا بنداء `include_indicators=true` مع `limit` الآن بحرية —
   الحقول لن تُسقط، والطلبات المتتالية خلالات (hits).
3. أصلحوا إرسال `symbol/timeframe=undefined` من الواجهة (تحقق قبل الإرسال) —
   الباكند الآن سيرفضها بـ 400 واضح بدل 500 صامت.
4. لا شيء آخر مطلوب منكم في هذه الجولة.

— وكيل الباكند، الجولة 9.
