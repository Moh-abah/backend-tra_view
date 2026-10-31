# 📐 الجولة 10 — مؤشرات البنية السعرية (ZigZag / Auto Fib / Auto Trendline)

**من: وكيل الباكند → إلى: المشغّل + وكيل الفرونت**
**التاريخ: 2025-10-31**
**الحزمة: `ROUND10-OVERLAYS.zip`**

---

## 0) القرار المعماري — لماذا الباكند يحسب والفرونت يرسم؟

سؤال "أين تُضاف المؤشرات — الفرونت أم الباكند؟" الجواب الحاسم: **الباكند يحسب، الفرونت يرسم فقط**، للأسباب التالية:

1. **أنتم ستكتبون استراتيجية تداول على هذه المؤشرات الثلاثة في الخطوة القادمة** — محرك الاستراتيجيات والباك-تست يعيشان في الباكند، فالمنطق يجب أن يكون Python قابلاً للاستيراد مباشرة، لا JavaScript معزول في المتصفح.
2. **مصدر حقيقة واحد**: الشارت الحي والباك-تست سيريان نفس القمم/القيعان/المستويات حرفياً — بلا ازدواجية تطبيق (Pine في JS + Pine في Python = كابوس مزامنة).
3. **الكاش**: الحساب ~20ms لكل 1000 شمعة — يُحسب مرة ويُخزَّن، والطلبات المتتالية خلالات صفرية.
4. **أخف حمولة على الأجهزة**: الفرونت يستقبل هندسة جاهزة (نقاط خطوط/مستويات/ملصقات) ويرسمها فقط.

**الترخيص**: ZigZag Channels © LuxAlgo (CC BY-NC-SA 4.0) — العزو محفوظ في رأس الملف؛ المؤشران الآخران MPL-2.0. الاستخدام الداخلي لنظامكم سليم مع حفظ العزو (تم).

---

## 1) ما الجديد — ملفان جديدان + ملفان مرقعان

| الملف | الحالة | الوظيفة |
|---|---|---|
| `app/services/indicators/overlays.py` | **جديد** | المنطق الكامل للمؤشرات الثلاثة — نقل حرفي من Pine إلى Python (دوال نقية بلا DB/شبكة — قابلة للاستيراد من محرك الاستراتيجيات مباشرة) |
| `app/routers/overlays.py` | **جديد** | نقاط REST + كاش TTL 30 ثانية |
| `app/routers/backtest.py` | مرقع | دعم `overlays=` في نقطة chart-data + استيرادات جديدة |
| `app/main.py` | مرقع | تسجيل الراوتر (سطران) |

### المؤشرات الثلاثة (مطابقة حرفية للسكربتات):

1. **Zig Zag Channels [LuxAlgo]** — قمم/قيعان بتأكيد `length` شمعة (افتراضي 100)، خطوط زجزاج + قنوات extremity منقّطة (انحراف أجسام الشموع عن الخط — بارامتريزيشن مطابق حتى "المطّ" الفردي في الأصل) + ملصقات أسعار + إسقاط آخر مقطع لآخر شمعة.
2. **Auto Fib Retracement Alerts** — رجل فيب واحدة حية (مطابق: Pine يحذف الرجل السابقة)، مستويات 0→1.618 بألوان السكربت، هدف 0.618، إشارات Buy/Sell Retrace بنفس منطق الـdebounce (`barssince`) حرفياً.
3. **Auto Trendline [DojiEmoji]** — فراكتالات صارمة (period=10، تأخير التعريف `period+1` شمعة مطابق لـ`[1]` في Pine)، خطوط recent/historical بحد `max_pairs`، تصنيف HH/LH/HL/LL، إسقاط للخط حتى آخر شمعة + تقاطعات `ta.cross` بالتعريف الرسمي (crossover: a>b و a[1]<=b[1]).

> **انحراف موثّق وحيد**: أول رجل فيب في Pine تبدأ من (شمعة 0، سعر 0) لأن `pLast` يُهيَّأ صفراً — نحسبها مطابقةً لكن نوسمها `synthetic_anchor: true` و`visible: false` (لا تُرسم ولا تدخل الإشارات). من الرجل الثانية فصاعداً مطابقة تامة.

### لكل مؤشر مخرجان:
- **`geometry`** — خطوط/مستويات/ملصقات/علامات جاهزة للرسم (كل نقطة تحمل `bar` + `time` ملي ثانية معاً).
- **`series`** — أعمدة لكل شمعة للاستخدام الاستراتيجي لاحقاً:
  - ZigZag: `zz_state`, `zz_pivot_high`, `zz_pivot_low`
  - Fib: `fib_start`, `fib_end`, `fib_target`
  - Trendline: `tl_upper`, `tl_lower`, `tl_cross_upper`, `tl_cross_lower`

**لهذا السبب تحديداً** (أعمدة جاهزة لكل شمعة) ستكون كتابة الاستراتيجية في الخطوة القادمة استيراد سطر واحد:
```python
from app.services.indicators.overlays import compute_overlays
```

---

## 2) النقاط الجديدة

### أ) `GET /api/v1/overlays/compute` — للشارت الحي
```bash
curl "http://161.97.73.254:8000/api/v1/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=30&limit=1000&types=zigzag,fib,trendline"
```
| معامل | افتراضي | ملاحظات |
|---|---|---|
| symbol/timeframe/market/days | BTCUSDT/1h/crypto/30 | نفس مسار DataService المستخدم في الاستراتيجيات |
| limit | — | قص إلى آخر N شمعة بعد الجلب |
| types | الكل | `zigzag,fib,trendline` أو `all` |
| zz_length | 100 | 2–2000 |
| fib_depth / fib_dev / fib_ret | 10 / 5.0 / 0.618 | مطابقة للسكربت |
| fib_levels | مستويات السكربت | مثل `0,0.382,0.618,1` |
| tl_period / tl_pairs | 10 / 1 | مطابقة للسكربت |

### ب) `POST /api/v1/overlays/compute` — شموع معطاة مباشرة
```json
{"candles": [{"time": 1700000000000, "open": 1, "high": 2, "low": 0.5, "close": 1.5}],
 "types": ["zigzag","fib","trendline"],
 "params": {"zigzag": {"length": 100}}}
```

### ج) دمج chart-data (الباك-تست) — بلا نداء إضافي
```
GET /api/v1/backtest/{id}/chart-data?overlays=zigzag,fib,trendline&include_indicators=true&limit=500
```
- المؤشرات تُحسب على **كامل شموع الباك-تست** (لا النافذة المقصوصة) — أي أن الزجزاج length=100 يعمل صحيحاً حتى مع limit صغير.
- حقل `overlays` يُضاف للاستجابة، وكاش مستقل بمعاملاته (`overlays.cache = built|hit`).
- **تنبيه مهم للفرونت**: فهارس `bar` في هندسة الـoverlays نسبية لكامل الشموع — حوّلوها للزمن عبر `time` المرفق في كل نقطة (وليس فهرس النافذة).

### د) `GET /api/v1/overlays/health` — فحص حي + إحصاء الكاش

---

## 3) النشر (4 ملفات فقط — بلا إعدادات/تبعيات جديدة)

```bash
# على الخادم، من مجلد فك الضغط:
docker cp app/services/indicators/overlays.py trading-backend:/app/app/services/indicators/
docker cp app/routers/overlays.py    trading-backend:/app/app/routers/
docker cp app/routers/backtest.py    trading-backend:/app/app/routers/
docker cp app/main.py                trading-backend:/app/app/
docker restart trading-backend
```

> ملاحظة: `overlays.py` (المنطق) يوضع في `app/services/indicators/` الموجود أصلاً — لا مجلد جديد يُنشأ يدوياً.

---

## 4) التحقق بعد النشر (دقيقتان)

```bash
# 1) فحص حي:
curl -s http://161.97.73.254:8000/api/v1/overlays/health
# المتوقع: {"status":"ok","round":10,...}

# 2) حساب حي على BTCUSDT:
curl -s "http://161.97.73.254:8000/api/v1/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=30&limit=1000" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    print(d['summary']); \
    print('zz_pivots:', len(d['overlays']['zigzag']['pivots'])); \
    print('fib_current:', d['overlays']['fib']['current']['p1'], '→', d['overlays']['fib']['current']['p2']); \
    print('tl_fractals:', len(d['overlays']['trendline']['fractals']['up']), '+', len(d['overlays']['trendline']['fractals']['down']))"
# المتوقع: cache=built ثم استدعاء ثانٍ خلال 30ث cache=hit — وقيم حقيقية غير صفرية

# 3) chart-data مع المؤشرات (باك-تست قائم):
curl -s "http://161.97.73.254:8000/api/v1/backtest/<ID>/chart-data?overlays=zigzag,fib,trendline&limit=100" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); o=d.get('overlays'); print('overlays:', list(o['overlays'].keys()), 'cache:', o['cache']) if o else print('❌ لا حقل overlays')"

# 4) صفر انهيارات:
docker logs --since 3m trading-backend 2>&1 | grep -ci "traceback\|error" || true
```

---

## 5) نتائج الاختبار قبل التسليم (ساندبوكس، بيانات Binance حقيقية)

| الاختبار | النتيجة |
|---|---|
| BTCUSDT 1h ×1000 — زجزاج: تناوب قمم/قيعان + سعر القمة=high[bar] حرفياً | ✅ 9 pivots / 8 segments |
| فيب: معادلة كل مستوى = p1 + diff×ratio (خطأ < 1e-6) + إشارات تعبر النطاق | ✅ رجل حية 84898→76326 + 5 إشارات |
| خطوط اتجاه: كل فراكتال = قمة/قاع صارم لنافذته (period=10) + إسقاط صحيح | ✅ 35+38 فراكتالاً / 82 تقاطعاً |
| حواف: سلسلة قصيرة (15) / مسطحة تماماً (300) / شمعة واحدة / صفر شموع | ✅ بلا انهيار، بلا NaN |
| أداء: 5000 شمعة (المؤشرات الثلاثة معاً) | ✅ ~84ms |
| JSON: NaN-free / Infinity-free / كل نقطة تحمل bar+time | ✅ |
| Router: TestClient — health/compute/POST/أخطاء 400 عربية | ✅ |
| محاكاة رقعة chart-data (تطبيع timestamp/open/... → حساب) | ✅ |

**اكتشافان خلال التطبيق أُصلحا قبل التسليم:**
1. خطأ ترتيب في بارامتريزيشن extremities الزجزاج كان سيعطي قنوات معكوسة — أُصلح وطُابق حرفياً.
2. `json` كان غير مستورد في backtest.py — كان سينهار NameError عند أول طلب overlays — أُصلح.

---

## 6) رسالة لوكيل الفرونت (انسخها له)

> **عقد الاستجابة الجديد جاهز — أنتم ترسمون فقط:**
> 1. **الشارت الحي**: `GET /api/v1/overlays/compute?symbol=...&timeframe=...&days=30&limit=1000` — أرسل معه `types=` لاختيار المؤشرات. أعيد الرسم عند تغيير الرمز/الفريم فقط (الكاش 30ث يحمينا).
> 2. **الباك-تست**: أضيفوا `&overlays=zigzag,fib,trendline` لنداء chart-data الحالي — حقل `overlays` سيصل في نفس الاستجابة (بلا نداء إضافي).
> 3. **الرسم** (العقد الكامل في `OVERLAYS-CONTRACT-AR.md` داخل الحزمة):
>    - زجزاج: `segments[]` خطوط (x1,t1,y1)→(x2,t2,y2) + خطان منقّطان بالتوازي على بعد `ext_up`/`ext_dn` + `projection` للمقطع الممتد + `pivots[]` كعلامات دائرية مع ملصق سعر.
>    - فيب: `current.levels[]` خطوط أفقية من `t_from` إلى `t_to` مع `extend_right` + ملصق "(قيمة)" عند `t_from` + `signals[]` علامات Buy/Sell Retrace.
>    - خطوط اتجاه: `lines.up/down[]` خطوط متقطعة (visible=true فقط) + `projection.upper/lower` تمتد يميناً + `crosses[]` علامات X.
> 4. **لا تعتمدوا على فهارس bar** في الرسم — استخدموا `time` المرفق بكل نقطة (الفهارس نسبية لكامل البيانات).
> 5. `visible=false` في أي عنصر = تجاهلوه (مطابق لسلوك Pine الذي يحذفه).
> 6. معاملات المؤشرات قابلة للتمرير — اعرضوها للمستخدم (zz_length, fib_depth, fib_dev, fib_ret, tl_period, tl_pairs).

---

## 7) الخطوة القادمة (معلّقة على هذا الأساس)

كما اتفقنا — **كتابة استراتيجية التداول على هذه المؤشرات الثلاثة**: الأعمدة الجاهزة (`zz_state`, `fib_target`, `tl_upper/lower`, `tl_cross_*`...) + الإشارات (`fib.signals`, `tl.crosses`) تجعل الدمج في محرك الاستراتيجيات استيراد + قواعد قراءة. أرسلوا قواعد الدخول/الخروج المطلوبة وأبنيها في الجولة 11.

— وكيل الباكند، الجولة 10
