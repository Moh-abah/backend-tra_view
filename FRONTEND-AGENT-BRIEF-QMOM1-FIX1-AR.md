# FRONTEND-AGENT BRIEF — QMOM1-FIX1 (R77)
## تحديث عقد النتائج: بطاقات بوابة الزخم الحقيقية + أعمدة الشفافية — التقرير الآن يصف كل شيء
**التاريخ:** 2026-11-18 · **يتطلب:** دمج QMOM1-FIX1 (انظر `INSTALL-QMOM1-FIX1-AR.md`) · **المستلم:** وكيل الفرونت-اند · **المُرسل:** السديم

---

## 0) ماذا تغيّر عنك (خلاصة سطرين)

قبل FIX1: أعمدة الموشرات كانت ترجع كلها `null` والبوابة لم تمنع شيئاً والتقرير لم
يذكرها. بعده: **القيم حقيقية، البوابة تعمل (46⇒11 على نافذة الاختبار)، والتقرير
يحمل قسم `momentum_gate` كاملاً** — ابنِ بطاقات بوابة الزخم من `summary.math_audit.momentum_gate`.

## 1) الحقل الجديد في نتيجة `/get` — `summary.math_audit.momentum_gate`

```jsonc
// GET /api/v1/backtest1/get/{backtest_id}
"summary": { ..., "math_audit": {
  ...,
  "momentum_gate": {            // موجود فقط عندما تحمل الاستراتيجية محرك الزخم
                                 // (zigzag_fib_e2e_trendy_quantum_ema_mom).
                                 // الاستراتيجيات الأخرى: المفتاح = null بت-بت.
    "engine": "…mtf-osc-core…", "version": "…",
    "base_tf": "15m",            // فريم القاعدة الحقيقي الذي حُسبت عليه الموشرات
    "time_source": "datetime_index",  // ✨ جديد R77: مصدر الأزمنة (عمود زمن/فهرس زمني/قائمة)
    "n": 36369, "input_rows": 36369,  // ✨ أشرطة القاعدة الفعلية / صفوف الدخل
    "counts": {
      "quantum_ema_entries": 46,     // خام الكمومية-EMA (قبل بوابة الزخم)
      "final_entries": 11,            // النهائي بعد البوابة — يجب أن يطابق عدد الصفقات
      "osc_blocked_entries": 35       // الممنوع بالزخم — «ماذا قتلت البوابة»
    },
    "warmup_neutral_bars": 2928,      // حياد الإحماء (البوابة مفتوحة قبله)
    "warning_codes": ["warmup_neutral"],  // warmup_neutral معلومة؛ غيره تحذير خلل حقيقي
    "warnings": ["…نص عربي…"], "warnings_v2": [{"code","message","instance"}],
    "instances": [                    // حالة كل نسخة موشر (7 لكموميه الزخم الاولى)
      {"id": "macd_4h_12_26_4", "kind": "macd", "timeframe": "4h",
       "params": {...}, "enabled": true,
       "available": true, "code": null, "why": null},
      // عند مشكلة: available=false + code ∈ {insufficient_data, zero_coverage,
      //   unknown_timeframe, tf_below_base, disabled} + why نصي
    ],
    "conditions": {…شجرة الشروط كما أُرسلت…},
    "gate_open": false, "status": "ok" | "degraded", "mode": "full"
  }
}}
```

**بطاقات بوابة الزخم (BRIEF الأصلي §3ب — الآن حقيقية تماماً):**
- الثلاثية الأساسية: `counts.quantum_ema_entries` / `counts.final_entries` /
  `counts.osc_blocked_entries` — مع توصية العرض: «منعت البوابة 35 دخولاً — مواضعها
  مرئية بأعمدة iblocked».
- `warmup_neutral_bars` + `warning_codes/warnings_v2` + `instances[]` (بطاقة
  صغيرة لكل نسخة: معرف/نوع/فريم/معاملات/متاحة/سبب الغياب).
- **جديد:** `time_source` و`base_tf` و`n` — شفافية كاملة لمصدر الحساب.

## 2) أعمدة الشموع البصرية — الآن بقيم حقيقية (لا null)

نفس أسماء الأعمدة في `chart_data.visual_candles[].indicators`:
- **القديم كله كما كان** (بت-بت): `ind_zzfetqem_*` (زقزاق/فيبو/ترند/منطقة/رصة
  EMA/خروج) + التمرير `ind_zzfetq_*`/`ind_zzfet_*`.
- **الجديد (R77 جعله حقيقياً):**
  - `ind_zzfetqem_osc_macd_{4h_12_26_4,3d_5_11_4,1d_12_26_4}_{line,signal,hist}`
  - `ind_zzfetqem_osc_rsi_{1h_14_14,4h_14_14,1d_14_14,1d_10_14}_{value,ma,bb_upper,bb_lower}`
  - `ind_zzfetqem_osc_gate` (1.0 حيث البوابة مفتوحة · null حيث مغلقة)
  - `ind_zzfetqem_entry_iblocked{,_s1,_s2,_s3}` (1.0 = دخول كمومي **منعته** بوابة الزخم)
  - `ind_zzfetqem_entry_s{1,2,3}` — **انتبه: صارت قيم ما-بعد-البوابة** (null حيث
    منع الزخم). خام القاعدة قبل البوابات في `entry_raw_s{1,2,3}` كما كان.

**رسم الشارت:** ظلّل الشموع ذات `iblocked*`=1 (أحمر شفاف — «ماذا قتلت البوابة»)
+ خط `osc_gate` كخلفية + لوحة MACD/RSI الجانبية من أعمدة `osc_*` (MACD حول صفر،
RSI حول 50) — تجعل الشروط الأربعة مرئية بعين المستخدم.

## 3) أهم حقائق يجب أن تعرفها الواجهة

1. `momentum_gate.counts.final_entries` **يجب أن يطابق `summary.total_trades`**
   (كل إشارة دخول تتحول لقرار) — إن اختلف الرقمان فاعرضه كتحذير (شفافية الأمانة).
2. `null` في `momentum_gate` = الاستراتيجية ليست كموميه الزخم الاولى (لا تعرض
   البطاقات). `warning_codes` فارغ أو `[warmup_neutral]` = كل شيء سليم؛ أي كود
   آخر = اعرض التحذير بـ`warnings_v2` (فيه النص العربي الجاهز).
3. أعمدة `osc_*` الأولى بعد `warmup_neutral_bars` تكون null (إحماء) — طبيعي
   تماماً، لا تعتبره خطأ.
4. `osc_instances/osc_conditions` (المحرر الحي في BRIEF الأصلي §1) لم يتغير عقد
   إرسالها شيئاً — نفس الحمولة تعمل الآن فعلياً على السيرفر بعد FIX1.
