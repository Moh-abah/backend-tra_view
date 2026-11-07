# 📋 BACKEND REPORT — ROUND 13 (الإصدار 13.0)

**التاريخ:** 2026-11-01
**المرجع:** تعليمات الجولة 13 من وكيل الواجهة (إبادة العمولات نهائياً · الدقة المتناهية · ثغرتان)
**الأساس:** v12.9 المنشورة على الإنتاج (تحقق حي 13/13) — ملفات الحزمة مطابقة لأساس `deployed_v12.9`
**الإصدار:** **13.0**
**البيئة المحلية للتحقق:** Next.js sandbox — خادم FastAPI محلي (uvicorn 127.0.0.1:8600، SQLite، بلا Redis → مسار in-process)

---

## 0) ملخص تنفيذي

| البند | الحالة | الدليل |
|---|---|---|
| 1 — إبادة العمولة بنيوياً (schemas + engine + ميت) | ✅ منفذ | PASS-1/1b/6 + حذف engine.py و engine_copy.py |
| 2 — عقد الدقة المتناهية (1e-9 + precision_report + صيغة موحدة) | ✅ منفذ | PASS-2/3/5 |
| 3-أ — /indicators/compute الصيغة النصية (لا تجاهل صامت) | ✅ منفذ | PASS-4a/4b |
| 3-ب — رفع zzfib levels/out_of_range إلى summary | ✅ منفذ | PASS-EXTRA |
| الترقيم المرجعي للبطل محفوظ | ✅ حرفياً | 10 صفقات · −1.8561111466784315% |
| VERIFY-R13.sh | ✅ ALL PASS | ملف الأدلة الكامل مرفق |

---

## 1) 🔴 المطلوب 1 — إبادة العمولة (سياسة Zero-Fee)

### 1.2-أ مخططات الطلب (schemas)
**`app/backtest/schemas.py` (BacktestConfig):**
- `commission_rate` و `slippage_percent`: `deprecated=True` في OpenAPI + وصف صريح.
- `@model_validator(mode="after") zero_fee_policy`: أي قيمة > 0 → **422** برسالة عربية حرفية:
  > النظام يعمل بلا عمولات ولا انزلاق نهائياً (سياسة Zero-Fee). حقل commission_rate لم يعد مقبولاً بقيمة > 0 — احذفه من الحمولة.
- غياب الحقل أو 0 → يُقبل بصمت (توافق خلفي). ممنوع الإسقاط الصامت مع تطبيق قيمة — القيمة > 0 تُرفض دائماً (بما فيها مسار الاسم البديل `commission` الذي يُطبَّع إلى commission_rate ثم يُرفض).

**`app/services/strategy/schemas.py` (StrategyConfig):** نفس العقد بالضبط (`zero_fee_policy`).

### 1.2-ب المحرك (engine1.py) — مسح جذري بلا كود ميت
- `_close_trade_logic`: حُذف كلياً — لا `commission_rate`، لا `slippage_rate`، لا `commission_exit`، لا `slippage_cost`، لا فرع `if commission > 0`. الحساب صافٍ بالبنية: `trade.pnl = pnl` كما هو.
- فتح الصفقات (مسارا next_open وsignal_close): حُذف سطر حساب `commission = entry_price * position_size * config.commission_rate` — الحقول في الاستجابة ثابتة `commission=0.0, slippage=0.0`.
- `trade_points` (دخول/خروج/نهاية-البيانات): `"commission": 0.0` ثابت (DEPRECATED موثق).
- `metrics.py::_build_equity_curve` و `engine1.py::_build_symbol_equity_curve`: حُذف خصم عمولة الدخول.
- **حذف ملفين ميتين بالكامل:** `app/backtest/engine.py` و `app/backtest/engine_copy.py` — كانا يحملان كود عمولة قديماً ولم يكونا مستوردين في أي مكان (تحقق grep شامل). الحذف يضمن أن كود العمولة **لا يعود يوماً**.
- التواقيع: لا يوجد أي وسيط commission_rate/slippage بقيمة افتراضية في أي توقيع دالة حي.

### 1.2-ج الاستجابة (توافق خلفي محدود)
- `Trade.commission` و `Trade.slippage`: ثابتان 0.0 مع `deprecated=True` (توافق قرائي جولة واحدة).
- `pnl_gross = pnl` دائماً (موثق في وصف الحقول وفي notes الـpreset).
- `summary.fees_applied` يبقى — إثبات شفافية، ثابت 0.0.
- `math_audit.formula` الصيغة الصافية الحرفية (انظر §2).

### 1.3 جانب الواجهة — مستلم (لا عمل علينا)

---

## 2) 🔴 المطلوب 2 — عقد الدقة المتناهية

- **الصيغة الموحدة الموثقة** (في وصف حقول Trade وفي notes الـpreset):
  - `price_delta_pct = (exit − entry) / entry × 100 × direction`
  - `result_pct = price_delta_pct` (نفس القيمة بلا اختلاف — مُنفذ حرفياً في المحرك وtrade_points)
  - `pnl = (exit − entry) × units × direction − 0` (بلا خصم إطلاقاً)
  - `total_pnl_percent = Σpnl / initial_capital × 100`
- **لا تقريب:** صفر استدعاءات `round()/ :.2f / quantize` على الأسعار أو pnl أو النسب في محرك الحساب (الفحص الوحيد المتبقي `.2f` هو سطر log توثيقي في Monte Carlo — عرض نصي فقط).
- **math_audit المشدّد:** `max_abs_error ≤ 1e-9` (كان 0.01) + `formula_tolerance: 1e-9` + `precision_report: {formula_tolerance: 1e-9, float64: true, rounded_fields: []}` + قيم خام بلا `round()` في التقرير.
- **تسلسل JSON:** لا serializer مخصص يقصّ — Pydantic/FastAPI يسلفان float64 كاملة (الدليل الحي: `6.366e-05`، `−1.8561111466784315`).

---

## 3) 🟡 المطلوب 3 — الثغرتان

### 3-أ /indicators/compute — لا تجاهل صامت
- الصيغة النصية مدعومة رسمياً: `{"indicators":["zigzag_fib"]}` (وأيضاً `"zigzag_fib"` مفردة) → تُطبَّع إلى كائن بلا params → **13 عمود ind_zzf_*** كاملة.
- أي عنصر غير صالح (رقم/null/dict بلا name/id/label/نص فارغ) → **422** برسالة عربية واضحة:
  > صيغة المؤشرات غير صالحة — استخدم [{"name": "...", "params": {...}}] أو صيغة نصية مبسطة ["اسم المؤشر"]
- ينطبق على POST وGET معاً (التنفيذ المشترك `_compute_indicators_impl`).

### 3-ب رفع المستويات إلى metadata/summary
- `GET/POST /overlays/compute` (المسارات الثلاثة) يرفع الآن إلى `summary`:
  - `zzfib_levels: [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]` + `zzfib_out_of_range: []`
  - `fib_levels` + `fib_out_of_range` (للتناظر)
- الواجهة تتحقق آلياً دون تنقيب جسم الاستجابة.

---

## 4) ملاحظات الواجهة — مستلمة (توافق)
- Fib [0,1] حرفياً من الواجهة — مطابق لعقدنا؛ الامتدادات عبر params فقط.
- العنونة الثلاثية `indicator:<name>:<col>` بلا تغيير.
- `fill_model`: الحقل الرسمي موجود في BacktestConfig (`"next_open"` الافتراضي | `"signal_close"`) — جاهز لمنتقي الواجهة متى أضفته.
- إن غيّرنا params افتراضية مستقبلاً سنُعلمكم لمزامنة سجل الواجهة.

---

## 5) معايير القبول الحرفية — تنفيذ + مخرجات أصلية (محلي 127.0.0.1:8600)

> الأداة: `VERIFY-R13.sh` (مرفق) — الأدلة الكاملة الحرفية في `VERIFY-R13-LOCAL-EVIDENCE.txt` (مرفق).
> ملاحظة بيئة: الإنتاج 161.97.73.254 لا يمكن الوصول إليه من بيئة التطوير هذه (لا SSH/شبكة خارجية للمنفذ) — النشر عبر docker cp كما في 12.9 ثم `VERIFY-R13.sh --external`. كل ما يلي مُثبت محلياً على نفس كود الحزمة.

### PASS-1 — رفض العمولة الصريحة
```
HTTP: 422
body: {"detail": [{"type": "value_error", "loc": ["body"], "msg": "Value error, النظام يعمل بلا عمولات ولا انزلاق نهائياً (سياسة Zero-Fee). حقل commission_rate لم يعد مقبولاً بقيمة > 0 — احذفه من الحمولة.", ...
PASS-1
```
PASS-1b (slippage_percent=0.1): `HTTP: 422 | {"detail": [{"type": "value_error", ... "msg": "Value error, النظام يعمل بلا عمولات ولا انزلاق نهائياً (سياسة Zero-Fee). حقل slippage_percent لم يعد مقبولاً بقيمة > 0 — احذفه من الحمولة.", ...`

### PASS-2 — الصيغة الصافية في math_audit
```
formula: pnl == (exit_price - entry_price) * units * (long? +1 : -1)
PASS-2 (الصيغة الصافية حرفياً)
```

### PASS-3 — التسامح المشدّد + precision_report
```
max_abs_error: 0.0 | tolerance: 1e-09
precision_report: {'formula_tolerance': 1e-09, 'float64': True, 'rounded_fields': []}
PASS-3 (max_abs_error ≤ 1e-9 + precision_report)
```

### PASS-4 — الصيغة النصية في indicators/compute
```
HTTP: 200
ind_zzf_* columns: 13 ['ind_zzf_dir', 'ind_zzf_i1', 'ind_zzf_i2', 'ind_zzf_level_0', 'ind_zzf_level_0236', 'ind_zzf_level_0382', 'ind_zzf_level_05', 'ind_zzf_level_0618', 'ind_zzf_level_0786', 'ind_zzf_level_1', 'ind_zzf_p1', 'ind_zzf_p2', 'ind_zzf_touch']
PASS-4a (الصيغة النصية → 13+ عمود ind_zzf_*)
invalid format HTTP: 422 | {"detail": "صيغة المؤشرات غير صالحة — استخدم [{\"name\": \"...\", \"params\": {...}}] أو صيغة نصية مبسطة [\"اسم المؤشر\"]"}
PASS-4b (العناصر غير الصالحة تُرفض 422 — لا تجاهل صامت)
```

### PASS-5 — الدقة تحت السنت (WINUSDT 1m، سعر 6.366e-05)
```
HTTP: 200 | status: COMPLETED
WINUSDT close: 6.366e-05 | sub-cent: True
level rows checked: 50 | worst relative error: 0.0
PASS-5b (ind_zzf_level_0618 == p1 + (p2−p1)×0.618 حرفياً)
WINUSDT trades: 8 | fees: 0.0 | audit consistent: True
worst relative pnl error (WINUSDT): 0.0
PASS-5c (pnl بدقة 1e-12 نسبياً على أسعار تحت السنت)
```
وعلى صفقات البطل أيضاً: `worst relative pnl error (champion): 0.0` (أفضل من 1e-12 المطلوبة — تطابق بتّي).

### PASS-6 — تراجع آمن + Zero-Fee إبادة
```
trades: 10 | total_pnl_percent: -1.8561111466784315 | fees_applied: 0.0 | fill_model: next_open
champion trades: 10 | pnl%: -1.8561111466784315
PASS-6 (fees_applied=0.0 · commission=0.0 · result_pct==price_delta_pct · البطل يعيد صفقات)
```
- **الرقم المرجعي مطابق حرفياً** لتقريركم الحي: 10 صفقات · −1.8561% (−1.8561111466784315 كاملة).
- تراجع chart-data (تحقق إضافي): `GET /backtest1/{id}/chart-data?include_indicators=true` → 4800 صف · 7 أعمدة ind_* · بلا بادئة مزدوجة · commission=0.0 في كل النقاط.
- التراجع الكامل (استعادة 12.9): إعادة docker cp لملفات 12.9 + restart → 12.1 يعود PASS (لا تغييرات DB/عقود قراءة خارج ما ورد أعلاه).

### PASS-EXTRA — رفع المستويات
```
summary.zzfib_levels: [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
summary.zzfib_out_of_range: []
PASS-EXTRA — levels/out_of_range مرفوعة إلى summary
```

---

## 6) الملفات المعدّلة (14) + MD5

```
616e4ffa649f76661d3d0dec9d0d5ac4  app/backtest/schemas.py
543d3e0ae93f6011bd2f9d4d81569086  app/backtest/engine1.py
dfd462c24fb62a1224bbcbddb714b510  app/backtest/metrics.py
711c8693c8a491019c2b6aa24fd41ce1  app/services/strategy/schemas.py
9988d8b1ef00613e46bbc3d2a6c1c47a  app/services/strategy/full_strategy.py
c89b0cba779c2d1c08d2be3f150a4934  app/services/strategy/presets.py
9c0e1133c9aca4c292ef2c98c0219857  app/services/strategy/strategys/rsi_strategy.py
7707bdead76a5821c1a94d0a4f23d381  app/services/strategy/strategys/mean_reversion_strategy.py
e6cabb3406b6dc91ed0f69a083480865  app/services/strategy/strategys/macd_strategy.py
a8b692c69eb040bfae4c7e86499a9813  app/services/strategy/strategys/test_strategy.py
02d4dea45dc0231522f9dadb6e533014  app/services/strategy/strategys/trend_strategy.py
2d8ec193f452c2ad25c5e751fbb1d33c  app/routers/indicators.py
e45759b96ca696a777e7d617e5fab951  app/routers/overlays.py
5141662e29c686c3488a2a9da9107aac  VERIFY-R13.sh (جديد)
```

**ملفات محذوفة (ميتة — كانت تحمل كود عمولة):**
```
app/backtest/engine.py        (غير مستوردة — grep شامل)
app/backtest/engine_copy.py   (غير مستوردة — grep شامل)
```

**أسماء معدّلة أخرى:** `commission_rate=0.0` في `full_strategy.py` و `strategys/*.py` الخمسة (كانت 0.001 قديمة في قوالب أمثلة).

---

## 7) الحزم المُسلَّمة (الإصدار 13.0)

| الملف | المحتوى |
|---|---|
| `BACKEND-v13.0-HOTFIX-13FILES.zip` | الملفات المعدّلة الـ13 + VERIFY-R13.sh + تعليمات النشر + MD5 |
| `BACKEND-v13.0-FULL.zip` | نسخة كاملة (73MB) بأساس 12.9 + كل تعديلات الجولة 13 |
| `BACKEND_REPORT_ROUND13.md` | هذا التقرير |
| `VERIFY-R13-LOCAL-EVIDENCE.txt` | مخرجات VERIFY-R13 الأصلية حرفياً (ALL PASS) |
| `ROUND13-MD5SUMS.txt` | بصمات MD5 |

## 8) خطوات النشر (نفس أسلوب 12.9)

انظر `HOTFIX-README-R13.txt` داخل الحزمة — docker cp للملفات الـ13 + حذف الملفين الميتين + `docker restart trading-backend` ثم:
```bash
R13_BASE=http://161.97.73.254:8000/api/v1 ./VERIFY-R13.sh --external
```
المتوقع: ALL PASS على الإنتاج (نفس الكود الذي أعاد ALL PASS محلياً).

## 9) بنود للتنسيق مع الواجهة
1. `price_delta_pct` أصبحت **موقّعة بالاتجاه** (×direction) و`result_pct = price_delta_pct` — حدّثوا أي عمود يعرضها إن كان يفترض الإشارة.
2. `Trade.commission/slippage` و `trade_points.commission`: ثابتان 0.0 و`deprecated: true` في OpenAPI — لا تعتمدوا عليهما.
3. `StrategyConfig` لا يقبل commission_rate > 0 الآن (422) — حمولاتكم القديمة بلا الحقل أو بـ0 سليمة.
4. `/indicators/compute` يدعم الصيغة النصية `["zigzag_fib"]` رسمياً (اخترنا الدعم بدل الرفض — أوسع توافقاً).
5. `/overlays/compute` summary يحمل الآن `zzfib_levels/zzfib_out_of_range/fib_levels/fib_out_of_range`.

**جاهزون للنشر — الجولة 13 مكتملة محلياً ALL PASS ✅**
