# 🖥️ عقد وكيل الفرونت-اند الشامل الكامل — نظام الباك-تست (بعد جولة SPLIT-ZZ1)

> **الغرض:** بناء واجهة **مكتملة ومرنة** تتيح تعديل وإضافة وتغيير كل معامل أي استراتيجية،
> وتركيب الشروط ودمج «هذي لهذي وذي وذي»، وتخصيص متوسطات EMA وفريماتها، وكل المخارج —
> بلا حاجة لتعديل باك-اند مستقبلي (كل شيء في هذه الوثيقة قابل للتكوين من JSON).
>
> **أساس الوثيقة:** الكود المنشور الحي (EMAGATE-UNIFIED + LIBRARY-FULL + SPLIT-TP1 +
> **SPLIT-ZZ1 الجديدة**) — كل حقل موثق هنا مقروء فعليًا من المحرك، وكل عقد عرض مُحقون
> في النتائج الحية.

---

## 0) النظرة الكلية — استراتيجية واحدة = خمس طبقات قابلة للتركيب

```
┌─ الرأس: الرمز/الفريم/النافذة/رأس المال/المراكز/التراكم/نموذج التنفيذ
├─ الدخول: محرك الإشارة (زقزاق+فيبو+كمومية+رصة EMA) × بوابات (ترند/منطقة/رصة/زخم)
├─ الشروط: بوابة الزخم المرنة (شجرة and/or/not بأي عمق — الموشرات بأي فريم)
├─ المخارج: exit_rules (JSON فوق المؤشرات) + SL/TP/تريلينق + التيك-بروت المقسم + الخروج المقسم بانعكاس الهيكل
└─ العرض: chart_data + trade_points (entry/exit/partial_exit) + trades.metadata + risk_echo
```

**قاعدة ذهبية للواجهة:** كل طبقة مستقلة قابلة للتعديل منفردة — تعديل أي طبقة لا يلمس
الأخريات (عقد «الإضافة النقية» في الباك-اند: حقل غائب = سلوك تاريخي بت-بت).

---

## 1) حمولة الباك-تست — الرأس (root BacktestConfig)

`POST /api/v1/backtest1/run` — الحقول null أو الغائبة = معطلة:

| الحقل | النوع | الدلالة |
|---|---|---|
| `name` / `description` | نص | اسم الباك-تست ووصفه (يظهران في المكتبة) |
| `mode` | نص | `standard` |
| `symbols` | قائمة | `["MMTUSDT"]` — رمز واحد حاليًا في الجولة |
| `timeframe` | فريم | فريم الشارت: `1s..Ns · 1m..Nm · "60"/1h · "240"/4h · 1D · 1W · 1M · 3M` — **أرقام مجردة = دقائق** |
| `start_date` / `end_date` | ISO | نافذة الباك-تست (بالتوقيت `timezone`) |
| `timezone` / `tz_offset_minutes` | — | `UTC` / `0` |
| `market` | نص | `crypto` |
| `initial_capital` | رقم | رأس المال الابتدائي |
| `position_sizing` | نص | `percentage` ⇒ `position_size_percent` نسبة مئوية حقيقية (1=1% · 100=كامل الرصيد) |
| `max_positions` | رقم | 1 = مركز واحد · 2..100 = مراكز متزامنة مستقلة (R55) |
| `compounding` | bool | كل صفقة بـ100% من الرصيد الجاري + مركز واحد فقط (R60) |
| `multi_position_compounding` | bool | N خانات: كل مركز = الرصيد÷N ويتجدد بعد كل إقفال (R62) |
| `fill_model` | نص | `next_open` (افتراضي — قرار إغلاق/تنفيذ فتح) أو `signal_close` |
| `stop_loss_percent` | رقم؟ | (0..100) فقط ⇒ ستوب لوز. **null/0/100 = معطل** |
| `take_profit_percent` | رقم؟ | مثل السابق — جني كامل |
| `trailing_stop_percent` | رقم؟ | (0.1..50) ⇒ تريلينق **يلغي SL/TP** عند تفعيله |
| `take_profit_splits` | قائمة؟ | ✅ SPLIT-TP1: مستويات الجني المقسم (§6ب) |
| **`structure_split_exits`** | قائمة؟ | ✅ **SPLIT-ZZ1 الجديدة**: الخروج المقسم بانعكاس هيكل الزقزاق (§6ج) |
| `max_daily_loss_percent` | رقم؟ | يُحفظ فقط (غير مقروء من المحرك) |
| `enable_short_selling` / `enable_margin` / `leverage` | — | بيع/هامش/رافعة |
| `commission_rate` / `slippage_percent` | — | **صفر دائمًا** (سياسة Zero-Fee — أي قيمة >0 تُرفض 422) |
| `require_confirmation` | bool | تأكيد الإشارة |

**تنبيهات 422 للواجهة:** أي قيمة >0 لعمولة/انزلاق تُرفض · مجموع أحجام
`take_profit_splits` >100% يُرفض · مجموع أحجام `structure_split_exits` >100% يُرفض ·
أشكال غير مفهومة في القائمتين تُرفض برسائل عربية.

---

## 2) strategy_config — قواعد الدخول والخروج (JSON فوق أعمدة المؤشر)

### entry_rules
```json
{"name": "…", "enabled": true, "position_side": "long",
 "weight": 0.34,
 "condition": {
   "type": "indicator_value", "operator": ">",
   "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema_mom:zzfetqem_entry_s1",
   "right_value": 0}}
```
- `left_value`: `indicator:<اسم-المؤشر>:<عمود>` أو عمود سعر (`close`).
- `operator`: `> >= < <= == !=`.
- `right_value`: رقم أو مرجع عمود.
- **شرط مركب:** `"type": "and"|"or"` + `conditions: [...]` بأي عمق (`logical_and/logical_or`
  تُوحَّد تلقائيًا).
- `weight` (0..1): وزن القاعدة · `position_side`: `long/short`.

### exit_rules — **كل مداخل الذكاء هنا**
```json
{"name": "خروج كسر الترندات", "enabled": true,
 "condition": {"type": "indicator_value", "operator": ">=",
               "left_value": "indicator:…:zzfetqe_trend_votes_bear",
               "right_value": 3},
 "exit_type": "signal_exit",
 "arm_after_gain_pct": 10,
 "only_losing_positions": false}
```
| الحقل | الدلالة |
|---|---|
| `exit_type` | `signal_exit` (مخرج إشارة) · `stop_loss/take_profit/trailing_stop` |
| `arm_after_gain_pct` | **تعطيل القاعدة حتى يرتفع السعر X% فوق الدخول** (Latch) — None/0 = معطل |
| `only_losing_positions` | **true = إغلاق الخاسر فقط عند سعر التنفيذ** (الرابح تركب) — SMART-EXIT1 |

**فخ الأعمدة (مهم للواجهة!):** ميّز بين الأعمدة العدّادية والثنائية —
`zzfetqe_trend_votes_bear` **عدّاد 0..3** (يقبل `>= 2/3`) · `zzfetqem_zone_exit` **ثنائي 0/1**
(يقبل `> 0` فقط — `>= 3` لا يُطلق أبدًا!). أضف تحذيرًا في محررك عند مقارنة عمود ثنائي
بعتبة > 1.

---

## 3) محرك الإشارة — `zigzag_fib_e2e_trendy_quantum_ema_mom` (كموميه الزخم الاولى)

كل معاملات `indicators[0].params` (قابلة للتعديل/الحذف/الإضافة من الواجهة):

### أ) رادار الزقزاق + الفيبو
| المعامل | الافتراضي | الدلالة |
|---|---|---|
| `mode` | `luxalgo` | نمط الزقزاق |
| `length` | 100 | عيار رادار الزقزاق (226 للجبّارة · 100 للديفولت) — **المحاور المؤكدة ومنها مستويات الاختراق وبنية HH/HL/LL/LH** |
| `touch_level` | 0.618 | مستوى لمس الفيبو (خامل في البوابات) |
| `depth/deviation/backstep` | 12/20/3 | معاملات نمط zigzag الكلاسيكي |

### ب) بوابة الترند
| المعامل | الافتراضي |
|---|---|
| `trend_periods` | `[7, 15, 25]` — **قائمة حرة: أضف/احذف/غيّر أي فترة** (الجديدة 8 و13 مدعومة كاملة — تُرسم وتُبث) |
| `trend_confirm` | `majority` (أو `all`/`any`...) |
| `trend_gate` | `["s1","s2","s3"]` — أي إشارات تخضع للبوابة |

### ج) المنطقة الكمومية
| المعامل | الدلالة |
|---|---|
| `zone_gate` | `["s1","s2","s3"]` — جواز المنطقة (HH+HL مفتوحة / LL+LH مغلقة) لكل الإشارات |

### د) رصة EMA — **التخصيص الكامل** ⭐
| المعامل | الافتراضي | الدلالة |
|---|---|---|
| `ema_lengths` | `[21,50,100,200,350,500]` | **قائمة حرة تمامًا**: أضف/احذف/رتب/غيّر (مثال: `[8,13,21,50,100,200,350,500]` — أطوال 8 و13 تُرسم بألوان صريحة: **8 سماوي #00BCD4 · 13 كهرماني #FFC107**، وأي طول مخصص يأخذ لونًا من لوحة احتياط دائرية — لا خط بلا لون أبدًا) |
| `ema_resolution` | `"60"` (ساعة) | **أي فريم**: `1s..Ns · 5m/15m/30m · 60/1h · 240/4h · 1D · 1W · 1M · 3M` — الأرقام المجردة = دقائق. رصة على فريم مختلف عن فريم الشارت ببناء سببي (بلا استشراف) |
| `ema_source` | `close` | `open/high/low/close/hl2/hlc3/ohlc4` |
| `ema_offset` | 0 | إزاحة شموع |
| `ema_gate` | `["s1","s2","s3"]` | جواز الرصة للإشارات |
| `ema_stack_mode` | `hierarchical` | **الوضع الهرمي الموحد** (EMAGATE-UNIFIED) |
| `ema_stack_base` | 21 | القاعدة المعفاة من الترتيب (الأسرع) |

**شروط الرصة الهرمية السبعة** (تُبث أعمدة تشخيص لكل واحد):
1. السعر فوق كل المتوسطات (`zzfetqe_ema_stack_price_ok`)
2. السلّم مرتب تصاعديًا حسب الأطوال (`ladder_ok` — عمود لكل زوج متجاور `pair_ok_{a}_{b}`)
3. الأسرع من القاعدة (`ema_stack_base`) معفاة من الترتيب
4-7. الأزواج المتجاورة كلها مرتبة

### هـ) هيكل الخروج
| المعامل | الافتراضي | الدلالة |
|---|---|---|
| `zone_exit_resolution` | `"5"` (5 دقائق) | فريم حساب هيكل الخروج: **null/none/الفراغ = فريم الشارت (السلوك التاريخي)** · `5m` أدق حقيقي (من طبقة البيانات) · `60/240/1D/1W` أعلى (تجميع من شموع الشارت) |
| `zone_exit_length` | 100 | عيار الزقزاق لذلك الفريم |

---

## 4) بوابة الزخم المرنة (QMOM1) — `osc_instances` + `osc_conditions` ⭐⭐

### أ) النسخ `osc_instances` — أي موشر، أي فريم، أي عدد
```json
{"kind": "macd", "id": "macd_4h_12_26_4", "timeframe": "4h",
 "fast": 12, "slow": 26, "signal": 4, "enabled": true, "doc": "…"}
{"kind": "rsi",  "id": "rsi_1d_14_14", "timeframe": "1d",
 "period": 14, "ma_length": 14, "bb_std": 2, "enabled": true}
{"kind": "mom",  "id": "mom_…", "timeframe": "…", "length": 10, "enabled": true}
```
- `kind`: `macd` (fast/slow/signal) · `rsi` (period/ma_length/bb_std) · `mom` (length).
- `timeframe`: **أي فريم 1s..1mo** (يُحسب على شموع القاعدة بتجميع صاعد + إسقاط سببي —
  بلا استشراف).
- `id`: فريد — تُبث سلاسله كأعمدة: `zzfetqem_osc_<id>_line/signal/hist` (macd) ·
  `value/ma/bb_upper/bb_lower` (rsi) · `line/pct` (mom).
- `enabled`: تعطيل النسخة = محايد.

### ب) شجرة الشروط `osc_conditions` — and/or/not بأي عمق
```json
{"logic": "and", "conditions": [
  {"name": "…", "enabled": true, "logic": "and", "conditions": [
     {"left": "osc:macd_4h_12_26_4.line", "op": ">", "right": 0},
     {"left": "osc:macd_4h_12_26_4.line", "op": ">", "right": "osc:macd_4h_12_26_4.signal"}]},
  {"left": "osc:rsi_1d_14_14.value", "op": "<=", "right": 60, "enabled": true}
]}
```
- الورقة: `{left, op, right, enabled, skip_unavailable}` — المرجع `osc:<id>.<field>` أو
  رقم. `enabled: false` = تعطيل محايد (كأن الفرع غير موجود).
- **محرر شجري مقترح:** عقد قابلة للإضافة/الحذف/السحب، لكل عقد: نوع (و/أو/ورقة) +
  مفاتيح enabled + اختيار المرجع من قائمة النسخ المنشأة + العملية + القيمة/المرجع.

### ج) الشروط الخمسة الحية في القالب (بعد SPLIT-ZZ1)
| # | الشرط | الورقة |
|---|---|---|
| 1 | MACD 4h (12/26/4) فوق الصفر ∧ إيجابي | `line > 0 ∧ line > signal` |
| 2 | MACD 3d (5/11/4) فوق MACD 1d (12/26/4) | `3d.line > 1d.line` |
| 3 | RSI 1h و 4h (14/14/2) فوق RSI اليومي | `1h.value > 1d.value ∧ 4h.value > 1d.value` |
| 4 | RSI اليومي (10/14/2) أو (14/14/2) فوق 50 — يكفي أحدهما | `or(10_14 > 50, 14_14 > 50)` |
| **5** | **الجديد (SPLIT-ZZ1): RSI اليومي (14/14/2) لا يتجاوز 60 — حدوده بين 50 و 60 فقط** | `rsi_1d_14_14.value <= 60` |

> إن أراد صاحب القرار نطاقًا صارمًا على النسخة نفسها (50 < قيمة ≤ 60 بمعزل عن
> شرط 4): ورقة مركبة `and(value > 50, value <= 60)` — مدعومة كما هي.

---

## 5) عقد العرض — ما يرجعه الباك-تست للرسم

### أ) شموع الرسم وبيانات المؤشر
- `chart_data`: الشموع (مخفَّفة ×2 للعرض على البيانات الضخمة) + `indicator_data` لكل
  محرك.
- أعمدة الرسم القائمة (فرونت current): خطوط EMA `ind_zzfetqe_ema_<len>` (بما فيها
  **8 و13 بألوانها**) · المنطقة · الرصة · الزقزاق/فيبو · الترندات `tr_p7/15/25` ·
  تظليل `zzfetqe_trend_votes_bear`.
- صدى التكوين الكامل في `/get` (config echo 100%).

### ب) نقاط الصفقات `trade_points` — ثلاثة أنواع
| `type` | متى | حقول مميزة |
|---|---|---|
| `entry` | فتح | `entry_price, position_size, trade_id, decision_reason, fill_entry` |
| `exit` | إغلاق كامل | `exit_price, exit_reason, pnl (إجمالي مجزأ), position_size (المتبقي المُغلق), fill_exit` |
| **`partial_exit`** | جني جزئي (SPLIT-TP1 أو SPLIT-ZZ1) | `price, position_size (المُباع), pnl, gain_percent+size_percent (تيبي) · resolution+length+size_percent (انعكاس), remaining_size, remaining_percent_of_original, exit_reason` |

**مقترح العرض:** علامات مثلثية صغيرة على الشارت لكل `partial_exit` (بلون مميز عن
علامات الخروج) + لوحة «جني جزئي» داخل بطاقة الصفقة.

### ج) كائن الصفقة `trades[]`
- `pnl` = **الإجمالي** (جني مقسم + انعكاسات + ختامي) · `pnl_percentage` على الكمية الأصلية.
- `partial_exits` = كل أحداث الجني الجزئي (النوعان معًا).
- `metadata.split_tp` / `metadata.structure_split`: `{original_size, realized_pnl,
  events[], rules_config/levels_config}` — **events لكل انعكاس: `{time, resolution,
  length, rule, size_percent, size_sold, price, pnl, remaining_size}`**.
- `metadata.split_tp_summary`: يفصل `realized_pnl_gain_levels` عن
  `realized_pnl_structure_reversals`.
- `exit_reason`: `Split TP +5% (25%)` · `Split TP Hit (Full)` ·
  `Structure Split same·L25 (25%)` · `Structure Split Exit (Full)` ·
  `خروج قاعدي (+N جني مقسم)`.

### د) الصدى المحاسبي `math_audit.risk_echo` (يصل في `effective_config` أيضًا)
```
take_profit_splits / split_tp_active / split_tp_total_size_percent /
split_tp_trades / split_tp_partial_exits
structure_split_exits / structure_split_active / structure_split_total_size_percent /
structure_split_trades / structure_split_partial_exits / structure_split_semantics
```
+ `math_audit.momentum_gate` (عدادات بوابة الزخم: خام/نهائي/ممنوع لكل إشارة s1/s2/s3
+ التحذيرات + حالات النسخ).

---

## 6) المخارج الكاملة — خمسة أنواع تركّب معًا

### أ) exit_rules (JSON) — §2
بوابات إشارة فوق أي عمود مؤشر (كسر ترندات `zzfetqe_trend_votes_bear >= N` · خروج
منطقة `zzfetqem_zone_exit > 0` · أي عمود) + `arm_after_gain_pct` + `only_losing_positions`.

### ب) SL/TP/التريلينق (الجذر)
`stop_loss_percent` · `take_profit_percent` · `trailing_stop_percent` (يلغي SL/TP).

### ج) التيك-بروت المقسم `take_profit_splits` (SPLIT-TP1)
```json
"take_profit_splits": [{"gain_percent": 5, "size_percent": 25},
                        {"gain_percent": 7, "size_percent": 25}]
```
لمسة داخل الشمعة عند سعر المستوى بالضبط · ربع الكمية الأصلية · Latch لكل مستوى ·
أشكال مريحة: `[[5,25],[7,25]]`.

### د) **الخروج المقسم بانعكاس هيكل الزقزاق `structure_split_exits` (SPLIT-ZZ1 — الجديد)** ⭐⭐⭐
```json
"structure_split_exits": [
  {"resolution": "same",  "length": 100, "size_percent": 25,
   "name": "انعكاس الشارت", "enabled": true},
  {"resolution": "5m",   "length": 25,  "size_percent": 25,
   "name": "انعكاس 5 دقائق"},
  {"resolution": "1h",   "length": 50,  "size_percent": 15}
]
```
| الحقل | القيم |
|---|---|
| `resolution` | `same`/`chart`/`base`/فارغ = **فريم الشارت نفسه** · أو أي فريم (`1s..1M`): **أدق** من الشارت = شموع حقيقية من طبقة البيانات · **أعلى** = تجميع صاعد من شموع الشارت |
| `length` | عيار زقزاق الانعكاس على ذلك الفريم (افتراضي 100) |
| `size_percent` | النسبة من الكمية الأصلية تُباع عند **كل** انعكاس (LL+LH) أثناء فتح الصفقة |
| `enabled` / `name` | تعطيل محايد / تسمية في الأسباب |

**الدلالات الدقيقة (للنص التوضيحي في الواجهة):**
- الانعكاس يُؤكَّد على **إغلاق** شمعة ⇒ البيع الجزئي عند **open الشمعة التالية**
  (نفس دلالات exit_rules — قرار إغلاق، تنفيذ فتح، بلا استشراف).
- كل حدث مرة واحدة · أحداث متكررة = جنيات متتالية حتى النفاد الدفاعي.
- **الخروج الكامل بنفس الشمعة له الأولية** (لا جني جزئي عند خروج كامل).
- الاستنفاد = ختام `Structure Split Exit (Full)`.
- يعمل مع أي استراتيجية (حقل جذري) ومع المراكز الأساسية/الإضافية/SHORT.
- غياب الحقل = هوية بت-بت (لا مفتاح يُبث).

### هـ) التفاعل بين المخارج (أولوية داخل الشمعة)
التريلينق ← الستوب ← الجني المقسم (لمسات) ← التيبي المتبقي · وعند الفتح: إشارات
خروج/انعكاس الكاملة ← الانعكاسات المقسمة ← دخول جديد.

---

## 7) محررات الواجهة المقترحة (الأولويات)

1. **محرر شجرة الشروط** (osc_conditions): عقد و/أو/ورقة + enabled + مراجع النسخ —
   الأهم لأنه يمكّن «نضيف شروطنا ونركب ونعدل كل تكوين استراتيجيه ونضيف هذي لهذي».
2. **محرر النسخ** (osc_instances): kind + timeframe (منقي الفريمات) + معاملاتها + doc.
3. **محرر رصة EMA**: قائمة أطوال قابلة للتحرير (chips قابلة للإضافة/الحذف) + منتقي
   `ema_resolution` (فريمات) + المصدر + البوابة + الوضع الهرمي والقاعدة + معاينة
   ألوان (8 #00BCD4 · 13 #FFC107 · الستة كما هي).
4. **محرر الجني المقسم** (take_profit_splits): صفوف gain%/size% + مجموع حي + تحذير >100%.
5. **محرر الانعكاس المقسم** (structure_split_exits): صفوف {resolution (منتقي فريمات +
   خيار «نفس الشارت») + length + size% + enabled + name} + مجموع حي + شرح الدلالات.
6. **محرر exit_rules**: شرط JSON + exit_type + arm_after_gain_pct + only_losing_positions
   + **تحذير فخ الأعمدة الثنائية/العدّادية**.
7. **بطاقة صدى**: اعرض `risk_echo` (split_tp_* + structure_split_*) و
   `momentum_gate` و`partial_exits` لكل صفقة.

---

## 8) أمثلة حية جاهزة (في الحزمة)

| الملف | الغرض |
|---|---|
| `payloads/payload_qmom1_mmt_5cond.json` | الشروط الخمسة (البوابة الجديدة) — MMT · 15m · نافذة #10000604 |
| `payloads/payload_qmom1_mmt_5cond_splitzz.json` | الشروط الخمسة + انعكاسان مقسمان (same/25 + 5m/25) — المثال الذهبي |
| `payload_qmom1_mmt_10000604.json` (جولة SPLIT-TP1) | الأربعة الشروط كما هي — مرجع الهوية |

---

## 9) قائمة تحقق الواجهة (Checklist)

- [ ] كل حقل في §1 قابل للتحرير (null = معطل — لا ترسل 0 حيث يعطل)
- [ ] منتقي فريمات موحد (نفس الصيغ: 1s..Ns · Nm · "60"/1h · 240/4h · 1D · 1W · 1M · 3M)
- [ ] محرر شجرة الشروط يعمّق أي مستوى ويعطّل أي فرع
- [ ] EMA: أطوال حرة + فريم حر + ألوان 8/13 والاحتياط
- [ ] الجني المقسم + الانعكاس المقسم: صفوف قابلة للإضافة/الحذف + مجموع حي + رسائل 422 العربية تُعرض للمستخدم
- [ ] exit_rules مع arm/only-losing + تحذير الأعمدة
- [ ] الشارت: علامات partial_exit + لوحة جني جزئي لكل صفقة + أعمدة الرسم القائمة كما هي
- [ ] المكتبة: قائمة الباك-تستات كاملة (`/tasks?all=true` أو `limit=100000` — رقعة LIBRARY-FULL الحية)

— السديم 🌌 · جولة SPLIT-ZZ1 · 2026-11-19
