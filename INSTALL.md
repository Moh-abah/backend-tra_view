# دليل تركيب R45 — سجل العمليات المؤسساتي + كاش الشموع

> **هذه الحزمة تراكمية فوق R44**: أنت لم تدمج `backend_ROUND44_LOCKSHIELD.zip`
> بعد — لا مشكلة. هذه الحزمة تتضمن درع R44 كاملاً (نفس session.py حرفياً
> بنفس البصمة) + كل ملفات R45. ادمج هذه الحزمة وحدها وستحصل على الجولتين معاً.

## ما الذي تحصل عليه

| المشكلة التي رفعتها | الحل في هذه الحزمة |
|---|---|
| «الباك تست لا يتم تخزينها في قاعدة البيانات ونريد نوصل لها ونراجعها» | كل نتيجة تُحفظ في `backtest_runs` (كما كان) + **سجل عمليات دائم** `backtest_tasks` يوثق كل عملية برقمها وحالتها ومدتها ولقطتها السطحية — يُسترجع أي اختبار سابق من `/tasks` و`/get/{id}` حتى بعد إعادة التشغيل |
| «التاسك مرقمة f397b2fa — أريدها 10000001 ثم 10000002 حتى 99999999» | عدّاد ذرّي في قاعدة البيانات (`task_id_counter`): ترقيم تسلسلي صريح يظهر في كل الردود والسجلات، لا يعيد الأرقام حتى بعد حذف الصفوف، وينتهي بخطأ صريح عند 99999999 |
| «كل مرة بيجلب شموع جديدة — المفروض يخزنها ويجلب فوقها آخر شموع» | جدول `candle_cache`: أول تشغيل لرمز/فريم يجلب ويخزن نهائياً، وكل تشغيل تالٍ يقرأ من القاعدة فوراً ويجلب **فقط الرأس الناقص** — سنة كاملة بفريم الدقيقة تُجلب مرة واحدة |
| «يتحمل أكثر من باك تست ويرسل إشعارات للتقدم وكم بقي» | `/status/{رقم}` يعيد نسبة التقدم + المرحلة + الرسالة + المنقضي + ETA (من متوسط آخر 10 عمليات ناجحة لنفس الرمز/الفريم، وإلا استقراء من النسبة) — والنظام يتحمل تشغيلات متوازية (مثبت: 6 متوازية + قارئان بصفر أخطاء) |
| «قائمة المكتبة تعرض — و — فقط» | `GET /tasks` يعيد لكل عملية: الرقم، الاسم، الحالة، النسبة الحية، WR%، عدد الصفقات، PnL%، المدة، التاريخ — كل ما تحتاجه شاشة Library |

## الملفات (9 للتشغيل + أدلة + بطاريات)

**معدّلة (5):**
```
app/config.py                      ← إعدادات R45 (TASK_ID_*/CANDLE_CACHE_*)
app/routers/backtest1.py           ← الترقيم + السجل + الكاش + /tasks + /candle-cache
app/routers/backtest.py            ← الترقيم + السجل + /status الرقمي
app/tasks/backtest_tasks.py        ← رقم العملية + CachedDataService في المُنفّذ
app/database/session.py            ← درع R44 (لم يُمس — نفس بصمة R44 حرفياً)
```

**جديدة (4):**
```
app/models/backtest_task.py        ← ORM سجل العمليات + عدّاد الأرقام
app/models/candle_cache.py         ← ORM كاش الشموع
app/services/task_registry.py      ← خدمة السجل (تخصيص/تقدم/مدد/ETA/تنظيف)
app/services/candle_cache.py       ← خدمة الكاش + غلاف CachedDataService
```

**أدلة وأدلة إثبات:**
```
test_battery_r45.py                ← بطارية 60 فحصاً (بلا سيرفر)
prove_r45.py + بيئة الساندبوكس    ← الإثبات الحي 34/34 فوق HTTP
rollback/                          ← نسخ ما قبل R45 للتراجع الفوري
MD5SUMS                            ← بصمات كل ملفات الحزمة
```

## خطوات التركيب (5 دقائق)

```bash
# 0) نسخة احتياطية (إلزامية)
cp -r your-backend your-backend-backup-before-r45

# 1) انسخ الملفات التسعة فوق مصدرك (نفس المسارات)
unzip backend_ROUND45_REGISTRY.zip -d r45
cp r45/app/config.py                     your-backend/app/config.py
cp r45/app/database/session.py           your-backend/app/database/session.py
cp r45/app/routers/backtest.py           your-backend/app/routers/backtest.py
cp r45/app/routers/backtest1.py          your-backend/app/routers/backtest1.py
cp r45/app/tasks/backtest_tasks.py       your-backend/app/tasks/backtest_tasks.py
cp r45/app/models/backtest_task.py       your-backend/app/models/backtest_task.py
cp r45/app/models/candle_cache.py         your-backend/app/models/candle_cache.py
cp r45/app/services/task_registry.py     your-backend/app/services/task_registry.py
cp r45/app/services/candle_cache.py      your-backend/app/services/candle_cache.py

# 2) لا هجرة يدوية — الجداول الثلاثة تُنشأ تلقائياً عند أول طلب
#    (backtest_tasks + task_id_counter + candle_cache — CREATE TABLE IF NOT EXISTS)

# 3) أعد تشغيل الخدمة والـ worker معاً (كلاهما يستخدمان العدّاد)
docker compose restart api worker   # أو ما يعادلها

# 4) تحقق
curl http://localhost:8000/api/v1/backtest1/tasks
#    ← {"success": true, "count": 0, "stats": {...}, "data": []}

# 5) البطاريات (من جذر مشروعك)
python3 test_battery_r45.py    # ← 60/60
python3 test_battery_r44.py    # ← 44/44 (E2 يتحقق من ملفات محركك الحقيقية)
```

## الإعدادات (كلها اختيارية — الافتراضي آمن بلا أي .env)

| المتغير | الافتراضي | المعنى |
|---|---|---|
| `TASK_ID_START` | `10000001` | أول رقم عملية |
| `TASK_ID_MAX` | `99999999` | نهاية العداد (خطأ صريح بعده) |
| `TASK_REGISTRY_REAP_SECONDS` | `1800` | تنظيف المهام الميتة (سقوط العملية). `0` = تعطيل |
| `CANDLE_CACHE_ENABLED` | `true` | مفتاح الكاش الرئيسي (`false` = سلوك ما قبل R45) |
| `CANDLE_CACHE_DFSPACE` | `true` | كاش مسار المحرك القياسي (فضاء DataFrame) |
| `CANDLE_CACHE_MAX_CANDLES` | `600000` | سقف الشموع لكل مفتاح (الأحدث يبقى) |
| `CANDLE_CACHE_REFRESH_HEAD` | `true` | جلب أحدث الشموع فوق المخزنة |

## ملاحظات تشغيلية مهمة

1. **أعد تشغيل الـ worker مع الـ API معاً** — كلاهما يخصص أرقاماً من نفس
   العدّاد (آمن للتزامن، لكن النسخة القديمة من الـ worker لن تحدّث السجل).
   أثناء نشر مختلط (API جديد + worker قديم) يعمل كل شيء، وصف السجل يُشفى
   تلقائياً من نتيجة celery عند قراءة الحالة.

2. **فجوات نادرة في الترقيم ممكنة** عند إعادة محاولة بعد قفل عابر — نفس
   سلوك sequences في PostgreSQL. التسلسل والتفرد مضمونان دائماً.

3. **الكاش لا يغيّر نتائج المحاكاة إطلاقاً**: النافذة المطلوبة تُقص لنفس
   الحدود، وأي فشل داخلي في الكاش ⇦ جلب مباشر (سلوك اليوم). أسوأ حالة =
   ما قبل R45، لا كسر أبداً.

4. **حجم القاعدة**: سنة بفريم الدقيقة ≈ 525 ألف شمعة ≈ 60-80MB لكل فضاء
   (c للمسار الموحد وd للمسار القياسي). السقف الافتراضي 600 ألف شمعة لكل
   مفتاح. راقبها عبر `GET /backtest1/candle-cache` وامسح مفتاحاً بـ
   `DELETE /backtest1/candle-cache/{cache_key}` متى شئت.

5. **التوقيتات في السجل كلها UTC** (حقول `*_at` بصيغة ISO).

## التحقق بعد التركيب — سيناريو الدخان الكامل

```bash
# 1) أول عملية موحدة بالتريلينق → رقم تسلسلي
curl -X POST http://localhost:8000/api/v1/backtest1/run -H "Content-Type: application/json" -d '{
  "symbols": ["BTCUSDT"], "timeframe": "1h", "days": 30,
  "name": "اختبار-الدخان", "strategy_config": {"name": "zzfib"},
  "exit_strategy": {"strategy": "zzfib", "config": {"use_trailing": true, "trailing_giveback_pct": 20.0}}
}'
# ← {"task_id": "10000001", "task_number": 10000001, "progress": {...}, ...}

# 2) راقب التقدم
curl http://localhost:8000/api/v1/backtest1/status/10000001

# 3) شغّل ثانية بنفس الرمز/الفريم باستراتيجية مختلفة → صفر جلب جديد
#    (تحقق من meta.cache في /status)

# 4) المكتبة
curl http://localhost:8000/api/v1/backtest1/tasks

# 5) النتيجة الكاملة
curl http://localhost:8000/api/v1/backtest1/get/{backtest_id}
```
