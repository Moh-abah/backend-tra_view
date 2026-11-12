# 🔧 الجولة R56 — إصلاحات استقرار الإنتاج (4 ملفات فقط)

> **القاعدة**: آخر إصدار من رابطك (مشروعك + R55 مدموج — تحققنا بت-بت).
> هذه الحزمة = **4 ملفات معدّلة فقط** فوقه. كل شيء آخر في مشروعك لا يُمَس.

---

## لماذا كان النظام «يعيد تهيئة نفسه»؟ — السلسلة الكاملة من سجل إنتاجك

من سجل `trading-backend` بتاريخ 2026-11-08 (11:45 → 12:42)، هذه ليست أعطال
عشوائية — هي **سلسلة واحدة بعضها يجرّ بعضًا**:

```
[الجذر 1] backtest1.py يرسل المهمة الموحدة إلى Celery (delay تنجح ✅)
    ثم يستدعي reg.update(..., meta=...) والتوقيع يقبل meta_patch فقط
    ← TypeError بعد نجاح الإرسال!
        ↓
[التمويه] المقبض العام يظن أن الإرسال كله فشل
    «Failed to dispatch task: TaskRegistry.update() got an unexpected
     keyword argument 'meta'» → مسار الطوارئ داخل عملية الـAPI
        ↓
[التوأم] نفس الباك تست يعمل مرتين: مرة عند عامل Celery (نجحت 105 ث)
    ومرة داخل عملية uvicorn — 1,288,139 شمعة داخل عامل الـAPI
        ↓
[الانهيار] عامل uvicorn يبتلع جيجابايتات ← يقتله نظام التشغيل
    «Child process [9] died» ← uvicorn يطلق بديلًا
    «Started server process [671] … Application startup complete»
        ↓
[ما تراه أنت] النظام «يعيد تهيئة نفسه» كل بضع دقائق بلا سبب ظاهر
```

وبينما تجري هذه الفوضى، عامل Celery نفسه كان يتعفن ببطء:

```
[الجذر 2] كل مهمة celery تنشئ event loop جديدًا وتغلقه — لكن مسبح
    اتصالات قاعدة البيانات (asyncpg) وعميل Redis المشتركين يحتفظان
    باتصالات مرتبطة بالحلقة المغلقة:
    «RuntimeError: Task ... got Future ... attached to a different loop»
    «RuntimeError: Event loop is closed»
        ↓
    كل مهمة بعد الأولى: [R45] registry update failed (تبدو عالقة
    PROGRESS في الواجهة) + Redis get_cached failed (كاش الشموع ميت)
        ↓
[الجذر 3] عند فتح نتيجة أنشأها عامل Celery من عميل بلا gzip:
    كاش /get يخزّن زوج ("raw", bytes) والفحص المبكر يعالج "gz" فقط
    ← 'tuple' object has no attribute 'encode' → 500 دائم لكل طلب
    لاحق على نفس الباك تست (41d9a610 في سجلك — أربعة 500 متتالية
    ثم حذفته يدويًا)
        ↓
[الجذر 4] حاوية العامل تظهر unhealthy رغم عملها الطبيعي:
    Dockerfile يفحص http://localhost:8000/health — والعامل لا يشغّل
    uvicorn أصلًا ← unhealthy للأبد
        ↓
[الجذر 5] ميزانية كاش المستندات 900MB × عاملَي uvicorn = 1.8GB
    ثابتة + الأحمال العابرة لـ /chart-data — على الخادم الصغير
    هذا هو وقود دورات «Child process died» المتأخرة
```

وخطأ `ValueError: Exception information must include the exception type`
(بعد فشل مهمة rsi_simple غير الصالحة) سببه `update_state(state="FAILURE")`
اليدوي الذي يكتب نتيجة فاشلة بلا `exc_type` فيتعثر celery نفسه في
`mark_as_failure`.

---

## الإصلاحات الأربعة

### 1) `app/routers/backtest1.py` — درع مضاد للتوائم
- `meta=` → الاسم الصحيح **`meta_patch=`** (خطأ التوقيع الذي فجّر كل شيء).
- **الدرع**: بعد نجاح `delay()` لا يوجد أي فشل بعده أبدًا — أي استثناء في
  تحديث السجل يُسجَّل تحذيرًا فقط ويعود الرد نجاحًا. انتهى عصر «أرسلها ثم
  أعد تشغيلها داخل الـAPI».
- معالجة زوج `("raw", bytes)` في `/get` — انتهى 500 الدائم.

### 2) `app/routers/backtest.py` — نفس الدرع + نفس إصلاح /get
- تسجيل السجل بعد `delay()` محمي بنفس الطريقة (كان نفس خطر التوائم لو فشل
  `register` بعد إرسال ناجح).
- زوج raw في `/backtest/get/{id}` — نفس إصلاح backtest1/get.

### 3) `app/tasks/backtest_tasks.py` — كسر تلوث حلقات الأحداث
- دالة `_dispose_worker_async_state()`: في نهاية **كل مهمة** وعلى حلقة
  المهمة نفسها قبل إغلاقها: `engine.dispose()` + `redis_client.disconnect()`
  ← كل مهمة تبدأ باتصالات جديدة نظيفة على حلقتها الخاصة. المهمة 2، 3، 100…
  كلها تعمل مثل المهمة الأولى.
- إزالة `update_state(state="FAILURE")` اليدوي — الاستثناء المرفوع يوثّق
  نفسه في celery بلا كسر `mark_as_failure`، والسجل الدائم يُقفله
  `finish_failure` كالمعتاد.

### 4) `docker-compose.yml` — صحة العامل + ذاكرة دفاعية
- **healthcheck حقيقي للعامل**: `celery inspect ping` على عقدة العامل نفسها
  (يردّ MainProcess حتى أثناء انشغال العمال بالمحاكاة) — يعلّم الحاوية
  healthy عندما تعمل فعلًا. ميزانية الكاش: `BACKTEST_CACHE_BUDGET_MB=350`
  و`BACKTEST_PARSED_CACHE_MAX_MB=150` لكل عامل uvicorn بدل 900MB — ارفعها
  بحرية على الأجهزة الأكبر من `.env`.

---

## التركيب (أمر واحد)

```bash
# من مجلد مشروعك (حيث docker-compose.yml ومجلد app/)
unzip -o backend_R56_PATCH_ONLY.zip -d /مسار/مشروعك
docker compose up -d --build   # يعيد بناء الbackend والعامل بالكود الجديد
```
`-o` يستبدل الملفات الأربعة فقط ولا يلمس أي شيء آخر. **لا هجرات**.

## التحقق بعد التركيب (5 خطوات — كلها من سجلك أنت)

1. **لا مزيد من إعادة التهيئة**: `docker logs -f trading-backend` ثم شغّل
   اختبار 580 الموحد (بتريلينق 20%). المتوقع: **صفر** «Child process died»
   وصفر «Failed to dispatch task» — سطر واحد:
   `📤 [R49] unified-exit → Celery worker`.
2. **لا توائم**: كل تشغيل = مهمة واحدة عند العامل + صف واحد في
   `/api/v1/backtest1/tasks`.
3. **العامل صحي**: خلال دقيقة-دقيقتين `docker ps` يظهر
   `trading-celery-worker ... (healthy)` بدل unhealthy.
4. **المهام المتتالية**: شغّل باك تست ثانيًا فورًا بعد الأول — سجل العامل
   **بلا** `attached to a different loop` وبلا `Event loop is closed`،
   والتقدم في الواجهة يكتمل 100% (لا عالق PROGRESS).
5. **/get من كل العملاء**: افتح نتيجة من متصفح ومن curl — كلها 200.
   (curl بلا gzip كان يسمّم النتيجة بـ500 دائم).

## ماذا عن استراتيجية rsi_simple التي فشلت؟
فشلها **صحيح ومقصود**: الحمولة نفسها غير صالحة (indicators بلا name ·
type خارج القائمة · entry_rules فارغة) — الرسالة نفسها ترشدك إلى
`POST /api/v1/strategies1/validate` للتحقق المسبق. الجديد فقط أنها تفشل
الآن بنظافة (سجل واضح بلا استثناءات backend مشوشة).
