# QMOM1-FIX1 — حزمة إصلاح علة #10000616 (بوابة الزخم لم تعمل على السيرفر)
## BACKEND-QMOM1-FIX1 — دليل الدمج الخطوة بخطوة (5 ملفات — إصلاحات جراحية + إضافات فقط)
**التاريخ:** 2026-11-18 · **الأساس:** نسخة QMOM1 المنشورة على السيرفر الآن (نفس الملفات الخمسة أدناه كما رُصدت بعد الدمج) · **المُرسل:** السديم

---

## 0) لماذا هذه الحزمة — ماذا حدث بالضبط في #10000616

شغّلنا «كموميه الزخم الاولى» بنفس تكوين #10000604 تماماً (MMTUSDT · 15m · length=100 ·
ema_lengths بـ21 · zone_exit_resolution=5 · نفس الفترة) والنتيجة خرجت **= الأساس بت-بت**
(46 صفقة · -26.53% · WR 34.78%) والـ 25 عمود موشرات كلها `None`. شخّصنا الجذر بدقة
(إعادة إنتاج محلية كاملة + تتبع المسار على السيرفر) — **ثلاث علل لا علة واحدة:**

| # | العلة | الأثر على السيرفر |
|---|---|---|
| **1** | `_norm_candles` في `mtf_oscillator_core.py`: DataFrame بلا عمود `time` كان يسقط على `candles.columns[0]` = **عمود السعر `open`!** محرك الباك-تست (`engine1._normalize_candle_index`) يسقط عمود time ويضع DatetimeIndex — فأُخذت أسعار MMT (0.1..0.5) كأزمنة (×1000 = 100..500ms) → `detect_base_tf` أعاد "1s" زوراً → كل نسخ الموشرات صمتت (NaN كامل بلا أي تحذير — القسم كذب بـ `available=True`) | **كل أعمدة الموشرات None + osc_gate=None → البوابة لم تُقيَّم أصلاً** |
| **2** | محرك الزخم كان يبوّب العمود المجمّع `zzfetqem_entry` **فقط** — وقواعد دخول الاستراتيجية تشير إلى `zzfetqem_entry_s{1,2,3}` (العقد الموعود في BRIEF §1ب: «الدخول النهائي = نهائي الكمومية ∧ قيمة الشجرة») فمرّت الإشارات كلها من دون البوابة | **حتى لو عملت البوابة لما منعت صفقة واحدة — 46 دخولاً كما هي** |
| **3** | قسم `osc` (العدادات/التحذيرات/حالات النسخ) كان يُحسب ويضيع داخل الأنبوب — لا يصل إلى نتيجة الباك-تست | **التقرير لا يصف شيئاً من البوابة — الفرونت أعمى** |

**الإصلاح (R77) في ثلاث طبقات — كلها الآن مثبتة محلياً:**

| الملف | الإصلاح |
|---|---|
| `app/services/indicators/mtf_oscillator_core.py` | (أ) مصدر الأزمنة الصحيح: عمود زمن صريح (بمرادفاته timestamp/date/datetime/…) ← **DatetimeIndex** (جذر الإصلاح) ← ملاذ أخير **مُتحقَّق منه** ضد نطاق صدق epoch-ms (فشله ⇒ إسقاط كامل **معلَن** بتحذير `time_source_invalid` — بلا تلفيق أزمنة من أسعار أبداً). (ب) صدق التغطية: نسخة حسبت بلا أي قيمة صالحة ⇒ `zero_coverage` معلنة (لا `available=True` زوراً). (ج) تحصين `_col_to_ms` (كان ينفجر بـ TypeError على عمود زمني بتوقيت). (د) شفافية القسم: `time_source` + `n` + `input_rows` |
| `app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema_mom.py` | **البوابة تُطبَّق فعلياً على `zzfetqem_entry_s{1,2,3}`** (كما وعد العقد) — كل إشارة تُبوّب على حدة + شفافية `iblocked_{tag}` (ما قتلته البوابة وأين) |
| `app/services/indicators/overlay_columns.py` | `columns_for_configs(..., return_sections=True)` ⇒ يعيد الأعمدة **+ أقسام osc** للمحركات المبوّبة (QMOM1 + الماكدية) — الوضع الافتراضي False = العقد القديم بت-بت |
| `app/services/strategy/strategy_engine1.py` | يلتقط الأقسام إلى `self.indicator_sections` (مع سقوط آمن لنسخ أقدم من overlay_columns) |
| `app/backtest/engine1.py` | قناة الصدى: `_simulate_with_strategy` يخزن قسم الرمز → `_create_backtest_result` يكتبه في **`summary.math_audit.momentum_gate`** (عدادات/تحذيرات/نسخ/مصدر الزمن/حياد الإحماء — عقد BRIEF §3ب «بطاقات بوابة الزخم») |

---

## 1) ما الذي في الحزمة (بالمسارات)

```
merge_package/
├── app/services/indicators/
│   ├── mtf_oscillator_core.py                        ← الإصلاح 1 (مصدر الأزمنة + الصدق)
│   ├── overlays_zlf_e2e_trendy_quantum_ema_mom.py      ← الإصلاح 2 (بوابة s1/s2/s3)
│   └── overlay_columns.py                             ← الإصلاح 3أ (return_sections)
├── app/services/strategy/strategy_engine1.py          ← الإصلاح 3ب (التقاط الأقسام)
├── app/backtest/engine1.py                            ← الإصلاح 3ج (math_audit.momentum_gate)
├── diffs/*.diff                                       ← فروقات موحدة ضد الأساس (5 ملفات)
├── tools/
│   ├── verify_qmom1_fix.py                            ← بطارية R77 (41 فحصاً)
│   ├── verify_engine_e2e.py                           ← تكامل المحرك الكامل (12 فحصاً)
│   └── live_verify.py                                 ← التحقق الحي بعد الدمج (بث → استطلاع → فحوص)
├── INSTALL-QMOM1-FIX1-AR.md                           ← هذا الملف
├── REPORT-QMOM1-FIX1-AR.md                            ← تقرير الإصلاح الكامل بالأدلة
└── FILES-QMOM1-FIX1.md5                                ← بصمات كل ملف
```

**طبيعة التغييرات:** كل الفروقات في `diffs/` إصلاحات جراحية صغيرة + إضافات —
السطور المحذوفة عدّها الإجمالي **13 سطراً فقط** (كلها الأسطر المعطوبة المعنية
بالذات — انظر `diffs/*.diff`). لا مسارات جديدة ولا هجرات ولا نقاط نهاية جديدة.

---

## 2) خطوات الدمج (على سيرفر الباك-اند)

```bash
# 0) (تأكيد الأساس — بصمات ملفات QMOM1 المنشورة حالياً):
md5sum <PROJECT>/app/services/indicators/mtf_oscillator_core.py \
       <PROJECT>/app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema_mom.py \
       <PROJECT>/app/services/indicators/overlay_columns.py
#   يجب أن تطابق أساس FILES-QMOM1-FIX1.md5 (قسم BASIS) — وإن اختلف شيء
#   فطبّق diffs/*.diff يدوياً بدل النسخ الكامل (المراسي موجودة في الفروقات).

# 1) انسخ ملفات الإصلاح الخمسة (المسارات كما هي):
cp merge_package/app/services/indicators/mtf_oscillator_core.py                       <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema_mom.py     <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/overlay_columns.py                             <PROJECT>/app/services/indicators/
cp merge_package/app/services/strategy/strategy_engine1.py                              <PROJECT>/app/services/strategy/
cp merge_package/app/backtest/engine1.py                                               <PROJECT>/app/backtest/

# 2) أعد تشغيل الخدمة (uvicorn + celery كما معتاد) — لا هجرات قواعد بيانات إطلاقاً.
```

> **ملاحظة أمان إضافية:** إن كنت تفضل الدمج الجراحي اليدوي — طبّق `diffs/*.diff`
> بالاتجاه نفسه (patch -p1 من جذر `<PROJECT>`) — كلها صغيرة ومراسيها فريدة.

## 3) التحقق بعد الدمج

**أ) محلياً (بلا سيرفر) — إذا عندك نسخة runtime محلية:**
```bash
QMOM_RUNTIME=<مسار runtime> python3 tools/verify_qmom1_fix.py     # متوقع: PASS 41 / FAIL 0
QMOM_RUNTIME=<مسار runtime> python3 tools/verify_engine_e2e.py     # متوقع: PASS 12 / FAIL 0
# (عدّل RUNTIME/DATA/PAYLOAD داخل السكربتين لبيئتك)
```

**ب) حياً (البوابة الحقيقية — نفس اختبار #10000604 الحرفي):**
```bash
python3 tools/live_verify.py    # يبث حمولة #10000604 نفسها → يستطلع → يفحص كل شيء
```
يتحقق تلقائياً من: (1) `summary.math_audit.momentum_gate` موجود وكامل، (2) أعمدة
الموشرات الـ25 **بقيم حقيقية** في الشموع البصرية، (3) `osc_gate` و`iblocked_*`
يرصدان، (4) الصفقات ≤ 15 (متوقع **11** على نفس النافذة: 46 خام ⇒ 11 مسموح + 35
ممنوع)، (5) كل الأعمدة القديمة موجودة، (6) العدادات متسقة مع الصفقات الفعلية.

---

## 4) ماذا سيتغير في الأرقام (توقع صادق — من المحاكاة المحلية على نفس بيانات MMT 15m)

| المقياس | الأساس #10000604 | QMOM1 المعطوبة #10000616 | **QMOM1-FIX1 (متوقع)**
|---|---|---|---|
| دخولات خام الكمومية (قبل بوابة الزخم) | 46 | 46 | **46** (نفسها — لم نلمس منطق الكمومية) |
| دخولات نهائية بعد بوابة الزخم | — | 46 (البوابة شكلية!) | **11** |
| ممنوعة بالزخم | — | 0 | **35** |
| أعمدة osc بقيم | — | 0/25 (كلها None) | **25/25** |
| `momentum_gate` في التقرير | — | لا يوجد | **كامل** (عدادات/تحذيرات/نسخ/مصدر الزمن) |

الأثر على الدخولات الخاطئة/المتأخرة هو هدف البوابة بالضبط: منعت 35 دخولاً مشكوكاً
فيها على نافذة الاختبار المحلية — الرقم النهائي على نافذة السيرفر الكاملة (109,098
شمعة) سيخرج من التشغيل نفسه.

## 5) الاسترجاع (Rollback)

انسخ نسخ ما قبل الإصلاح للملفات الخمسة (أساس بصمات `FILES-QMOM1-FIX1.md5` قسم
BASIS)، أو طبّق `diffs/*.diff` معكوسة. لا شيء آخر يعتمد عليها: التغييرات كلها
داخل مسارات QMOM1 نفسها + حقن مفتاح اختياري في math_audit (None عند غياب محرك
الزخم = استراتيجيات أخرى بت-بت كما هي).

## 6) روابط العقود

- **تقرير الإصلاح الكامل (الجذر/الأدلة/السلوك بت-بت):** `REPORT-QMOM1-FIX1-AR.md`
- **عقد الفرونت المحدَّث (بطاقات بوابة الزخم + أعمدة الشفافية):** `FRONTEND-AGENT-BRIEF-QMOM1-FIX1-AR.md`
- بصمات الأساس والمُصلَح: `FILES-QMOM1-FIX1.md5`
