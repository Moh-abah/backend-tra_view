# حزمة MTF EMA — المتوسط المتحرك الأسي متعدد الفريمات (+ إثبات فريمات الكمومية)

## ما هذه الحزمة؟

**أ) مؤشر جديد كلياً `mtf_ema`** — نقل Pine v5 الذي أرسله صاحب القرار:

```pine
//@version=5
indicator("Multi Time Frame Exponential Moving Average", shorttitle="MTF EMA", overlay=true)
ma_len = input.int(title="Length", defval=100)
src = input.source(title="Source", defval=close)
ma_offset = input.int(title="Offset", defval=0)
res = input.resolution(title="Resolution", defval="60")
htf_ma = ta.ema(src, ma_len)
out = request.security(syminfo.tickerid, res, htf_ma)
plot(out, color=color.red, offset=ma_offset)
```

بناء كامل قابل للتخصيص من الواجهة (من دون أي شرط عليه الآن — رسم فقط،
كما طُلب)، مع سببية صارمة (بلا أي استشراف) ونسخ متعددة جاهزة للمرحلة
القادمة («الترندية الكمومية المتحركة»).

**ب) إجابات مثبتة بالتجربة الحية عن فريمات الكمومية** — انظر
`REPORT-MTFEMA-AR.md` القسم 1 و2.

---

## 1) التثبيت (دمج إضافي صافي — صفر سطور محذوفة)

انسخ الملفات من `app/` فوق شجرة الباك اند الحية:

| الملف | الحالة |
|---|---|
| `app/services/indicators/overlays_mtf_ema.py` | **جديد كلياً** — المحرك (556 سطراً) |
| `app/services/indicators/overlay_columns.py` | +إضافة تسجيل (أسماء/معاملات/أعمدة) |
| `app/services/indicators/overlays.py` | +إضافة تسجيل (نوع + توزيع + مفاتيح معاملات) |
| `app/services/indicators/__init__.py` | +سطر استيراد واحد (تسجيل ذاتي) |
| `app/services/indicators/calculator.py` | +جسر الحاسبة (الأسماء/العمود الأساسي/الأعمدة الفرعية/المعاملات) |

الاعتماديات: موجودة أصلاً على الخادم منشورة (لا تُشحن في الحزمة):
`zigzag_fib_core.py` (norm_candles) · `mtf_oscillator_core.py`
(resample_ohlcv + EMA ببذرة SMA + المراسي — نواة PRO73).

## 2) التحقق بعد التثبيت

```bash
cd tools
python3 verify_mtfema.py                 # الأساسية: الكمومية + EMA100@60m
python3 verify_mtfema.py --multi        # 3 نسخ (fast/slow/day)
```

المتحقَّق منه: مقاييس الكمومية بت-بت كما كانت (+69.338535% · 31 · PF
1.978684961471487 — MTF EMA لم يمس قراراً واحداً) + عمود `ind_mtfema_value`
في كل شمعة + **القيم مطابقة بت-بت لمرجع مستقل يُحسب من شموع الرد نفسها**.

## 3) عقد الفرونت (الرسم)

في شموع الباك-تست (`chart_data.visual_candles[].ind_mtfema_*`):

| العمود | المعنى |
|---|---|
| `ind_mtfema_value` | خط النسخة الأساسية — **عمود الرسم الافتراضي** |
| `ind_mtfema_main` | النسخة الضمنية (نفس قيمة value بت-بت في الحالة البسيطة) |
| `ind_mtfema_<id>` | خط كل نسخة عند التعدد (ديناميكي حسب المعرفات) |

- القيمة `null` = فترة الإحماء (أول `length` شريط HTF) — طبيعي ومقصود.
- القيمة خط سعري متدرّج (يتغير عند إغلاق كل شريط HTF) — يُرسم كخط أحمر
  على الشارت (نمط Pine: `plot(out, color=color.red)`).

## 4) التخصيص من الواجهة (strategy_config.indicators[].params)

```json
{
  "name": "mtf_ema",
  "type": "trend",
  "params": {
    "length": 100,          // Length (Pine ma_len) — طول EMA على الفريم الأعلى
    "source": "close",      // Source — close/open/high/low/hl2/hlc3/ohlc4
    "offset": 0,            // Offset (إزاحة رسم يميناً بالشموع — موجبة فقط)
    "resolution": "60"      // Resolution — صيغة Pine (انظر الجدول)
  },
  "enabled": true
}
```

**صيغ resolution المقبولة** (Pine بحذافيرها + صيغ النظام + خطوات مخصصة):

| صيغة | المعنى | صيغة | المعنى |
|---|---|---|---|
| `"60"` | 60 دقيقة (الافتراضي) | `"240"` | 4 ساعات |
| `"1"`/`"5"`/`"15"`/`"30"` | دقائق | `"120"`/`"480"`/`"720"` | 2h/8h/12h |
| `"1S"`/`"5S"`/`"30S"` | ثوانٍ | `"D"`/`"1D"`/`"2D"`/`"3D"`/`"5D"` | أيام |
| `"W"`/`"1W"`/`"2W"` | أسابيع | `"M"`/`"1M"`/`"3M"`/`"12M"` | أشهر تقويمية |
| `"1m"`..`"4h"`, `"1d"`, `"1w"`, `"1M"` | صيغ النظام | `"6h"`, `"10m"`, `"20"` | أي خطوة مخصصة |

ملاحظة حالة الأحرف (مطابقة Pine): `"1M"` شهر ≠ `"1m"` دقيقة.

**النسخ المتعددة (للمرحلة القادمة — جاهزة الآن):**

```json
"params": {"instances": [
  {"id": "fast", "length": 21,  "resolution": "60"},
  {"id": "slow", "length": 100, "resolution": "240"},
  {"id": "day",  "length": 50,  "resolution": "D", "source": "hlc3"}
]}
```
أي عدد نسخ، لكل نسخة معاملاتها الكاملة → أعمدة `ind_mtfema_fast/slow/day...`
(نفس نمط `osc_instances` في PRO73 — بوابات «الترندية الكمومية المتحركة»
القادمة ستُبنى فوقها مباشرة).

## 5) الشروط (لاحقاً — جاهزة الآن بلا أي تغيير إضافي)

صيغة المرجع في entry/exit rules كما تعملها الواجهة:
```
indicator:mtf_ema:mtfema_value        → ind_mtfema_value
indicator:mtf_ema:mtfema_fast         → ind_mtfema_fast
indicator:mtf_ema:mtfema_a            → ind_mtfema_a
```
(جسر الحاسبة + محلل الشروط يتعرفان عليها الآن — إضافة شروط لاحقاً
= بناء القاعدة في الواجهة فقط، صفر كود خلفي.)

## 6) الضمانات التعاقدية

- **السببية الصارمة**: قيمة الفريم الأعلى عند شمعة القاعدة = EMA آخر
  شريط HTF **مغلق** فقط (الشريط النامي لا يُرى إطلاقاً — نفس عقد نواة
  الموشرات PRO73). ملاحظة: رسم TradingView التاريخي يعرض قيمة الشريط
  عند إغلاقه على شموع الفترة كلها (تطلّع مستقبلي في الباك-تست) — نحن
  نرجع القيمة المؤكدة فقط: ما يراه المتداول الحي.
- **EMA بنمط TradingView**: بذرة SMA(length) ثم تصفية أسّية — نفس رياضيات
  `ta.ema`.
- **offset موجب فقط**: إزاحة رسم يميناً (بصرية — سببية سليمة). السالب
  يُصفَّر مع تحذير (تطلّع مستقبلي ممنوع بعقد النظام).
- **فريم أدنى من فريم الشموع**: قيم None + تقرير `why=tf_below_base`
  في instances — لا انهيار أبداً.
- **صفر تداخل**: أسماء `mtf_ema`/`mtfema_*`/`ind_mtfema_*` جديدة كلياً —
  لا تمس أي محرك قائم بت-بت (مثبت: مقاييس الكمومية المرجعية لا تتغير).

## 7) الفحوص المنجزة قبل التسليم (محلياً)

- **اختبار وحدة**: المحرك ضد مرجع مستقل بت-بت (15,313 شمعة 15m) —
  32 حالة تطبيع فريم + EMA100@60m/EMA21/EMA50@240m/EMA100@1D/offset +
  4 نسخ متعددة + فريم أدنى + offset سالب + أشهر تقويمية → **كلها ✓**
- **اختبار تكامل المسار الإنتاجي الكامل** (config_to_overlay_params →
  compute_overlays → columns_for_configs): الأعمدة تخرج بالطول الموحد
  وبالقيم المرجعية بت-بت، وتكوين مشترك (كمومية + mtf_ema) يتعايش
  (111 عموداً: 62 كمومية + 47 تمرير ترندي + 2 MTF EMA).
- **اختبار جسر الحاسبة**: `mtf_ema` بالاسم البسيط وبالنسخ المتعددة ✓.
- **اختبار فريمات الكمومية الحي** (ثلاث مهام على الخادم — انظر التقرير):
  5m كامل · 5m بنطاق مخصص length=50 · 1m شهر.

## 8) الملفات في الحزمة

```
app/services/indicators/overlays_mtf_ema.py        (جديد كلياً)
app/services/indicators/overlay_columns.py         (+تسجيل)
app/services/indicators/overlays.py                (+تسجيل)
app/services/indicators/__init__.py                (+استيراد)
app/services/indicators/calculator.py              (+جسر)
payloads/mtfema_verify_payload.json               (حمولة التحقق الأساسية)
payloads/mtfema_multi_payload.json                (حمولة 3 نسخ — إثبات جاهزية)
tools/verify_mtfema.py                            (التحقق الحي بعد النشر)
diffs/                                             (فروق موحدة — +116/-0 صافي)
README-MTFEMA-AR.md                                (هذا الملف)
REPORT-MTFEMA-AR.md                                (الإجابات والأدلة)
FILES-MTFEMA.md5                                   (بصمات md5)
```
