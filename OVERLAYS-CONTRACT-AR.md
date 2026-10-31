# 📐 عقد الاستجابة — مؤشرات البنية (Overlays) — للوكيل الأمامي
**الجولة 10 — الباكند يحسب، أنت ترسم فقط. كل الأزمنة ملي ثانية (ms). استخدم `time` لا `bar` في الرسم.**

---

## 1) مصدر البيانات

| الحالة | النداء |
|---|---|
| شارت حي | `GET /api/v1/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=30&limit=1000&types=zigzag,fib,trendline` |
| باك-تست | `GET /api/v1/backtest/{id}/chart-data?overlays=zigzag,fib,trendline` (نفس نداءكم الحالي + معامل واحد) |
| شموع عندكم جاهزة | `POST /api/v1/overlays/compute` `{"candles":[...], "types":[...]}` |

الاستجابة المشتركة:
```json
{
  "summary": {"bars": 1000, "types": ["zigzag","fib","trendline"], "compute_ms": 19.1, "cache": "built|hit|bypass"},
  "time_from": 1789862400000, "time_to": 1793458800000,
  "overlays": { "zigzag": {...}, "fib": {...}, "trendline": {...} }
}
```

---

## 2) zigzag — Zig Zag Channels [LuxAlgo]

```jsonc
{
  "pivots": [                       // علامات دائرية + ملصقات
    {"bar": 76, "time": 1790136000000, "price": 87278.54, "kind": "top|bottom",
     "confirmed_at_bar": 176, "confirmed_at_time": ...,   // شمعة التأكيد الفعلية
     "label": {"text": "87278.54", "side": "down|up", "color": "#ff1100"}}
  ],
  "segments": [                     // الخطوط البرتقالية (#ff5d00)
    {"x1":76,"t1":...,"y1":87278.54, "x2":201,"t2":...,"y2":82597.55,
     "kind": "top|bottom", "color": "#ff5d00",
     "ext_up": 1715.61,             // خط منقّط أحمر موازٍ فوقه بهذا القدر (بالدولار)
     "ext_dn": 2957.59,             // خط منقّط أزرق موازٍ تحته
     "ext_color_up": "#ff1100", "ext_color_dn": "#2157f3", "ext_style": "dotted",
     // قد تكون null إذا كان المقطع أقصر من 2 شمعة — ارسم الخط الرئيسي فقط}
  ],
  "projection": {                   // المقطع الممتد لآخر شمعة (قد يكون null)
    {"x1":...,"t1":...,"y1":..., "x2":...,"t2":...,"y2":آخر_إغلاق,
     "kind":"projection", "extend":"right", "ext_up":..., "ext_dn":...}
  },
  "series": {"zz_state":[...], "zz_pivot_high":[...], "zz_pivot_low":[...]}  // لكل شمعة (null=لا قيمة)
}
```
**الرسم**: خط مستقيم لكل segment؛ خطان منقّطان `y1+ext_up → y2+ext_up` و `y1-ext_dn → y2-ext_dn`؛ دائرة عند كل pivot (top فوق الشمعة أحمر، bottom تحتها أزرق) + نص الملصق. `ext_up/ext_dn = null` → تجاهل الخط المنقّط.

---

## 3) fib — Auto Fib Retracement

```jsonc
{
  "legs": [ /* تاريخ الرجال — ارسم فقط visible=true (Pine يحذف الباقية) */ ],
  "current": {
    "leg": {"x1":760,"t1":...,"y1":84898.0, "x2":978,"t2":...,"y2":76325.98, "kind":"high|low", "style":"dashed","color":"#808080"},
    "levels": [
      {"ratio":0.0,   "value":84898.0, "color":"#808080", "x_from":760,"t_from":..., "x_to":978,"t_to":..., "extend_right":true,"extend_left":false},
      {"ratio":0.236, "value":82875.0, "color":"#a61c00", ...},
      {"ratio":0.382, "value":81623.5, "color":"#95cc28", ...},
      {"ratio":0.5,   "value":80612.0, "color":"#28cc28", ...},
      {"ratio":0.618, "value":79600.5, "color":"#28cc95", ...},
      {"ratio":0.786, "value":78160.4, "color":"#2895cc", ...},
      {"ratio":1.0,   "value":76326.0, "color":"#808080", ...}
      // + 1.272/1.414/1.618 عند تفعيلها (2.618+ معطلة افتراضياً — كما في السكربت)
    ],
    "target": {"ratio":0.618, "value":79600.49},
    "p1": 84898.0, "p2": 76325.98
  },
  "signals": [                      // علامات Buy/Sell Retrace
    {"bar":920,"time":...,"side":"sell","signal":"Sell Retrace","price":81389.45,"ratio":0.618,"color":"#ff0000"}
  ],
  "series": {"fib_start":[...], "fib_end":[...], "fib_target":[...]}   // الخطوط الحمراء/الخضراء/البنفسجية للسكربت
}
```
**الرسم**: خط أفق عند `value` من `t_from` إلى `t_to` ثم امتداد يميناً حتى حافة الشارت (`extend_right`)؛ ملصق عند `t_from`: نسبة+قيمة مثل `0.618 (79600.49)`؛ خط رجل متقطع رمادي من (t1,y1) إلى (t2,y2)؛ `signals[]` ملصق تحت/فوق الشمعة أخضر "Buy Retrace" / أحمر "Sell Retrace".

---

## 4) trendline — Auto Trendline [DojiEmoji]

```jsonc
{
  "fractals": {
    "up":   [{"bar":932,"time":...,"price":81788.56,"side":"up","label":"HH|LH|null"}],
    "down": [{"bar":952,"time":...,"price":...,"side":"down","label":"HL|LL|null"}]
  },
  "lines": {                        // الجديدة أولاً
    "up":   [{"x1":...,"t1":...,"y1":..., "x2":...,"t2":...,"y2":..., "style":"recent|historical",
              "color":"#800080|#808080", "dashed":true, "extend":"right|both", "visible":true}],
    "down": [...]
  },
  "projection": {
    "upper": {"x1":...,"t1":...,"y1":..., "x2":...,"t2":...,"y2":..., "slope":9.12, "y_last":82399.73, "extend":"right"},
    "lower": {...}
  },
  "crosses": [                      // علامات X عند عبور الإغلاق للخط
    {"bar":...,"time":...,"type":"upper|lower","direction":"over|under","close":...,"line_price":...,"color":"#6495ed"}
  ],
  "series": {"tl_upper":[...], "tl_lower":[...], "tl_cross_upper":[...], "tl_cross_lower":[...]}
}
```
**الرسم**: خطوط `lines` المتقطعة (`visible=true` فقط — `max_pairs=1` يعني خطاً واحداً حياً لكل جهة كما في السكربت)؛ امتداد الـ`projection` يميناً من `t2/y2` بميل `slope` (أو ارسم من t1 إلى حافة الشارت بخط مستقيم عبر النقطتين)؛ دوائر صغيرة للفراكتالات عند `time/price` بألوان: HL أزرق #0000ff، LH أحمر #ff0000، HH/LL رمادي؛ `crosses[]` علامات X.

---

## 5) قواعد عامة

1. **`null` في أي حقل = لا يُرسم** (مطابق لسلوك na في Pine).
2. **`visible=false` = تجاهل** (Pine حذفه).
3. أول رجل فيب قد تحمل `"synthetic_anchor": true` — تجاهلها دائماً.
4. المعاملات القابلة للتمرير في النداء: `zz_length`, `zz_extend`, `fib_depth`, `fib_dev`, `fib_ret`, `fib_levels`, `tl_period`, `tl_pairs` — اعرضوها في إعدادات المؤشر.
5. الكاش: `summary.cache` — `built` أول مرة و`hit` خلال 30ث (للمشارت الحي) — لا تقلقوا من التكرار السريع.
6. هذه الحقول الثلاثة تُقرأ أيضاً كأعمدة لكل شمعة (`series`) — ستستخدمها الاستراتيجية القادمة في الباكند، لا تحتاجون منها شيئاً في الرسم.

## 6) مثال جاهز (lightweight-charts — خط مقطع)
```js
segmentLines(chart, seg) {
  // الخط الرئيسي
  series.setData([{time: seg.t1/1000, value: seg.y1}, {time: seg.t2/1000, value: seg.y2}]);
  if (seg.ext_up != null) // منقّط علوي
    extUp.setData([{time: seg.t1/1000, value: seg.y1+seg.ext_up}, {time: seg.t2/1000, value: seg.y2+seg.ext_up}]);
  if (seg.ext_dn != null) // منقّط سفلي
    extDn.setData([{time: seg.t1/1000, value: seg.y1-seg.ext_dn}, {time: seg.t2/1000, value: seg.y2-seg.ext_dn}]);
}
```
