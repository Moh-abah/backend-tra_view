# 📋 تقرير تدقيق النسخة المنشورة — الجولة 12.1
## Audit of Deployed v12.9 (post-merge) · الإصلاح الكامل لعائد 0-أ · 7 إصلاحات جذرية

**التاريخ:** 2026-11-01 · **من:** وكيل الباك-END · **إلى:** وكيل الواجهة
**النسخة المُدقَّقة:** `deployed_backend.zip` (المنشورة على السيرفر بعد كل عمليات الدمج) — 73.0MB · 91MB مفكوكة
**بيئة التدقيق:** نسخة مطابقة من إنتاج شُغِّلت محلياً (uvicorn + SQLite) — **كل مخرجات أوامر القبول أدناه حرفية من هذا التشغيل**
**الحزمة المُسلَّمة:** `BACKEND-v12.9-AUDIT-FIX.zip` (النسخة 12.9 كاملة بعد الإصلاح) + `BACKEND-v12.9-HOTFIX-6FILES.zip` (6 ملفات معدَّلة فقط للـ docker cp)

---

## 0) الحكم النهائي على النسخة المنشورة

النسخة المنشورة تحتوي فعلاً على تنفيذ الجولة 12 (المؤشر zigzag_fib، عمولة 0، الشفافية الحسابية، preset البطل) — **لكن الفحص سطراً سطراً ودالةً دالة كشف 7 عيوب جذرية، أبرزها أن عائد 0-أ الأصلي (البادئة المزدوجة) ما زال حياً في 3 نقاط، ونقطة chart-data في backtest1 كانت معطوبة 404 دائماً، وstrategies1/run كان يُسقط كل المؤشرات بصمت.** كلها أُصلحت ومُختبِرت في هذا التدقيق — النسخة المُصلحة هي 12.9.

| # | العيب المكتشَف (بالسطر) | الجاذر | الحالة |
|---|---|---|---|
| A1 | `engine1.py:770` — `pd.notna(val)` يُسقط أعمدة العقد ind_* من شموع فترة التمهيد → مفاتيح كل شمعة مختلفة عن الأخرى (أعمدة تتلوى وتختفي) | جذر عائد 0-أ الأول | ✅ مُصلَّح |
| A2 | `backtest1.py:589/594/814` — ثلاث نقاط `f"ind_{name}"` بلا حماية → `ind_ind_zz_pivot` (العائد الأصلي حرفياً في النسخة المنشورة) | جذر عائد 0-أ الثاني | ✅ مُصلَّح |
| A3 | `backtest1.py:495+` — نقطة `/{id}/chart-data` تقرأ `backtest.visual_candles` وهو **حقل غير موجود في ORM** (البيانات في عمود chart_data) → **404 دائماً** حتى مع وجود بيانات | نقطة معطوبة كلياً | ✅ مُصلَّح (تفويض للتنفيذ الصحيح) |
| A4 | `overlays.py:1022` — تمرير `params.fib.levels` حرفياً (كما في أوامر القبول) → **500** `unexpected keyword argument 'levels'` | كسر أوامر القبول | ✅ مُصلَّح (توحيد مرادفات levels→level_ratios) |
| A5 | حقل `out_of_range` (بند 5-ب.1) **غير موجود في الكود إطلاقاً** — ناقص | بند مفقود | ✅ أُضيف لـ fib وzzfib |
| A6 | `strategies1.py:519` — النافذة المتنامية `iloc[:i+1]` مع كاش full_data → كل القرارات تُحسب على أول 50 شمعة مقتطعة → **صفر إشارة دائماً** في strategies1/run | عيب جوهري | ✅ مُصلَّح (تحضير مرة واحدة + تقييم على التاريخ كاملاً) |
| A7 | `strategies1.py:551` — الفلترة `action in ['BUY','SELL']` لكن `DecisionAction.value = 'buy'/'sell'` (صغيرة) → `active_decisions_count` **صفر حتى مع إشارات فعلاً** | عيب جوهري | ✅ مُصلَّح |
| A8 | `schemas.py:341` — `indicator_data: Dict[str, Dict[str, List[float]]]` صارمة ترفض null → أي إدراج أعمدة العقد في indicator_data **يُسقط النتيجة كاملة** (3418 خطأ تحقق) | انفجار خفي | ✅ مُصلَّح (Optional[float] → null) |

---

## 1) بند 0-أ — إصلاح العائد (النهائي هذه المرة، بالدليل)

### 1.1 ما كان يحدث في النسخة المنشورة (دليل الاعتراف)
```
GET /backtest1/get/{id} → visual_candles[0] ind_ cols (2):
  ['ind_ind_zz_pivot', 'ind_zigzag_channels']     ← بادئة مزدوجة + عمود وحيد خاطئ
```
**السلسلة الكاملة للسبب الجذري** (مُثبَّتة بفحص مباشر للـ DataFrame):
1. `overlay_columns.py` يُحقن 6 أعمدة `ind_zz_*` في df (dtype=object، قيم None في التمهيد) — صحيح.
2. `engine1.py` يبني visual candle من كل أعمدة df لكن `pd.notna(val)` **يُسقط** كل قيمة NaN → شموع التمهيد تفقد 5 من 6 أعمدة.
3. عمود `zigzag_channels` الخام (من apply_indicators) يتسرب إلى indicators بجانب أعمدة العقد.
4. `backtest1.py` عند القراءة يضيف `ind_` **فوق** أسماء أصلاً مسبوقة → `ind_ind_zz_pivot`.

### 1.2 الإصلاح
- **engine1.py:** أعمدة العقد (تبدأ بـ `ind_`) تُكتب **دائماً** — NaN/None → `null` في JSON. مجموعة مفاتيح كل شمعة ثابتة وكاملة (العقد المُلزم).
- **backtest1.py (3 نقاط):** `_k if _k.startswith("ind_") else f"ind_{_k}"` — لا بادئة مزدوجة بعد اليوم في أي مسار.
- **schemas.py:** `indicator_data` يقبل null لفترة التمهيد بدل سقوط النتيجة كاملة.

### 1.3 مخرجات القبول (حرفية — بعد الإصلاح)
```
[0-أ] champion 200 days backtest1/run
status: COMPLETED | backtest_id: 4bc9e4bf-f97c-4d64-92da-04044645799b
trades: 10 | pnl%: -1.8561 | fees_applied: 0.0 | fill_model: next_open
ind_ cols (7): ['ind_zigzag_channels', 'ind_zz_pivot', 'ind_zz_pivot_high',
                'ind_zz_pivot_low', 'ind_zz_prev_pivot_high',
                'ind_zz_prev_pivot_low', 'ind_zz_state']
double-prefix: [] | unique keysets: 1
math_audit: checked=10 max_err=0.0 consistent=True

GET /backtest1/get:      ind cols: 7 | double-prefix: []
GET /backtest1/{id}/chart-data: rows: 4800 | ind cols: 7 | double-prefix: []
  metadata.symbol: BTCUSDT | display_symbol: BTCUSDT
```
> **المطابقة الرجعية:** 10 صفقات · −1.8561% — حرفياً الرقم المرجعي الموثق في preset البطل (10 صفقات · −1.86% · next_open · عمولة 0) ✅
> ملاحظة: 7 أعمدة وليست 16 في تشغيل البطل لأن الاستراتيجية تُفعِّل zigzag_channels فقط — أعمدة fib/atl تظهر عند تفعيل مؤشراتها (عقد الـ16 عموداً الكامل مُتحقَّق أدناه عند تشغيل الثلاثة معاً).

---

## 2) عقد الـ16 عموداً بالمؤشرات الثلاثة (قبول [12] حرفي)

```
16-col contract (3 indicators): 16 PASS
['ind_atl_cross_lower', 'ind_atl_cross_upper', 'ind_atl_lower', 'ind_atl_signal',
 'ind_atl_upper', 'ind_fib_dir', 'ind_fib_end', 'ind_fib_signal', 'ind_fib_start',
 'ind_fib_target', 'ind_zz_pivot', 'ind_zz_pivot_high', 'ind_zz_pivot_low',
 'ind_zz_prev_pivot_high', 'ind_zz_prev_pivot_low', 'ind_zz_state']
```

---

## 3) البند 1 — zigzag_fib (كامل، بالدليل)

### 3.1 التسجيل (/indicators/available)
```
available zigzag_fib: ['zigzag_fib']
available 'zzf' filter (حرفي كما في طلبكم): ['zzfib']
display_name: ['ZigZag Fib Retracement (ZigZag-anchored)']
```

### 3.2 أعمدة ind_zzf_* (POST /indicators/compute)
```
zzf columns (13): ['ind_zzf_dir', 'ind_zzf_i1', 'ind_zzf_i2', 'ind_zzf_level_0',
 'ind_zzf_level_0236', 'ind_zzf_level_0382', 'ind_zzf_level_05', 'ind_zzf_level_0618',
 'ind_zzf_level_0786', 'ind_zzf_level_1', 'ind_zzf_p1', 'ind_zzf_p2', 'ind_zzf_touch']
```

### 3.3 العنونة الثلاثية (/strategies1/validate)
```json
{"valid": true, "msg": "Strategy configuration is valid"}
```
(بـ `left_value: "indicator:zigzag_fib:zzfib_touch"` حرفياً)

### 3.4 overlay zzfib (POST /overlays/compute)
```
zzfib keys: ['current', 'legs', 'name', 'notes', 'out_of_range', 'params', 'series', 'signals']
zzfib current keys: ['dir', 'i1', 'i2', 'leg', 'levels', 'live_extension', 'p1', 'p2', 'target']
zzfib out_of_range: []
legs: 12 (على 1440 شمعة BTCUSDT 1h)
```

---

## 4) البندان 2/3 — عمولة 0 + الشفافية الحسابية (بالدليل)

```
next_open (افتراضي):  trades: 10 | pnl%: -1.8561 | fees_applied: 0.0
signal_close (صريح):  trades: 10 | pnl%: -1.0276 | fees_applied: 0.0
math_audit: {'checked': 10, 'max_err': 0.0, 'consistent': True,
             'formula': 'pnl == (exit_price - entry_price) * units * (long?+1:-1) - commission - slippage'}
exit transparent cols missing: NONE — all 8 present
  (price_delta · price_delta_pct · direction · result_pct · pnl_gross · commission · fill_entry · fill_exit)
hand-check trade0: pnl=16.332050740009887 vs formula=16.332050740009887 | diff=0.0000000000
```
> **توثيق فرق نموذج التنفيذ (بند 4):** next_open = 10 صفقات · −1.86% مقابل signal_close = 10 صفقات · −1.03% على نفس النافذة — الفرق فعلي ويظهر في fill_entry/fill_exit لكل صفقة. (ملاحظة: أرقام إنتاج مرجعية سابقة كانت +112% لنافذة تاريخية مختلفة؛ البنية نفسها — الاختيار يدوي عبر `fill_model`.)

---

## 5) البند 4 — البطل v2 مُثبَّت + رفض الشكل المجهول

- `/strategies1/presets` يحتوي `zigzag_hl_v2_zero_fee` بحمولة كاملة (زيغزاق length=100، Higher Low Structure، خروج قمة مؤكدة، SL 2%، TP 99%، عمولة 0، position_size_percent 1.0 عشري).
- الشكل المجهول `{"type":"composite","logic":"and"}` → **يرفض برسالة واضحة** (وليس 0 صفقة صامتة):
```
composite bad shape → status: FAILURE | clear error: True
error: فشل تهيئة الاستراتيجية... Input should be 'indicator_value', 'indicator_crossover',
'price_crossover', 'volume_condition', 'time_condition', 'logical_and', 'logical_or' or 'logical_not'
```

---

## 6) البند 5 — الأداء والصحة

- `market/candles?before=` (تمرير يسار): **~85ms** لكل صفحة 2000 شمعة (كاش parquet فُعِّل — كان العائق الوريث غياب pyarrow في البيئة؛ في الإنتاج موجود).
- `/health` مع Redis متوقفاً: `{"status":"ok","services":{"database":{"status":"up"}}}` — لا انهيار، ومسار inprocess بلا Redis يعمل (مُثبَت أعلاه: كل التشغيلات في هذا التدقيق كانت inprocess).
- `chart-data?include_indicators=true` يعيد كل أعمدة ind_* (7 أعمدة البطل — 4800 شمعة).

---

## 7) البند 5-ب — المستويات والدقة والرموز

### 7.1 سياسة مستويات [0,1] + out_of_range
```
fib   out_of_range: [] | levels: [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
zzfib out_of_range: []
بتمرير صريح levels=[0,0.5,1,1.618,2.618] → out_of_range: [1.618, 2.618]  (شفافية كاملة)
```

### 7.2 الدقة تحت العُشر (WINUSDT)
```
candles: 720 | close<0.01: True | close sample: [4.822e-05, 4.886e-05, ...]
full precision: 4.822e-05 (0.00004822) — بلا أي تقريب/تنسيق
```

### 7.3 تعارض الرموز المتعددة
```
symbols: ['BTCUSDT', 'DOGEUSDT'] | metadata.symbol: BTCUSDT | display_symbol: BTCUSDT
chart_data_by_symbol: BTCUSDT→240 شمعة · DOGEUSDT→240 شمعة (وسم symbol على كل شمعة)
```

---

## 8) strategies1/run — إصلاحان جذريان (A6/A7)

قبل الإصلاح: `active_decisions_count: 0` دائماً (نافذة متنامية تُقتطع + مقارنة 'BUY' مع 'buy').
بعد الإصلاح:
```
total_bars: 1390 | active_decisions_count: 2
- buy | Higher Low Structure | 2026-10-02T13:00:00+00:00
- buy | Higher Low Structure | 2026-10-06T22:00:00+00:00
```
> **الاتساق:** 60 يوماً → إشارتا buy في strategies1/run ↔ صفقتان في backtest1/run — نفس المنطق على نفس البيانات.

---

## 9) الملفات المعدَّلة (6) — MD5 للنسخة 12.9

| الملف | MD5 | السطور |
|---|---|---|
| `app/backtest/engine1.py` | `855e148c6f3f0a7b118cd4022ebceb38` | 2140 |
| `app/backtest/schemas.py` | `0c127d29b5fd7bed0037c4f8d52608df` | 521 |
| `app/routers/backtest.py` | `5e888e5182c40877ade0ca06a859d0fa` | 886 |
| `app/routers/backtest1.py` | `4ef8fdde9af93f0de9edc3e1f54ddcc8` | 764 |
| `app/routers/strategies1.py` | `eb3d06742446986e539aed5d9264ecd9` | 744 |
| `app/services/indicators/overlays.py` | `c53be6cf92885c7f1ba42c3f26498e74` | 1074 |

**النشر:** `docker cp` للملفات الستة داخل الحاوية ثم `docker restart trading-backend` — أو استخدم الحزمة الكاملة `BACKEND-v12.9-AUDIT-FIX.zip`.

---

## 10) خلاصة القبول — كلها ✅

| أمر القبول | النتيجة |
|---|---|
| 0-أ: ind_* ثابتة + لا بادئة مزدوجة + البطل يصدّر صفقات | ✅ 10 صفقات · −1.8561% |
| 1: zigzag_fib مسجَّل + 13 عمود ind_zzf_* + validate صحيح | ✅ |
| 2: عمولة 0 في كل المسارات + fees_applied + fill_model | ✅ fees 0.0 |
| 3: 8 أعمدة شفافية + math_audit consistent | ✅ max_err=0.0 |
| 4: preset البطل + رفض composite المجهول | ✅ |
| 5: candles ~85ms + /health بلا انهيار + chart-data كامل | ✅ |
| 5-ب.1: مستويات [0,1] + out_of_range | ✅ |
| 5-ب.2: WINUSDT 4.822e-05 بلا تقريب | ✅ |
| 5-ب.3: by_symbol + display_symbol | ✅ |
| إضافي: strategies1/run يُصدر إشارات فعلاً | ✅ 2 buy |

**ملحوظة بيئة التدقيق:** سانبوكس التطوير كان يواجه Binance 418 (تهدئة IP مؤقتة) أحياناً — ليس عيباً كودياً؛ أوامر القبول القائمة على شموع مضمّنة (candles[]) لا تتأثر. بعد النشر على الإنتاج شغّل `VERIFY-R12.1.sh` ضد `http://161.97.73.254:8000` للتأكيد الحرفي هناك.
