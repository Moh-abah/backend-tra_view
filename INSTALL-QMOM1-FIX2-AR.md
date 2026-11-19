# حزمة الإصلاح QMOM1-FIX2 (R78) — «الدمج فقط إضافة» — استعادة بيانات رسم الكمومية-EMA كاملة

**التاريخ**: 2026-11-18 (بعد نشر FIX1 ونجاح البوابة على المهمة الحية #10000617)
**المشكلة المؤكدة من المهمة الحية**: المهمة #10000617 أرجعت 217 عمود مؤشر فقط —
عائلة الكمومية-EMA الأصلية `ind_zzfetqe_*` (78 عموداً — ومنها **خطوط EMA الستة**
`ind_zzfetqe_ema_{21,50,100,200,350,500}`) والعمود المجمّع
`ind_zigzag_fib_e2e_trendy_quantum_ema` **لم تُرجَع** — استُبدلت بـ `zzfetqem_*`
بدلاً من أن تُضاف فوقها. النتيجة: الفرونت الذي يرسم EMA من `ind_zzfetqe_ema_*`
لا يجد بيانات → لا EMA تُرسم.

## الجذر (بتشخيص مثبت)

`overlays_zlf_e2e_trendy_quantum_ema_mom.py` كان يعيد تسمية سلاسل الأساس
`zzfetqe_*` → `zzfetqem_*` (استبدال، لا إضافة)، و`_zzfetqem_columns` في
`overlay_columns.py` يقبل البادئات `zzfetqem_/zzfetq_/zzfet_` فقط فلا طريق
لعائلة `zzfetqe_*` إلى الشارت.

## الإصلاح (R78 — إضافة صرفة، ملفان، صفر مساس بأي قائم)

1. **`app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema_mom.py`**
   - سلاسل الأساس `zzfetqe_*` تبقى **بأسمائها الأصلية** + تُضاف المرآة
     `zzfetqem_*` — **نفس كائن القائمة في الذاكرة تحت الاسمين** (تطابق
     بت-بت بالبناء، صفر نسخ إضافي، صفر تغيير في أي قيمة قائمة).
   - عمودان مجمّعان جديدان (عقد قيم المؤشر الكلاسيكي — نفس ما كان البطل
     #10000604 يرجعه):
     - `zigzag_fib_e2e_trendy_quantum_ema` = خام الكمومية-EMA 0/1 (46 شمعة
       إشارة — **قيم البطل بت-بت**، تمت مطابقتها 18,212/18,212 مع نتيجة
       السيرفر الحية).
     - `zigzag_fib_e2e_trendy_quantum_ema_mom` = النهائي بعد بوابة الزخم 0/1
       (11 شمعة إشارة).
2. **`app/services/indicators/overlay_columns.py`** — `_zzfetqem_columns`:
   يقبل الآن أيضاً بادئة `zzfetqe_` والاسمين المجمّعين → عائلة
   `ind_zzfetqe_*` كاملة (78) + العمودان المجمّعان يصلان شموع الشارت.

**عقد الشارت بعد الإصلاح**: 297 عمود مؤشر لكل شمعة =
`ind_zzfetqe_*` (78 — **كما كان البطل بالضبط**) + `ind_zzfetqem_*` (108 —
البوابة والزخم) + `ind_zzfetq_*` (62) + `ind_zzfet_*` (47) + عمودان
`ind_zigzag_*` المجمّعان.

## التثبيت (دقيقتان)

1. انسخ الملفين من `app/` إلى جذر المشروع على السيرفر (كل ملف يستبدل نظيره):
   - `app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema_mom.py`
   - `app/services/indicators/overlay_columns.py`
2. أعد تشغيل الخدمة.
3. تحقق:
   ```
   python3 tools/verify_qmom1_fix2.py            # البطارية المحلية (12 فحصاً)
   python3 tools/verify_qmom1_fix2.py --live     # + بث مهمة حية والتحقق منها
   ```
   (عدّل `QMOM_RUNTIME`/`QMOM_DATA`/`QMOM_SERVER` إن اختلفت المسارات.)

## البصمات

راجع `FILES-QMOM1-FIX2.md5`.
