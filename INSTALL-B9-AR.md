# دليل دمج حزمة B9 (النسخة المصححة) — «ماكد 9B + ترند 100» · خروج ولادة خط علوي فقط + الخط فوق السعر

**الأساس المطلوب**: السيرفر الحي الحالي (backend_PRO109 — R9-DCA cumulative) ·
**نوع الحزمة**: إضافة صرفة (لا تحل محل أي ملف محرك قائم عدا التسجيل والقوالب) ·
**التاريخ**: 2026-11-22 · **إصدار الحزمة**: **FIX** — التصحيح الأخير مطبَّق.

> **ما الذي تغيّر في إصدار FIX؟** قاعدة الخروج فقط — من «ولادة خط ترند-100 جديد
> (علوي **أو** سفلي)» إلى:
> **ولادة خط ترند-100 علوي جديد فقط ∧ قيمة الخط العلوي فوق السعر (أعلى من الإغلاق)**
> — حرفياً كما أمر صاحب القرار. **محرك B9 لم يتغير ولا سطر واحد فيه** (التصحيح
> على مستوى الحمولات والقالب فقط — لا يحتاج كوداً جديداً). تسلسل العمل المتفق:
> **حزمة ← تطبيق على السيرفر ← اختبار** — الاختبار لا يبدأ إلا بأمر صاحب القرار
> بعد التطبيق، ولذلك لا تحمل هذه الحزمة أي أرقام مرجعية جديدة؛ الأرقام السابقة
> (ETH +20.50% · XRP −1.52% · MBL +1.24%) كانت لنسخة الخروج القديمة وهي **مهملة**.

---

## 1) قائمة الملفات (جديد + معدل)

### ملفات جديدة (تنسخ كما هي)

| المسار | الدور |
|---|---|
| `app/services/indicators/overlays_b9_macd_gates.py` | محرك B9 المعزول (تسجيل ذاتي) — **لم يتغير في FIX** |
| `payloads/payload_B9_T100_ETHUSDT.json` | حمولة ETH الجاهزة — **الخروج المصحح** |
| `payloads/payload_B9_T100_XRPUSDT.json` | حمولة XRP الجاهزة — **الخروج المصحح** |
| `payloads/payload_B9_T100_MBLUSDT.json` | حمولة MBL الجاهزة — **الخروج المصحح** |
| `tools/verify_b9.py` | بطارية التحقق المستقلة (**12 فحصاً** — أُضيفت بطارية الخروج المصحح) |

### ملفات معدلة (تُستبدل بالنسخ المرفقة — الفرق إضافات تسجيل فقط)

| المسار | حجم التغيير | مضمونه |
|---|---|---|
| `app/services/indicators/overlays.py` | +31 سطراً | إضافة `b9_macd_gates` إلى OVERLAY_TYPES + known params + فرع الحساب المؤجل + حماية مسار «كل الأنواع» الافتراضي |
| `app/services/indicators/overlay_columns.py` | +61 سطراً | ALIASES (b9/b9_macd/b9_macd_gates) + KNOWN_OVERLAY_BASES + CONTRACT_COLUMNS + فرع تطبيع المعاملات + `_b9g_columns` + الحقن في columns_from_overlays_result |
| `app/services/indicators/__init__.py` | +1 سطر | استيراد التسجيل الذاتي |
| `app/services/strategy/presets.py` | +284 سطراً | قالب `B9_TREND100` + عنصر `b9_trend100_zero_fee` في `get_presets()` — **بقاعدة الخروج المصححة** (and: ولادة علوي ∧ الخط فوق السعر) |

> ⚠️ قبل الاستبدال: إن كانت نسخة السيرفر من هذه الملفات أحدث من PRO109 (جولات لاحقة)،
> طبّق `diffs/*.diff` المرفقة يدوياً بدل الاستبدال الكامل — كل التغييرات كتل إضافية معلّمة
> بتعليق `# ✅ B9` يسهل نقلها. لتصحيح الخروج على سيرفر سبق أن دُمجت فيه نسخة B9 القديمة،
> استخدم `diffs/B9-FIX/*.diff` (فروقات الحمولات والقالب فقط — بلا أي كود).

---

## 2) خطوات الدمج

```bash
# 1) نسخ الملف الجديد (المحرك — إن لم يكن منصوباً)
cp app/services/indicators/overlays_b9_macd_gates.py  <SERVER>/app/services/indicators/

# 2) استبدال/تطبيق الملفات المعدلة (أو تطبيق diffs/)
cp app/services/indicators/overlays.py          <SERVER>/app/services/indicators/
cp app/services/indicators/overlay_columns.py   <SERVER>/app/services/indicators/
cp app/services/indicators/__init__.py          <SERVER>/app/services/indicators/
cp app/services/strategy/presets.py             <SERVER>/app/services/strategy/

# 3) الحمولات (المصححة) وأداة التحقق
cp payloads/payload_B9_T100_*.json <SERVER>/payloads/
cp tools/verify_b9.py              <SERVER>/tools/

# 4) إعادة تشغيل الخدمة (uvicorn/celery worker معاً — التسجيل يتم عند الاستيراد)
```

> **حالة خاصة**: إذا كان السيرفر يحمل نسخة B9 القديمة أصلاً (المحرك منصوب
> ومسجَّل)، فالتصحيح لا يتطلب لمس أي ملف كود — يكفي استبدال الحمولات الثلاث
> و`presets.py` (أو تطبيق `diffs/B9-FIX/` فقط) ثم إعادة تشغيل الخدمة.

---

## 3) التحقق بعد الدمج

```bash
# أ) البطارية المستقلة (تحتاج كاش/جلب بيانات — تعمل أوفلاين من data/history)
python3 tools/verify_b9.py ETHUSDT
# المتوقع: 12 ناجح · 0 فاشل ⇒ VERIFY-B9 PASS
#    البطارية الخامسة الجديدة تطبع:
#    ولادات خط علوي: N · يخرج منها (فوق السعر): M · مرفوضة (السعر ≥ الخط): N−M

# ب) فحص التسجيل
curl -s http://localhost:8000/api/v1/indicators/available | grep -o "b9_macd_gates"
# المتوقع: b9_macd_gates (وبدون أخطاء إقلاع)
```

> **الاختبار المرجعي (ج)** — **مؤجَّل عمداً**: لا يبدأ إلا بعد التطبيق وبأمر صاحب
> القرار (التسلسل: حزمة ← تطبيق ← اختبار). عند أمره، تُبثّ الحمولات الثلاث كما هي:
> `POST /api/v1/backtest1/run` بـ `payloads/payload_B9_T100_{ETH,XRP,MBL}USDT.json`.

---

## 4) عقد الاستخدام

### الحمولة (BacktestConfig)

- `start_date` = بداية **بيانات الإحماء** (18 شهراً قبل نافذة التقييم — لجاهزية MACD الأسبوعي
  18/39/4 كما يراه TradingView بالتاريخ الكامل) · `end_date` = نهاية نافذة التقييم.
- `active_start`/`active_end` (داخل `params` لمؤشر b9_macd_gates) = **نافذة التقييم** بت-بت —
  الصفقات لا تحدث خارجها مهما كانت الإشارات، بينما القيم تُحسب على كامل البيانات.
- عند التغيير لعملة/نافذة أخرى: عدّل `symbols` + `start_date` + `end_date` + `active_start` +
  `active_end` **معاً**، وأزل active_* إن أردت الإشارات على كامل نافذة البيانات.

### المؤشرات في الاستراتيجية

```json
"indicators": [
  {"name": "b9_macd_gates", "type": "momentum",
   "params": {"instances": [...7 نسخ...], "conditions": {...شجرة B9...},
               "sub_labels": ["w_pos","d_pos","4h_core","any_above_4h"],
               "active_start": "...", "active_end": "..."}},
  {"name": "trend_fractal", "type": "support_resistance",
   "params": {"periods": [100], "confirm_mode": "all"}}
]
```

- **الدخول**: `indicator:b9_macd_gates:b9g_buy > 0` ∧ `indicator:trend_fractal:trf_p100_bias > 0`
- **الخروج (المصحح)**:
  `indicator:trend_fractal:trf_p100_new_upper > 0` **∧** `indicator:trend_fractal:trf_p100_upper > price:close`
  — ولادة خط **علوي** جديد فقط، والخط **فوق السعر**. (المقيّم يقبل `price:close`
  في أي طرف — لا يحتاج أي كود.)

### الأعمدة التعاقدية (ind_*)

`ind_b9g_buy` (الأساسية) · `ind_b9g_cond` (الشجرة بلا نافذة) · `ind_b9g_sub_{w_pos,d_pos,4h_core,any_above_4h}`
· `ind_b9g_osc_{macd_4h_12_26_6, macd_1d_6_13_4, macd_1d_12_26_6, macd_1d_18_39_4, macd_1w_6_13_4,
macd_1w_12_26_4, macd_1w_18_39_4}_{line,signal,hist}` (قيم MACD للرسم — null أثناء الإحماء).

---

## 5) قرارات معمارية موثقة (مهمة لأي مراجعة)

1. **signal = EMA** (ta.macd القياسي) — لا SMA كما في نواة QMOM1 (CM_MacD_Ult_MTF).
2. **الأسبوع من الاثنين** (مرساة TradingView) عبر `_build_htf_bars` من MTFEMA1.
3. **الإسقاط السببي الصارم** (آخر شريط HTF مكتمل فقط) = وضع confirmed الذي اختاره مؤلف
   السكربت؛ وضع useEarlyHTF=true (استشراف/يعيد الرسم) **غير منفّذ عمداً**.
4. **الإحماء فشل-إغلاق**: أي قيمة مفقودة ⇒ الورقة False (لا حياد إحماء هنا).
5. **EMA محلية NaN-aware** (`_ema_seeded` في ملف المحرك) — لا تعتمد على `_ema_talib`
   (التي تنشر NaN للأبد مع بادئة NaN)؛ على سلاسل نظيفة تطابقها بت-بت.
6. **إدارة نقية بإشارات فقط** في الحمولات المرجعية (بلا SL/TP/تريلينق/جني مقسم/تعزيز) —
   كما وصف الأمر؛ طبقات الإدارة القائمة تُضاف من الواجهة متى رُغب.
7. **(FIX) الخروج على مستوى الحمولة والقالب فقط** — لا كود جديد: الشرط المصحح يُعبَّر
   مباشرة بشروط المقيّم القائمة (`and` + مقارنة عمود مؤشر مع `price:close`). محرك
   B9 وترند-فراكتال **كلاهما بلا أي تعديل** في هذا الإصدار.
