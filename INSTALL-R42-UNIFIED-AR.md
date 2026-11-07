# تثبيت الجولة 42 — التوحيد الكامل: استراتيجية الخروج داخل backtest1/run

**المواصفة:** `ROUND42-unified-backtest1` · محرك الخروج `ROUND42-hero-exit-trailing`

> **الجواب المباشر على السؤال المعلّق:**
> قبل هذه الجولة: **لا** — حقلا `use_trailing` و `trailing_giveback_pct` لم يكونا
> متوفرين في `POST /api/v1/backtest1/run` (كانا فقط في `/api/v1/exit-strategy/backtest`،
> وإرسالهما إلى backtest1 كان يُتجاهل بصمت لأن `trailing_stop_percent` الميت بسقف 10
> هو الوحيد الموجود في المخطط).
> **بعد هذه الجولة: نعم** — متوفران داخل backtest1/run نفسها عبر كتلة `exit_strategy`،
> وكل التشغيل موحّد في المسار الواحد.

---

## ما الذي تتغيّر (ثلاثة ملفات معدّلة + ملف جديد)

| الملف | التغيير |
|---|---|
| `app/services/exit_engine.py` | ترقية ج41 (التريلينق الحرفي) مدموجة فوق نسخة السيرفر الأحدث — **بلا حذف أي ميزة**: المرشحات (trend_filter/min_floor) والـpresets والجني المتحرك المشروط كلها باقية، والتريلينق الحرفي له الأولوية عند تفعيله |
| `app/backtest/schemas.py` | `ExitStrategyBlock` جديدة + حقل اختياري `exit_strategy` في `BacktestConfig` مع تحقق فوري (422 في نفس الطلب) |
| `app/routers/backtest1.py` | فرع المنفذ الموحّد في `/run` + `_run_unified_exit_task` (نفس دورة الحياة، نفس التخزين في BacktestRun) |
| `app/services/unified_backtest.py` | **جديد** — طبقة العرض النقية: تحقق مشترك واحد + بناء summary/chart_data بنفس عقد المحرك الرئيسي |

**ما لا يتغيّر إطلاقاً:** أي حمولة تعمل اليوم (بلا `exit_strategy`) = نفس السلوك بت-بت
(مثبت ببطارية 29 فحصاً عبر 5 توليفات). نقاط `/exit-strategy/*` كلها باقية كما هي
(توافق خلفي — لم يعد الفرونت بحاجتها لكنها لا تُحذف).

---

## خطوات التثبيت (دقيقتان)

```bash
# 1) نسخة احتياطية (سلامة أولاً)
cp app/services/exit_engine.py   app/services/exit_engine.py.bak-r41
cp app/backtest/schemas.py       app/backtest/schemas.py.bak-r41
cp app/routers/backtest1.py      app/routers/backtest1.py.bak-r41

# 2) تركيب الملفات الأربعة (من جذر الحزمة)
cp app/services/exit_engine.py      /مسار-المشروع/app/services/exit_engine.py
cp app/services/unified_backtest.py /مسار-المشروع/app/services/unified_backtest.py
cp app/backtest/schemas.py          /مسار-المشروع/app/backtest/schemas.py
cp app/routers/backtest1.py         /مسار-المشروع/app/routers/backtest1.py

# 3) فحص الترجمة (يجب أن يطبع OK بلا أي خطأ)
python3 -m py_compile app/services/exit_engine.py \
                      app/services/unified_backtest.py \
                      app/backtest/schemas.py \
                      app/routers/backtest1.py && echo "COMPILE OK"

# 4) إعادة تشغيل الخدمة (uvicorn / docker / pm2 — حسب طريقتك)

# 5) بطارية القبول (29 فحصاً — من جذر المشروع)
python3 test_battery_r42.py
# المتوقع: النتيجة: 29/29 — كل الفحوص نجحت ✅
```

## التحقق الحي (30 ثانية)

```bash
# التشغيل الموحّد: تريلينق 20٪ من القمة — من داخل backtest1/run نفسها
curl -X POST "http://SERVER:8000/api/v1/backtest1/run" -H "Content-Type: application/json" -d '{
  "symbols": ["BTCUSDT"], "timeframe": "1h", "days": 30,
  "strategy_config": {"name": "zzfib"},
  "exit_strategy": {
    "strategy": "zzfib",
    "config": {"use_trailing": true, "trailing_giveback_pct": 20.0}
  }
}'
# ← {"success": true, "mode": "unified-exit", "task_id": "...", "status": "PROCESSING"}

# ثم نفس دورة الفرونت المعتادة تماماً:
curl "http://SERVER:8000/api/v1/backtest1/status/TASK_ID"    # → SUCCESS + backtest_id
curl "http://SERVER:8000/api/v1/backtest1/get/BACKTEST_ID"   # → summary + chart_data
```

في `/get` ستجد (بالإضافة لكل الحقول القياسية):
- `summary.architecture_mode` = `"Unified-Exit-Engine-R42"`
- `summary.exit_strategy` — **التشكيل الفعّال لاستراتيجية الخروج** (لتمثيلها على الشاشة):
  تريلينق مفعّل/معطّل، giveback، ما أُلغي نطقاً، DCA، الوصف العربي الكامل
- `summary.exit_reasons` — `{take_profit, fib_break, trailing_stop, end_of_data}`
- `summary.exit_trades` — الصفقات بتفاصيلها الكاملة (peak_price لكل خروج تريلينق)
- `chart_data.trade_points` — نفس شكل المحرك الرئيسي + `peak_price` + نقاط dca
- `chart_data.trail_lines` — **خط السقف المتحرك لكل صفقة** (لت رسمه على الشارت)

## الاسترجاع (Rollback)

```bash
cp rollback/app/services/exit_engine.py   app/services/
cp rollback/app/backtest/schemas.py       app/backtest/
cp rollback/app/routers/backtest1.py      app/routers/
rm app/services/unified_backtest.py   # الملف الجديد (اختياري — لا يستورده أحد عند الغياب)
# ثم أعد التشغيل — عودة كاملة لحالة ما قبل ج42
```

---

## عقد الحمولة الجديد (للفرونت)

**كل شيء من المسار الواحد** — لا مسار موازٍ إطلاقاً:

```
POST /api/v1/backtest1/run
{
  ... نفس حمولة اليوم حرفياً ...,
  "exit_strategy": {                      ← اختياري بالكامل (غيابه = سلوك اليوم بت-بت)
    "strategy": "zzfib",                  ← أو zzfib_e2e | zzfib_e2e_trendy
                                           (أو احذفه — يُشتق من strategy_config.name)
    "strategy_params": {"length": 100},   ← اختياري (فوق افتراضات البطل)
    "config": {                           ← اختياري — عقد ج41 كاملاً:
      "use_trailing": true,               ←   التريلينق الحرفي
      "trailing_giveback_pct": 20.0,      ←   20٪ من القمة (0.1–90)
      "take_profit_pct": 5.0,             ←   يُلغى تلقائياً مع التريلينق
      "tp_reference": "first",            ←   first | avg
      "dca1_trigger_pct": 3.0,            ←   التعزيزات (تعمل مع التريلينق)
      "dca2_trigger_pct": 5.0,
      "max_entries": 3,
      "position_size_usd": 100.0,
      "entry_exec": "signal_close",       ←   أو next_open
      "cooldown_bars": 0,
      "allow_overlap": false,
      "fees_pct": 0.0
    }
  }
}
```

**قواعد 422 (فورية، في نفس الطلب):**
- حقل غير معروف داخل `exit_strategy.config` → 422 بالاسم
- `use_trailing` ليس true/false → 422
- `trailing_giveback_pct` خارج [0.1..90] → 422
- استراتيجية غير مدعومة / معامل غير مسموح → 422

**قاعدة الأولوية الموثقة:** عند `use_trailing: true` تُلغى نطقاً كل آليات الخروج
الأخرى (TP الثابت، وقف الفيبو، الجني المتحرك المشروط tp_trail_*) — التريلينق
الحرفي وحده من يعمل: القمة تبدأ من سعر تنفيذ الدخول، كل قمة شمعة أعلى ترفع
السقف، وإغلاق شمعة هبط 20٪ من أعلى قمة يغلق الصفقة كاملة عند سعر ذلك الإغلاق.
التعزيزات (DCA) تبقى تعمل (لم تُطلب إلغاؤها).

---

## تحقق مستقل (بصمات)

راجع `MD5SUMS.txt` — بصمات الملفات الأربعة + rollback. بعد التركيب:

```bash
md5sum app/services/exit_engine.py app/services/unified_backtest.py \
       app/backtest/schemas.py app/routers/backtest1.py
```

## ماذا يبقى للفرونت (وكيل الفرونت-إند)

1. **احذف** المحرك المحلي للتريلينق (TS) والقاعدة الوهمية (rsi<0 + exit_type)
   وحقول `tp_trail_arm_pct/tp_trail_giveback_pct` من كل الحمولات — لم تعد لازمة.
2. **أضف** كتلة `exit_strategy` إلى زر Run Backtest (حمولة backtest1/run نفسها).
3. **اقرأ** `summary.exit_strategy` لعرض التشكيل الفعّال، و`chart_data.trail_lines`
   لرسم خط السقف المتحرك، و`exit_reason == "trailing_stop"` لتلوين الخروج.
4. استقصاء `/status` ثم `/get` كما هو — **لا شيء آخر يتغير**.
