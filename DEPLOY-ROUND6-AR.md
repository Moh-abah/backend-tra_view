# 🚑 الجولة 6 — حزمة الإصلاح الجذري لمشاكل الإنتاج (Round 6 Hotfix)

**من:** وكيل الباكند → **إلى:** وكيل الفرونت / المشغّل
**التاريخ:** 2026-10-30
**الحالة:** ✅ مُصلَّح ومُختبر محلياً بمحاكاة ظروف الإنتاج الفاشلة نفسها (36 اختباراً، كلها ناجحة)

---

## 1) المشاكل الثلاث من سجل الإنتاج (مع الدليل)

| # | الخطأ في السجل | الأثر على المستخدم |
|---|---|---|
| 1 | `drawings.py:30 → sqlite3.OperationalError: unable to open database file` (مئات المرات) | كل حفظ/تحميل لأدوات الرسم يعيد **500** — الأدوات لا تُحفظ أبداً (حتى GET يفشل) |
| 2 | `chart_ws → ❌ Failed to save global indicators: attempt to write a readonly database` | المؤشرات المحفوظة **تختفي** عند كل تحويل فريم — و`⚠️ No indicators configured` يتكرر كل نبضة |
| 3 | `live_stream → ⚠️ Ticker WS stalled (no first message in 15s) — retrying` كل 20 ثانية بلا نهاية | نظرة السوق/أسعار البث العام ميتة — لا أول رسالة أبداً |

---

## 2) السبب الجذري (مُثبت بالقراءة لا بالتخمين)

### المشكلتان 1 و 2 — `docker-compose.yml` (السطران 70-71 القديمان):
```yaml
- ./chart_states.db:/app/chart_states.db      # ⛔ ربط ملف واحد
- ./chart_drawings.db:/app/chart_drawings.db  # ⛔ ربط ملف واحد
```
- **ربط ملف واحد لملف غير موجود على المضيف** → Docker يُنشئ **directory فارغاً** بدل الملف → SQLite لا يفتح directory أبداً → `unable to open database file` (وهذا يفسّر فشل GET أيضاً).
- **ربط ملف واحد مملوك لـ root على المضيف** بينما الحاوية تعمل بـ `trader (uid 1000)` → الفتح ينجح للقراءة وأي كتابة/إنشاء journal يفشل → `attempt to write a readonly database`.
- **الدليل المقارن:** كاش الشموع `history_cache` (حجم مسمى named volume) يعمل بلا أي خطأ من أول يوم (`💾 cache now 43011 candles`) — لأن الأحجام المسمّاة تُهيَّأ بملكية صورة trader.

### المشكلة 3 — `binance_market_stream.py`:
- رابط وحيد `wss://stream.binance.com:9443/ws/!ticker@arr` بلا بدائل، بينما بث kline (الذي يعمل) لديه 4 روابط بديلة.
- **قياس حي (2026-10-30):** إطارات `!ticker@arr` (~1-2MB/ثانية) تعلق صامتة خلف وسطاء الشبكة — جربناها من شبكة خارجية: **أول رسالة لا تصل أبداً (Timeout)**. بينما `!miniTicker@arr` (إطارات ~14KB): **أول رسالة خلال 1.31 ث** ✅. هذا يفسّر بالضبط لماذا kline (إطارات صغيرة) يعمل وticker (إطارات ضخمة) يعلق.
- إضافةً: بلا `max_size=None` — حد websockets الافتراضي (1MB) يقطع إطارات ticker حتى لو وصلت.

---

## 3) ما الذي تغيّر (8 ملفات فقط)

| الملف | نوعه | ما فيه |
|---|---|---|
| `app/core/storage_health.py` | **جديد** | قلب الإصلاح: تشخيص + إصلاح ذاتي لتخزين SQLite (ثلاث طبقات دفاع — انظر أدناه) |
| `app/routers/drawings.py` | معدّل | المسار عبر `ensure_sqlite_ready` + إعادة محاولة ذاتية عند أي فشل فتح + `busy_timeout` |
| `app/websocket/chart_ws.py` | معدّل | `ChartStateDB` عبر التجهيز الذاتي + اتصالات بمهلة انتظار — **حفظ المؤشرات العامة لا يعود قابلاً للفشل بصلاحيات** |
| `app/providers/binance_market_stream.py` | معدّل | 8 روابط بديلة بالتناوب + `miniTicker` أولاً (قياس حي) + `max_size=None` + `open_timeout=10` |
| `app/core/live_stream.py` | معدّل | تراجع تصاعدي 5→10→20→30ث + السجل يعرض الرابط المستخدم وعدد الدورات |
| `app/main.py` | معدّل | `GET /health/storage` (تشخيص حي) + تقرير صحة التخزين عند الإقلاع |
| `docker-compose.yml` | معدّل | حذف ربط الملفين الفردي ← حجم مسمى `chart_data` + متغيرات `CHART_STATE_DB_PATH` / `DRAWINGS_DB_PATH` |
| `Dockerfile` | معدّل | إنشاء `/app/chart_data` بملكية trader داخل الصورة |

### كيف يعمل الإصلاح الذاتي (storage_health)؟
1. **الطبقة 1:** إنشاء مجلد القاعدة إن لم يوجد.
2. **الطبقة 2:** لو المسار **directory** (أثر Docker) وفارغ → يُزال ويُنشأ ملف حقيقي.
3. **الطبقة 3:** فحص كتابة فعلي (CREATE TABLE + INSERT + COMMIT). لو فشل:
   - محاولة `chmod` (تصحيح ملكية ناقصة)،
   - ثم الانتقال لمسار بديل قابل للكتابة (`STORAGE_FALLBACK_DIR` أو `/app/data` أو `./data`) **مع نسخ بيانات القاعدة القديمة إن كانت مقروءة — صفر فقدان بيانات**،
   - اسم البديل يحمل لاحقة hash ثابتة من المسار الأصلي → مستقر عبر إعادة التشغيل ولا يتداخل.
4. كل شيء يُسجَّل في `docker logs` بسطر واضح (🩹 / ✅ / ❌) مع سبب وأمر الإصلاح النهائي.

> ⚠️ **ملاحظة مهمة لك (المشغّل):** حتى لو نشرت **ملفات الكود فقط** دون تحديث compose، الخادم سيتعافى ذاتياً فوراً (البديل داخل طبقة الحاوية القابلة للكتابة). لكن النشر الكامل مع compose الجديد هو الحل الجذري الدائم الذي يُبقي البيانات بعد إعادة البناء.

---

## 4) خطوات النشر (على الخادم 161.97.73.254)

### الخيار A — النشر الكامل الموصى به (كود + compose):
```bash
cd /path/to/trading-backend        # مجلد المشروع على الخادم

# 1) انسخ ملفات الحزمة فوق الموجود (نفس المسارات النسبية)
cp -r ROUND6-HOTFIX/app/. ./app/
cp ROUND6-HOTFIX/docker-compose.yml ROUND6-HOTFIX/Dockerfile ./

# 2) (اختياري) انقذ بيانات المؤشرات القديمة إن وُجدت
docker cp trading-backend:/app/chart_states.db ./chart_states.db 2>/dev/null || true

# 3) أعِد البناء والتشغيل
docker compose down
docker compose up -d --build backend

# 4) (اختياري) استيراد المؤشرات القديمة إلى الحجم الجديد
docker cp ./chart_states.db trading-backend:/app/chart_data/chart_states.db 2>/dev/null || true
docker exec -u root trading-backend chown trader:trader /app/chart_data/chart_states.db 2>/dev/null || true
docker restart trading-backend
```

### الخيار B — ترقيع كود فقط (يتعافى ذاتياً):
انسخ ملفات `app/` فقط وأعد تشغيل الحاوية — `storage_health` يعالج الصلاحيات والمجلدات وحده ويسجل ما فعله.

### تحقق فوري بعد النشر (بنفس الجلسة):
```bash
bash VERIFY-ROUND6.sh http://161.97.73.254:8000
# أو يدوياً:
curl -s http://161.97.73.254:8000/health/storage | python3 -m json.tool
docker logs --tail 80 trading-backend | grep -E "Market ticker WS|🩹|Storage\["
```

**المتوقع في السجل:**
```
✅ Storage[chart_drawings] → /app/chart_data/chart_drawings.db (writable=True, fallback=False)
✅ Storage[chart_states]  → /app/chart_data/chart_states.db  (writable=True, fallback=False)
🟢 Market ticker WS connected: wss://data-stream.binance.vision/ws/!miniTicker@arr
```
**المتوقع في `docker logs`: صفر تكرار لـ** `unable to open database file` / `readonly database` / `Ticker WS stalled`.

---

## 5) أدلة الاختبار المحلية (36/36 ناجحة)

| الاختبار | النتيجة |
|---|---|
| محاكاة directory-artifact + readonly + نسخ بيانات + عدم تداخل البدائل + regression (storage unit) | **13/13 ✅** |
| REST أدوات الرسم كامل (GET/POST/upsert/DELETE) فوق أثر directory | **10/10 ✅** |
| WS الشارت كامل تحت readonly: init 5000 شمعة + RSI نوع oscillator حسب قيماً + `indicator_added` + `timeframe_changed` + **`💾 Saved 2 global indicators` مثبت على القرص** | **6/6 ✅** |
| إقلاع كامل HTTP: `/health/storage` + دورة drawings فوق ظروف الإنتاج الفاشلة | **7/7 ✅** |
| بث ticker حي: أول رسالة خلال **1.06ث** عبر miniTicker (كانت تعلق للأبد) | ✅ |

---

## 6) رسالة لوكيل الفرونت

1. **لا تغيير في أي عقد API/WS** — كل الأشكال والمسارات كما هي حرفياً. لا شيء مطلوب منك إطلاقاً.
2. أدوات الرسم: بعد النشر، `POST/GET /api/v1/chart/drawings/...` ستعيد 200 فعلاً — استمروا على بروتوكولكم الحالي.
3. المؤشرات المحفوظة لن تختفي بعد تحويل الفريم — إن رأيتم `applied: 0` بعد تحويل فريم، أرسلوا لوقت `docker logs` وسطر `/health/storage` وسنحسم فوراً.
4. نقطة جديدة **اختيارية للتشخيص فقط:** `GET /health/storage` — تقرير صحة تخزين حي (المسارات/الصلاحيات/أي بديل مُفعّل).
5. بث نظرة السوق سيعمل الآن عبر `miniTicker` (بيانات حية كل ثانية) — إن لاحظتم أن قائمة رموز البث أصغر من كامل السوق فهذا طبيعي تقنياً (miniTicker يبث المتغير فعلياً)، وإن أردتم القائمة الكاملة نُجرب شبكة أخرى ونُعيد ترتيب الروابط.

— وكيل الباكند، الجولة 6.
