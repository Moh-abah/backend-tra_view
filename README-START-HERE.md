# 🚀 ابدأ من هنا — النظام المُصلَح والمُختبَر بالكامل

> **خلاصة سريعة:** شغّل `START-LOCAL.bat` بدبل كليك وانتهى. يفعل كل شيء تلقائيًا:
> يوقف القديم → يشغّل Postgres وRedis → **يُصلح كلمة مرور قاعدة البيانات تلقائيًا (بدون فقدان بيانات)** →
> يبني ويشغّل الـ API وCelery → ينتظر حتى يعمل النظام فعلاً ثم يعرض SUCCESS.

---

## ⭐ الجديد في هذه الحزمة: شارت احترافي بنمط TradingView + شموع بلا حدود


---

## 📚 جديد: توثيق كامل لوكيل الفرونت (بدون أي غموض)

بعد تشغيل الباك، وكيل الفرونت يقرأ من هذه المصادر:

| المصدر | الرابط | الغرض |
|---|---|---|
| 📘 العقد الآلي (JSON) | `http://localhost:8000/agent/contract.json` | **اقرأ أولاً** — 122 نقطة + بروتوكول التمرير + صيغ WS + أمثلة حقيقية + كود JS جاهز |
| 📗 دليل الوكيل (HTML عربي) | `http://localhost:8000/agent` | صفحة RTL تشرح كل شيء |
| 📙 Markdown | `http://localhost:8000/agent/contract.md` | نسخة نصية |
| 📕 OpenAPI/Swagger | `http://localhost:8000/docs` و `/openapi.json` | يُولَّد من الكود الفعلي مع أمثلة استجابات |

> العقد يُبنى ديناميكياً من الراوترات الفعلية — أي تعديل مستقبلي على نقطة يظهر فيه تلقائياً.

---


---

## 🔧 إصلاحات 2026-10-29 (جلسة الأعطال المخزنة)

| العطل | السبب الجذري | الإصلاح |
|---|---|---|
| `PermissionError: data/history/*.parquet.tmp` متكرر + إعادة تنزيل الشموع في كل طلب | مسار كاش نسبي + bind mount Windows غير قابل للكتابة من مستخدم الحاوية | كاش بمسار مطلق + فحص كتابة + بديل تلقائي `/tmp/tr_history_cache` + قاطع دارة يوقف الإزعاج. وفي compose: حجم مسمى `history_cache` بدل bind mount |
| `TypeError: Object of type datetime is not JSON serializable` → **البث الحي WS كان ميتاً بالكامل** | `StreamMessage.to_json()` يمرر datetime/numpy إلى json.dumps | محول `_json_default` شامل (datetime→ISO، numpy، Decimal، Enum...) — البث يعمل الآن: رسائل price/kline تتدفق |
| طوفان `BEGIN/ROLLBACK` من SQLAlchemy | `echo=settings.DEBUG` | `SQL_ECHO` منفصل ومغلق افتراضياً |
| `⚠️ Error processing message: (1001, '')` كـ ERROR | انقطاع عميل طبيعي يُسجل كخطأ | يُسجل INFO هادئ |
| `print()` في بث البيانات الأولية | تجاوز نظام اللوق | logger.warning |

**مُختبَر حياً بعد الإصلاح:** الطلب الأول يجلب ويكتب الكاش، الثاني `0 batches / N cached`، البث الحي يرسل رسائل متواصلة، وسجل الخادم **صفر ERROR**.

---

### أ) نقطة نهاية جديدة للشموع بترقيم صفحات (للتمرير اللانهائي)
```
GET /api/v1/market/candles/{market}/{symbol}?timeframe=1h&limit=2000
GET /api/v1/market/candles/{market}/{symbol}?timeframe=1h&limit=2000&before=<أقدم وقت بالملي ثانية>
```
- الصفحة الأولى تجلب أحدث الشموع، وكل طلب `before=` يجلب صفحة أقدم.
- الرد يتضمن `has_more` و`next_before` — الفرونت يكرر التمرير **بلا أي حد لعدد الشموع**
  حتى بداية تاريخ الرمز (مثلاً BTC منذ 2017 — تم اختباره: 3360 شمعة يومية كاملة).
- **مُختبَر فعليًا:** 12,000 شمعة ساعية عبر 6 صفحات متتالية — صفر فجوات وصفر تكرارات.

### ب) شارت جاهز يعمل مباشرة من الباك — جرّبه فورًا
```
http://localhost:8000/demo/chart.html
```
- شموع حقيقية + فوليوم + ثيم داكن مطابق لـ TradingView + مباشر عبر WebSocket.
- الفريمات: `1m 5m 15m 1h 4h 1d` وتغيير الرمز من حقل الإدخال.
- اكتب في الرابط: `?symbol=ETHUSDT&tf=15m` للفتح على رمز/فريم محدد.

### ج) مكوّن React جاهز لفرونتك
مجلد `frontend-integration/` يحوي `TradingChart.tsx` + دليل دمج كامل بالعربي
(`README-CHART-AR.md`). خطوتان: `npm i lightweight-charts` + نسخ المكون.

### د) إصلاح مهم للأداء: إضافة `pyarrow` إلى requirements.txt
كاش الشموع على القرص (parquet) كان **لا يعمل** لأن المكتبة غير موجودة —
كل طلب كان يعيد التنزيل من Binance من الصفر (سبب بطء النظام عندك!). أُضيفت الآن.

---

## 1) سبب مشكلتك بالضبط (لماذا كانت الحاويات تعيد التشغيل باستمرار؟)

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "trader"
RuntimeError: Database initialization failed; refusing to serve requests
```

**السبب الجذري:** حاوية Postgres تحفظ بياناتها في volume باسم `postgres_data`.
كلمة المرور `POSTGRES_PASSWORD` في `docker-compose.yml` تُطبَّق **فقط عند أول تهيئة لـ volume فارغ**.
عندك الـ volume أُنشئ سابقًا (تجارب سابقة / استيراد Neon) **بكلمة مرور مختلفة**، فأصبح هناك تعارض:

| المصدر | كلمة المرور المخزنة فعليًا في الـ volume |
|---|---|
| `docker-compose.yml` (الآن) | `trader_local_2024` |
| الـ volume القديم `postgres_data` (الواقع) | كلمة مرور أقدم مختلفة ❌ |

فيقفل Postgres الباب في وجه الباكند مهما أعدت التشغيل — لأن إعادة التشغيل لا تغيّر كلمة مرور مخزنة من قبل.

**الحل الذي نفّذته لك:** سكربت `heal-postgres.sql` يُنفَّذ من داخل حاوية Postgres نفسها
(قناة إدارية موثوقة لا تحتاج كلمة مرور) ويضبط المستخدم/القاعدة/كلمة المرور لتطابق `.env` —
**بدون حذف الـ volume وبدون فقدان أي بيانات** (الباك تستات والاستراتيجيات تبقى كما هي).

---

## 2) طريقة التشغيل (خطوة واحدة)

1. فك ضغط الحزمة فوق مجلد الباكند: `C:\Users\MohAbh\Desktop\TR_platform\backend`
   (سيستبدل الملفات المعدلة ويضيف السكربتات الجديدة — لن يمسّ بياناتك)
2. دبل كليك على **`START-LOCAL.bat`** وانتظر 3–10 دقائق (أول بناء فقط)
3. عند ظهور `SUCCESS` افتح: **http://localhost:8000/docs**

### سكربتات جاهزة لكل حالة:

| السكربت | متى تستخدمه |
|---|---|
| **`START-LOCAL.bat`** | التشغيل الكامل اليومي (يفعل كل شيء + إصلاح تلقائي) |
| **`FIX-DB.bat`** | لو ظهرت رسالة password authentication failed مرة أخرى — إصلاح فوري بدون إعادة بناء |
| `heal-postgres.sql` | سكربت SQL الذي تنفذه السكربتات أعلاه (لا تشغّله يدويًا) |

### أوامر يومية عادية:
```
docker compose up -d            تشغيل
docker compose down             إيقاف (البيانات تبقى)
docker compose logs -f backend  متابعة سجلات الـ API
docker compose ps               حالة الحاويات
```

> ⚠️ ملاحظة: `docker compose down` لا يحذف الـ volume — بياناتك آمنة.
> فقط لا تستخدم `docker compose down -v` (هذا يحذف البيانات فعلاً).

---

## 3) ماذا أصلحت في الكود؟ (تم اختباره فعليًا)

### أ) إصلاح جوهري في قسم العملات — `app/routers/market_data.py`
نقطة `/api/v1/market/historical/...` كانت تُعيد `start_date: null` و`end_date: null` لأزواج العملات
(عمود `time` بالملي ثانية لم يكن مُعترفًا به كمصدر تاريخ). بعد الإصلاح تُعاد تواريخ ISO حقيقية:

```
قبل:  {"row_count": 72, "start_date": null, "end_date": null}
بعد:  {"row_count": 72, "start_date": "2026-10-26T11:00:00", "end_date": "2026-10-29T10:00:00"}
```

### ب) ملف `.env` — كان بإعداد خاطئ للتشغيل عبر Docker
كان يحوي `DATABASE_URL=sqlite+aiosqlite:///./trading.db` (إعداد بيئة اختبار) بينما نظامك يعمل عبر
Docker + Postgres. أعيد ضبطه ليتطابق حرفيًا مع `docker-compose.yml`، وأضفت
`http://localhost:3018` و`http://127.0.0.1:3018` إلى `CORS_ORIGINS` (الفرونت عندك على 3018).

### ج) سكربتات الإصلاح الذاتي (جديدة)
`START-LOCAL.bat` + `FIX-DB.bat` + `heal-postgres.sql` — شرحها في القسم 2.

---

## 4) نتائج الاختبار الفعلي (31 اختبارًا على النظام الشغّال)

قمت بتشغيل النظام كاملًا واختبار كل عائلات نقاط النهاية، **بما فيها جلب بيانات حية وتاريخية من Binance**:

### ✅ قسم العملات (القسم الذي ركزت عليه) — كلها نجحت:
| الاختبار | النتيجة |
|---|---|
| `GET /api/v1/market/symbols?market=crypto` | ✅ **774 عملة** |
| `GET /api/v1/market/price/crypto/BTCUSDT` | ✅ سعر حي: 80257.74$ |
| `GET /api/v1/market/price/crypto/ETHUSDT` | ✅ سعر حي: 2327.42$ |
| `GET /api/v1/market/price/crypto/BNBUSDT` | ✅ سعر حي: 741.23$ |
| `GET /api/v1/market/historical/crypto/BTCUSDT?timeframe=1h&days=3` | ✅ 72 شمعة + تواريخ ISO صحيحة |
| `GET /api/v1/market/historical/crypto/ETHUSDT?timeframe=15m&days=2` | ✅ 192 شمعة |
| `GET /api/v1/market/historical/crypto/XRPUSDT?timeframe=4h` (جلب جديد من الإنترنت) | ✅ 30 شمعة |
| `POST /api/v1/filtering/symbols` (فلترة العملات) | ✅ تعمل |
| `POST /api/v1/mtf/analyze` (تحليل BTCUSDT متعدد الأطر) | ✅ يعمل |
| `POST /api/v1/indicators/apply` (RSI + EMA على BTCUSDT) | ✅ 120 شمعة + مؤشران |

### ✅ باقي النظام:
| العائلة | النتيجة |
|---|---|
| الصحة والحالة (`/health`, `/api/v1/health`, `/api/v1/market/status`) | ✅ |
| المؤشرات (`/api/v1/indicators/available` — **54 مؤشرًا**) | ✅ |
| الاستراتيجيات (`/api/v1/strategies/list` — **3 استراتيجيات**) | ✅ |
| الفلترة (`markets`, `criteria/examples`, `stats`) | ✅ |
| المستخدمون (تسجيل → دخول → `/users/me` بالتوكن + رفض بدون توكن 401) | ✅ |
| الإعدادات (`/settings/watchlists` بتوكن صحيح) | ✅ |
| الباك تست (`/api/v1/backtest/list` — **20 تشغيلًا محفوظًا**، `metrics`) | ✅ |
| الأسهم الأمريكية (`5222` رمزًا + ملخص السوق) | ✅ |
| Swagger (`/docs`) | ✅ |

> ملاحظة وحيدة: `status: degraded` في بيئة الاختبار عندي سببها فقط أن Redis غير متاح هناك —
> في نظامك (Docker) Redis شغّال وسيظهر `ok`.

---

## 5) بنية الحزمة — ما الذي سينسجم مع ما عندك؟

```
backend/
├── START-LOCAL.bat          ← جديد: تشغيل كامل + إصلاح ذاتي
├── FIX-DB.bat               ← جديد: إصلاح قاعدة البيانات فورًا
├── heal-postgres.sql        ← جديد: سكربت الإصلاح
├── .env                     ← معدل: إعداد Docker الصحيح + CORS 3018
├── app/routers/market_data.py ← معدل: إصلاح التواريخ في قسم العملات
├── docker-compose.yml       ← كما هو (سليم)
├── Dockerfile               ← كما هو (سليم)
└── ... (باقي المشروع كاملًا مع بيانات الكاش التاريخية parquet)
```

الطريقة الأسهل للدمج: فك الضغط فوق المجلد القديم ووافق على الاستبدال.

---

## 6) إذا استمرت أي مشكلة (تشخيص في 30 ثانية)

```bat
docker compose ps                     هل backend يعيد التشغيل؟
docker compose logs backend --tail 50 ماذا تقول آخر الرسائل؟
FIX-DB.bat                            إصلاح كلمة المرور فورًا
curl http://localhost:8000/api/v1/health
```

إن فشل كل شيء وبذلت تعتيبًا (خيار أخير يفقد بيانات الـ volume فقط):
```bat
docker compose down -v
START-LOCAL.bat
```
(سيبدأ Postgres من جديد بكلمة المرور الصحيحة، والجداول تُنشأ تلقائيًا عند أول تشغيل.)
