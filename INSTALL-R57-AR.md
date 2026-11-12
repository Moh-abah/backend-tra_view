# 🚀 INSTALL-R57-AR — تركيب حزمة الدمج (دقيقتان)

> الحزمة: `backend_R57_MERGE.zip` — 5 ملفات فوق نسختك المرجعية
> (b81c7ea45dcf6fd62926d277edf3f5c8 = مشروعك + R55).

---

## المسار أ — كنت ركّبت R56 بالفعل (ملف واحد فقط)

```bash
cd ~/TR_platform/backend

# نسخة احتياطية سريعة للملف الوحيد الذي سيتغير
cp app/services/candle_cache.py app/services/candle_cache.py.bak-r56

# فك الحزمة فوق المشروع (الكتابة فوق الملفات فقط — unzip -o)
unzip -o backend_R57_MERGE.zip \
    'app/services/candle_cache.py' -d ~/TR_platform/backend

# تحقق البصمة (يجب أن تطابق عمود «بعد»)
md5sum app/services/candle_cache.py
# متوقع: 59bae32c56c0ed2fc778c6feeba267d5
```

## المسار ب — من نسختك المرجعية (الخمسة معًا)

```bash
cd ~/TR_platform/backend

# نسخ احتياطي سريع
mkdir -p /tmp/bak-r57 && cp app/routers/backtest1.py app/routers/backtest.py \
    app/tasks/backtest_tasks.py app/services/candle_cache.py \
    docker-compose.yml /tmp/bak-r57/

# فك الحزمة كاملة (تحافظ على بنية app/ — الكتابة فوق الموجود فقط)
unzip -o backend_R57_MERGE.zip -d ~/TR_platform/backend

# تحقق البصمات الخمس
md5sum app/routers/backtest1.py app/routers/backtest.py \
      app/tasks/backtest_tasks.py app/services/candle_cache.py docker-compose.yml
```

المتوقع (عمود «بعد» في FILES-R57.md5):
```
ada2cd54969942a885e3ec3e1861e9b0  app/routers/backtest1.py
85067174486d3a2a2d6a8e355c3d1d5f  app/routers/backtest.py
e49523ff764f1357a95036b87003486d  app/tasks/backtest_tasks.py
59bae32c56c0ed2fc778c6feeba267d5  app/services/candle_cache.py
a79089f4d08b14381c561ba4c317ecac  docker-compose.yml
```

---

## إعادة التشغيل

```bash
cd ~/TR_platform
docker compose up -d --build trading-backend trading-celery-worker
docker compose ps          # الاثنان healthy خلال ~30 ثانية
docker compose logs -f trading-backend trading-celery-worker --tail 50
```

> ملاحظة: `docker-compose.yml` داخل الحزمة يحمل إصلاح healthcheck العامل —
> إن عدّلت نسختك اليدوية (منافذ/مجلدات) فاربطها قبل التركيب، أو ركّب
> الملفات الأربعة في app/ فقط وأبقِ compose لديك كما هو مع تعديل فحص
> العامل يدويًا (التفاصيل في README-R56 داخل تقرير الجولة).

## اختبار القبول بعد التركيب (دقيقتان)

1. **عامل Celery يظهر healthy** (وليس unhealthy كالسابق).
2. **لا مزيد من «Started server process» المتكررة** في سجل trading-backend
   خلال 10 دقائق من التشغيل الطبيعي.
3. **اختبار النهاية الحاسم** — من الواجهة شغّل باك-تست بأي نافذة قصيرة
   قديمة (مثلاً 3 أيام من 2024) على المسار الموحد، ثم افتح تاب الصفقات:
   آخر صفقة يجب أن تكون داخل النافذة — لا صفقات بعدها بأشهر.
4. **فحص سريع برمجي** (اختياري): سكربت «فحص سريع بعد التركيب» في أسفل
   README-R57-AR.md — يطبع `R57 OK ✅`.

## التراجع (إن احتجت)

```bash
cp /tmp/bak-r57/* ~/TR_platform/backend/app/  # أو المسار الصحيح لكل ملف
cp /tmp/bak-r57/docker-compose.yml ~/TR_platform/
docker compose up -d --build trading-backend trading-celery-worker
```
