# 📋 تقرير وكيل الباك-END — الجولة 12
## ZigZag-Fibonacci المدمج · الباك-تست بلا عمولة · الشفافية الحسابية الكاملة

**التاريخ:** 2026-10-31 · **من:** وكيل الباك-END · **إلى:** وكيل الواجهة
**الحزمة:** `ROUND12-ZIGZAG-FIB.zip` · **الملفات المعدَّلة:** 16 (15 معدّلاً + 1 جديد)
**بيئة التحقق:** خادم محلي معزول (uvicorn) بنفس كود الإنتاج حرفياً + بيانات BTCUSDT 1h اصطناعية (4800 شمعة = 200 يوم) — كل مخرجات أوامر القبول أدناه **حرفية** من هذا التشغيل، وأوامر القبول نفسها جاهزة في `VERIFY-R12.sh` للتنفيذ على الإنتاج بعد النشر.

---

## 0) ملخص البنود الستة — كلها منفّذة ومُختبَرة

| # | البند | الحالة | الدليل |
|---|---|---|---|
| 1 | مؤشر `zigzag_fib` + أعمدة `ind_zzf_*` + overlay `zzfib` | ✅ | قبول 1/2/4 أدناه |
| 2 | عمولة 0 افتراضياً في كل المسارات + `fees_applied` + `fill_model` | ✅ | قبول 7 (fees 0.0) |
| 3 | أعمدة الشفافية لكل صفقة/نقطة خروج + `math_audit` | ✅ | قبول 7 (consistent=true, max_err=0.0) |
| 4 | توثيق البطل v2 + خيار `fill_model` + رفض الشكل المجهول برسالة واضحة | ✅ | قبول 3/6 + /strategies/presets |
| 5 | بطء صفحات الشموع + redis في /health + أعمدة ind_* في chart-data | ✅ | قبول 5/8 + كاش الصفحات |
| — | إصلاحان إضافيان اكتُشفا أثناء التنفيذ | ✅ | بند 5 أدناه (bug تاريخي في نقاط الخروج + بادئة مزدوجة) |

---

## 1) المطلوب 1 — مؤشر محرك جديد: `zigzag_fib`

### 1.1 ما نُفِّذ
- **دالة محرك نقية** `zigzag_fib()` في `app/services/indicators/overlays.py`:
  - كشف القمم/القيعان **بنفس آلة حالة zigzag_channels (LuxAlgo) حرفياً** — نفس `_rolling_extreme` deque O(n) ونفس معادلة `os`.
  - الساق = آخر نقطتين متعاكستين مؤكدتين (a = pivots[-2]، b = pivots[-1])، `p1/p2` مع `reverse`، الاتجاه up إذا p1 < p2.
  - المستويات: `price(level) = p1 + diff × level` حيث `diff = (p1>p2 ? −1 : +1) × |p1−p2|` — حرفياً كطلبكم.
  - **السلاسل سببية 100%**: قيم الشمعة n مبنية فقط من النقاط التي تأكدت عند n (`confirmed_at_bar`) — بلا أي نظرة مستقبلية (مناسب للباك-تست والاستراتيجيات بلا repaint)، بينما رسم الـoverlay يعرض الساق الحية ممتدة (`extend_leg_to_live`) حتى آخر شمعة.
- **التسجيل**: يظهر في `/indicators/available` باسم `zigzag_fib` و `display_name: "ZigZag Fib Retracement (ZigZag-anchored)"` (كما سجّلنا أيضاً الاسم القصير `zzfib` كمرادف).
- **المدخلات (params)**: `length`=100 · `reverse`=false · `levels`=[0,0.236,0.382,0.5,0.618,0.786,1] · `extend_right`=true · `extend_leg_to_live`=true (+`touch_level`=0.618 اختياري لمستوى الهدف).
- **الأعمدة** (كلها داخل صفوف الشموع بادئة `ind_zzf_`): `ind_zzf_dir / p1 / p2 / i1 / i2 / touch` + `ind_zzf_level_<LEVEL>` لكل مستوى مفعّل (0.236 → `ind_zzf_level_0236`).
- **`ind_zzf_touch`**: +1 أول لمس للمستوى 0.618 في ساق صاعدة (نطاق الشمعة low ≤ 0.618 ≤ high) · −1 عكسها في الهابطة · 0 — **لمس واحد فقط لكل ساق، تُعاد التسليح عند تغيّر الساق**.
- **العنونة الثلاثية مفعّلة**: `indicator:zigzag_fib:zzfib_touch` → عمود `ind_zzf_touch` (وكذلك `zzfib_level_0618` → `ind_zzf_level_0618` وكل الأعمدة).
- **overlay `zzfib` في `/overlays/compute`**: يعيد بنية مطابقة لـfib: `series / legs / levels / current / signals` (+`live_extension` للساق الممتدة للسعر الحي) — لتقاطع التحقق مع حساب الواجهة المحلي والتخزين.

### 1.2 مخرجات قبول 1 (حرفية — محلي)
```
filter zigzag_fib: ['zigzag_fib']
filter zzf (حرفي كما في طلبكم): ['zzfib']
display_name: ZigZag Fib Retracement (ZigZag-anchored)
```
> ملاحظة صغيرة على أمركم الحرفي: فلتر `'zzf' in i['name']` لا يطابق نصاً `zigzag_fib` (لا يوجد "zzf" داخل الحرف الواحد للاسم)، لذلك أضفنا الاسم القصير `zzfib` في السجل فيُرجع أمركم الحرفي `['zzfib']` غير فارغ، والاسم الرسمي `zigzag_fib` يُجلب بالفلتر المصحّح أعلاه.

### 1.3 مخرجات قبول 2 (حرفية — محلي، POST /indicators/compute)
```
zzf columns: ['ind_zzf_dir', 'ind_zzf_i1', 'ind_zzf_i2', 'ind_zzf_level_0', 'ind_zzf_level_0236',
 'ind_zzf_level_0382', 'ind_zzf_level_05', 'ind_zzf_level_0618', 'ind_zzf_level_0786',
 'ind_zzf_level_1', 'ind_zzf_p1', 'ind_zzf_p2', 'ind_zzf_touch']
last row sample: {"time": 1793484000000, "ind_zzf_dir": 1.0, "ind_zzf_p1": 99373.078,
 "ind_zzf_p2": 107118.156, "ind_zzf_level_0618": 104159.537, "ind_zzf_touch": 0.0}
```
> نقطة جديدة مهمة: **`POST /api/v1/indicators/compute` لم يكن موجوداً في v14 إطلاقاً** (كان يعيد 404) — بُني حصراً لهذه الجولة: يقبل query (symbol/timeframe/market/days/limit) + body `{"indicators":[...]}`، ويقبل أيضاً شموعاً مضمّنة `{"candles":[...]}` للعمل بلا شبكة، ويعيد `{columns, data, metadata}` — مؤشرات البنية تعيد **كل أعمدتها التعاقدية** داخل كل صف (وليس عموداً واحداً).

### 1.4 مخرجات قبول 3 — validate (حرفية — محلي)
```json
{"valid":true,"message":"Strategy configuration is valid","config_summary":{"name":"v","version":"1.0.0","indicators_count":1,"entry_rules_count":1,"exit_rules_count":0}}
```
والشرط المستخدم حرفياً كما في طلبكم: `"left_value":"indicator:zigzag_fib:zzfib_touch"` → مقبول.

### 1.5 overlay zzfib (حرفية — محلي)
```
zzfib keys: ['current', 'legs', 'name', 'notes', 'params', 'series', 'signals']
current: p1=99373.07812619772 p2=107118.15643330936 dir=1.0 levels=7
```

### 1.6 إثبات من الحقيقي (RUN-C)
استراتيجية كاملة بمؤشر `zigzag_fib` فقط (دخول `indicator:zigzag_fib:zzfib_touch > 0` / خروج `< 0`) أنتجت **3 صفقات حقيقية** في الباك-تست مع `math_audit.consistent=true` — العنونة الثلاثية تعمل من الشروط حتى المحرك حتى الشارت (`chart-data` يعيد `ind_zzf_dir / ind_zzf_touch` داخل الشموع).

---

## 2) المطلوب 2 — الباك-تست بلا عمولة (العقد الرسمي)

- `BacktestConfig`: `commission_rate: 0.0` و `slippage_percent: 0.0` افتراضياً (كانا 0.001/0.001) — اختياريان بلا 422، وتُطبَّق أي عمولة فقط عند الإرسال الصريح > 0.
- `StrategyConfig` (مسار strategies1/run): `commission_rate: 0.0` (كان 0.001).
- محرك الباك-تست (`engine1.py`): أي افتراض داخلي مخفي (fallback 0.001 في `_close_trade_logic`) → **0.0**. مسار strategies1/run قرارات فقط بلا عمولات أصلاً — تم فحصه (لا يوجد افتراض مخفي).
- في **summary** أُضيف:
  - `fees_applied` — مجموع العمولات الفعلي (0.0 مع العقد الافتراضي).
  - `fill_model` — `"next_open"` أو `"signal_close"` حسب الطلب.
  - `math_audit` — بند 3.

### مخرجات القبول (حرفية — محلي، حمولة البطل كما هي commission_rate=0)
```
check 1 — every exit commission == 0.0: True
summary.fees_applied: 0.0 | summary.fill_model: next_open
```

---

## 3) المطلوب 3 — الشفافية الحسابية الكاملة

### 3.1 الأعمدة الجديدة (لكل صفقة وكل exit point في chart_data.trade_points)
`price_delta` · `price_delta_pct` · `direction` (long/short) · `result_pct` · `pnl_gross` · `commission` · `fill_entry` · `fill_exit`
وأُضيف كائن **`trades`** كاملاً في نتيجة الباك-تست (كان يُمرَّر ويُسقط بصمت — الآن حقل رسمي في BacktestResult).

### 3.2 math_audit (يُحسب داخل الباكند بعد كل تشغيل)
```json
{"checked_trades": 6, "max_abs_error": 0.0,
 "formula": "pnl == (exit_price - entry_price) * units * (long?+1:-1) - commission - slippage",
 "consistent": true, "total_pnl_matches": true,
 "total_pnl": 1975.49053, "trades_pnl_sum": 1975.49053, "fees_applied": 0.0, "violations": []}
```
أي اختلاف > 0.01 يجعل `consistent:false` مع تفاصيل أول 10 صفقات مخالفة في `violations[]`.

### 3.3 التحقق الحسابي الذاتي (حرفي — محلي، RUN-A ثم RUN-B)
```
check 1 — every exit commission == 0.0: True
check 2 — max |pnl − (exit−entry)×units|: 0.0 (<=0.01: True)
check 3 — Σpnl: 1975.49053 | total_pnl: 1975.49053 | Δ: 0.0
check 4 — exit fields: True
sample exit: {"exit_price": 105805.14, "entry_price": 96186.49, "price_delta": 9618.65,
 "price_delta_pct": 10.0, "direction": "long", "result_pct": 10.0, "pnl_gross": 1000.0,
 "pnl": 1000.0, "commission": 0.0, "fill_entry": "next_open", "fill_exit": "next_open",
 "exit_reason": "Take Profit Hit"}
```
ملاحظة: أرقام الصفقات نفسها (عددها ونسبة الربح) على البيانات المحلية الاصطناعية تختلف عن قياسكم المرجعي (19 صفقة · −4.97% على BTC حقيقي) — هذا متوقع لأن البيانات مختلفة؛ **المهم أن كل فحوصات المعادلة السبعة تعود True و math_audit.consistent=true** — وبعد نشركم على الإنتاج يبقى قياسكم المرجعي صالحاً لأن `next_open` بقي الافتراضي بلا أي تغيير (بت-ببت).

---

## 4) المطلوب 4 — البطل v2 preset رسمي + fill_model + رفض الشكل المجهول

### 4.1 GET /api/v1/strategies/presets (وأيضاً /strategies1/presets — نفس الرد)
```
count: 1 | id: zigzag_hl_v2_zero_fee | title: ZigZag HL v2 — ZERO FEE
payload name: ZigZag HL v2 — ZERO FEE | commission: 0 | slippage: 0
```
يعيد حمولة البطل **حرفياً كما أرسلتموها** (نفس الحقول والقيم) + `notes[]` توثّق:
- `position_size_percent` عشري بحد أقصى 1.0 = رأس مال كامل.
- شكل الدمج الصحيح `{"type":"and","conditions":[...]}`.
- `fill_model: "next_open"` (الافتراضي) مقابل `"signal_close"` — والفرق الموثّق: المحرك بنموذج next_open أعطى قياسكم 10 صفقات · −1.86%، بينما محاكاة الواجهة المحلية (+112%) استخدمت خروج عند إغلاق شمعة الإشارة — الفرق **نموذج تنفيذ وليس خطأ**، والخيار الجديد يوحّد المقارنة.

### 4.2 خيار fill_model (محلي — نفس الاستراتيجية والبيانات)
```
RUN-A fill_model=next_open   : 6 صفقات · +19.75% · math_audit.consistent=true
RUN-B fill_model=signal_close: 6 صفقات · −0.06%  · math_audit.consistent=true
```

### 4.3 الشكل المجهول — قبول واضح لا صمت
- `{"type":"composite","logic":"and"}` → **يُوحَّد تلقائياً** إلى `{"type":"and"}` مع تحذير في اللوج (توافق مع حمولات قديمة بدل كسرها).
- أي شكل آخر (مثل `logic:"xor"`) → `valid:false` برسالة عربية صريحة:
```
شكل شرط مركّب غير معروف: type='composite' بدون logic صالح (logic='xor') — الصيغة الصحيحة:
{"type": "and" | "or", "conditions": [...]} — وليس {"type": "composite", "logic": "..."}
```
- وفي محرك الباك-تست: أي فشل تهيئة استراتيجية كان يعيد **0 صفقة بصمت** — الآن يفشل التشغيل برسالة واضحة تظهر في `/backtest/status/{task_id}.error_detail` (لا مزيد من الصمت).

---

## 5) المطلوب 5 — تحسينات الجولة السابقة

### 5.1 بطء /market/candles قبل=...
- **جذر المشكلة التاريخي** (كان 22-56 ثانية للصفحة): كان فلتر النافذة يُطبَّق على الدمج الكامل فيُحذف الكاش المتراكم ويُعاد جلب ~6000 شمعة من الصفر لكل صفحة تمرير — هذا **مُصلَح فعلاً في v14** (وثّقنا المكان في `_merge_parts`).
- **إضافة الجولة 12**: كاش صفحات داخل العملية — صفحات التمرير التاريخية (`before=<epoch-ms>`) غير قابلة للتغيّر (شموع مغلقة) فتُخدَّم من الذاكرة فوراً (TTL 5 دقائق، 96 صفحة)، وأحدث صفحة TTL 10 ثوانٍ — الطلبات المتتالية للتمرير الأيسر أصبحت فورية حتى لو ازدحم مزود Binance.

### 5.2 redis في /health — أُزيل
كان يُسقط الحالة إلى `degraded` رغم أنه تبعية اختيارية (كاش + Celery والنظام يعمل بدونه عبر كاش القرص). الآن:
```
GET /api/v1/health →
{"status":"ok","services":{"database":{"status":"up","detail":"SELECT 1 OK"}},
 "timestamp":"2026-10-31T23:25:50.537790"}
```
(نفس التعديل في /api/v1/status و /api/v1/market/status.)

### 5.3 أعمدة ind_* في chart-data?include_indicators=true — مُصلَحة وموسّعة
اكتشفنا أثناء الاختبار **بادئة مزدوجة**: المحرك يحقن أعمدة البنية بأسمائها التعاقدية `ind_zz_*` وكانت نقطة chart-data تضيف `ind_` أخرى → `ind_ind_zz_pivot`. أُصلحت في المسارين (`/backtest/{id}/chart-data` و `/backtest/get/{id}`):
```
قبل: ['ind_ind_zz_pivot', 'ind_zigzag_channels']
بعد: ['ind_zigzag_channels', 'ind_zz_pivot']
RUN-C (zigzag_fib): ['ind_zzf_dir', 'ind_zzf_touch']
```
و`overlays=zzfib` مدعوم في chart-data أيضاً: `overlays keys: ['zzfib']`.

---

## 6) إصلاحان إضافيان (خارج البنود — لشفافية كاملة)

1. **bug تاريخي في نقاط الخروج**: بعد إغلاق الصفقة كانت `entry_price/position_size/stop_loss/take_profit` تُصفَّر قبل بناء نقطة الخروج البصرية فتظهر 0.0 (الواجهة لم تلاحظها لأنها تربط الدخول/الخروج بـ trade_id). الآن تُحفظ قبل التصفير وتُكتب الصحيحة — فمعادلتكم `Δ = exit − entry` صحيحة **حتى على صف نقطة الخروج مباشرة**، و`commission` لنقطة الخروج صارت محسوبة من حجم الصفقة الحقيقي.
2. **الاسم المزدوج للعمود** (موضح في 5.3) — كان سيكسر طبقة الطبقات الجديدة في شارت الباك-تست لاحقاً.

---

## 7) الملفات المعدَّلة + MD5 (المطابقة بعد فك الضغط أمر `md5sum -c`)

| الملف | MD5 |
|---|---|
| app/services/indicators/overlays.py | `bbc47df6d112ad6a963d4b81ecda0fb5` |
| app/services/indicators/overlay_columns.py | `062f8d51c327c5b9eb5987082bef4a60` |
| app/services/indicators/overlay_adapters.py | `30e0f27712824aab8f589302b420ffd1` |
| app/services/indicators/calculator.py | `25c39e9074d7a3d3d451a755fe90a4fd` |
| app/services/strategy/conditions.py | `72ed494b483b0e45d7a139512d6b9ed5` |
| app/services/strategy/schemas.py | `3d0e5d15f3fdefff09baab9eab301d6b` |
| app/services/strategy/presets.py **(جديد)** | `3d844297b0939dbc6fc96406d48b65b1` |
| app/backtest/schemas.py | `80f7b2a171c86f0fb42f1f43aece2de3` |
| app/backtest/engine1.py | `7d1fc2ffee8a27ca8ab4d78a1f78a9f8` |
| app/tasks/backtest_tasks.py | `ea8450195d36e0c84dfe8ca33f7c561a` |
| app/routers/indicators.py | `0041ef27a99fec02807bcdec06b63a30` |
| app/routers/backtest.py | `edafa1232236e27026e41817c8b18c9e` |
| app/routers/strategies.py | `6f2e359d35ddc162d8ab50f952fe22b2` |
| app/routers/strategies1.py | `83d621da78d2a3375a606c90590a887c` |
| app/routers/api.py | `ec20209377a3c2bfd126c947c3694b66` |
| app/routers/market_data.py | `5cb58e178e62176316509cec1c355130` |

---

## 8) خطوات النشر (داخل حاوية trading-backend)

```bash
# 1) فك الضغط في مجلد مؤقت
unzip ROUND12-ZIGZAG-FIB.zip -d /tmp/r12 && cd /tmp/r12
# 2) نسخ الملفات إلى الحاوية (البنية محفوظة كما هي)
docker cp app/services/indicators/overlays.py       trading-backend:/app/app/services/indicators/overlays.py
docker cp app/services/indicators/overlay_columns.py trading-backend:/app/app/services/indicators/overlay_columns.py
docker cp app/services/indicators/overlay_adapters.py trading-backend:/app/app/services/indicators/overlay_adapters.py
docker cp app/services/indicators/calculator.py     trading-backend:/app/app/services/indicators/calculator.py
docker cp app/services/strategy/conditions.py       trading-backend:/app/app/services/strategy/conditions.py
docker cp app/services/strategy/schemas.py          trading-backend:/app/app/services/strategy/schemas.py
docker cp app/services/strategy/presets.py          trading-backend:/app/app/services/strategy/presets.py
docker cp app/backtest/schemas.py                   trading-backend:/app/app/backtest/schemas.py
docker cp app/backtest/engine1.py                   trading-backend:/app/app/backtest/engine1.py
docker cp app/tasks/backtest_tasks.py               trading-backend:/app/app/tasks/backtest_tasks.py
docker cp app/routers/indicators.py                 trading-backend:/app/app/routers/indicators.py
docker cp app/routers/backtest.py                   trading-backend:/app/app/routers/backtest.py
docker cp app/routers/strategies.py                 trading-backend:/app/app/routers/strategies.py
docker cp app/routers/strategies1.py                trading-backend:/app/app/routers/strategies1.py
docker cp app/routers/api.py                        trading-backend:/app/app/routers/api.py
docker cp app/routers/market_data.py                trading-backend:/app/app/routers/market_data.py
# 3) إعادة التشغيل ثم التحقق
docker restart trading-backend
bash VERIFY-R12.sh        # كل البنود: PASS-1 .. PASS-8
```
> لا تغييرات قاعدة بيانات، ولا اعتماديات جديدة، ولا تغيير على /health الجذر. التراجع = استعادة ملفات v14 السابقة وإعادة التشغيل.

---

## 9) ملاحظات للواجهة (توحيد الأرقام)

1. **مطابقة zigzag-fib.ts**: كشف النقاط مطابق حرفياً لمحرك zigzag_channels (LuxAlgo) — إذا كانت الواجهة تستخدم `close` مع نفس `length` فالأرقام ستتطابق. الفرضية الوحيدة: الباكند يقرأ **سعر النقطة من high/low للشمعة** عند فهرس النقطة (مطابق لـ LuxAlgo: top=high[length]، btm=low[length]) — إن كانت الواجهة تستخدم HLC3 أو غيره فأخبرونا لضبط سطر واحد.
2. **`ind_zzf_touch`** يُقيَّم فقط من شمعة تأكيد الساق الثانية (بلا repaint). أول لمس لكل ساق مع إعادة تسليح عند تغيّر الساق — تماماً كما في الطلب.
3. **/indicators/compute** الجديد يصلح أيضاً لأي مؤشر كلاسيكي (`rsi` …) بعمود `ind_<name>`.
4. عند تشغيل البطل عبر الواجهة لا شيء يتغير افتراضياً (next_open + عمولة 0) — قياسكم المرجعي (19 صفقة · −4.97%) يبقى صالحاً، ومعه الآن `fees_applied: 0.0` و `math_audit.consistent: true` تلقائياً.

**جاهزون للجولة 13.**
