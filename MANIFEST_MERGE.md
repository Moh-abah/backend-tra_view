# حزمة دمج — الجولة 6.1 (تحسينات الفرونت الثلاثة + تحصين التخزين القديم)

**التاريخ:** 30/10/2026
**الأساس:** مستودع الباك إند الحالي (الذي يعمل في الإنتاج 161.97.73.254:8000 الآن)
**طريقة الدمج:** استبدل الملفات الأربعة التالية بمواقعها في المشروع — لا حذف ولا إعدادات جديدة مطلوبة.

---

## 1) ملفات الحزمة (4 ملفات فقط)

| # | الملف | الحالة | السبب |
|---|-------|--------|-------|
| 1 | `app/routers/market_data.py` | **معدّل** | ✨ نقطة جديدة: `GET /api/v1/market/candles/{market}/{symbol}/range?timeframe=&from=&to=` (تحسين الفرونت #1) — الشموع نفسها والترقيم لم يُمَسا |
| 2 | `app/routers/drawings.py` | **معدّل** | ✨ حذف دفعي: `DELETE /api/v1/chart/drawings/{market}/{symbol}?drawing_ids=a,b,c` (تحسين الفرونت #2) — سلوك `drawing_id` المفرد والمسح الكامل كما هما حرفياً |
| 3 | `app/main.py` | **معدّل** | ✨ ترويسة `X-Max-Limit` على كل استجابات نقاط الشموع (تحسين الفرونت #3) — بقي `/health/storage` وتقرير الإقلاع من الجولة 6 كما هما |
| 4 | `app/core/chart_storage.py` | **معدّل** | 🔒 تحصين: وحدة قديمة غير مستخدمة كانت بمسار SQLite نسبي مباشر (قنبلة readonly كامنة) — مرّت الآن عبر `ensure_sqlite_ready` |

> لا توجد أي تغييرات أخرى. كل ملفات الجولة 6 الأساسية (storage_health / chart_ws / live_stream / binance_market_stream) موجودة أصلاً في مستودعك الحالي والمنشور في الإنتاج — **هذه الحزمة فوقه مباشرة**.

---

## 2) ما الجديد للفرونت (العقد)

### أ) `GET /api/v1/market/candles/{market}/{symbol}/range?timeframe=&from=&to=&limit=`
- `from`/`to` **epoch-ms شاملة الطرفين**، `from > to` → `400`.
- `limit` اختياري (افتراضي 5000، حد أقصى **20000**) — يُعاد **الأحدث** داخل النطاق.
- **العقد الثابت محفوظ حرفياً:** نفس استجابة `{ candles: [...], has_more, next_before }` بحقول الشمعة `time|open|high|low|close|volume` و`time` بالملي ثانية وترتيب تصاعدي.
- حقول إضافية: `from`, `to`, `truncated` (النطاق كان أوسع من limit), `limit`, `oldest_time`, `newest_time`, `market_status` (للأسهم).
- استمرارية التمرير: عند `has_more=true` مرّر `next_before` إلى نقطة `/candles?before=` كالعادة.
- **سريع دائماً:** حتى لو طلبت نطاق 10 سنوات على 1m، الجلب مقيّد بنافذة تكفي `limit` شمعة فقط — والنتيجة مطابقة لأن الأحدث داخل النطاق هو المُعاد على أي حال.
- مثال تم اختباره حياً (بيانات BTCUSDT حقيقية):
  `GET /range?timeframe=1h&from=1789196400000&to=1792792800000&limit=2000` → `count=1000`، كل الشموع داخل النطاق، `X-Max-Limit: 20000`.

### ب) `DELETE /api/v1/chart/drawings/{market}/{symbol}?drawing_ids=a,b,c`
- يقبل **فواصل** (`?drawing_ids=a,b,c`) **أو تكرار المعامل** (`?drawing_ids=a&drawing_ids=b`).
- **مع `timeframe`:** يُطبق على ذلك الفريم فقط. **بدونه:** يُطبق على كل فريمات الرمز (مثالي لزر «مسح الكل»).
- الاستجابة: `{"success": true, "deleted": N, "deleted_ids": [...], "not_found": [...], "timeframes_affected": ["15m","1m"]}` — مفتاحا `success`/`deleted` كما في السلوك القديم.
- إذا صار تخزين فريم فارغاً بعد الحذف يُحذف صفّه كلياً (GET يُرجع `count=0` كما هو متوقع).
- **التوافق القديم كامل:** `?drawing_id=` المفرد و`?timeframe=` (مسح فريم) وبدون معاملات (مسح الكل) تعمل كما كانت حرفياً.

### ج) ترويسة `X-Max-Limit`
- على **كل** استجابات مسار `/api/v1/market/candles*` (حتى 422/500):
  - `/candles/{market}/{symbol}` → `X-Max-Limit: 5000`
  - `/candles/{market}/{symbol}/range` → `X-Max-Limit: 20000`
- `limit=99999` → `422` **مع الترويسة** — يكتشفها العميل ذاتياً بلا توثيق خارجي.

---

## 3) ما تغيّر على الفرونت؟ لا شيء إلزامي
- كل نقاطكم الحالية بنفس الأشكال — التغيير **إضافي فقط** (نقطة جديدة + معامل اختياري جديد + ترويسة).
- اعتمادوا الريبلاي كما هو: بياناته من الذاكرة المحلية ولا يحتاج شيئاً من هذا.

---

## 4) الأدلة (طلب/استجابة — مُختبرة فعلياً)

### على الإنتاج الحي (الأساس الجولة 6) — 11/11 ✅
- `GET /health/storage` → `chart_drawings` و`chart_states` **writable=true** على `/app/chart_data/` (مستخدم `trader`).
- دورة drawings كاملة: POST `saved=3` → GET بنفس المعرفات → DELETE — كانت 500 `unable to open database file` قبل الجولة 6.
- `GET /candles?limit=100` → `count=100 has_more=true` + `before=` يعمل.
- WS: `chart_initialized` → مفاتيح `indicators_results = RSI_77a50452` (يطابق `md5("RSI:{\"period\": 14}")[:8]` رياضياً) → بث حي `price_update` → `set_timeframe` → `timeframe_changed` داخل نفس الاتصال (بلا readonly).

### محلياً على حزمة الدمج — 30/32 ✅ (والاثنان هجوم شبكة وليسا كوداً)
- كل دورات الحذف الدفعي (فواصل/تكرار/عبر فريمات/معرف شبح/not_found) ✅
- `/range` ببيانات BTCUSDT حقيقية: 1000 شمعة داخل النطاق، تصاعدية، بالملي، ترويسة 20000 ✅
- AAPL أسهم على `/range` → `count=64 market_status=open` ✅
- `from > to` → `400` ✅ — `limit=99999` → `422` مع `X-Max-Limit: 5000` ✅
- WS init+oscillator+set_timeframe محلياً ✅
- ⚠️ الفشلان المتبقيان (نطاق عميق 8 سنوات + فريم 2m عبر الشبكة) سببهما **حظر Binance مؤقت لعنوان بيئة الاختبار (418 cooldown)** — والمنطق نفسه أُثبت معزولاً بالكامل أدناه.

### إثبات معزول لمنطق النطاق العميق (مزوّد مزيّف — بلا شبكة) — 9/9 ✅
- نطاق 8 سنوات (~70 ألف شمعة 1h) + `limit=5000` → `count=5000`، `truncated=true`، `has_more=true`، `next_before=أقدم معادة`، آخر شمعة ملاصقة لـ `to`.
- نطاق 100 شمعة → `count=100` بالضبط (شاملة الطرفين)، `truncated=false`.
- فريم مركب 2m → شموع 2m محاذاة `% 120000 == 0`.

---

## 5) ماذا يتوقع الفرونت بعد النشر؟
1. `curl -s "http://161.97.73.254:8000/api/v1/market/candles/crypto/BTCUSDT/range?timeframe=1h&from=X&to=Y"` → 200 بالشكل أعلاه (قبل النشر: 404).
2. `curl -sI -X DELETE ".../drawings/crypto/BTCUSDT?drawing_ids=a,b"` → 200 مع `deleted_ids`.
3. ترويسة `X-Max-Limit` في أي استجابة شموع.

**انتهى — هذه آخر شيء يحتاجه الفرونت من الباك إند في هذه الجولة.**
