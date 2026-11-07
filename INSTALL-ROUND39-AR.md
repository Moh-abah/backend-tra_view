# 🛠️ دليل تركيب الجولة 39 — إتمام عقد الحمولة (رد ج38)

> **الزمن المتوقع:** دقيقتان · **الطبيعة:** 4 ملفات — إضافات صرفة فوق ج34
> (المطابقة البرهانية: حذف الجديد = ج34 حرفياً) · **لا هجرة بيانات ولا
> إعدادات جديدة.**

---

## 1) من هم المستهدفون

خادمك الذي يشغّل **round 34** (تحقق: `curl http://<host>:8000/api/v1/overlays/health`
→ `"round": 34`). إن كنت على round 33 فركّب ج34 أولاً ثم هذه فوقها.

## 2) التركيب (فوق شجرة المشروع الحالية)

```bash
# نسخ احتياطي سريع للملفات الأربعة (احتياط لا أكثر — التعديلات إضافات صرفة)
cp app/services/indicators/zigzag_fib_core.py        /tmp/r34-backup/
cp app/services/indicators/overlays_zlf_e2e.py       /tmp/r34-backup/
cp app/services/indicators/overlays_zlf_e2e_trendy.py /tmp/r34-backup/
cp app/routers/overlays.py                          /tmp/r34-backup/

# فك الحزمة ونسخ الملفات
unzip backend_ROUND39_contract.zip -d r39
cp r39/app/services/indicators/zigzag_fib_core.py         app/services/indicators/
cp r39/app/services/indicators/overlays_zlf_e2e.py        app/services/indicators/
cp r39/app/services/indicators/overlays_zlf_e2e_trendy.py app/services/indicators/
cp r39/app/routers/overlays.py                            app/routers/

# إعادة التشغيل (Docker: docker compose restart api — أو آليتك المعتادة)
```

> ملاحظة Docker: إن كان `app/` يُنسخ داخل الصورة فأعد البناء
> (`docker compose build api && docker compose up -d api`).

> ⚠️ **تحذير مهم:** انسخ **الملفات الأربعة المعدلة فقط** كما أعلاه (أو خمسة
> مع `trend_fractals.py` — وهو مطابق لنسختك حرفياً فنسخه اختياري). **لا تنسخ
> مجلد `app/` كاملاً بالقياس عليه** — ملفات `__init__.py` المرفقة فارغة
> عمداً لعزل برهان التحقق فقط، ونسخها فوق ملفات مشروعك الحقيقية سيعطّل
> تسجيل المؤشرات.

## 3) التحقق (بالترتيب)

### 3.1 البرهان الحتمي — قبل الإقلاع (بلا شبكة، 3 ثوانٍ)

```bash
cd r39
python3 verify_scripts/verify_round39_contract.py
# المتوقع: النتيجة: 50/50 فحصاً ناجحاً · 0 إخفاق
# (يقارن baseline_r34 المرفقة بملفات ج39 على اللقطة الذهبية 2000 شمعة)
```

لإعادة البرهان على ملفات **خادمك الفعلية** (بعد النسخ):

```bash
python3 verify_scripts/verify_round39_contract.py \
    --baseline verify_scripts/baseline_r34 \
    --candidate /path/to/your/project
# (كلا المسارين جذر مشروع — المجلد الذي يحتوي app/ بداخله)
```

### 3.2 بعد الإقلاع

```bash
curl -s http://<host>:8000/api/v1/overlays/health
# المتوقع: "round": 39 وround_note تبدأ بـ ROUND39
```

### 3.3 فحص الحمولة الحية (نفس نداءات الفرونت)

```bash
# باك-تست تجريبي ثم:
curl -s "http://<host>:8000/api/v1/backtest/<id>/chart-data" | python3 -c "
import json,sys
cd = json.load(sys.stdin)
zz = cd['overlays']['overlays']['zzfib_e2e']
print('pivots:', len(zz.get('pivots', [])))          # متوقع: legs + 1
print('window:', zz.get('window'))                    # متوقع: bars/time_from/to
lv = zz['ranges'][0]['levels'][0]
print('level fields:', sorted(lv.keys()))             # يشمل display/is_launch
print('launch level:', [l['display'] for l in zz['ranges'][0]['levels'] if l['is_launch']])
# متوقع: مستوى واحد (0.618 بمقياس المستخدم = 0.382 محرك)
"
```

### 3.4 من الواجهة (الفرونت)

شغّل باك-تست البطل E2E — يجب أن يظهر الزقزاق والفيبو كما في ج38 **بلا أي
تراجع**، والتشخيص يقرأ المصادر من الباكند مباشرة.

## 4) ماذا لو ظهرت مشكلة؟

| العرض | السبب | الحل |
|---|---|---|
| `verify` أقل من 50/50 | ملفات ج34 معدّلة يدوياً عندك | شغّل مع `--baseline` موضعاً لنسخة ج34 الأصلية من حزمة ج34 |
| health لا يزال 34 | نسخ `app/routers/overlays.py` لم يتم أو كاش الصورة | أعد النسخ/البناء |
| الفرونت لا يرى pivots | الواجهة لا تزال تشتق من legs (ج38) | لا ضرر — مرِّر `REPLY-TO-FRONTEND-R39-AR.md` للوكيل ليفضّل حقول ج39 |

## 5) التراجع (لو لزم)

```bash
cp /tmp/r34-backup/*.py مواضعها الأصلية   # إرجاع ج34 حرفياً
```
(لن يلزم — التعديلات إضافات صرفة، لكن الاحتياط واجب.)

## 6) سلامة الحزمة

```bash
md5sum -c MD5SUMS.txt   # من جذر الحزمة بعد الفك
```
