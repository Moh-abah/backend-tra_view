═══════════════════════════════════════════════════════════════
 BACKEND v13.1 — الجولة 13.1: الاستراتيجية الواحدة بثلاث إشارات دخول (ZLF)
═══════════════════════════════════════════════════════════════
التاريخ: 2026-11-01
الأساس: v13.0 المنشورة على الإنتاج (تحقق حي VERIFY-R13: ALL PASS — 2026-11-01)
النسخة: 13.1

───────────────────────────────────────────────────────────────
النشر على الإنتاج (نفس أسلوب 12.9 و13.0 — 3 ملفات فقط):
───────────────────────────────────────────────────────────────
  # 1) انسخ الملفات المعدّلة (3 ملفات) — من جذر الحزمة backend_v13:
  docker cp app/services/indicators/overlays.py        trading-backend:/app/app/services/indicators/overlays.py
  docker cp app/services/indicators/overlay_columns.py trading-backend:/app/app/services/indicators/overlay_columns.py
  docker cp app/services/strategy/presets.py           trading-backend:/app/app/services/strategy/presets.py

  # 2) إعادة التشغيل:
  docker restart trading-backend

  # 3) التحقق الحرفي (من ملف الحزمة):
  ZLF_BASE=http://161.97.73.254:8000/api/v1 ./VERIFY-ZLF.sh --external
  # وارجاع الجولة 13 كاملة (لا تراجع):
  R13_BASE=http://161.97.73.254:8000/api/v1 ./VERIFY-R13.sh --external

───────────────────────────────────────────────────────────────
ما الذي تغيّر (الجولة 13.1):
───────────────────────────────────────────────────────────────
الاستراتيجية الواحدة بثلاث إشارات دخول — من صور المستخدم الثلاث
(الحالة الأولى/الثانية/الثالثة من شكل الاستراتيجية) وبتأكيد المستخدم الحرفي:
«هي تعتبر ثلاث اشارات وكل اشاره تعتبر اشاره دخول — استراتيجية واحدة وثلاث شروط دخول».

الاسم: ZLF — ZigZag Liquidity Fibonacci (3 Entry Signals)
البنية: ZigZag (نفس كاشف zigzag_channels حرفياً) + فيبو على الساق الأخيرة
        + السيولة (عمود الحجم).

1) مرجع السيولة «شمعة أكبر» = الشمعة ذات أكبر حجم في النافذة
   [i − liq_lookback, i − 1] (قبيل الشمعة الحالية — سببية 100%، النافذة
   يجب أن تكتمل أولاً — لا حالة قبل i >= liq_lookback).
2) الحالات الثلاث تجاه قمة المرجع (تقسيم كامل — كل شمعة حالة واحدة بالضبط):
   S1 اختراق مؤكد:          high > ref_high و close > ref_high
   S2 اختراق كاذب (SFP):    high > ref_high و close <= ref_high (يرجع قبل الإغلاق)
   S3 رفض بلا اختراق:       high <= ref_high
3) شرط الحجم: volume[i] >= حجم شمعة المرجع (أكبر أو يساوي — «أكبر سيولة»).
4) الحدث السيولي = حالة مطابقة + شرط الحجم → ind_zzf_signal_s1/s2/s3 (وany).
5) الدخول = لمس مستوى 0.618 (أو النزول إلى «آخر منخفض» — مستوى 0) في ساق
   صاعدة وبوجود حدث سيولي معلّق. كل حدث يمنح فرصة دخول واحدة تُستهلك عند
   اللمس؛ التسليح ينتهي بعد liq_arm_bars شمعة من آخر حدث (يُجدَّد مع كل حدث)
   ولا يُصفَّر عند تغيّر الساق — لأن الحدث السيولي غالباً يسبق تأكيد نقطة
   الزيجزاق بطول length. الحدث في نفس شمعة اللمس يُسلّح فوراً.
6) الخروج = انقلاب الساق إلى هابطة (zzf_dir < 0 = تأكيد قمة — نفس روح
   البطل) + SL 2% (نفس عقد risk_management).
7) القالب الرسمي الجديد: id=zlf_triple_signal_zero_fee في /strategies1/presets
   — ثلاث قواعد دخول بوزن 0.34/0.33/0.33 (أي إشارة تكفي — OR داخل المحرك).

معاملات zigzag_fib الجديدة (كلها اختيارية — التوافق الخلفي كامل):
   liq_lookback  (افتراضي 20)  — نافذة مرجع السيولة
   liq_signals   (افتراضي true) — تفعيل أعمدة السيولة كلياً
   liq_arm_bars  (افتراضي 60)  — صلاحية تسليح الحدث بالشموع

الأعمدة التعاقدية الجديدة (12 عموداً — المجموع 25 عمود ind_zzf_*):
   ind_zzf_liq_state    : 0 لا مرجع / 1 اختراق مؤكد / 2 اختراق كاذب / 3 رفض
   ind_zzf_liq_ref_high : قمة شمعة المرجع
   ind_zzf_liq_ref_vol  : حجم شمعة المرجع
   ind_zzf_liq_vol_ok   : 1 إذا volume[i] >= ref_vol
   ind_zzf_signal_s1/s2/s3 : الحدث السيولي لكل حالة (1/0)
   ind_zzf_signal_any   : أي حدث سيولي
   ind_zzf_entry_s1/s2/s3  : +1 دخول مُسلّح بهذه الحالة (لمس 0.618 في ساق صاعدة)
   ind_zzf_entry        : +1 الدخول الجامع (أي حالة)
   (وإشارات الرسم: "ZLF Liquidity S1/S2/S3" و"ZLF Entry Up" في signals[])

المرجع المحلي (قبل النشر): BTCUSDT · 1h · 200 يوم · next_open:
   12 صفقة · +13.08% total_pnl_percent · fees_applied=0.0 ·
   math_audit.max_abs_error=0.0 (≤1e-9) · precision_report كامل ·
   إسناد الدخولات: S2:2 · S3:10 (S1 نادر — يتطلب إغلاقاً فوق قمة المرجع).

التحقق المحلي (كلها في ملفات الأدلة المرفقة):
   test_zlf_unit.py        → ALL ZLF UNIT TESTS PASS (11 فحصاً) — ZLF-UNIT-EVIDENCE.txt
   VERIFY-ZLF.sh (محلي)    → ALL PASS (Z1..Z6) — VERIFY-ZLF-LOCAL-EVIDENCE.txt
   VERIFY-R13.sh (محلي)    → ALL PASS (لا تراجع — البطل 13/13 كما هو)

───────────────────────────────────────────────────────────────
MD5 (مطابق ROUND13.1-MD5SUMS.txt):
───────────────────────────────────────────────────────────────
762eefe5f58c4c434c99a907429f27a5  app/services/indicators/overlays.py
f25603a8fc33f77334f0da3595e2f956  app/services/indicators/overlay_columns.py
19ee19ab26329babcfadd160c1135ebf  app/services/strategy/presets.py
991239b5cdecc04e2387816bbd5b6214  VERIFY-ZLF.sh
03df326d557e804f1ba2898ae609ab19  test_zlf_unit.py

ملفات لم تُمسّ: كل شيء آخر (schemas.py، engine1.py، metrics.py، …) —
الجولة 13.1 إضافية بحتة وبلا أي تغيير على عقود الجولة 13.

التراجع الآمن: استعادة الملفات الثلاثة من حزمة v13.0 + إعادة تشغيل.
