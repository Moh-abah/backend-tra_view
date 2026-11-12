# 📦 دليل الدمج — R50.1 (حزمة الدمج النهائية)

> **ما هذه الحزمة؟** 10 ملفات كود معدّلة + هذا الدليل + التقرير الكامل + بصمات MD5.
> تُدمج فوق نسختك الحالية في `~/TR_platform/backend` **بدون أي تغيير في قاعدة البيانات أو العقود أو دقة النتائج**.

---

## محتويات الحزمة (13 ملفًا)

```
app/routers/backtest.py        ← قلب الإصلاح (لا تجميد + كاش مضغوط) + إصلاحات ذاكرة R50.1
app/routers/backtest1.py       ← نفس العلاج للمسار الموحد + فحص كاش مبكر + إبطال حذف
app/services/task_registry.py  ← نداءات Redis خارج حلقة الأحداث + تحلل آمن
app/services/candle_cache.py   ← /candle-cache خفيف
app/utils/json_safe.py         ← orjson (تسريع 3-5× مع رجوع آمن للـ json القياسي)
app/main.py                    ← GZipMiddleware + إعادة محاولة init_db
app/database/session.py        ← مسبح PG موسّع (10+20 قابل للضبط)
Dockerfile                     ← عمال uvicorn متعددون
docker-compose.yml             ← عامل Celery محصّن (تزامن 2 + إعادة تدوير + BLAS=1)
requirements.txt               ← + orjson
REPORT-R50-AR.md               ← التقرير الكامل (تقرير المطوّر + تدقيق R50.1 + إعادة البناء + ضبط جهازك)
INSTALL-R50-MERGE-AR.md        ← هذا الدليل
FILES-R50.md5                  ← بصمات التحقق
```

---

## خطوات الدمج (10 دقائق)

```bash
# 0) (لجهاز 6 أنوية) افحص الذاكرة واختر صفك من الجدول أدناه قبل البدء
free -h

# 1) نسخة احتياطية على السيرفر
cd ~/TR_platform/backend
cp -r app /tmp/app-backup-r50 && cp Dockerfile docker-compose.yml requirements.txt /tmp/

# 2) ارفع الحزمة إلى السيرفر (أو scp من جهازك) ثم:
mkdir -p /tmp/r501 && unzip -o backend_R50_1_PERFORMANCE.zip -d /tmp/r501

# 3) تحقق من سلامة الملفات (يجب أن ترى OK اثنتي عشرة مرة)
cd /tmp/r501 && md5sum -c FILES-R50.md5

# 4) انسخ الملفات فوق الكود (لا تلمس .env إطلاقًا في هذه الخطوة)
cp app/routers/backtest.py        ~/TR_platform/backend/app/routers/
cp app/routers/backtest1.py       ~/TR_platform/backend/app/routers/
cp app/services/task_registry.py  ~/TR_platform/backend/app/services/
cp app/services/candle_cache.py   ~/TR_platform/backend/app/services/
cp app/utils/json_safe.py         ~/TR_platform/backend/app/utils/
cp app/main.py                    ~/TR_platform/backend/app/
cp app/database/session.py        ~/TR_platform/backend/app/database/
cp Dockerfile docker-compose.yml requirements.txt ~/TR_platform/backend/

# 5) (اختياري حسب الجدول) أضف سطر الضبط في .env — انظر "جدول الذاكرة"

# 6) أعد البناء — إلزامي لأن Dockerfile و requirements تغيّرا
cd ~/TR_platform/backend && docker compose up -d --build

# 7) راقب الإقلاع (Ctrl+C للخروج من المتابعة — الحاويات تستمر)
docker logs -f trading-backend
docker logs -f trading-celery-worker   # يجب أن ترى: ready · concurrency: 2
```

---

## جدول الذاكرة (أضف السطر المناسب في `.env` — اختياري)

| ذاكرة السيرفر (`free -h` ← total) | الأسطر المضافة في `.env` |
|---|---|
| **16GB** (الأرجح لخطة 6 أنوية) | لا شيء. للطاقة القصوى: `CELERY_WORKER_CONCURRENCY=3` |
| **8GB** | `BACKTEST_CACHE_BUDGET_MB=600` + `BACKTEST_PARSED_CACHE_MAX_MB=250` + `WEB_CONCURRENCY=1` |
| **4GB** | `BACKTEST_CACHE_BUDGET_MB=400` + `BACKTEST_PARSED_CACHE_MAX_MB=200` + `WEB_CONCURRENCY=1` + `CELERY_WORKER_CONCURRENCY=1` |

بعد أي تعديل في `.env`: `docker compose up -d` (بلا --build).

---

## إثبات الشفاء على الإنتاج (5 دقائق)

```bash
# أ) النبض يجب أن يبقى تحت 0.5s دائمًا — شغّلها وافتح باك-تست ثقيلًا من المتصفح
watch -n1 'curl -s -o /dev/null -w "health: %{time_total}s\n" http://localhost:8000/health'

# ب) عامل Celery حي ويستقبل
docker logs --tail 20 trading-celery-worker

# ج) الضغط يعمل (الحجم يجب أن يكون MBs لا عشرات MBs)
HEAVY=$(docker exec trading-postgres psql -U trader -d trading_db -tAc \
  "SELECT id FROM backtest_runs ORDER BY created_at DESC LIMIT 1")
curl -s -H "Accept-Encoding: gzip" -o /dev/null \
  -w "size=%{size_download}B time=%{time_total}s\n" \
  "http://localhost:8000/api/v1/backtest1/get/$HEAVY"

# د) الفتح المتكرر سريع (كاش البايتات المبكر — إصلاح R50.1)
curl -s -o /dev/null -w "warm: %{time_total}s\n" -H "Accept-Encoding: gzip" \
  "http://localhost:8000/api/v1/backtest1/get/$HEAVY"

# هـ) أطلق باك-تست جديدًا من الواجهة أثناء تشغيل (أ) — النبض لا يتأثر
```

**علامات النجاح:** /health ثابت تحت 0.5s أثناء أي عملية · `docker ps` يظهر `trading-backend` و `trading-celery-worker` و `(healthy)` · الفتح المتكرر <0.2s · لا `Started server process [1]` متكررة في اللوجز.

---

## التراجع (إن احتجت — لن تحتاج)

```bash
cp -r /tmp/app-backup-r50/* ~/TR_platform/backend/app/
cp /tmp/Dockerfile /tmp/docker-compose.yml /tmp/requirements.txt ~/TR_platform/backend/
cd ~/TR_platform/backend && docker compose up -d --build
```

---

## ماذا يحدث بعد إعادة تشغيل السيرفر (reboot)؟

كل شيء ينهض تلقائيًا: `restart: unless-stopped` على الحاويات الأربع + بيانات PostgreSQL في الحجم الدائم `postgres_data` + كاش الشموع في `history_cache`. سيرفرك عليه تحديث نواة معلق (`System restart required`) — أفضل توقيت له **بعد الدمج والتحقق مباشرة**.
