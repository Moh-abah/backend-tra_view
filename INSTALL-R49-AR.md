# 🔧 R49 — إصلاح تجميد الباك اند مع الباك تست الثقيل

> **التشخيص مُثبت حيًا على PostgreSQL 17.4 حقيقي + المستند الثقيل نفسه (SOLUSDT 1m × 90 يوم = 129,600 شمعة / 87MB JSON / 208MB رد chart-data).**

---

## ١) لماذا كان النظام يتجمّد ويعيد تشغيل نفسه؟ (الجذور الثلاثة المُثبتة)

### الجذر ١ — البناء الثقيل داخل حلقة الأحداث (التجميد الكامل)
uvicorn يعمل **بعامل واحد** (`CMD ["uvicorn", ...]` بلا `--workers`) — حلقة أحداث واحدة تخدم كل شيء.
وكل هذه النقاط كانت تعمل **CPU ثقيلًا داخل الحلقة مباشرة**:

| النقطة | ما كانت تفعله | القياس الفعلي قبل الإصلاح |
|---|---|---|
| `GET /backtest1/get/{id}` | تحميل 87MB JSON من PG + تسطيح مؤشرات 129,600 شمعة **في الحلقة** وبلا أي كاش | **10.6 ثانية لكل طلب** — كل فتح من المكتبة |
| `GET /backtest/{id}/chart-data` + overlays | بناء ovl_candles + حساب 5 أنواع overlays على كامل السلسلة **في الحلقة** | **46 ثانية** (التعليق التاريخي في كودك يقيس 109-231 ثانية في الإنتاج) |
| تسلسل الرد (JSONResponse.render) | sanitize + json.dumps لرد 87-208MB **في الحلقة** | 5-10 ثوانٍ إضافية **حتى مع وجود كاش بناء** |

**النتيجة**: أثناء فتح أي باك تست ثقيل تتجمد *كل* النقاط (`/health` و`/status` و`/tasks`) — الفرونت يعرض «انتهت مهلة جلب تفاصيل الباك-تست من المحرك — أعد المحاولة».

### الجذر ٢ — إعادة التشغيل الذاتي (بصمة لوجك: `Started server process [1]` بلا أي traceback)
- healthcheck كان `timeout 5s / retries 3` → أي تجميد فوق ~90 ثانية يعلم الحاوية unhealthy.
- الذاكرة كانت تنفجر: الكاش القديم خزّن **3-4 نسخ مستقلة** لكل مستند (raw + get payload + chart base + ovl_candles) — قياس R49: **1.22GB RSS بعد 4 طلبات فقط** على مستند 87MB → OOM kill (SIGKILL بلا traceback — يطابق لوجك حرفيًا) → إعادة تشغيل → الكاش الذاكي يُفقد → الفتح التالي يعيد البناء من الصفر → حلقة الموت تتكرر.

### الجذر ٣ — المسار الموحد (exit_strategy) يعمل داخل عملية الـ API
المهام 10000002/3 ذهبت لعامل Celery، لكن **10000004 (unified-exit) اشتغلت داخل عملية الـ API** (خيط يسرق GIL طوال 127 ثانية) — لهذا توقفت استطلاعات المكتبة طوال المحاكاة في لوجك.

### 🎁 خطأ إضافي مكتشف ومُصلَّح: `Token "Infinity" is invalid`
المحاكاة أحيانًا تنتج `Infinity` في summary (sharpe/calmar عند drawdown صفري). `json.dumps` يكتبها حرفيًا وPostgreSQL يرفضها → **تضيع نتيجة محاكاة ناجحة كاملة عند الحفظ**. (ثبت حيًا: نفس التشغيلة فشلت قبل الإصلاح ونجحت بعده.)

---

## ٢) الإصلاحات (5 ملفات فقط)

| الملف | الإصلاح |
|---|---|
| `app/routers/backtest.py` | أساس معالج **واحد مشترك** لكل backtest_id يُبنى داخل `asyncio.to_thread` + كل التقطيع/الفلترة/overlays/التسلسل في خيوط عامل + كاش **bytes جاهزة** للردود (get/get1/chart-data حسب مفتاح المعاملات) + **ميزانية بايتات** للكاش (`BACKTEST_CACHE_BUDGET_MB` افتراضي 900MB) بدل LRU=12 |
| `app/routers/backtest1.py` | `/backtest1/get` أصبح بكاش + مشاركة الأساس (كان بلا كاش إطلاقًا!) + المسار الموحد يُرسل إلى **عامل Celery** عند توفر الـ broker (fallback داخلي عند غيابه) + إصلاح wait=true |
| `app/tasks/backtest_tasks.py` | مهمة `run_unified_exit_task` جديدة لعامل Celery (نفس دورة الحياة/التقدم/الحفظ حرفيًا) + `clean_for_db` ينظف ±Infinity/NaN قبل الحفظ |
| `Dockerfile` | healthcheck: `timeout 10s / retries 5` |
| `docker-compose.yml` | نفس تحصين healthcheck |

**متغيرا بيئة جديدان (اختياريان):**
- `BACKTEST_CACHE_BUDGET_MB` (افتراضي `900`) — ميزانية كاش الردود بالميغابايت. ارفعها إلى `2000`+ إن كان خادمك يملك 16GB+ وتريد استباقًا أكبر.
- `BACKTEST_CACHE_MAX` (افتراضي `3`) — أقصى عدد مداخل كاش.

---

## ٣) خطوات التنفيذ على الخادم (مؤكدة — بلا أي فقدان بيانات)

> نفّذها من مجلد `~/TR_platform/backend` — الملفات الخمسة في مجلد `R49-files` بهيكل المسارات نفسها.

```bash
cd ~/TR_platform/backend

# ── 0) نسخة احتياطية فورية للملفات الخمسة (تراجع فوري عند أي شيء) ──
mkdir -p ~/R49-backup/app/routers ~/R49-backup/app/tasks
cp app/routers/backtest.py      ~/R49-backup/app/routers/
cp app/routers/backtest1.py     ~/R49-backup/app/routers/
cp app/tasks/backtest_tasks.py  ~/R49-backup/app/tasks/
cp Dockerfile                   ~/R49-backup/
cp docker-compose.yml           ~/R49-backup/

# ── 1) رفع الملفات الخمسة من R49-files ثم النسخ ──
# (انسخ مجلد R49-files إلى الخادم بأي طريقة تناسبك ثم:)
cp R49-files/app/routers/backtest.py      app/routers/backtest.py
cp R49-files/app/routers/backtest1.py     app/routers/backtest1.py
cp R49-files/app/tasks/backtest_tasks.py  app/tasks/backtest_tasks.py
cp R49-files/Dockerfile                   Dockerfile
cp R49-files/docker-compose.yml           docker-compose.yml

# ⚠️ القاعدة الذهبية: لا تمس .env ولا أي ملف *.db

# ── 2) التحقق من سلامة الملفات (MD5) ──
md5sum app/routers/backtest.py app/routers/backtest1.py \
       app/tasks/backtest_tasks.py Dockerfile docker-compose.yml
# قارن مع MD5SUMS-R49.txt المرفق — يجب أن تتطابق حرفيًا

# ── 3) إعادة البناء والتشغيل (API + العامل معًا — مهم للمسار الموحد الجديد) ──
docker compose build --no-cache backend celery-worker
docker compose up -d

# ── 4) التحقق الحي ──
sleep 25
docker ps --format "table {{.Names}}\t{{.Status}}"
docker logs --tail 5 trading-backend
curl -s http://localhost:8000/health
```

### التحقق الحي بعد النشر (من متصفحك أو curl)
1. افتح **مكتبة الباك تستات** واضغط باك تست ثقيلًا:
   - أول فتح: ثوانٍ قليلة (بناء أول مرة) — **والنظام كله يظل حيًا**.
   - أي فتح تالي: **فوري (أجزاء من الثانية)**.
2. أثناء أي تحميل ثقيل افتح تبويبًا آخر على `/api/v1/backtest1/tasks` — يجب أن يستجيب فورًا (كان يتجمد).
3. `docker logs -f trading-backend` — ابحث عن سطور الكاش الجديدة:
   `💾 Backtest cache stored [xxxx] (entries=2, ~546MB budget=900MB)`
4. شغّل باك تست موحدًا جديدًا (استراتيجية خروج) وتأكد من سطر:
   `📤 [R49] unified-exit → Celery worker` — المحاكاة صارت في العامل المنفصل.

---

## ٤) التراجع الفوري (لو احتجت)
```bash
cd ~/TR_platform/backend
cp ~/R49-backup/app/routers/backtest.py      app/routers/
cp ~/R49-backup/app/routers/backtest1.py     app/routers/
cp ~/R49-backup/app/tasks/backtest_tasks.py  app/tasks/
cp ~/R49-backup/Dockerfile                   .
cp ~/R49-backup/docker-compose.yml           .
docker compose build backend celery-worker && docker compose up -d
```

---

## ٥) الأرقام المقاسة (قبل ← بعد) على نفس المستند الثقيل

| القياس | قبل R49 | بعد R49 |
|---|---|---|
| `GET /backtest1/get` (فتح المكتبة) | 10.6 ث **لكل طلب** (بلا كاش) | أول: ~4 ث ← **التكرار: 15-800ms** |
| `GET /backtest/get` | إعادة بناء كاملة كل مرة | أول: ~6 ث ← **التكرار: 24ms** |
| `chart-data` + 5 أنواع overlays (رد 208MB) | **46 ث تجميدًا كاملًا للنظام** | أول: ~23 ث في خيط عامل ← **التكرار: 35-60ms** |
| `/health` أثناء حمل ثقيل | 6.7 ث+ وتجميد كامل | **median 2ms / أسوأ 1.4 ث** |
| ذاكرة الكاش | نسخ متعددة، RSS انفجر 1.22GB بعد 4 طلبات | أساس واحد + bytes، **ميزانية مضبوطة** |
| حفظ نتائج بها Infinity | فشل صامت (Token "Infinity" is invalid) | **يُنظف ويُحفظ** |

**النتيجة النهائية لاختبار الانحدار: 23/23 ✅** (مسار موحد wait=true، مسار قياسي، tasks، get ×2، chart-data + overlays ×2، list، candle-cache، صحة أثناء الحمل، حذف + إبطال كاش).
