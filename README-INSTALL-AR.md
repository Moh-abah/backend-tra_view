# حزمة دمج PRO73 — التثبيت على backend_PRO73.zip

> المصدر الحرفي: `backend_PRO73.zip` (MD5 `ad31b9a417aa7f7f26803fff752f50a8` · 576 ملفاً بما فيها الفارغات)
> هذه الحزمة = **إضافة فقط** (**23 ملفاً جديداً + 8 معدلة = 31 تغييراً فعلياً**) — صفر مساس بأي ملف آخر، وصفر مساس بمحركي الترندية/الملتهبة الأصليين (الهوية مُثبتة بت-بت بالبطارية 52/52).
>
> **عدّة سابقة مصححة**: بيانات إصدارات أقدم ذكرت «38/41 جديدًا» — كان تصنيفًا منفوخًا: ملفات `__init__.py` فارغة (0 بايت) موجودة في الأساس نفسه ظُنّت «جديدة». العدّ الحالي محسوب بمقارنة بايت-ببايت مباشرة مع محتويات الـ zip الأساس. الملفات الـ29 وحدها هي كل التغيير.

## محتوى `files/` — كل ملف بمساره الجاهز للصق (29)

**الكود — 4 جديدة:**
| المسار بعد اللصق | ما هو |
|---|---|
| `app/services/indicators/mtf_oscillator_core.py` | نواة الموشرات متعدد النسخ/الفريمات (14 فريماً · RSI+EMA+BB · MACD · Momentum · بوابة and/or/not · `skip_unavailable` · بلا نظرة مستقبلية) |
| `app/services/indicators/overlays_zlf_e2e_trendy_macd.py` | محرك «ترنديه ماكديه» (الترندية + طبقة الدمج + بوابة الحالات · عقد `zzfetm_*` → أعمدة `ind_zzfetm_*`) |
| `app/services/indicators/overlays_zlf_e2e_blazing_macd.py` | محرك «ملتهبه ماكديه» (الملتهبة + نفس الطبقة · عقد `zzfbm_*` · الأنواع s1/s2/s3/n5/n6) |
| `app/services/indicators/osc_cases.py` | نسخ المستند الكاملة (67: ماكد 28 · RSI 16 · مومنتم 23) + الحالات الـ13 بنص المالك + 6 وحدات ماكرو |

**الكود — 7 معدلة + عقد SIGMA محدّث (8 معدلة إجمالًا — إضافات داخلها فقط):**
| المسار | التعديل |
|---|---|
| `app/services/indicators/overlays.py` | التوزيع + حارس الأداء |
| `app/services/indicators/overlay_columns.py` | عقد الأعمدة + تمرير `osc_instances/osc_conditions` + إحالة بالمرجع |
| `app/services/indicators/calculator.py` | الاسم المستعار `ind_zzfetm`/`ind_zzfbm` |
| `app/services/indicators/__init__.py` | التسجيل الذاتي |
| `app/services/strategy/presets.py` | القالبان الرسميان `trendy_macdized_zero_fee`/`blazing_macdized_zero_fee` بنسخ المستند 67 |
| `app/routers/backtest.py` | خريطة عائلات الراوتر — طبقة الرسم تصل تلقائياً |
| `app/services/live_strategy_service.py` | النقطة الحية تقبل المحركين الماكديين (strategy=zigzag_fib_e2e_trendy_macd / blazing_macd) |

**البطاريات والأدلة — 12 جديدة:** `tests-r73/` (البطارية الرئيسية 52/52 · بطارية الحالات 65/65 · مكتبة التكامل · تحقق البطل 1651.25% · سجلا تشغيل اليوم `battery-run.log`/`cases-run.log` · الأدلة JSON في `tests-r73/r73-evidence/`)

**السكربتات — 3 جديدة:** `scripts/build_pro73_merge_package.py` (إعادة بناء الحزمة) · `scripts/pro73_package_extras/verify_pro73_merge.py` (التحقق ما بعد الدمج) · هذا الـ README

**التقارير — 5 جديدة:** `DELIVERY-REPORT-PRO73-FINAL-AR.md` (التسليم النهائي) · `BACKEND-REPORT-PRO73-R3-AR.md` (التقني الشامل R1→R3) · `BACKEND-REPORT-PRO73-AR.md` · `ADOPTION-REPORT-AR.md` · `ENCYCLOPEDIA-SECTION14-PRO73-AR.md` · وبصمة `FILES-PRO73.md5`

## خطوات الدمج (5 دقائق)

### على ويندوز (بلا أي أوامر)
1. فك `backend_PRO73.zip` (أساسك) في مجلد المشروع — سترى بجانب `app/` ملفات `README.md` ونحوها.
2. فك `pro73-merge-package.zip` (هذه الحزمة).
3. ادخل مجلد `files/` **المفكوك**، اعمل **تحديد الكل (Ctrl+A) → نسخ → لصق داخل مجلد المشروع** (نفس المستوى الذي فيه `app/` و`proof-lab/`)، ووافق على **استبدال الـ6 المعدلة**.
4. تحقق فوري: `python verify\verify_pro73_merge.py` من جذر المشروع (بعد فك الحزمة انقل مجلد `verify` بجانب المشروع أو شغّله من مساره). المتوقع: `PASS=9 FAIL=0` — شموع تركيبية، بلا أي بيانات خارجية.
5. (اختياري) البطاريات الكاملة: `python tests-r73\test_r73_battery.py` ثم `python tests-r73\test_r73_cases.py` (يتطلبان `SOLUSDT_1m.npz` في `r70-workspace/data`).
6. (اختياري) خدمة التحكم للفرونت إند: انسخ مجلد `control-service` بجانب الباك اند (لا داخله) وشغّل `python server.py` — منفذ ثابت 8730.

### على لينكس
```bash
mkdir backend && cd backend && unzip /path/to/backend_PRO73.zip
unzip -o /path/to/pro73-merge-package.zip -d /tmp/pkg
cp -r /tmp/pkg/files/. .
python3 /tmp/pkg/verify/verify_pro73_merge.py   # المتوقع: PASS=9 FAIL=0
```

## ملاحظات أمانة
- **ما لم يُمسّ**: كل ما عدا الـ29 أعلاه — نفس MD5 لحزمتك الأصلية (576/576).
- `MD5SUMS.txt` الأصلي يبقى كما هو؛ بصمات هذه الحزمة في `MANIFEST-MD5.txt` والبيان الكامل في `MANIFEST.json` والفروقات التفصيلية في `diffs/*.diff`.
- ملفات `__init__.py` الفارغة في مجلداتك الأصلية تبقى كما هي — الحزمة لا تعيد نسخها (كانت تُنسخ في إصدارات أقدم دون أي أثر).
- ملفات البيانات التشغيلية (`chart_states.db` ونحوها) ليست جزءاً من الدمج.
- النسخ `1s/5s/30s` غير متاحة على قاعدة 1m — تُتجاوز تلقائياً عبر `skip_unavailable` في حالة «جميع الفريمات»، وتُحسب طبيعياً عند شموع أدق (1s).
- الحد التفاعلي لنوافذ الخدمة 75 يوماً (ذاكرة)؛ نافذة البطل الكاملة (665,099 شمعة) تُتحقق عبر `tests-r73/verify_champion_1651.py` خارج الخدمة.
