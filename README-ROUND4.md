# ✅ الجولة 4 — قيم المؤشرات الحقيقية + توحيد indicator_id + أدوات الرسم

> **حزمة الدمج**: 13 ملفًا فقط (12 معدلًا + 1 جديد) — تُدمج فوق نسختك الحالية مباشرة.
> **كل بند مُختبر حيًا** قبل الحزم — النتائج أدناه.

---

## 🔴 العيوب الخمسة من تقرير الفرونت — كلها مُصلحة ومُثبتة

### 1) 🔴🔥 قيم المؤشرات null في chart_initialized و indicator_added — **مُصلحة جذريًا**
**الجذور الثلاثة التي وجدناها وأصلحناها:**
1. **النتائج لا تُخزَّن حتى أول إغلاق شمعة** — كانت `chart.indicators_results` فارغة حتى تُغلق أول شمعة (دقيقة كاملة للـ 1m، **وللأسهم المغلقة: للأبد**). الآن: **bootstrap فوري** — عند أول نبضة (وفي init نفسه) يُحسب على كامل التاريخ ويُخزَّن.
2. **الحساب على آخر 500 شمعة فقط** عند الإغلاق كان ينكمش المصفوفات — الآن **حساب كامل التاريخ (5000)** في كل إغلاق.
3. **كاش قديم عبر الجلسات** — كان يرجع نتائج جلسة سابقة (أوقات مختلفة). أُضيفت **بصمة زمنية** (أول/آخر طابع) للتحقق.

**إضافة هيكلية: مهمة backfill ذاتية** — إن فشل الجلب الأولي (حظر/تهدئة مزود → شارت بـ 0 شمعة)، مهمة خلفية تعيد المحاولة كل 60 ثانية حتى 12 مرة، ثم تبث رسالة جديدة **`chart_backfilled`** بالتاريخ الكامل + المؤشرات محسوبة. init يرسل الآن علم **`backfill_in_progress`** ليعرف الفرونت.

| الاختبار الحي | النتيجة |
|---|---|
| init بمؤشرات محفوظة | 5000 شمعة + **3 مؤشرات × 5000 قيمة غير-null** |
| RSI(14) + RSI(7) معًا | **كلاهما يعمل بقيم حقيقية منفصلة** (`rsi_66b862bf` + `rsi_be58ad58`) |
| إغلاق شمعة حقيقي | `candle_close` بمؤشرات id-keyed |

### 2) 🔴 remove_indicator لا يُحذف من المحفوظات — **مُصلحة**
السبب: الكود كان يفحص **قائمة** كأنها dict فلا يحذف شيئًا من قاعدة المحفوظات.
الآن: الحذف (WS أو REST) يفلتر المحفوظات **بدقة النسخة**:
- حذف بـ `indicator_id` → يمسح **نسخة واحدة فقط** (RSI 14 يبقى و7 يُحذف) — مُختبر: `removed_from_saved: 1`
- بعد إعادة الاتصال: `reconnect keys: ['rsi_66b862bf']` — **المحذوف لا يعود** ✅

### 3) 🟠 مفاتيح بالاسم بدل indicator_id — **موحدة كلها**
- **كل** رسائل الخادم الآن بمفاتيح `indicator_id`: `chart_initialized.data.indicators_results` + `price_update.indicators` + `candle_close.indicators` + `indicator_added/updated/removed`
- init يرسل **`data.indicators_id_map`** = `{id: name}` للشفافية
- كل قيمة تحمل `indicator_id` + `name` الأصلي داخلها
- **تصادم الأسماء محلول**: كل تكوين يُختم بمعرف فريد تُستخدمه الحاسبة كمفتاح نتيجة

### 4) 🟠 طوابع وقت الأسهم — **نظيفة من المصدر**
- **منظّف مركزي جديد** `sanitize_candle_time_ms`: يحول ثواني/ميكروثانية/نانوثانية → ms، يرفض المستحيل، ويحاذي الفريم تمامًا
- **بقعة +1ms الجذرية**: `get_chart_data` كانت تلحق الشمعة الحية بوقت `last+1ms` — الآن **تدمج في bucket آخر شمعة مغلقة** (`is_live: true`)
- الصدى في WS كان يفعل الشيء نفسه — أُزيل

| الاختبار الحي | النتيجة |
|---|---|
| AAPL آخر شمعة | `1793232000000` — **محاذاة يومية كاملة** (كانت `...001`) |
| كل الشموع | **0/5000 غير محاذاة** |
| REST + WS معًا | كلها عبر المنظف الواحد |

### 5) 🟡 market_status في كل دفعة — **منفذة**
- `price_update` (WS) يحمل `market_status: "open" | "closed" | "pre_market" | "post_market"` (توقيت نيويورك + DST تلقائيًا) — مُختبر حيًا: `post_market`
- `candle_close` يحمله أيضًا + REST candles للأسهم + symbols + summary + top-movers

---

## 🟡 الميزات السبع — كلها منفذة

| # | الميزة | التفاصيل المُختبرة |
|---|---|---|
| 1 | **أدوات الرسم** | `GET/POST/DELETE /api/v1/chart/drawings/{market}/{symbol}?timeframe=` — SQLite دائم، upsert كامل، حذف فريم أو أداة واحدة بالمعرف — **roundtrip مُختبر** |
| 2 | **limit في /apply** | `POST /api/v1/indicators/apply?limit=100` → 100 قيمة بالضبط + `metadata.limit_applied` — مُختبر |
| 3 | **REST لإدارة المؤشرات** | `POST /indicators/manage/add` + `manage/remove` + `manage/update` — تعمل بلا WS، بنفس `indicator_id`، تحفظ دائمًا — **roundtrip مُختبر** |
| 4 | **إعادة مزامنة القيم** | `GET /indicators/values/{indicator_id}?symbol=&timeframe=&limit=&from_ms=&to_ms=` — من الذاكرة أو حساب كامل — مُختبر: أعاد 50 قيمة حقيقية |
| 5 | **رموز الكريبتو** | `GET /api/v1/market/symbols?market=crypto` كانت موجودة — أضفنا **كاش قرص دائم** فتعمل حتى أثناء حظر Binance |
| 6 | **market_status للأسهم** | في `/stocks/symbols` (لكل رمز) + summary + top-movers + REST candles — مُختبر |
| 7 | **تبديل الفريم بلا قطع** | `{"action":"set_timeframe","timeframe":"1h"}` داخل نفس الاتصال (ويدعم `update_timeframe` القديم) — مُختبر: 1d→1h بـ5000 شمعة في نفس الـ socket + إصلاح market hardcoded |

---

## 📦 محتويات حزمة الدمج (13 ملفًا)

```
app/core/managers.py              ← bootstrap + backfill + rekey + dual-id + دمج الشمعة الحية
app/core/indicators.py            ← بصمة زمنية للكاش
app/core/live_stream.py           ← market_status في نبضات الأسهم
app/websocket/chart_ws.py         ← معالجات المؤشرات الموحدة + set_timeframe + حذف دائم
app/routers/indicators.py         ← limit + manage/add|remove|update + values/{id}
app/routers/market_data.py        ← منظّف الطوابع + market_status
app/routers/stock_analysis.py     ← market_status في 3 نقاط
app/routers/drawings.py           ← ✨ جديد — أدوات الرسم
app/routers/agent_docs.py         ← عقد الوكيل محدّث (round4_updates)
app/providers/binance_provider.py ← كاش قرص للرموز
app/providers/us_stock_provider.py← get_market_status + quote fields
app/utils/dataframe_utils.py      ← sanitize_candle_time_ms
app/main.py                       ← تسجيل راوتر الرسومات
```

## 🚀 التركيب
```bash
unzip -o TR_platform_backend_MERGE-ONLY_round4_real-values_unified-ids_drawings_2026-10-29.zip -d /path/to/
cd /path/to/backend_pro
docker compose up -d --build
```

> 💡 **للفرونت**: اقرأ القسم الجديد `round4_updates` في `GET /agent/contract.json` — فيه قائمة "ما تحذفه من كودك" (self-heal، حل الاسم↔المعرف، sanitizeCandleTime، حماية ×5 فريمات).
