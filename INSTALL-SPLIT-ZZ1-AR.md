# 📦 دليل تركيب حزمة SPLIT-ZZ1 «الخروج المقسم بانعكاس هيكل الزقزاق» + الشرط الخامس

> **الأساس المطلوب:** أن يكون `backend-SPLIT-TP1-MERGE.zip` منشورًا على السيرفر الحي
> (161.97.73.254) — هذه الحزمة **إضافات نقية فوقه** (4 ملفات فقط).
> إن لم يكن SPLIT-TP1 منشورًا بعد: انشر حزمته أولًا (دليلها الخاص)، ثم هذه.

---

## ما الذي تضيفه هذه الحزمة؟ (طلبان حرفيان من صاحب القرار — 2026-11-19)

1. **SPLIT-ZZ1 — الخروج المقسم بانعكاس هيكل الزقزاق:**
   «باقي شيء وهي طريقه الخروج حق تقسيم الخروج عشان اقدر اخصصها على اي استراتيجيه
   بانعكاس هيكل الزقزاق سواء ع نفس الشارت او فريم اقل منه او فريم اعلى منه»
   — حقل جذري جديد في تكوين الباك-تست:
   `"structure_split_exits": [{resolution, length, size_percent, enabled}, ...]`
   كل قاعدة تحسب انعكاس هيكل الزقزاق (LL+LH — CHoCH) على **أي فريم** (نفس الشارت ·
   أدق ببيانات حقيقية · أعلى بتجميع صاعد) وعند كل انعكاس أثناء فتح الصفقة تُباع
   حصتها من الكمية الأصلية عند open الشمعة التالية.

2. **الشرط الخامس في بوابة الزخم QMOM1:**
   «بالنسبة لrsi اليومي ذو الااعداد 14/14/2 يجب ان لا يتجاوز مستوى 60 اي بمعنى
   حدوده بين مستوى 50 و 60 فقط» — `osc:rsi_1d_14_14.value <= 60` (مع الشرط الرابع
   النطاق الفعلي: 50 < RSI ≤ 60) — مضاف إلى قالب QMOM1 في presets + حمولة المثال.

---

## الملفات الأربعة (استبدال فوق الأساس المنشور)

| الملف في الحزمة | المسار على السيرفر | ماذا فيه |
|---|---|---|
| `app/services/indicators/overlays_zone_exit_mtf.py` | نفس المساس | + `compute_zone_exit_same` (انعكاس الهيكل على فريم الشارت نفسه — نفس آلة الكمومية بت-بت، متحقق على MMT: 25=25 حدثًا صفر اختلاف) |
| `app/backtest/schemas.py` | نفس المسار | + نموذج `StructureSplitExit` + الحقل `structure_split_exits` + الفاليديتورز (أشكال مريحة + رفض >100% برسالة عربية 422) |
| `app/backtest/engine1.py` | نفس المسار | + الحساب (`_compute_structure_split_events` مع مسار LTF الحقيقي) + التنفيذ عند open الشمعة التالية + الاستنفاد + المحاسبة (metadata.structure_split + مصالحة الختام) + صدى risk_echo |
| `app/services/strategy/presets.py` | نفس المسار | + الشرط الخامس في قالب QMOM1 (الشروط الأربعة كما هي + الخامس الجديد) |

**لا يُلمس أي ملف آخر إطلاقاً.** غياب `structure_split_exits` من أي حمولة قائمة ⇒
**هوية بت-بت كاملة** (مثبتة: -112.867057$ · 11 صفقة · منحنى الرصيد كاملًا — مطابق
للأساس المنشور بت-بت على شجرتين مستقلتين).

---

## خطوات التركيب

```bash
# 1) خذ نسخة احتياطية من الملفات الأربعة الحالية (سطر واحد)
cd /path/to/backend
for f in app/services/indicators/overlays_zone_exit_mtf.py \
         app/backtest/schemas.py app/backtest/engine1.py \
         app/services/strategy/presets.py; do cp "$f" "$f.bak-splitzz1"; done

# 2) انسخ ملفات الحزمة فوقها (من مجلد الحزمة)
cp app/services/indicators/overlays_zone_exit_mtf.py  <backend>/app/services/indicators/
cp app/backtest/schemas.py                            <backend>/app/backtest/
cp app/backtest/engine1.py                            <backend>/app/backtest/
cp app/services/strategy/presets.py                 <backend>/app/services/strategy/

# 3) تحقق من البصمات (يجب أن تكون كلها OK)
cd <backend>
md5sum -c FILES-SPLIT-ZZ1.md5

# 4) امسح ذاكرة بايثون وأعد تشغيل الخدمة
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
# (أعد تشغيل الخدمة كما تعتاد — docker/systemd)
```

---

## بوابة القبول الحية (3 مهام — الأرقام المتوقعة بت-بت)

بعد النشر، شغّل الحمولات الثلاث من `payloads/` عبر `POST /api/v1/backtest1/run`
(نفس MMTUSDT · 15m · نافذة #10000604 · $1000 · max_positions=10):

| # | الحمولة | المتوقع بت-بت |
|---|---|---|
| G1 | `payload_qmom1_mmt_10000604.json` (من جولة SPLIT-TP1 — بلا splits) | **-112.867057$ · 11 صفقة** — هوية كاملة مع الأساس المنشور (هذا أصرم اختبار: لا شيء انكسر) |
| G2 | `payload_qmom1_mmt_5cond.json` (الشروط الخمسة) | **-15.241165$ · 2 صفقة** (البوابة الخمسة: 11→2 — عزل الشرط الخامس) |
| G3 | `payload_qmom1_mmt_5cond_splitzz.json` (الخمسة + انعكاسان مقسمان) | جني جزئي حقيقي (نقاط partial_exit على الشارت) — الرصيد = 1000 + Σ pnl الصفقات |

**إن فشلت G1 بت-بت ⇒ لا تكمل: راجع التركيب.** (فرق بيانات أمامية بضعة سنتات على
نهاية النافذة مقبول كما في الجولات السابقة — الأرقام المذكورة على نفس لقطة البيانات.)

## عقد مختصر للواجهة (التفصيل الكامل في FRONTEND-AGENT-BRIEF-SPLIT-ZZ1-AR.md)

```json
"structure_split_exits": [
  {"resolution": "same",  "length": 100, "size_percent": 25, "enabled": true},
  {"resolution": "5m",   "length": 25,  "size_percent": 25, "name": "انعكاس 5 دقائق"}
]
```
- `resolution`: `same` = فريم الشارت نفسه · أو أي فريم (`5m/15m/1h/4h/1d/1D/1W/1M...`)
  — أدق يُجلب حقيقيًا من طبقة البيانات، أعلى يُبنى بتجميع صاعد.
- `length`: عيار رادار الزقزاق على ذلك الفريم (الافتراضي 100 عند الغياب).
- `size_percent`: النسبة من **الكمية الأصلية** تباع عند كل انعكاس (ربع = 25).
- `enabled`: تعطيل القاعدة = `false` (محايد تمامًا).
- المجموع عبر القواعد ≤ 100% (رفض 422 عربي).
- التنفيذ: انعكاس يُؤكد على إغلاق شمعة ⇒ **بيع جزئي عند open الشمعة التالية**
  (نفس دلالات exit_rules). خروج كامل بنفس الشمعة ⇒ أولويته أعلى (لا جني جزئي عنده).
- يظهر في: نقاط `partial_exit` (trade_points) + `trades[].partial_exits` +
  `trades[].metadata.structure_split` + `math_audit.risk_echo.structure_split_*`.

— السديم 🌌
