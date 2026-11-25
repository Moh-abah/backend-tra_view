# حزمة الدمج B9-T100-GATE1 (v4.3) — دليل التركيب

> **المشكلة التي تُصلحها هذه الحزمة (حرفياً)**:
> 1. «الدخول في الصفقة تم الدخول فيها والسعر ما زال تحت خط ترند 100» — كانت بوابة
>    ترند-100 تُقيَّم عند **شمعة الإشارة** فقط (إغلاق الشمعة فوق الخط) بينما **التنفيذ**
>    يحدث على افتتاح الشمعة التالية (`next_open`) — فيمكن أن يهبط السعر تحت الخط
>    خلال الدقائق الفاصلة فيُفتح المركز والسعر تحت الخط فعلياً.
> 2. «الباك اند لا يرجع رسومات الترند واحداثياتها» — كانت إحداثيات خطوط الترند
>    تُحسب داخل المحرك ثم **تُهمل** عند التسوية إلى أعمدة `ind_trf_*` فلا تصل للفرونت.

---

## ما الذي تتضمنه الحزمة (8 ملفات + مشغّلات + أداة تحقق)

| # | الملف | التغيير |
|---|---|---|
| 1 | `app/backtest/engine1.py` | بوابة التنفيذ الحرفية عند الدخول + التقاط رسومات الترند + نقاط الرفض + صدى البوابة في النتيجة |
| 2 | `app/backtest/schemas.py` | حقلا `BacktestResult` الاختياريان: `trend_drawings` و `skipped_entry_points` |
| 3 | `app/services/indicators/overlay_columns.py` | قسم `trend_fractal` في `sections` (إحداثيات الخطوط — كانت تهمل) |
| 4 | `app/tasks/backtest_tasks.py` | مفتاحا `chart_data` الجديدان: `trend_lines` + `skipped_entry_points` |
| 5-8 | `payloads/payload_B9_T100_LIVE_GATE1_{ETHUSDT,XRPUSDT,MBLUSDT}.json` | نفس حمولات LIVE المنشورة + `execution_gates` |
| — | `launchers/GATE1-1..9_*.json` | مشغّلات الاختبارات التسعة نفسها + `execution_gates` |
| — | `tools/verify_b9_gate.py` | أداة التحقق من العقد بعد التشغيل |

---

## خطوات التركيب

```bash
# 1) انسخ الملفات الأربعة إلى جذر نظامك (نفس بنية المجلدات):
cp app/backtest/engine1.py        <جذر-نظامك>/app/backtest/engine1.py
cp app/backtest/schemas.py        <جذر-نظامك>/app/backtest/schemas.py
cp app/services/indicators/overlay_columns.py <جذر-نظامك>/app/services/indicators/overlay_columns.py
cp app/tasks/backtest_tasks.py    <جذر-نظامك>/app/tasks/backtest_tasks.py

# 2) تحقق من البصمات (اختياري لكن مستحسن):
md5sum -c FILES-B9-T100-GATE1.md5

# 3) أعد تشغيل الخدمة (uvicorn/celery — كما تعيد تشغيلها عادةً).

# 4) استورد الحمولات الثلاث الجديدة (اختياري — للإدارة في قاعدة الاستراتيجيات):
#    POST /api/v1/strategies1/save_to_db  بمحتوى payloads/payload_B9_T100_LIVE_GATE1_MBLUSDT.json (وهكذا للثلاثة)

# 5) شغّل اختبار التحقق — نفس حمولة 10001690/POSTFIX-D نفسها + البوابة فقط:
#    POST /api/v1/backtest1/run  بمحتوى launchers/GATE1-8_MBLUSDT_15m.json
#    (و GATE1-1..9 لباقي الاختبارات التسعة)

# 6) بعد اكتمال المهمة تحقق حرفياً من العقد:
python3 tools/verify_b9_gate.py --task <رقم-المهمة-الجديد> --base http://161.97.73.254:8000
```

---

## كيف تعمل البوابة (العقد الجديد)

في `strategy_config` تُضاف قائمة اختيارية:

```json
"execution_gates": [
  {
    "name": "بوابة ترند-100 عند التنفيذ — لا دخول والسعر تحت خط الترند 100",
    "on": "entry",
    "side": "long",
    "column": "ind_trf_p100_upper",
    "require": "price_above",
    "enabled": true
  }
]
```

- **متى تُقيَّم؟** عند لحظة التنفيذ نفسها: `next_open` ⇒ افتتاح شمعة الدخول —
  نفس السعر الذي ترسمه الواجهة عند نقطة الدخول على الشارت.
- **ماذا تتحقق؟** `سعر التنفيذ > قيمة ind_trf_p100_upper عند شمعة الدخول نفسها`.
  سببية كاملة (لا استشراف): القيمة من الشمعة الحالية فقط — نفس ما يفعله بوت حي
  قبل وضع الأمر.
- **عند الرفض:** لا يُفتح المركز، وتُسجَّل **نقطة `skipped_entry`** شفافيةً (يرسمها
  الفرونت إذا شاء: «دخول مرفوض بالبوابة»)، والإشارة نفسها لا تُعاد محاولتها
  (قرار شمعة واحدة — نفس دلالات next_open). إن بقيت الشروط متحققة في الشموع
  التالية تأتي إشارة جديدة تدخل عندئذٍ فوق الخط.
- **غياب `execution_gates` كلياً ⇒ السلوك السابق بت-بت** (أثبتنا التطابق
  الرقمي بت-بت — انظر التقرير). كل الاستراتيجيات الأخرى لا تُلمس إطلاقاً.

## ماذا ترجع النتيجة الجديدة للفرونت اند

داخل `chart_data` (من `GET /api/v1/backtest1/get/{id}`):

```jsonc
"trend_lines": {                      // ✦ رسومات الترند بإحداثياتها — ليرسمها الفرونت
  "engine": "Fractal-Auto-Trendlines",
  "spec": "ROUND33-dojiemoji-fidelity",
  "params": {"periods": [100], "confirm_mode": "all", "threshold": 1},
  "by_symbol": {
    "MBLUSDT": {
      "lines": {
        "p100": {
          "period": 100,
          "upper": [ { "kind": "upper", "x1": 298, "t1": 1694831400000, "y1": 0.002847,
                        "x2": 195, "t2": 1694738700000, "y2": 0.00286,
                        "slope": -1.2621e-07, "formed_at_bar": 399,
                        "formed_at_time": 1694922300000, "active": false,
                        "replaced_at_bar": 832 } , ... ],
          "lower": [ ... ]
        }
      },
      "current": { ... },        // الخطان الحيّان الآن بقيمتهما عند آخر شمعة
      "events": { ... }          // عدادات: pivots/lines/crosses
    }
  }
},
"skipped_entry_points": [          // ✦ الدخولات التي رفضتها البوابة — شفافية كاملة
  { "timestamp": "...", "type": "skipped_entry", "symbol": "MBLUSDT",
    "direction": "long", "would_be_price": 0.002504, "line_value": 0.00250602,
    "margin_pct": -0.0806, "reason": "بوابة الترند-100 عند التنفيذ: سعر الدخول تحت خط الترند-100 — الدخول مرفوض" }
]
```

رسم كل خط في الفرونت: قطعة مستقيمة من `(t1, y1)` إلى `(t2, y2)` — وإن أردت
تمديده يميناً استخدم `slope` (`y(x) = y1 + slope × (x − x1)` بالشموع، أو
`y(t) = y1 + slope × (t − t1) / ms_per_candle`). `active=false` يعني وُلد خط
أحدث بعده (`replaced_at_bar`).

وفي `summary.math_audit.execution_gates` صدى إحصائي لكل رمز:
`{active, gates[], checked, blocked}`.

## ملاحظات التوافق (مهمة)

- الملفات الأربعة مبنية **حرفياً على نسخ نظامك المنشورة** (`B9-LIVE1 v4.2`
  للأعمدة + نسختك الأصلية للمحرك/المخططات/المهام) — فروق التعديل فقط هي
  المذكورة أعلاه، وكلها اختيارية الفعالية.
- `overlays.py` و `overlays_b9_macd_gates.py` **لم يُلمسا** — كما هما في LIVE1.
- استراتيجيات **بلا** `trend_fractal`: لا رسومات ولا بوابة — نفس النتيجة القديمة
  بت-بت (حقلان `null` في chart_data فقط).
- استراتيجيات **بها `trend_fractal` بلا `execution_gates`**: ترجع الرسومات الجديدة
  (بيانات إضافية للفرونت) **دون أي تغيير في الصفقات** — أثبتنا التطابق بت-بت.
- حجم `trend_lines` صغير (~100-150KB لكل نتيجة 15m/110k شمعة مقابل 45MB موجودة).
