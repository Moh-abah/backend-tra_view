# خطة التراجع R45 (فورية وآمنة)

## التراجع الكامل إلى ما قبل R45 (يبقى R44)

الملفات الأربعة المعدّلة تعود لنسخها في `rollback/` (وهي نسخ R44 كما были
قبل R45)، وتُحذف الملفات الأربعة الجديدة:

```bash
# 1) أعد الملفات المعدلة إلى نسخ R44
cp rollback/backtest1.py      app/routers/backtest1.py
cp rollback/backtest.py       app/routers/backtest.py
cp rollback/backtest_tasks.py app/tasks/backtest_tasks.py
cp rollback/config.py         app/config.py
# (session.py لم تتغير في R45 — لا شيء تفعله لها)

# 2) احذف ملفات R45 الجديدة
rm app/models/backtest_task.py
rm app/models/candle_cache.py
rm app/services/task_registry.py
rm app/services/candle_cache.py

# 3) أعد التشغيل
docker compose restart api worker
```

## البيانات بعد التراجع

- جدولا `backtest_tasks` و`candle_cache` و`task_id_counter` **يبقيان في
  القاعدة** (لا يحذفهما التراجع) — الجداول الجديدة لا يقرؤها كود ما قبل
  R45 فلا تؤثر بشيء، والسجل التاريخي محفوظ إن أعدت الترقية لاحقاً.
- جدول `backtest_runs` (النتائج الكاملة) لم يمَسه R45 إطلاقاً.
- النتائج التي حُفظت أثناء R45 تُقرأ عاديًا بعد التراجع عبر `/get/{id}`
  (نفس الجدول ونفس العقد).

## حذف الجداول نهائياً (اختياري — فقط إن أردت نظافة كاملة)

```sql
-- تحذير: يمحو سجل العمليات والكاش نهائياً (لا يمس النتائج في backtest_runs)
DROP TABLE IF EXISTS backtest_tasks;
DROP TABLE IF EXISTS candle_cache;
DROP TABLE IF EXISTS task_id_counter;
```

## تعطيل بلا تراجع (أسرع حل وسط)

- كاش الشموع متوقف: `CANDLE_CACHE_ENABLED=false` (جلب مباشر كما قبل).
- كاش المسار القياسي فقط متوقف: `CANDLE_CACHE_DFSPACE=false`.
- تنظيف المهام الميتة متوقف: `TASK_REGISTRY_REAP_SECONDS=0`.

الترقيم والسجل لا يمكن "تعطيلهما" جزئياً — إن أردت العودة للمعرّفات
السداسية العشوائية فهذا هو التراجع الكامل أعلاه (دقيقتان).
