# حزمة الدمج EMAGATE-UNIFIED — بوابة رصة EMA الموحدة المركزية (الشروط السبعة) + قالب كموميه الزخم الاولى

**التاريخ**: 2026-11-19 · **الأساس**: آخر إصدار للمشروع بعد كل عمليات الإضافة والدمج
(`backend_PRO102.zip` — من رابط جوجل درايف المرسل من صاحب القرار — يشمل حتى QMOM1-FIX2) · **المُرسل**: السديم

**أوامر صاحب القرار (الحرفية):**
1. «باقي ملاحضه بسيطه وهي ان القوالب لا تحتوي على الاستراتيجيه الجديده» — القوالب الرسمية
   لم تكن تحمل قالب «كموميه الزخم الاولى» (QMOM1).
2. «ايضا لدينا اضافه على كل اجزاء النضام التي تحتوي على بوابه المتوسطات ال ema ونريد
   منك تطبيق التعديل على اي مكان فيه البوابه واي استراتيجه فيها البوابه عشان يكون
   العمل موحد ومركزي ومنظم» — توحيد بوابة EMA في كل مكان توجد فيه.
3. شرح الشروط السبعة لمتوسطات EMA (حرفياً — انظر §1).
4. (2026-11-19) «اجعله ع الديفولت 100 (لا 226)» + «اذكر ema_lengths كاملة مع الجديدة» —
   قالب QMOM1 ولوحة إعدادات المحرك على **الديفولت length=100 + الرصة الستة الكاملة
   [21,50,100,200,350,500] مع EMA21 الجديدة**.

---

## 1) عقد الشروط السبعة (المصدر الوحيد للحقيقة — نص صاحب القرار)

متوسطات EMA إيجابية تعبر عن اتجاه صعودي وتسمح بالشراء عند ترتبها تحت السعر تصاعدياً
(الأصغر أولاً ثم الأكبر تحته — مثل EMA8 أعلاهم ثم 13 ثم 21 ثم 35 ثم 50 وهكذا):

1. **السعر يأتي أولاً فوق متوسطات EMA** (كلها).
2. تحت السعر يأتي **EMA 21 فوق EMA 50** ولا يوجد أي متوسط أكبر منهما فوقهما —
   **إلا متوسط أصغر من EMA 21 فيجوز أن يعلو فوق EMA 21**.
3. **EMA 50 (إن وجد) فوق EMA 100 (إن وجد)** — ولا أكبر منهما فوقهما.
4. **EMA 100 (إن وجد) فوق EMA 200 (إن وجد)** — ولا أكبر منهما فوقهما.
5. **EMA 200 (إن وجد) فوق EMA 350 (إن وجد)** — ولا أكبر منهما فوقهما.
6. **EMA 350 (إن وجد) فوق EMA 500 (إن وجد)** — ولا أكبر منهما فوقهما.
7. **EMA 500 (إن وجد) فوق أي متوسط أكبر منه** (إن وُجد — يعمَّم للأي كبير).

**الصياغة التنفيذية الموحدة** (تغطي السبعة لأي مجموعة أطوال):
`ok = جاهزية ∧ (السعر > كل المتوسطات) ∧ (ترتيب السلّم كاملاً: كل زوج أطوال a < b ⇒ EMA_a > EMA_b)`
حيث **السلّم** = الأطوال ≥ `ema_stack_base` (الافتراضي 21 — حدّ الإعفاء بنص الشرط 2)
و**السريعة** = الأصغر من القاعدة (مثل 8/13) — معفاة من الترتيب، يشترط لها الشرط 1 فقط.
جمل «لا يوجد أكبر فوقهم» محقَّقة بالبناء عند اكتمال ترتيب السلّم (برهان التسلسل في
رأس الملف).

## 2) ما الذي في الحزمة (بالمسارات)

```
merge_package/
├── app/services/indicators/
│   ├── ema_stack_gate.py                          ← ⭐ جديد كلياً: النواة المركزية الموحدة
│   │   (compute_ema_stack_gate + norm_ema_stack_mode/base — الوضعان
│   │   hierarchical/strict + التشخيص السبعمعة price_ok/ladder_ok/pairs)
│   ├── overlays_zlf_e2e_trendy_quantum_ema.py      ← تعديل: المحرك يستدعي النواة المركزية
│   │   حصراً (بديل الحساب المضمّن) + المعاملان الجديدان + 7 أعمدة تشخيص +
│   │   meta شامل (mode/base/ladder/fast/pairs/rule_ar) + get_default_params
│   ├── overlays_zlf_e2e_trendy_quantum_ema_mom.py  ← تعديل: تمرير المعاملين للمحرك الأساس
│   │   (بوابة واحدة مركزية — لا مسار جانبي) + get_default_params
│   ├── overlays.py                                ← إضافات فقط: المفتاحان في قائمتَي
│   │   السماح (الكمومية-EMA + QMOM1)
│   └── overlay_columns.py                          ← إضافات فقط: تمرير المعاملين في
│       فرعي config_to_overlay_params + عمودا التشخيص في القائمة المعلنة
├── app/services/strategy/presets.py                ← إضافات فقط: قالب «كموميه الزخم
│   الاولى» QMOM1_TRIPLE_SIGNAL كاملاً (13 قالباً) + ملاحظة العقد السبعة +
│   الرصة الهرمية صريحة في قوالب الكمومية-EMA/الجبارة/QMOM1
├── strategies/qmom1_كموميه_الزخم_الاولى.json        ← إضافات فقط: المفتاحان صريحان +
│   الديفولت 100 + الرصة الستة الكاملة مع EMA21
├── strategies/zlf_almighty_quantum_ema_sol15m.json  ← إضافات فقط: المفتاحان صريحان
├── tools/verify_emagate_unified.py                 ← بطارية التحقق (31 فحصاً)
├── tools/reference_basis_outputs.json              ← المرجع الملتقط من الشيفرة الأصلية
│   (قبل التعديل — للتحقق بت-بت بعد التثبيت)
├── diffs/                                          ← فروقات موحدة ضد الأساس PRO102
├── FILES-EMAGATE-UNIFIED.md5                       ← بصمات كل ملف
└── INSTALL-EMAGATE-UNIFIED-AR.md                   ← هذا الملف
```

**أين البوابة قبل وبعد (خريطة «موحد ومركزي ومنظم»):**

| المكان | قبل | بعد |
|---|---|---|
| حساب الرصة | مضمّن داخل `overlays_zlf_e2e_trendy_quantum_ema.py` (سلسلة بترتيب التمرير) | **نواة واحدة** `ema_stack_gate.py` يستدعيها المحرك حصراً |
| الاستراتيجيات ذات البوابة | الكمومية-EMA · الجبّارة A226 · كموميه الزخم الاولى (QMOM1 بالتفويض) | الثلاثة نفسها — من النواة نفسها (QMOM1 يمرر بالتفويض الكامل) |
| القوالب الرسمية | 12 (QMOM1 مفقود) | **13 — قالب QMOM1 كامل** |

**لا يوجد أي تغيير على أي سطر قائم خارج قائمة الملفات أعلاه** — والفروقات بنية إضافة
(استبدال الحساب المضمّن بالنواة المركزية — نفس النتائج بت-بت للتكوينات القائمة، مثبتة
بالمرجع الملتقط قبل التعديل: **31/31 فحصاً PASS**).

**المجلد المضغوط للدمج**: `backend-EMAGATE-UNIFIED-MERGE.zip` — نفس البنية أعلاه
بمساراتها الكاملة؛ فك الضغط فوق جذر المشروع مباشرة يستبدل كل ملف نظيره:

## 3) التثبيت (دقيقتان)

```bash
# 1) الأسهل — فك المجلد المضغوط فوق جذر مشروع الباك-اند (المسارات كاملة جاهزة):
unzip -o backend-EMAGATE-UNIFIED-MERGE.zip -d <PROJECT>

# (أو نسخة ملف-ملف — نفس الأثر):
# 1) انسخ ملفات الحزمة إلى جذر مشروع الباك-اند (كل ملف يستبدل نظيره):
cp merge_package/app/services/indicators/ema_stack_gate.py                        <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema.py    <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema_mom.py <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/overlays.py                               <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/overlay_columns.py                       <PROJECT>/app/services/indicators/
cp merge_package/app/services/strategy/presets.py                                 <PROJECT>/app/services/strategy/
# 2) (اختياري) استراتيجيتا القالب الصريحتان:
cp merge_package/strategies/qmom1_كموميه_الزخم_الاولى.json                         <PROJECT>/strategies/
cp merge_package/strategies/zlf_almighty_quantum_ema_sol15m.json                  <PROJECT>/strategies/
# 3) أعد تشغيل الخدمة (uvicorn/celery كما معتاد) — لا هجرات قواعد بيانات إطلاقاً.
```

## 4) التحقق بعد التثبيت

```bash
python3 tools/verify_emagate_unified.py     # 31 فحصاً (يحتاج pandas — بيانات MMT الافتراضية)
# عدّل EMAGATE_RUNTIME=<PROJECT> و EMAGATE_DATA=<MMT_15m.json> و EMAGATE_REFERENCE=<reference_basis_outputs.json>
```

ثم على السيرفر الحي:
```bash
curl -s http://161.97.73.254:8000/api/v1/strategies/presets | python3 -m json.tool | rg -c "qmom1_quantum_momentum_zero_fee"
# ⇒ 1 (قالب كموميه الزخم الاولى ظاهر)
```
وأي تشغيل قائم (تكوينات 21/50/100/200/350/500 أو 50/100/200/350/500) يعيد نفس النتائج
بت-بت — عقد الإضافة الصرفة.

## 5) البصمات

راجع `FILES-EMAGATE-UNIFIED.md5`.
