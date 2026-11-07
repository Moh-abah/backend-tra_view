# تعليمات الدمج — ROUND34 (الحزمة الأكفأ: الموحدة الكاملة)

> **ما هذه الحزمة؟** الجولة 34 الكاملة: نواة واحدة `zigzag_fib_core.py`
> لزقزاق + فيبو + نطاقات (الاستراتيجيات الثلاث)، إصلاح جذري لعلة الأزمنة
> الصفرية في رسومات الباك تست (ISO)، تمرير الحجم لمسار الرسم، ومستويات
> فيبو لكل نطاق تاريخي بحدود ولادة/نهاية.
>
> **مُثبتة بالفحص (على نسختك نفسها قبل التسليم):** 40/40 رسمية + 7/7 لقضية
> APPBUSDT + تطابق 7/7 هاشات اللقطة الذهبية — كل ذلك مع حجب الشبكة بالكامل.

---

## 1) محتويات الحزمة (28 ملفاً)

### كود — جديدة (2):
1. `app/services/indicators/zigzag_fib_core.py` — **النواة الموحدة** (زقزاق luxalgo + tradingview · فيبو · نطاقات بولادة/موت · محلل وقت ISO/Z/ثوانٍ/ms)
2. `app/routers/agent_report.py` — API تقرير وكيل الفرونت

### كود — معدلة (7):
3. `app/services/indicators/overlays.py` — zigzag_channels + zigzag_fib فوق النواة
4. `app/services/indicators/overlays_zlf_e2e.py` — البطل e2e فوق النواة + levels لكل نطاق
5. `app/services/indicators/overlays_zlf_e2e_trendy.py` — الترندية فوق النواة + levels لكل نطاق
6. `app/services/indicators/trend_fractals.py` — تطبيع من النواة (إصلاح ISO للترندات)
7. `app/routers/backtest.py` — تمرير volume في مسار overlays لـ chart-data
8. `app/routers/overlays.py` — وسم الجولة 34
9. `app/main.py` — تسجيل راوتر تقرير الوكيل

### فحوصات وأدلة:
10. `verify_round32.py` — **الحزمة الرسمية 40 فحصاً** (حتمية: تعمل بلا شبكة)
11. `verify_scripts/e2e_appbusdt_test.py` — إعادة إنتاج بلاغ APPBUSDT (7/7)
12. `verify_scripts/regression_test.py` — فحص A/B بايت-ببايت (اختياري — يحتاج OLD_SRC)
13. `verify_scripts/build_visual_payload.py` + `build_html.py` — توليد صفحة التحقق البصري
14. `evidence/golden_btc_1m.json` — **بيانات اللقطة الذهبية** (2000 شمعة BTCUSDT 1m — أساس الحتمية)
15. `evidence/golden_round34.json` — هاشات النتائج المرجعية للأنواع السبعة
16. `evidence/APPBUSDT_5m_week.json` — بيانات بلاغك الفعلية (1009 شمعة)
17. `evidence/round34_visual_check.html` — التحقق البصري الجاهز (افتحه في المتصفح)
18. `evidence/round34_verification.json` + `verify_round32.json` — نتائج الفحوصات
19. `REPORT-ROUND34-AR.md` — التقرير الكامل · `MD5SUMS.txt` — بصمات السلامة

---

## 2) خطوات الدمج (5 دقائق)

```bash
# (مهم) احتفظ بنسخة احتياطية من المشروع الحالي — للاستعادة وللـ A/B الاختياري
cp -r /path/to/backend /path/to/backend_backup_before_round34

# 1) فك الحزمة فوق جذر المشروع (استبدال الملفات عند السؤال)
cd /path/to/backend
unzip -o backend_ROUND34_unified.zip

# 2) نظّف الكاش المترجم (مهم بعد أي استبدال ملفات)
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# 3) إن كان لديك محاولة ج34 سابقة (نواة zigzag_core.py) — احذف ملفها الميت:
rm -f app/services/indicators/zigzag_core.py
#   (لا يستورده شيء بعد هذا الدمج — كودي يعتمد zigzag_fib_core.py)

# 4) أعد تشغيل الخدمة — لا ترحيل قاعدة بيانات ولا متغيرات بيئة جديدة
```

### التحقق بعد الدمج:

```bash
# أ) الفحص الرسمي (40/40 — بلا شبكة، من أي مجلد):
python verify_round32.py

# ب) إعادة إنتاج بلاغ APPBUSDT (7/7 — إشارتك 07:40 بالضبط):
python verify_scripts/e2e_appbusdt_test.py

# ج) صحة الخدمة الحية:
curl http://localhost:8000/api/v1/agent/health
# → {"status":"ok","round":34,"core_spec":"ROUND34-unified-zigzag-fib"}

# د) تقرير عقود الرسم الكامل للفرونت:
curl http://localhost:8000/api/v1/agent/report | jq .
curl "http://localhost:8000/api/v1/agent/report/live?symbol=BTCUSDT&timeframe=1h" | jq .

# هـ) التحقق البصري (افتح الملف في المتصفح — بلا خادم):
#    evidence/round34_visual_check.html

# و) فحص A/B بايت-ببايت (اختياري — يقارن باحتياطك القديم):
OLD_SRC=/path/to/backend_backup_before_round34 python verify_scripts/regression_test.py
```

> **ملاحظة السكربتات:** كلها بمسارات نسبية الآن — تعمل من أي مجلد، وتقرأ
> الأدلة من `evidence/` بجوار المشروع. للمشروع في مسار آخر: `NEW_SRC=/path python verify_scripts/...`

---

## 3) ماذا تتوقع أن يتغيّر في الواجهة (للفرونت)

| البند | قبل | بعد الدمج |
|---|---|---|
| أزمنة أرجل الزقزاق/الفيبو/الترندات في شارت الباك تست | كلها `0` | صحيحة ms — **الرسومات ترسم كالحي حرفياً** |
| مراجع R وإشارات النطاقات في حمولة رسم الباك تست | غائبة (لا volume) | موجودة ومطابقة لأعمدة الاستراتيجية |
| فيبو النطاقات التاريخية | النطاق الحي فقط | **كل نطاق يحمل `levels[]`** من خط الولادة لنهاية عمره |
| عقد الرسم الحي/الباك تست | مختلفان البنية | واحد بالمعنى الحرفي (نفس الدوال والبنى والأسماء) |
| مسارات API جديدة | — | `/api/v1/agent/report` + `/report/live` + `/health` |

**إجراء فرونت واحد مطلوب:** أي كاش أمامي لأزمنة صفرية قديمة يجب إبطاله.

---

## 4) استكشاف الأخطاء

| المشكلة | الحل |
|---|---|
| `ModuleNotFoundError: app.services...` | شغّل من جذر المشروع، أو مرّر `NEW_SRC=/path/to/project` |
| نتائج فحص مختلفة عن 40/40 | تأكد أن `evidence/golden_btc_1m.json` موجود (أساس الحتمية) وأن الكاش نُظّف |
| خطأ استيراد zigzag_core | بقايا محاولة ج34 أخرى — `rm -f app/services/indicators/zigzag_core.py` |
| `verify_round32.py` يحاول الشبكة | لن يفعل إلا إذا فقد `evidence/golden_btc_1m.json` — الحتمية أولاً بالتصميم |

---

## 5) سلامة الحزمة

```bash
md5sum -c MD5SUMS.txt   # من جذر الحزمة بعد الفك
```
