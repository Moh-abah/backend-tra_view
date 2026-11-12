"""Exit-Engine — محرك استراتيجية الخروج (ROUND40.1).

محرك نقي مستقل قابل لإعادة الاستخدام — صفر اعتماديات خارج مكتبة بايثون
القياسية. لا يستورد أي شيء من المؤشرات أو الراوترات أو قواعد البيانات:
مدخله (شموع + إشارات دخول مجهزة بأرضية فيبوناتشي + إعدادات) ومخرجه
تقرير صفقات كامل. أي استراتيجية مستقبلية تستطيع استخدامه بتزويده:

    entries = [
        {
            "bar": 142, "time": 1792279800000, "price": 81360.29,
            "floor": 80809.25,                      # أدنى مستوى فيبو (0 أو 1)
            "floor_meta": {"source": "range", ...}, # توثيق مصدر الأرضية
            "signal": {...},                        # إشارة الدخول الأصلية (كما هي)
        },
        ...
    ]
    result = run_exit_backtest(candles, entries, config)

======================================================================
 عقد استراتيجية الخروج (نص الخطة حرفياً — ROUND40)
======================================================================
 1) عند ظهور إشارة شراء يُفتح مركز بقيمة `position_size_usd` (100$ افتراضياً).
 2) عند صعود السعر بمقدار `take_profit_pct` (5%) من المرجع
    (`tp_reference`: سعر الدخول الأول حرفياً / أو متوسط المراكز) يُغلق
    المركز كاملاً بربح.
 3) إذا هبط السعر من سعر الدخول بمقدار `dca1_trigger_pct` (3%) يُشترى
    شراء ثانٍ بنفس الحجم، وإذا هبط `dca2_trigger_pct` (5%) شراء ثالث —
    طالما أن السعر ما زال داخل نطاق الفيبوناتشي (فوق أدنى مستوياته:
    المستوى 0 أو 1 — أيهما أدنى) ولم يكسره.
 4) بدون وقف خسارة نسبي: وقف الخسارة الوحيد هو إغلاق شمعة تحت أدنى
    مستوى من مستويات الفيبوناتشي (0 أو 1) — عندها تُغلق الصفقة كاملة.
    ✅ R64 — صار هذا الخروج بزر تفعيل/إلغاء (fibo_floor_exit، الافتراضي
    مفعّل = السلوك التاريخي بت-بت). عند تعطيله يعمل بدله وقف خسارة
    نسبي stop_loss_pct (٪ تحت سعر الدخول الأول بلمس اللمّة — نفس
    دلالات المحرك الرئيسي، وفجوة هبوط تحت الوقف تُنفَّذ عند الافتتاح).
    في المسار الموحد (/backtest1/run) يُورَث stop_loss_pct تلقائياً من
    stop_loss_percent بجذر الكونفيق إن لم يُرسل صراحةً في كتلة الخروج
    (الأولوية الموثقة: الصريح في الكتلة > جذر الكونفيق > معطّل).
 5) أقصى عدد مراكز `max_entries` = 3 (أساسي + تعزيزان).
 6) ✅ R66 — وضع الحجم التراكمي `position_sizing`:
    • 'fixed_usd' (الافتراضي — سلوك اليوم بت-بت): كل دخول
      (الأول + التعزيزان) = `position_size_usd` ثابت 1:1:1.
    • 'percent_of_equity': كل دخول = `position_size_pct` ٪ من
      الرصيد الجاري E (1 = 1٪ · 100 = كامل الرصيد — نفس دلالات
      R58 في المحرك الرئيسي). الرصيد يبدأ من بذرة `initial_capital`
      (الجذر في المسار الموحد / 10000$ افتراضياً) ويتحدّث بعد كل
      إغلاق محقق: E += pnl_usd (ربحاً أو خسارة — العمولات مخصومة
      من pnl أصلاً). الدخول الأول والتعزيزان بنفس الحجم داخل
      الدورة (E لا يتغير أثناء الدورة المفتوحة).
      قواعد الحواف (نفس فلسفة المحرك الرئيسي):
        • جدار التصفية: E ≤ 0 ⇒ توقف فتح أي دورة جديدة فوراً +
          صدى account_liquidated في summary.capital.
        • أرضية الغبار: حجم محسوب < 1$ ⇒ يُثبّت على 1$ + عدّاد
          dust_floored_entries.
        • غير المحقق لا يُراكم: صفقات نهاية البيانات لا تحدّث E.
        • allow_overlap: كل دورة تُقاس على E لحظة فتحها فقط.

 ترتيب الفحص داخل كل شمعة (موثق وحتمي):
   أ) كسر أرضية الفيبو — على إغلاق الشمعة (definitive).
      ✅ R64: عند fibo_floor_exit=false يُستبدل بوقف نسبي على لمس اللمّة
      (low <= الدخول الأول × (1 − stop_loss_pct/100)) بتنفيذ عند سعر
      الوقف (أو الافتتاح عند فجوة هبوط دونه). كلاهما مُلغى مع التريلينق
      الحرفي (use_trailing) كما تُلغى كل الآليات.
   ب) تعزيزات DCA — على لمس اللمّة (low <= الزناد) والزناد داخل النطاق.
   ج) جني الربح — على لمس القمة (high >= الهدف).

 السببية 100%: لا نظرية مستقبل. الإشارة تُحسب عند إغلاق شمعتها، والدخول
 عند سعر إشارة الإغلاق (`entry_exec: signal_close` — الافتراضي) أو افتتاح
 الشمعة التالية (`next_open`). الإدارة تبدأ بعد شمعة الدخول (signal_close)
 أو داخل شمعة الدخول نفسها بعد الافتتاح (next_open).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# الهوية
# ---------------------------------------------------------------------------
EXIT_ENGINE_NAME = "Exit-Engine"
EXIT_ENGINE_SPEC = "ROUND42-hero-exit-trailing"

# ---------------------------------------------------------------------------
# 1) الإعدادات — كلها قابلة للتعديل من واجهة الفرونت-إند
# ---------------------------------------------------------------------------
EXIT_CONFIG_DEFAULTS: Dict[str, Any] = {
    "take_profit_pct": 5.0,     # جني الربح ٪ من المرجع
    "tp_reference": "first",    # first = سعر الدخول الأول (حرفياً) | avg = متوسط المراكز
    "dca1_trigger_pct": 3.0,    # هبوط ٪ من سعر الدخول → شراء ثانٍ (0 = تعطيل)
    "dca2_trigger_pct": 5.0,    # هبوط ٪ من سعر الدخول → شراء ثالث (0 = تعطيل)
    "max_entries": 3,           # أقصى عدد مراكز في الصفقة (1 = بلا تعزيز)
    "position_size_usd": 100.0, # حجم كل مركز بالدولار
    "entry_exec": "signal_close",  # signal_close | next_open
    "cooldown_bars": 0,         # عدد الشموع الإجبارية بعد إغلاق صفقة قبل التالية
    "allow_overlap": False,     # السماح بصفقات متزامنة (متقدم — الافتراضي صفقة واحدة)
    # ✅ R55 — السقف الرقمي للصفقات المتزامنة (يحل محل allow_overlap البولياني):
    # None = السلوك التاريخي (allow_overlap يحكم: false ⇒ صفقة واحدة، true ⇒ بلا سقف)
    # 1    = صفقة واحدة في كل لحظة (مثل allow_overlap=false تماماً)
    # 2..10 = إشارة جديدة والصفقات المفتوحة < N ⇒ صفقة مستقلة؛ بلغ N ⇒ تجاهل
    # يمرّر تلقائياً من جذر الطلب BacktestConfig.max_positions
    "max_concurrent_positions": None,
    "fees_pct": 0.0,           # عمولة ٪ لكل عملية (دخول + خروج) — 0 = بلا عمولات
    # --- ROUND40.1: مرشحات جودة الدخول + الجني المتحرك المشروط (معطّلة افتراضياً) ---
    "trend_filter_sma_bars": 0,     # فلتر الاتجاه: لا دخول إلا فوق SMA(N) — 0 = معطّل
    "min_floor_distance_pct": 0.0,  # أدنى مسافة ٪ بين سعر الدخول وأرضية الفيبو — 0 = معطّل
    "tp_trail_arm_pct": 0.0,        # جني متحرك مشروط: يتفعّل عند ربح ٪ من الدخول الأول — 0 = معطّل
    "tp_trail_giveback_pct": 1.5,   # بعد التفعيل: تراجع ٪ من القمة يغلق الصفقة
    # --- ROUND42 (ترقية ج41): التريلينق الحرفي — له الأولوية عند تفعيله ---
    "use_trailing": False,           # true = تريلينق منذ لحظة الدخول (يُلغي TP/وقف الفيبو/الجني المتحرك المشروط)
    "trailing_giveback_pct": 20.0,  # هبوط الإغلاق ٪ من أعلى قمة يغلق الصفقة (نص الطلب: 20)
    # --- ✅ R64: زر تفعيل/إلغاء خروج «إغلاق شمعة تحت آخر مستوى فيبو» ---
    # true (الافتراضي — السلوك التاريخي بت-بت): كسر أرضية الفيبو على
    # الإغلاق يغلق الصفقة. false: خروج الفيبو معطّل ويعمل بدله الوقف
    # النسبي stop_loss_pct (يُورَث في المسار الموحد من stop_loss_percent
    # بجذر الكونفيق إن لم يُرسل صراحةً — الأولوية: الصريح > الجذر > معطّل).
    "fibo_floor_exit": True,
    # ✅ R64 — الوقف النسبي البديل (٪ تحت سعر الدخول الأول): 0 = معطّل.
    # يعمل فقط عند fibo_floor_exit=false · بلمس اللمّة (نفس دلالات
    # المحرك الرئيسي — فجوة هبوط تحت الوقف تُنفَّذ عند الافتتاح).
    # يُلغيه التريلينق الحرفي ككل الآليات.
    "stop_loss_pct": 0.0,
    # --- ✅ R66: وضع الحجم التراكمي (Compounding لمحرك الخروج) ---
    # fixed_usd (الافتراضي) = سلوك اليوم بت-بت: كل دخول position_size_usd
    # ثابت 1:1:1. percent_of_equity = كل دخول (الأول + التعزيزان) نسبة من
    # الرصيد الجاري، والرصيد يتحدّث بعد كل إغلاق محقق (ربحاً أو خسارة).
    "position_sizing": "fixed_usd",
    # نسبة كل دخول من الرصيد الجاري (تُقرأ فقط في percent_of_equity):
    # 1 = 1٪ · 100 = كامل الرصيد — نفس دلالات R58 حرفياً. None = لم تُحدد
    # (خطأ تحقق صريح عند طلب الوضع التراكمي بلا نسبة).
    "position_size_pct": None,
    # بذرة التراكم: للمسار المستقل /exit-strategy/backtest فقط (اختيارية).
    # في المسار الموحد /backtest1/run تُقرأ initial_capital الجذرية دائماً
    # (تُمرر للمنفذ عبر meta) ولا تُرسل داخل الكتلة.
    "initial_capital": None,
}

EXIT_CONFIG_SCHEMA: Dict[str, Dict[str, Any]] = {
    "take_profit_pct": {
        "type": "float", "min": 0.1, "max": 100.0, "step": 0.1, "default": 5.0,
        "label_ar": "جني الربح ٪",
        "desc_ar": "عند صعود السعر هذه النسبة من سعر المرجع يُغلق المركز كاملاً بربح.",
    },
    "tp_reference": {
        "type": "enum", "options": ["first", "avg"], "default": "first",
        "label_ar": "مرجع قياس الربح",
        "desc_ar": "first = من سعر الدخول الأول (حرفياً كما في الخطة). avg = من متوسط أسعار كل المراكز المفتوحة (ينخفض الهدف مع كل تعزيز).",
    },
    "dca1_trigger_pct": {
        "type": "float", "min": 0.0, "max": 50.0, "step": 0.1, "default": 3.0,
        "label_ar": "تعزيز 1: هبوط ٪",
        "desc_ar": "إذا هبط السعر هذه النسبة من سعر الدخول يُشترى مركز ثانٍ بنفس الحجم. اكتب 0 لتعطيل هذا التعزيز.",
    },
    "dca2_trigger_pct": {
        "type": "float", "min": 0.0, "max": 50.0, "step": 0.1, "default": 5.0,
        "label_ar": "تعزيز 2: هبوط ٪",
        "desc_ar": "إذا هبط السعر هذه النسبة من سعر الدخول يُشترى مركز ثالث بنفس الحجم. اكتب 0 لتعطيل هذا التعزيز.",
    },
    "max_entries": {
        "type": "int", "min": 1, "max": 5, "step": 1, "default": 3,
        "label_ar": "أقصى عدد مراكز",
        "desc_ar": "عدد المراكز الأقصى في الصفقة الواحدة (الأساسي + التعزيزات). 3 = الخطة الأصلية.",
    },
    "position_size_usd": {
        "type": "float", "min": 1.0, "max": 1000000.0, "step": 1.0, "default": 100.0,
        "label_ar": "حجم المركز ($)",
        "desc_ar": "قيمة كل مركز بالدولار — يُدفع نفس المبلغ في الدخول وفي كل تعزيز.",
    },
    "entry_exec": {
        "type": "enum", "options": ["signal_close", "next_open"], "default": "signal_close",
        "label_ar": "سعر تنفيذ الدخول",
        "desc_ar": "signal_close = عند سعر إغلاق شمعة الإشارة (افتراضي). next_open = عند افتتاح الشمعة التالية (أكثر تحفظاً).",
    },
    "cooldown_bars": {
        "type": "int", "min": 0, "max": 10000, "step": 1, "default": 0,
        "label_ar": "فترة تبريد (شموع)",
        "desc_ar": "عدد الشموع الإجبارية بعد إغلاق أي صفقة قبل السماح بصفقة جديدة. 0 = السماح فوراً من الشمعة التالية.",
    },
    "allow_overlap": {
        "type": "bool", "default": False,
        "label_ar": "السماح بصفقات متزامنة (قديم)",
        "desc_ar": "false = صفقة واحدة في نفس الوقت (الخطة). true = كل إشارة تفتح صفقة مستقلة تعمل بإدارة كاملة (متقدم). يُتجاهل عند تحديد max_concurrent_positions.",
    },
    "max_concurrent_positions": {
        "type": "int", "min": 1, "max": 10, "step": 1, "default": None, "nullable": True,
        "label_ar": "أقصى صفقات متزامنة",
        "desc_ar": "سقف رقمي للصفقات المفتوحة معاً: إشارة جديدة والصفقات المفتوحة أقل من العدد ⇒ تُفتح صفقة مستقلة بإدارة كاملة؛ بلغت العدد ⇒ تُتجاهل الإشارة. فارغ (null) = السلوك التاريخي وفق allow_overlap.",
    },
    "fees_pct": {
        "type": "float", "min": 0.0, "max": 2.0, "step": 0.01, "default": 0.0,
        "label_ar": "العمولة ٪ لكل عملية",
        "desc_ar": "عمولة المنصة كنسبة من قيمة كل عملية (دخول وخروج). 0 = نتائج صافية استراتيجية بحتة.",
    },
    "trend_filter_sma_bars": {
        "type": "int", "min": 0, "max": 1000, "step": 1, "default": 0,
        "label_ar": "فلتر الاتجاه (SMA)",
        "desc_ar": "لا يُفتح أي مركز إلا إذا كان إغلاق شمعة الإشارة فوق المتوسط المتحرك البسيط لآخر N شمعة (شراء مع الاتجاه فقط). 0 = معطّل — سلوك الخطة الأصلي.",
    },
    "min_floor_distance_pct": {
        "type": "float", "min": 0.0, "max": 50.0, "step": 0.1, "default": 0.0,
        "label_ar": "أدنى مسافة عن الأرضية ٪",
        "desc_ar": "يُرفض الدخول إذا كانت أرضية الفيبو أقرب من هذه النسبة تحت سعر الدخول — الدخول الملاصق للأرضية خروجه شبه مؤكد. 0 = معطّل.",
    },
    "tp_trail_arm_pct": {
        "type": "float", "min": 0.0, "max": 100.0, "step": 0.1, "default": 0.0,
        "label_ar": "جني متحرك: تفعيل عند ربح ٪",
        "desc_ar": "عند بلوغ الربح غير المحقق هذه النسبة (من سعر الدخول الأول) يُلغى هدف الربح الثابت ويُتابع السعر صعوداً — لتحصد ما يتجاوز الهدف. 0 = معطّل (هدف ثابت كما في الخطة).",
    },
    "tp_trail_giveback_pct": {
        "type": "float", "min": 0.1, "max": 50.0, "step": 0.1, "default": 1.5,
        "label_ar": "جني متحرك: تراجع الإغلاق ٪",
        "desc_ar": "بعد تفعيل الجني المتحرك: إذا تراجع السعر هذه النسبة من أعلى قمة بلغها يُغلق المركز كاملاً عند نقطة التتبع.",
    },
    "use_trailing": {
        "type": "bool", "default": False,
        "label_ar": "تفعيل التريلينق (ملاحقة الصعود)",
        "desc_ar": "عند التفعيل يُلغى جني الربح ووقف الفيبو والجني المتحرك المشروط — التريلينق وحده من يعمل: يُحسب منذ لحظة دخول الصفقة، وكل قمة جديدة يصلها السعر ترفع السقف، وهبوط الإغلاق بنسبة التريلينق من أعلى قمة يغلق الصفقة كاملة.",
    },
    "trailing_giveback_pct": {
        "type": "float", "min": 0.1, "max": 90.0, "step": 0.1, "default": 20.0,
        "label_ar": "التريلينق: هبوط ٪ من القمة",
        "desc_ar": "نسبة الهبوط من أعلى قمة وصلها السعر منذ الدخول التي تُغلق عندها الصفقة كاملة (افتراضي 20٪).",
    },
    # --- ✅ R64: زر تبديل خروج الفيبو + الوقف النسبي البديل ---
    "fibo_floor_exit": {
        "type": "bool", "default": True,
        "label_ar": "خروج كسر الفيبو (إغلاق تحت آخر مستوى)",
        "desc_ar": "مفعّل (الافتراضي) = إغلاق شمعة تحت أدنى مستوى فيبوناتشي (0 أو 1) يغلق الصفقة كاملة — الوقف التاريخي الوحيد. معطّل = يُستخدم وقف الخسارة النسبي stop_loss_pct بدلاً منه (وفي المسار الموحد /backtest1/run يُورث تلقائياً من stop_loss_percent بجذر الكونفيق إن لم يُحدَّد هنا).", 
    },
    "stop_loss_pct": {
        "type": "float", "min": 0.0, "max": 100.0, "step": 0.1, "default": 0.0,
        "label_ar": "وقف الخسارة البديل ٪",
        "desc_ar": "وقف خسارة نسبي يعمل فقط عند تعطيل خروج كسر الفيبو: لمس السعر (اللمّة) تحت سعر الدخول الأول بهذه النسبة يغلق الصفقة عند سعر الوقف — فجوة هبوط تحت الوقف تُنفَّذ عند الافتتاح. 0 = معطّل. يُلغيه التريلينق الحرفي عند تفعيله.",
    },
}


# ✅ R66 — إضافة الحقول الثلاثة للوضع التراكمي إلى مخطط العرض (تُلحق
# بنهاية EXIT_CONFIG_SCHEMA أعلاه عند الاستيراد — لا تُكرر حرفياً هنا
# حفاظاً على القراءة؛ الشرح العربي الكامل في المخطط الرئيسي أدناه).
EXIT_CONFIG_SCHEMA.update({
    "position_sizing": {
        "type": "enum", "options": ["fixed_usd", "percent_of_equity"], "default": "fixed_usd",
        "label_ar": "وضع الحجم (ثابت / تراكمي)",
        "desc_ar": "fixed_usd = حجم ثابت بالدولار لكل دخول (سلوك اليوم). percent_of_equity = الوضع التراكمي: كل دخول (الأول + التعزيزان معاً) نسبة من الرصيد الجاري، والرصيد يتحدّث بعد كل إغلاق محقق — ما تم ربحه يُتداول ويُعزّز به.",
    },
    "position_size_pct": {
        "type": "float", "min": 0.1, "max": 100.0, "step": 0.1, "default": None, "nullable": True,
        "label_ar": "نسبة كل دخول من الرصيد ٪ (تراكمي)",
        "desc_ar": "تُقرأ فقط في الوضع التراكمي (position_sizing=percent_of_equity): 1 = 1٪ من الرصيد الجاري لكل دخول، 100 = كامل الرصيد — نفس دلالات نسبة المركز في المحرك الرئيسي. الدخول الأول والتعزيزان بنفس النسبة حرفياً.",
    },
    "initial_capital": {
        "type": "float", "min": 0.01, "max": 100000000.0, "step": 1.0, "default": None, "nullable": True,
        "label_ar": "بذرة التراكم ($)",
        "desc_ar": "رأس المال الابتدائي الذي يبدأ منه التراكم — للمسار المستقل /exit-strategy/backtest فقط (اختياري، الافتراضي 10000$). في المسار الموحد /backtest1/run تُقرأ دائماً من initial_capital بجذر الكونفيق ولا تُرسل داخل هذه الكتلة.",
    },
})


def normalize_exit_config(raw: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """يطبّع ويتحقق من إعدادات الخروج.

    يعيد (config_normalized, errors) — الأخيرة فارغة عند الصحة. الحقول غير
    المعروفة تُرفض بالاسم (حماية من أخطاء الفرونت-إند الطباعية).
    """
    cfg = dict(EXIT_CONFIG_DEFAULTS)
    errors: List[str] = []
    raw = raw or {}
    if not isinstance(raw, dict):
        return cfg, ["الإعدادات يجب أن تكون كائن JSON (object)"]

    allowed = set(EXIT_CONFIG_DEFAULTS.keys())
    for key in raw:
        if key not in allowed:
            errors.append(f"حقل غير معروف: '{key}' — الحقول المسموحة: {sorted(allowed)}")

    # --- take_profit_pct ---
    v = raw.get("take_profit_pct", cfg["take_profit_pct"])
    try:
        v = float(v)
    except (TypeError, ValueError):
        errors.append("take_profit_pct يجب أن يكون رقماً")
        v = None
    if v is not None and not (0.1 <= v <= 100.0):
        errors.append(f"take_profit_pct خارج النطاق [0.1..100]: {v}")
    elif v is not None:
        cfg["take_profit_pct"] = v

    # --- tp_reference ---
    v = raw.get("tp_reference", cfg["tp_reference"])
    if v not in ("first", "avg"):
        errors.append(f"tp_reference يجب أن يكون 'first' أو 'avg' (وصل: {v!r})")
    else:
        cfg["tp_reference"] = v

    # --- dca1/dca2 ---
    for field in ("dca1_trigger_pct", "dca2_trigger_pct"):
        v = raw.get(field, cfg[field])
        try:
            v = float(v)
        except (TypeError, ValueError):
            errors.append(f"{field} يجب أن يكون رقماً")
            v = None
        if v is not None and not (0.0 <= v <= 50.0):
            errors.append(f"{field} خارج النطاق [0..50] (0 = تعطيل): {v}")
        elif v is not None:
            cfg[field] = v
    d1, d2 = cfg["dca1_trigger_pct"], cfg["dca2_trigger_pct"]
    if d1 > 0 and d2 > 0 and d2 < d1:
        errors.append(
            f"ترتيب التعزيزات مقلوب: dca2_trigger_pct ({d2}) يجب أن يكون أعمق من أو يساوي "
            f"dca1_trigger_pct ({d1}) — الهبوط الأعمق يأتي لاحقاً"
        )

    # --- max_entries ---
    v = raw.get("max_entries", cfg["max_entries"])
    try:
        v = int(v)
    except (TypeError, ValueError):
        errors.append("max_entries يجب أن يكون عدداً صحيحاً")
        v = None
    if v is not None and not (1 <= v <= 5):
        errors.append(f"max_entries خارج النطاق [1..5]: {v}")
    elif v is not None:
        cfg["max_entries"] = v

    # --- position_size_usd ---
    v = raw.get("position_size_usd", cfg["position_size_usd"])
    try:
        v = float(v)
    except (TypeError, ValueError):
        errors.append("position_size_usd يجب أن يكون رقماً")
        v = None
    if v is not None and not (1.0 <= v <= 1_000_000.0):
        errors.append(f"position_size_usd خارج النطاق [1..1000000]: {v}")
    elif v is not None:
        cfg["position_size_usd"] = v

    # --- entry_exec ---
    v = raw.get("entry_exec", cfg["entry_exec"])
    if v not in ("signal_close", "next_open"):
        errors.append(f"entry_exec يجب أن يكون 'signal_close' أو 'next_open' (وصل: {v!r})")
    else:
        cfg["entry_exec"] = v

    # --- cooldown_bars ---
    v = raw.get("cooldown_bars", cfg["cooldown_bars"])
    try:
        v = int(v)
    except (TypeError, ValueError):
        errors.append("cooldown_bars يجب أن يكون عدداً صحيحاً")
        v = None
    if v is not None and not (0 <= v <= 10000):
        errors.append(f"cooldown_bars خارج النطاق [0..10000]: {v}")
    elif v is not None:
        cfg["cooldown_bars"] = v

    # --- allow_overlap ---
    v = raw.get("allow_overlap", cfg["allow_overlap"])
    if not isinstance(v, bool):
        errors.append(f"allow_overlap يجب أن يكون true/false (وصل: {v!r})")
    else:
        cfg["allow_overlap"] = v

    # --- ✅ R55: max_concurrent_positions (السقف الرقمي) ---
    v = raw.get("max_concurrent_positions", cfg["max_concurrent_positions"])
    if v is None or (isinstance(v, str) and not v.strip()):
        cfg["max_concurrent_positions"] = None  # null/فارغ = سلوك تاريخي
    else:
        try:
            v_i = int(v)
        except (TypeError, ValueError):
            errors.append(f"max_concurrent_positions يجب أن يكون عدداً صحيحاً 1..10 أو null (وصل: {v!r})")
        else:
            if not (1 <= v_i <= 10):
                errors.append(f"max_concurrent_positions خارج النطاق [1..10]: {v_i}")
            else:
                cfg["max_concurrent_positions"] = v_i

    # --- fees_pct ---
    v = raw.get("fees_pct", cfg["fees_pct"])
    try:
        v = float(v)
    except (TypeError, ValueError):
        errors.append("fees_pct يجب أن يكون رقماً")
        v = None
    if v is not None and not (0.0 <= v <= 2.0):
        errors.append(f"fees_pct خارج النطاق [0..2]: {v}")
    elif v is not None:
        cfg["fees_pct"] = v

    # --- trend_filter_sma_bars (ROUND40.1) ---
    v = raw.get("trend_filter_sma_bars", cfg["trend_filter_sma_bars"])
    try:
        v = int(v)
    except (TypeError, ValueError):
        errors.append("trend_filter_sma_bars يجب أن يكون عدداً صحيحاً")
        v = None
    if v is not None and not (0 <= v <= 1000):
        errors.append(f"trend_filter_sma_bars خارج النطاق [0..1000] (0 = معطّل): {v}")
    elif v is not None:
        cfg["trend_filter_sma_bars"] = v

    # --- min_floor_distance_pct (ROUND40.1) ---
    v = raw.get("min_floor_distance_pct", cfg["min_floor_distance_pct"])
    try:
        v = float(v)
    except (TypeError, ValueError):
        errors.append("min_floor_distance_pct يجب أن يكون رقماً")
        v = None
    if v is not None and not (0.0 <= v <= 50.0):
        errors.append(f"min_floor_distance_pct خارج النطاق [0..50] (0 = معطّل): {v}")
    elif v is not None:
        cfg["min_floor_distance_pct"] = v

    # --- tp_trail_arm_pct / tp_trail_giveback_pct (ROUND40.1) ---
    for field in ("tp_trail_arm_pct", "tp_trail_giveback_pct"):
        v = raw.get(field, cfg[field])
        try:
            v = float(v)
        except (TypeError, ValueError):
            errors.append(f"{field} يجب أن يكون رقماً")
            v = None
        lo, hi = (0.0, 100.0) if field == "tp_trail_arm_pct" else (0.1, 50.0)
        if v is not None and not (lo <= v <= hi):
            errors.append(f"{field} خارج النطاق [{lo}..{hi}]: {v}")
        elif v is not None:
            cfg[field] = v
    arm_v, gb_v = cfg["tp_trail_arm_pct"], cfg["tp_trail_giveback_pct"]
    if arm_v > 0 and gb_v >= arm_v:
        errors.append(
            f"tp_trail_giveback_pct ({gb_v}) يجب أن يكون أصغر من tp_trail_arm_pct ({arm_v}) "
            f"— وإلا فقد يغلق الجني المتحرك تحت نقطة تفعيله"
        )

    # --- use_trailing / trailing_giveback_pct (ROUND42 — ترقية ج41) ---
    v = raw.get("use_trailing", cfg["use_trailing"])
    if not isinstance(v, bool):
        errors.append(f"use_trailing يجب أن يكون true/false (وصل: {v!r})")
    else:
        cfg["use_trailing"] = v
    v = raw.get("trailing_giveback_pct", cfg["trailing_giveback_pct"])
    try:
        v = float(v)
    except (TypeError, ValueError):
        errors.append("trailing_giveback_pct يجب أن يكون رقماً")
        v = None
    if v is not None and not (0.1 <= v <= 90.0):
        errors.append(f"trailing_giveback_pct خارج النطاق [0.1..90]: {v}")
    elif v is not None:
        cfg["trailing_giveback_pct"] = v

    # --- ✅ R64: fibo_floor_exit / stop_loss_pct (زر تبديل خروج الفيبو) ---
    v = raw.get("fibo_floor_exit", cfg["fibo_floor_exit"])
    if not isinstance(v, bool):
        errors.append(f"fibo_floor_exit يجب أن يكون true/false (وصل: {v!r})")
    else:
        cfg["fibo_floor_exit"] = v
    v = raw.get("stop_loss_pct", cfg["stop_loss_pct"])
    try:
        v = float(v)
    except (TypeError, ValueError):
        errors.append("stop_loss_pct يجب أن يكون رقماً")
        v = None
    if v is not None and not (0.0 <= v <= 100.0):
        errors.append(f"stop_loss_pct خارج النطاق [0..100] (0 = معطّل): {v}")
    elif v is not None:
        cfg["stop_loss_pct"] = v
    # لا نرفع خطأ عند تعطيل الفيبو بلا وقف بديل (حق المستخدم) — لكن
    # الوصف ونقطة /validate تحذّران صراحةً من «بلا وقف نهائياً».

    # --- ✅ R66: وضع الحجم التراكمي (position_sizing / position_size_pct / initial_capital) ---
    v = raw.get("position_sizing", cfg["position_sizing"])
    if v not in ("fixed_usd", "percent_of_equity"):
        errors.append(f"position_sizing يجب أن يكون 'fixed_usd' أو 'percent_of_equity' (وصل: {v!r})")
    else:
        cfg["position_sizing"] = v

    v = raw.get("position_size_pct", cfg["position_size_pct"])
    if v is not None:
        try:
            v = float(v)
        except (TypeError, ValueError):
            errors.append("position_size_pct يجب أن يكون رقماً (1 = 1٪ من الرصيد، 100 = كامل الرصيد)")
            v = None
        if v is not None and not (0.1 <= v <= 100.0):
            errors.append(f"position_size_pct خارج النطاق [0.1..100] (1 = 1٪ من الرصيد الجاري، 100 = كامل الرصيد): {v}")
        elif v is not None:
            cfg["position_size_pct"] = v

    # الوضع التراكمي بلا نسبة صالحة = خطأ تحقق صريح (لا افتراض خفي)
    if cfg["position_sizing"] == "percent_of_equity" and cfg.get("position_size_pct") is None:
        errors.append(
            "position_sizing='percent_of_equity' يتطلب position_size_pct صالحة "
            "[0.1..100] (1 = 1٪ من الرصيد الجاري لكل دخول — الأول والتعزيزان معاً)"
        )

    v = raw.get("initial_capital", cfg["initial_capital"])
    if v is not None:
        try:
            v = float(v)
        except (TypeError, ValueError):
            errors.append("initial_capital يجب أن يكون رقماً أكبر من 0")
            v = None
        if v is not None and not (v > 0.0):
            errors.append(f"initial_capital يجب أن يكون أكبر من 0 (وصل: {v})")
        elif v is not None:
            cfg["initial_capital"] = v
    # قاعدة الأولوية الموثقة (R66): في المسار الموحد /backtest1/run تحكم
    # initial_capital الجذرية دائماً (تُمرر للمنفذ عبر meta) — وأعلام التراكم
    # الجذرية (compounding / multi_position_compounding) لا تتدخل في أحجام
    # كتلة الخروج: حين تكون الكتلة مفعلة فأحجامها هي الحاكمة.

    # قاعدة الأولوية الموثقة: عند تفعيل use_trailing يُلغى الجني المتحرك
    # المشروط أيضاً (tp_trail_*) — التريلينق الحرفي هو من يعمل وحده. لا
    # نرفع خطأ عند إرسال الاثنين معاً: الأولوية حتمية ومعلنة في الوصف.
    # ✅ R64 — التريلينق الحرفي يُلغي أيضاً خروج الفيبو والوقف النسبي البديل.

    return cfg, errors


def _describe_overlap(cfg: Dict[str, Any]) -> str:
    """✅ R55 — وصف سياسة الصفقات المتزامنة (السقف الرقمي أولًا ثم التاريخية)."""
    cap = cfg.get("max_concurrent_positions")
    if cap is not None:
        return f"سقف رقمي = {int(cap)} صفقة متزامنة كحد أقصى"
    return "مسموحة (متقدم)" if cfg.get("allow_overlap") else "غير مسموحة — صفقة واحدة في كل لحظة"


def describe_exit_config(cfg: Dict[str, Any]) -> str:
    """يولّد وصفاً عربياً بشرياً للإعدادات — يُستخدم في /describe."""
    d1 = "معطّل" if cfg["dca1_trigger_pct"] <= 0 else f"عند هبوط {cfg['dca1_trigger_pct']:g}٪"
    d2 = "معطّل" if cfg["dca2_trigger_pct"] <= 0 else f"عند هبوط {cfg['dca2_trigger_pct']:g}٪"
    ref = "سعر الدخول الأول" if cfg["tp_reference"] == "first" else "متوسط أسعار المراكز المفتوحة"
    exec_txt = "سعر إغلاق شمعة الإشارة" if cfg["entry_exec"] == "signal_close" else "افتتاح الشمعة التالية"
    # ✅ R64 — نص وقف الخسارة حسب وضع زر الفيبو (تاريخي / نسبي بديل / بلا وقف)
    if cfg.get("use_trailing"):
        sl_txt_r64 = None  # التريلينق الحرفي يُلغي الوقف — يُوثّق في فقرته الخاصة أدناه
    elif cfg.get("fibo_floor_exit", True):
        sl_txt_r64 = "وقف الخسارة الوحيد: إغلاق شمعة تحت أدنى مستوى فيبوناتشي يغلق الصفقة كاملة (لا وقف نسبي)."
    elif float(cfg.get("stop_loss_pct", 0.0) or 0.0) > 0:
        sl_txt_r64 = (f"خروج كسر الفيبو معطّل (زر R64) — وقف الخسارة نسبي: لمس السعر تحت "
                      f"{cfg['stop_loss_pct']:g}٪ من سعر الدخول الأول يغلق الصفقة عند سعر الوقف "
                      f"(فجوة هبوط تحت الوقف تُنفّذ عند الافتتاح).")
    else:
        sl_txt_r64 = "خروج كسر الفيبو معطّل ولا وقف بديل (stop_loss_pct=0) — الصفقة تُدار بالهدف والتعزيزات حتى نهاية البيانات."
    parts = [
        # ✅ R66 — الجملة الأولى تتغير مع الوضع التراكمي (نسبة من الرصيد
        # الجاري بدل المبلغ الثابت). الوضع الثابت يبقى بنصه التاريخي بت-بت.
        (
            f"عند ظهور إشارة شراء يُفتح مركز بقيمة {cfg['position_size_pct']:g}٪ من الرصيد الجاري عند {exec_txt} "
            f"(الوضع التراكمي R66 — الدخول الأول والتعزيزان بنفس النسبة)."
            if cfg.get("position_sizing") == "percent_of_equity"
            else f"عند ظهور إشارة شراء يُفتح مركز بقيمة {cfg['position_size_usd']:g}$ عند {exec_txt}."
        ),
        f"جني الربح: عند صعود السعر {cfg['take_profit_pct']:g}٪ من {ref} يُغلق المركز كاملاً بربح.",
        f"التعزيز الأول: {d1} من سعر الدخول يشتري مركزاً ثانياً بنفس الحجم، والتعزيز الثاني: {d2} يشتري ثالثاً —",
        "بشرط بقاء السعر داخل نطاق الفيبوناتشي (فوق أدنى مستوياته: 0 أو 1).",
        f"أقصى عدد مراكز في الصفقة: {cfg['max_entries']}.",
    ]
    # ✅ R66 — فقرة الوضع التراكمي الصريحة (نص المطلوب 5 حرفياً)
    if cfg.get("position_sizing") == "percent_of_equity":
        parts.append(
            f"الوضع التراكمي: كل دخول (الأول + التعزيزان) = النسبة × الرصيد الجاري، "
            f"والرصيد يتحدث بعد كل إغلاق محقق (ربحاً أو خسارة) — ما تم ربحه يُتداول ويُعزّز به. "
            f"يبدأ الرصيد من البذرة (initial_capital) ويتوقف فتح أي دورة جديدة فور استنفاده "
            f"(جدار التصفية)، والأحجام دون 1$ تُثبّت على 1$."
        )
    if sl_txt_r64 is not None:
        parts.append(sl_txt_r64)
    parts.extend([
        f"فترة التبريد بين الصفقات: {cfg['cooldown_bars']} شمعة. "
        f"الصفقات المتزامنة: {_describe_overlap(cfg)}.",
        f"العمولة: {cfg['fees_pct']:g}٪ لكل عملية.",
    ])
    if cfg.get("trend_filter_sma_bars", 0) > 0:
        parts.append(
            f"فلتر الاتجاه مفعّل: لا دخول إلا إذا كان إغلاق شمعة الإشارة فوق متوسط SMA({cfg['trend_filter_sma_bars']}) — شراء مع الاتجاه فقط."
        )
    if cfg.get("min_floor_distance_pct", 0) > 0:
        parts.append(
            f"فلتر المسافة مفعّل: يُرفض الدخول إذا كانت أرضية الفيبو أقرب من {cfg['min_floor_distance_pct']:g}٪ تحت سعر الدخول."
        )
    if cfg.get("tp_trail_arm_pct", 0) > 0 and not cfg.get("use_trailing"):
        parts.append(
            f"جني ربح متحرك: عند ربح {cfg['tp_trail_arm_pct']:g}٪ من الدخول الأول يُلغى الهدف الثابت ويتابع السعر صعوداً، "
            f"ويُغلق كامل المركز عند تراجع {cfg['tp_trail_giveback_pct']:g}٪ من القمة."
        )
    if cfg.get("use_trailing"):
        parts.append(
            f"التريلينق الحرفي مفعّل ({cfg['trailing_giveback_pct']:g}٪ من القمة): يُلغى جني الربح ووقف الفيبو والوقف النسبي البديل (R64) والجني المتحرك المشروط — "
            f"يُحسب منذ لحظة دخول الصفقة، وكل قمة جديدة يصلها السعر ترفع السقف، "
            f"وإغلاق شمعة هبطت {cfg['trailing_giveback_pct']:g}٪ من أعلى قمة يغلق الصفقة كاملة."
        )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# 1.5) الإعدادات الجاهزة (Presets) — ROUND40.1
# ---------------------------------------------------------------------------
# توليفات مدروسة يختارها المستخدم من الواجهة بضغطة واحدة. "plan" هي الخطة
# الحرفية (نفس الافتراضات)؛ و"recommended" من دراسة التحسين على بيانات
# حقيقية (انظر OPTIMIZATION-STUDY-AR.md في حزمة الجولة).
EXIT_ENGINE_PRESETS: List[Dict[str, Any]] = [
    {
        "name": "plan",
        "label_ar": "الخطة الحرفية",
        "desc_ar": "الإعدادات الافتراضية تماماً كما نُصّت الخطة: هدف 5٪ من سعر الدخول الأول، تعزيزان عند 3٪ و5٪، بلا فلاتر ولا جني متحرك.",
        "config": dict(EXIT_CONFIG_DEFAULTS),
    },
    {
        "name": "recommended",
        "label_ar": "الموصى بها (دراسة التحسين)",
        "desc_ar": "من دراسة تحسين على 6 عملات × فريمين × 3 استراتيجيات (55,296 باك-تست): هدف 3٪ من متوسط المراكز، تعزيزان عميقان عند 5٪ و8٪، تبريد 50 شمعة — قلّصت خسائر الخطة الحرفية بنسبة ~70٪ في النوافذ الهابطة ومضاعفة نسبة الصفقات الرابحة، وحوّلت نافذتي السوق المحايدة والهابطة على BTC إلى ربح (انظر OPTIMIZATION-STUDY-AR.md).",
        "config": {
            **EXIT_CONFIG_DEFAULTS,
            "take_profit_pct": 3.0,
            "tp_reference": "avg",
            "dca1_trigger_pct": 5.0,
            "dca2_trigger_pct": 8.0,
            "cooldown_bars": 50,
        },
    },
]


# ---------------------------------------------------------------------------
# 2) تطبيع الشموع (محلي — المحرك مكتفٍ ذاتياً)
# ---------------------------------------------------------------------------
def _norm_candles(candles: Any) -> Tuple[List[Optional[int]], List[Optional[float]],
                                          List[Optional[float]], List[Optional[float]],
                                          List[Optional[float]]]:
    """(times, opens, highs, lows, closes) من list[dict] بصيغة time/open_time."""
    t: List[Optional[int]] = []
    o: List[Optional[float]] = []
    h: List[Optional[float]] = []
    l: List[Optional[float]] = []
    c: List[Optional[float]] = []

    def _num(v: Any) -> Optional[float]:
        try:
            f = float(v)
            return f if math.isfinite(f) else None
        except (TypeError, ValueError):
            return None

    for row in (candles or []):
        if row is None:
            continue
        if not isinstance(row, dict):
            getter = getattr(row, "model_dump", None) or getattr(row, "dict", None)
            row = getter() if callable(getter) else dict(row.__dict__)
        low = {str(k).lower(): v for k, v in row.items()}
        tv = low.get("time", low.get("open_time", low.get("timestamp", low.get("date"))))
        try:
            t.append(int(tv) if tv is not None else None)
        except (TypeError, ValueError):
            t.append(None)
        o.append(_num(low.get("open", low.get("o"))))
        h.append(_num(low.get("high", low.get("h"))))
        l.append(_num(low.get("low", low.get("l"))))
        c.append(_num(low.get("close", low.get("c"))))
    return t, o, h, l, c


# ---------------------------------------------------------------------------
# 3) المحرك — باك-تست استراتيجية الخروج
# ---------------------------------------------------------------------------
def run_exit_backtest(
    candles: Any,
    entries: Sequence[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
    initial_capital: Optional[float] = None,
) -> Dict[str, Any]:
    """يشغّل استراتيجية الخروج على الشموع وفق إشارات الدخول المجهزة.

    candles : شموع (list[dict] بصيغة time/open_time + open/high/low/close).
    entries : إشارات دخول مرتبة (كل واحدة بـ bar/time/price/floor/floor_meta/signal).
    config  : إعدادات EXIT_CONFIG_DEFAULTS (تُطبَّع داخلياً).
    initial_capital : ✅ R66 — بذرة التراكم عند position_sizing=
    'percent_of_equity'. الأولوية الموثقة: هذا المعامل (الحقن الخارجي —
    initial_capital الجذرية في المسار الموحد / top-level في المسار
    المستقل) > initial_capital داخل الكتلة > 10000$ افتراضياً.
    يُتجاهل تماماً في الوضع الثابت (fixed_usd — سلوك اليوم بت-بت).

    المخرجات: {ok, errors?, engine, config, window, trades, summary, notes,
    compounding_audit? (الوضع التراكمي فقط)}.
    """
    cfg, errors = normalize_exit_config(config)
    t, o, h, l, c = _norm_candles(candles)
    N = len(c)

    result: Dict[str, Any] = {
        "engine": {"name": EXIT_ENGINE_NAME, "spec": EXIT_ENGINE_SPEC},
        "config": cfg,
        "window": {
            "bars": N,
            "time_from": t[0] if N else None,
            "time_to": t[-1] if N else None,
        },
        "trades": [],
        "summary": {},
        "notes": [],
    }
    if errors:
        result["ok"] = False
        result["errors"] = errors
        return result
    result["ok"] = True

    if N == 0:
        result["notes"].append("لا شموع — لا صفقات.")
        result["summary"] = _summarize([], {"signals_total": 0, "signals_used": 0,
                                            "signals_ignored_open": 0,
                                            "signals_ignored_cooldown": 0}, cfg)
        return result

    # --- تجهيز الإشارات: دمج إشارات البار الواحد في دخول واحد ---
    by_bar: Dict[int, Dict[str, Any]] = {}
    invalid_entries = 0
    for e in sorted(entries or [], key=lambda x: x.get("bar", 0)):
        try:
            bar = int(e.get("bar"))
            price = float(e.get("price"))
            floor = float(e.get("floor"))
        except (TypeError, ValueError):
            invalid_entries += 1
            continue
        if bar < 0 or bar >= N or not (math.isfinite(price) and math.isfinite(floor)):
            invalid_entries += 1
            continue
        sig_name = str((e.get("signal") or {}).get("signal", "?"))
        if bar in by_bar:
            by_bar[bar]["signals"].append(sig_name)
        else:
            by_bar[bar] = {
                "bar": bar,
                "time": e.get("time", t[bar]),
                "price": price,
                "floor": floor,
                "floor_meta": e.get("floor_meta") or {},
                "signal": e.get("signal") or {},
                "signals": [sig_name],
            }

    tp_pct = cfg["take_profit_pct"] / 100.0
    dca1 = cfg["dca1_trigger_pct"] / 100.0
    dca2 = cfg["dca2_trigger_pct"] / 100.0
    max_entries = int(cfg["max_entries"])
    size_usd = float(cfg["position_size_usd"])
    fees_rate = cfg["fees_pct"] / 100.0
    # ✅ R55 — السقف الرقمي للصفقات المتزامنة: None = السلوك التاريخي
    # (allow_overlap البولياني يحكم)، وإلا فهو الحاكم الأوحد (1..10).
    max_concurrent_cap = cfg.get("max_concurrent_positions")
    max_open_observed = 0
    # --- ROUND40.1 ---
    sma_bars = int(cfg["trend_filter_sma_bars"])
    min_floor_dist = float(cfg["min_floor_distance_pct"]) / 100.0
    trail_arm = float(cfg["tp_trail_arm_pct"]) / 100.0
    trail_gb = float(cfg["tp_trail_giveback_pct"]) / 100.0
    trail_on = trail_arm > 0
    # --- ROUND42 (ترقية ج41): التريلينق الحرفي — له الأولوية المطلقة ---
    # عند تفعيله تُلغى كل آليات الخروج الأخرى (TP الثابت، وقف الفيبو،
    # الجني المتحرك المشروط) — التريلينق وحده من يعمل:
    #   • القمة تبدأ من سعر تنفيذ الدخول (لحظة الدخول)
    #   • كل قمة شمعة (high) أعلى ترفع السقف — لا ينخفض أبداً
    #   • إغلاق شمعة هبط giveback ٪ من أعلى قمة يغلق الصفقة كاملة
    #     عند سعر ذلك الإغلاق (reason = trailing_stop)
    trailing_literal_on = bool(cfg["use_trailing"]) and float(cfg["trailing_giveback_pct"]) > 0
    giveback_literal = float(cfg["trailing_giveback_pct"]) / 100.0
    # --- ✅ R64 — زر تبديل خروج الفيبو + الوقف النسبي البديل ---
    # fibo_exit_on = خروج «إغلاق شمعة تحت آخر مستوى فيبو» (true = الافتراضي
    # التاريخي بت-بت). عند تعطيله يعمل الوقف النسبي stop_loss_pct إن كان
    # > 0: لمس اللمّة تحت سعر الدخول الأول × (1−النسبة) — تنفيذ عند سعر
    # الوقف، وفجوة هبوط دونه تُنفَّذ عند الافتتاح (نفس دلالات المحرك
    # الرئيسي). التريلينق الحرفي (إن تفعّل) يُلغي كليهما كما يُلغي كل الآليات.
    fibo_exit_on = bool(cfg.get("fibo_floor_exit", True))
    sl_frac_r64 = float(cfg.get("stop_loss_pct", 0.0) or 0.0) / 100.0
    sl_active_r64 = sl_frac_r64 > 0
    # --- ✅ R66: الوضع التراكمي — كل دخول نسبة من الرصيد الجاري ---
    # compounding_on: فقط عند position_sizing='percent_of_equity' — أي
    # حمولة أخرى (غياب الحقل أو fixed_usd) = سلوك اليوم بت-بت حرفياً.
    compounding_on = cfg.get("position_sizing") == "percent_of_equity"
    pct_r66 = float(cfg.get("position_size_pct") or 0.0)
    _seed_src_r66 = (
        initial_capital if initial_capital is not None
        else (cfg.get("initial_capital") if cfg.get("initial_capital") is not None else 10000.0)
    )
    seed_r66 = float(_seed_src_r66)
    equity_r66 = seed_r66          # الرصيد الجاري E — يتحدّث عند كل إغلاق محقق
    liquidated_r66 = False         # جدار التصفية: E ≤ 0 ⇒ لا دورات جديدة
    dust_floored_r66 = 0           # عدد الأحجام المثبتة على أرضية 1$
    first_cycle_usd_r66 = None     # حجم أول دورة (للصدى في capital)

    positions: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    counters = {
        "signals_total": len(by_bar),
        "signals_used": 0,
        "signals_ignored_open": 0,
        "signals_ignored_cooldown": 0,
        "signals_ignored_trend_filter": 0,
        "signals_ignored_floor_distance": 0,
    }
    cooldown_until = -1

    # متوسط متحرك بسيط سببي لفلتر الاتجاه (ROUND40.1) — يحسب مرة واحدة O(N)
    sma_arr: List[Optional[float]] = [None] * N
    if sma_bars > 0:
        acc, cnt = 0.0, 0
        for k in range(N):
            ck = c[k]
            if ck is None:
                acc, cnt = 0.0, 0
                continue
            acc += ck
            cnt += 1
            if cnt > sma_bars:
                acc -= c[k - sma_bars]  # داخل سلسلة non-None متصلة — مضمون
                cnt -= 1
            if cnt == sma_bars:
                sma_arr[k] = acc / sma_bars

    def _trend_ok(bar_i: int) -> bool:
        """فلتر الاتجاه: إغلاق الشمعة فوق SMA (True إذا كان الفلتر معطلاً)."""
        if sma_bars <= 0:
            return True
        s = sma_arr[bar_i] if 0 <= bar_i < N else None
        ck = c[bar_i] if 0 <= bar_i < N else None
        return s is not None and ck is not None and ck > s

    def _floor_dist_ok(e: Dict[str, Any]) -> bool:
        """فلتر المسافة: الأرضية بعيدة كفاية تحت سعر الدخول (True إذا معطّلة)."""
        if min_floor_dist <= 0:
            return True
        try:
            p_, f_ = float(e.get("price")), float(e.get("floor"))
        except (TypeError, ValueError):
            return False
        return (p_ - f_) >= min_floor_dist * p_

    def _cycle_usd() -> float:
        """✅ R66 — حجم دورة جديدة: الثابت التاريخي أو نسبة الرصيد الجاري.

        الوضع الثابت: position_size_usd حرفياً (بت-بت). الوضع التراكمي:
        round(E × pct/100, 2) مع أرضية غبار 1$ (كل تثبيت يُعدّ في
        dust_floored_r66 — الدخول الأول والتعزيزان يتشاركون نفس القيمة
        داخل الدورة فالعداد يزداد مرة لكل دورة مُثبّتة).
        """
        if not compounding_on:
            return size_usd
        nonlocal dust_floored_r66
        raw_usd = round(equity_r66 * pct_r66 / 100.0, 2)
        if raw_usd < 1.0:
            dust_floored_r66 += 1
            raw_usd = 1.0
        return raw_usd

    def _open_position(entry: Dict[str, Any], exec_bar: int, exec_price: float) -> None:
        first_price = exec_price
        # ✅ R66 — حجم هذه الدورة (الثابت أو نسبة الرصيد لحظة الفتح):
        # التعزيزان يستخدمان نفس القيمة — بنية 1:1:1 محفوظة في الوضعين.
        cycle_usd = _cycle_usd()
        nonlocal first_cycle_usd_r66
        if compounding_on and first_cycle_usd_r66 is None:
            first_cycle_usd_r66 = cycle_usd
        pending: List[Dict[str, Any]] = []
        if max_entries >= 2 and dca1 > 0:
            pending.append({"kind": "dca1", "price": first_price * (1.0 - dca1)})
        if max_entries >= 3 and dca2 > 0:
            pending.append({"kind": "dca2", "price": first_price * (1.0 - dca2)})
        positions.append({
            "trade_id": len(trades) + 1,
            "entry_signal": entry,
            "entry_exec": cfg["entry_exec"],
            "open_bar": exec_bar,
            "open_time": t[exec_bar],
            "floor": entry["floor"],
            "floor_meta": entry["floor_meta"],
            "entries": [{
                "kind": "entry", "bar": exec_bar, "time": t[exec_bar],
                "price": exec_price, "usd": cycle_usd, "qty": cycle_usd / exec_price,
            }],
            # ✅ R66 — حجم الدورة المُجمّد لحظة الفتح (E لا يتغير أثناء الدورة)
            "cycle_usd": cycle_usd,
            "pending_dcas": pending,
            "fired_dcas": [],
            "disabled_dcas": [p["kind"] for p in pending if p["price"] < entry["floor"]],
            "mfe_pct": 0.0,
            "mae_pct": 0.0,
            "trail_armed": False,
            "trail_peak": None,
            "trail_armed_bar": None,
            # ROUND42 — قمة التريلينق الحرفي تبدأ من سعر تنفيذ الدخول
            "peak_price": exec_price,
        })

    def _avg_price(pos: Dict[str, Any]) -> float:
        invested = sum(en["usd"] for en in pos["entries"])
        qty = sum(en["qty"] for en in pos["entries"])
        return invested / qty if qty > 0 else 0.0

    def _tp_price(pos: Dict[str, Any]) -> float:
        base = pos["entries"][0]["price"] if cfg["tp_reference"] == "first" else _avg_price(pos)
        return base * (1.0 + tp_pct)

    def _trail_view(pos: Dict[str, Any]) -> Dict[str, Any]:
        """كتلة trail في الصفقة — حرفياً مثل السيرفر الحالي عند تعطيل
        التريلينق (توافق بت-بت)، وتُثري بكتلة literal عند تفعيله."""
        view: Dict[str, Any] = {
            "enabled": trail_on,
            "armed": pos["trail_armed"],
            "armed_at_bar": pos["trail_armed_bar"],
            "peak_price": pos["trail_peak"],
        }
        if trailing_literal_on:
            view["literal"] = {
                "enabled": True,
                "giveback_pct": float(cfg["trailing_giveback_pct"]),
                "peak_price": pos.get("peak_price"),
            }
        return view

    def _close_position(pos: Dict[str, Any], bar: int, price: float, reason: str,
                        extra: Optional[Dict[str, Any]] = None) -> None:
        nonlocal equity_r66, liquidated_r66
        invested = sum(en["usd"] for en in pos["entries"])
        qty = sum(en["qty"] for en in pos["entries"])
        exit_notional = qty * price
        fees = fees_rate * (invested + exit_notional)
        pnl = exit_notional - invested - fees
        # ✅ R66 — التراكم: المحقق فقط يحدّث الرصيد الجاري (صفقات نهاية
        # البيانات غير محققة — أرباحها لا تدخل E). العمولات مخصومة من
        # pnl أصلاً فتُحسم من الرصيد تلقائياً. جدار التصفية: E ≤ 0 يوقف
        # فتح أي دورة جديدة (يُفحص في بوابة الإشارات).
        eq_before_r66 = equity_r66
        eq_after_r66 = equity_r66
        if compounding_on and reason != "end_of_data":
            equity_r66 = equity_r66 + pnl
            eq_after_r66 = equity_r66
            if equity_r66 <= 0.0:
                liquidated_r66 = True
        exit_record: Dict[str, Any] = {"reason": reason, "bar": bar, "time": t[bar], "price": price}
        if extra:  # ✅ R64 — توثيق إضافي للخروج (مثل سعر الوقف النسبي)
            exit_record.update(extra)
        if trailing_literal_on:
            # توثيق قمة التريلينق الحرفي لحظة الخروج (أعلى قمة منذ الدخول)
            exit_record["peak_price"] = pos.get("peak_price")
        trade_rec = {
            "trade_id": pos["trade_id"],
            "opened_at_bar": pos["open_bar"],
            "opened_at_time": pos["open_time"],
            "signal": {
                "bar": pos["entry_signal"]["bar"],
                "time": pos["entry_signal"].get("time"),
                "signals": list(pos["entry_signal"]["signals"]),
                "price": pos["entry_signal"]["price"],
            },
            "entry_exec": pos["entry_exec"],
            "floor": {
                "value": pos["floor"],
                "meta": pos["floor_meta"],
            },
            "entries": [dict(en) for en in pos["entries"]],
            "exit": exit_record,
            "was_open_at_end": reason == "end_of_data",
            "bars_held": bar - pos["open_bar"],
            "invested_usd": invested,
            "qty_total": qty,
            "avg_price": invested / qty if qty else 0.0,
            "exit_notional_usd": exit_notional,
            "fees_usd": fees,
            "pnl_usd": pnl,
            "pnl_pct": (pnl / invested * 100.0) if invested else 0.0,
            "dca_fired": list(pos["fired_dcas"]),
            "dca_disabled_outside_range": list(pos["disabled_dcas"]),
            "mfe_pct": pos["mfe_pct"],
            "mae_pct": pos["mae_pct"],
            "trail": _trail_view(pos),
        }
        # ✅ R66 — صدى نمو الأحجام لكل صفقة (الوضع التراكمي فقط —
        # الحمولات الثابتة تبقى بمفاتيحها التاريخية بت-بت).
        if compounding_on:
            trade_rec["equity_before_usd"] = round(eq_before_r66, 6)
            trade_rec["equity_after_usd"] = round(eq_after_r66, 6)
            trade_rec["cycle_usd"] = pos.get("cycle_usd")
        trades.append(trade_rec)

    for i in range(N):
        # ============ 1) إدارة المراكز المفتوحة عند الشمعة i ============
        for pos in list(positions):
            # الإدارة تبدأ بعد شمعة الدخول (signal_close) أو داخلها بعد الافتتاح (next_open)
            if cfg["entry_exec"] == "signal_close" and i <= pos["open_bar"]:
                continue
            if i < pos["open_bar"]:
                continue
            hi, lo, cl = h[i], l[i], c[i]
            first_price = pos["entries"][0]["price"]

            # تتبع MFE/MAE نسبةً لسعر الدخول الأول
            if hi is not None:
                pos["mfe_pct"] = max(pos["mfe_pct"], (hi / first_price - 1.0) * 100.0)
            if lo is not None:
                pos["mae_pct"] = min(pos["mae_pct"], (lo / first_price - 1.0) * 100.0)

            # (أ٠) التريلينق الحرفي (ROUND42 — ترقية ج41): كل ارتفاع يصل
            #      إليه السعر يرفع السقف؛ قمة الشمعة نفسها تُحتسب قبل فحص
            #      خروجها. الخروج الوحيد هنا: إغلاق الشمعة هبط giveback ٪
            #      من أعلى قمة منذ لحظة الدخول — عندها تُغلق الصفقة كاملة
            #      عند سعر ذلك الإغلاق (لا لمس لمّة ولا تنفيذ عند الافتتاح:
            #      الحرفية المطلوبة هي إغلاقٌ مؤكّد تحت السقف).
            if trailing_literal_on:
                if hi is not None and hi > pos["peak_price"]:
                    pos["peak_price"] = hi
                if cl is not None and cl <= pos["peak_price"] * (1.0 - giveback_literal):
                    _close_position(pos, i, cl, "trailing_stop")
                    positions.remove(pos)
                    cooldown_until = max(cooldown_until, i + cfg["cooldown_bars"])
                    continue

            # (أ) وقف الخسارة — ✅ R64 زر التبديل:
            #     • fibo_floor_exit=true (الافتراضي التاريخي): إغلاق الشمعة
            #       تحت أدنى مستوى فيبو يغلق الصفقة كاملة عند سعر الإغلاق.
            #     • fibo_floor_exit=false: خروج الفيبو معطّل — يعمل بدله
            #       الوقف النسبي (إن كان stop_loss_pct > 0): لمس اللمّة تحت
            #       الدخول الأول × (1−stop_loss_pct/100) يغلق عند سعر الوقف،
            #       وفجوة هبوط تحت الوقف تُنفَّذ عند الافتتاح (نفس دلالات
            #       المحرك الرئيسي). كلاهما مُلغى مع التريلينق الحرفي.
            if not trailing_literal_on:
                if fibo_exit_on:
                    if cl is not None and cl < pos["floor"]:
                        _close_position(pos, i, cl, "fib_break")
                        positions.remove(pos)
                        cooldown_until = max(cooldown_until, i + cfg["cooldown_bars"])
                        continue
                elif sl_active_r64:
                    _sl_price_r64 = first_price * (1.0 - sl_frac_r64)
                    if lo is not None and lo <= _sl_price_r64:
                        _fill_r64 = _sl_price_r64
                        if o[i] is not None and o[i] < _sl_price_r64:
                            _fill_r64 = o[i]  # فجوة هبوط تحت الوقف — تنفيذ عند الافتتاح
                        _close_position(pos, i, _fill_r64, "stop_loss",
                                        extra={"stop_price": _sl_price_r64})
                        positions.remove(pos)
                        cooldown_until = max(cooldown_until, i + cfg["cooldown_bars"])
                        continue

            # (ب) الجني المتحرك المشروط (ROUND40.1 — مُلغى مع التريلينق الحرفي):
            #     يتفعّل عند بلوغ الربح غير المحقق ذراع التفعيل (من سعر الدخول
            #     الأول) وعندها يُلغى الهدف الثابت ويتولى التتبع الإغلاق عند
            #     تراجع giveback من أعلى قمة. لا يُقيَّم التوقف في شمعة التفعيل
            #     نفسها (تحفظاً — ترتيب اللمسات داخل الشمعة مجهول).
            if trail_on and not trailing_literal_on:
                if not pos["trail_armed"]:
                    if hi is not None and hi >= first_price * (1.0 + trail_arm):
                        pos["trail_armed"] = True
                        pos["trail_peak"] = hi
                        pos["trail_armed_bar"] = i
                elif lo is not None:
                    stop_price = pos["trail_peak"] * (1.0 - trail_gb)
                    if lo <= stop_price:
                        fill = stop_price
                        if o[i] is not None and o[i] < stop_price:
                            fill = o[i]  # فجوة هبوط تحت نقطة التتبع — تنفيذ عند الافتتاح
                        _close_position(pos, i, fill, "trail_stop")
                        positions.remove(pos)
                        cooldown_until = max(cooldown_until, i + cfg["cooldown_bars"])
                        continue
                    if hi is not None and hi > pos["trail_peak"]:
                        pos["trail_peak"] = hi

            # (ج) التعزيزات: لمس اللمّة والزناد داخل النطاق (>= الأرضية)
            if lo is not None:
                for pend in list(pos["pending_dcas"]):
                    if len(pos["entries"]) >= max_entries:
                        break
                    if pend["price"] >= pos["floor"] and lo <= pend["price"]:
                        fill = pend["price"]
                        if o[i] is not None and o[i] < fill:
                            fill = o[i]  # فجوة هبوط تحت الزناد — أمر الحد يُنفّذ عند الافتتاح (أفضل للمشتري)
                        pos["entries"].append({
                            "kind": pend["kind"], "bar": i, "time": t[i],
                            # ✅ R66 — التعزيز بنفس حجم دورته (نفس نسبة الرصيد
                            # نفسه لحظة الفتح — بنية 1:1:1 محفوظة في الوضعين)
                            "price": fill, "usd": pos["cycle_usd"],
                            "qty": pos["cycle_usd"] / fill,
                        })
                        pos["fired_dcas"].append(pend["kind"])
                        pos["pending_dcas"].remove(pend)

            # (د) جني الربح الثابت: لمس القمة للهدف (يُلغى بعد تفعيل التتبع
            #     ومع التريلينق الحرفي — التريلينق هو من يعمل وحده)
            if not trailing_literal_on and not (trail_on and pos["trail_armed"]):
                tp = _tp_price(pos)
                if hi is not None and hi >= tp:
                    fill = tp
                    if o[i] is not None and o[i] > tp:
                        fill = o[i]  # فجوة صعود فوق الهدف — تنفيذ عند الافتتاح (أفضل للبائع)
                    _close_position(pos, i, fill, "take_profit")
                    positions.remove(pos)
                    cooldown_until = max(cooldown_until, i + cfg["cooldown_bars"])

        # ============ 2) فتح مراكز جديدة عند إشارات الشمعة i ============
        if len(positions) > max_open_observed:
            max_open_observed = len(positions)
        entry = by_bar.get(i)
        if entry is not None:
            # ✅ R55 — بوابة السقف الرقمي: عند تحديد max_concurrent_positions
            # (من جذر الطلب max_positions) يحكم وحده؛ وإلا السلوك التاريخي
            # (allow_overlap=false ⇒ صفقة واحدة · true ⇒ بلا سقف).
            if max_concurrent_cap is not None:
                blocked_by_open = len(positions) >= int(max_concurrent_cap)
            else:
                blocked_by_open = (not cfg["allow_overlap"]) and bool(positions)
            # ✅ R66 — جدار التصفية (الوضع التراكمي فقط): استنفاد الرصيد
            # الجاري (E ≤ 0) يوقف فتح أي دورة جديدة فوراً — كل إشارة لاحقة
            # تُوثّق في عدّاد signals_ignored_liquidated (نفس فلسفة المحرك
            # الرئيسي: جدار −100٪ الصلب). الوضع الثابت لا يدخل هذا الفرع
            # إطلاقاً (شرط compounding_on خاطئ دائماً — بت-بت محفوظ).
            if compounding_on and equity_r66 <= 0.0:
                # ✅ R66 — مفتاح كسول: يُنشأ فقط عند أول تجاهل فعلي بعد
                # التصفية، فلا يظهر مطلقاً في entry_signals للحمولات الثابتة
                # (توافق رجعي بت-بت مع R64) ولا يُزداد بمفتاح غير مهيأ.
                counters["signals_ignored_liquidated"] = (
                    counters.get("signals_ignored_liquidated", 0) + 1
                )
            elif blocked_by_open:
                counters["signals_ignored_open"] += 1
            elif i <= cooldown_until:
                counters["signals_ignored_cooldown"] += 1
            elif not _trend_ok(i):
                counters["signals_ignored_trend_filter"] += 1
            elif not _floor_dist_ok(entry):
                counters["signals_ignored_floor_distance"] += 1
            else:
                if cfg["entry_exec"] == "next_open":
                    if i + 1 < N and o[i + 1] is not None:
                        _open_position(entry, i + 1, o[i + 1])
                        counters["signals_used"] += 1
                    else:
                        counters["signals_ignored_cooldown"] += 1  # لا شمعة تالية — لا تنفيذ
                else:
                    price = entry["price"] if entry["price"] is not None else c[i]
                    if price is not None:
                        _open_position(entry, i, price)
                        counters["signals_used"] += 1

    # ============ 3) نهاية البيانات: الصفقات المفتوحة تُقيَّم بالأخير ============
    last_close = c[N - 1] if N else None
    for pos in positions:
        if last_close is not None:
            _close_position(pos, N - 1, last_close, "end_of_data")
        else:
            _close_position(pos, N - 1, pos["entries"][0]["price"], "end_of_data")

    if invalid_entries:
        result["notes"].append(
            f"تم استبعاد {invalid_entries} إشارة دخول غير صالحة (بلا أرضية فيبو أو خارج النافذة)."
        )
    result["trades"] = trades
    # ✅ R66 — حالة الرصيد الجاري للملخص الموسع (الوضع التراكمي فقط؛
    # الوضع الثابت يمرّر None فيبقى الملخص بمفاتيحه التاريخية بت-بت).
    equity_state_r66: Optional[Dict[str, Any]] = None
    if compounding_on:
        equity_state_r66 = {
            "initial": seed_r66,
            "final": equity_r66,
            "liquidated": liquidated_r66,
            "dust_floored": dust_floored_r66,
            "first_cycle_usd": first_cycle_usd_r66,
        }
        result["compounding_audit"] = _compounding_audit(trades, seed_r66, pct_r66)
        result["notes"].append(
            f"الوضع التراكمي (R66): كل دخول = {pct_r66:g}٪ من الرصيد الجاري — "
            f"البذرة {seed_r66:g}$، الرصيد النهائي {round(equity_r66, 2):g}$. "
            f"position_size_usd في الملخص يصدى بحجم أول دورة "
            f"({round(first_cycle_usd_r66, 2) if first_cycle_usd_r66 is not None else '—'}$) "
            f"للتوافق البنيوي — الأحجام الفعلية لكل دورة في trades[].entries[].usd."
        )
        if liquidated_r66:
            result["notes"].append(
                "جدار التصفية (R66): استُنفد الرصيد الجاري (E ≤ 0) — توقف فتح أي دورة "
                "جديدة فوراً (account_liquidated=true)."
            )
    result["summary"] = _summarize(trades, counters, cfg, max_open_observed=max_open_observed,
                                   equity_state=equity_state_r66)
    return result


def _compounding_audit(
    trades: List[Dict[str, Any]], seed: float, pct: float,
) -> Dict[str, Any]:
    """✅ R66 — التدقيق الرياضي الذاتي للوضع التراكمي (نمط math_audit ج12).

    يعيد بناء تسلسل الرصيد من الأحداث الزمنية ويتحقق بت-بت:
      1) كل دخول (entry|dca1|dca2) == max(1$, round(E لحظة فتح الدورة × pct/100, 2))
      2) كل إغلاق محقق: equity_before_usd == E المعاد بناؤه لحظة الإغلاق،
         و equity_after_usd == equity_before_usd + pnl_usd (المحقق فقط —
         صفقات نهاية البيانات لا تحدّث E)
    الترتيب الزمني الحتمي داخل البار الواحد (يطابق الحلقة الرئيسية):
      0) فتح next_open (زمن الافتتاح — سبق إدارة الشمعة)
      1) الإغلاقات (القسم 1 — خلال الشمعة)
      2) فتح signal_close (زمن الإغلاق — بعد إدارة الشمعة)
    """
    def _phase(kind: int, tr: Dict[str, Any]) -> int:
        if kind == 0:  # إغلاق
            return 1
        return 0 if str(tr.get("entry_exec")) == "next_open" else 2

    events: List[Tuple[int, int, Dict[str, Any]]] = []
    for tr in trades:
        events.append((int(tr["opened_at_bar"]), 1, tr))   # فتح
        events.append((int(tr["exit"]["bar"]), 0, tr))     # إغلاق
    events.sort(key=lambda e: (e[0], _phase(e[1], e[2]), e[1]))

    checked = 0
    max_err = 0.0
    E = float(seed)
    for _bar, kind, tr in events:
        if kind == 1:  # فتح دورة — كل الأحجام من E هذه اللحظة (1:1:1)
            expected = round(E * pct / 100.0, 2)
            if expected < 1.0:
                expected = 1.0
            for en in tr["entries"]:
                err = abs(float(en["usd"]) - expected)
                if err > max_err:
                    max_err = err
                checked += 1
        else:  # إغلاق — المحقق فقط يحدّث E
            if tr["exit"]["reason"] != "end_of_data":
                err_before = abs(float(tr.get("equity_before_usd", E)) - E)
                E += float(tr["pnl_usd"])
                err_after = abs(float(tr.get("equity_after_usd", E)) - E)
                max_err = max(max_err, err_before, err_after)
                checked += 1
    return {
        "mode": "percent_of_equity",
        "checked_entries": checked,
        "max_abs_error": round(max_err, 10),
        "formula": (
            "entry_usd == max(1, round(E * pct/100, 2)) for entry|dca1|dca2 "
            "من E لحظة فتح الدورة؛ E += pnl_usd عند كل إغلاق محقق فقط"
        ),
        "seed_usd": round(float(seed), 6),
        "final_equity_usd": round(E, 6),
        "consistent": bool(max_err <= 0.011),
    }


def _summarize(trades: List[Dict[str, Any]], counters: Dict[str, int], cfg: Dict[str, Any],
              max_open_observed: int = 0,
              equity_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """ملخص تنفيذي للصفقات + منحنى رأس المال التراكمي.

    equity_state: ✅ R66 — حالة الرصيد الجاري (الوضع التراكمي فقط).
    None = الوضع الثابت: المخرجات بمفاتيحها التاريخية بت-بت حرفياً.
    """
    closed = [tr for tr in trades if not tr["was_open_at_end"]]
    open_end = [tr for tr in trades if tr["was_open_at_end"]]
    wins = [tr for tr in closed if tr["pnl_usd"] > 0]
    losses = [tr for tr in closed if tr["pnl_usd"] <= 0]
    gross_win = sum(tr["pnl_usd"] for tr in wins)
    gross_loss = abs(sum(tr["pnl_usd"] for tr in losses))
    realized = sum(tr["pnl_usd"] for tr in closed)
    unrealized = sum(tr["pnl_usd"] for tr in open_end)

    equity_curve = []
    cum = 0.0
    # ✅ R66 — في الوضع التراكمي يُرفق الرصيد المطلق (initial + cumulative)
    # بكل نقطة ليُرسم منحنى الرصيد مباشرة بلا أي حساب في الواجهة.
    compounding_view = equity_state is not None
    eq_usd_r66 = float(equity_state["initial"]) if compounding_view else 0.0
    for tr in sorted(closed, key=lambda x: x["exit"]["bar"]):
        cum += tr["pnl_usd"]
        point: Dict[str, Any] = {
            "trade_id": tr["trade_id"],
            "closed_at_bar": tr["exit"]["bar"],
            "closed_at_time": tr["exit"]["time"],
            "realized_pnl_usd": round(tr["pnl_usd"], 6),
            "cumulative_pnl_usd": round(cum, 6),
        }
        if compounding_view:
            eq_usd_r66 += tr["pnl_usd"]
            point["equity_usd"] = round(eq_usd_r66, 6)
        equity_curve.append(point)

    tp_exits = sum(1 for tr in closed if tr["exit"]["reason"] == "take_profit")
    trail_exits = sum(1 for tr in closed if tr["exit"]["reason"] == "trail_stop")
    trail_literal_exits = sum(1 for tr in closed if tr["exit"]["reason"] == "trailing_stop")
    fib_exits = sum(1 for tr in closed if tr["exit"]["reason"] == "fib_break")

    def _avg(vals: List[float]) -> Optional[float]:
        return round(sum(vals) / len(vals), 4) if vals else None

    # ✅ R66 — أقصى تعرض للدورة الواحدة: الوضع التراكمي يقيسه من أكبر حجم
    # دورة فعلي (الأحجام تنمو مع الرصيد) بدل الثابت التاريخي.
    _max_exposure_usd = round(cfg["position_size_usd"] * cfg["max_entries"], 6)
    if equity_state is not None:
        _cycles = [float(tr["entries"][0]["usd"]) for tr in trades if tr.get("entries")]
        _max_exposure_usd = round((max(_cycles) if _cycles else 0.0) * cfg["max_entries"], 6)

    profit_factor: Optional[float]
    if gross_loss > 0:
        profit_factor = round(gross_win / gross_loss, 4)
    else:
        profit_factor = None if gross_win == 0 else float("inf")

    exits_view: Dict[str, Any] = {
        "take_profit": tp_exits,
        "trail_stop": trail_exits,
        "fib_break": fib_exits,
        "end_of_data": len(open_end),
    }
    # ROUND42 — مفتاح التريلينق الحرفي يظهر فقط عند تفعيله (توابت بت-بت عند التعطيل)
    if cfg.get("use_trailing"):
        exits_view["trailing_stop"] = trail_literal_exits
    # ✅ R64 — عدّاد الوقف النسبي البديل يظهر فقط عند تعطيل خروج الفيبو
    # (توافق بت-بت: الحمولات التاريخية كلها fibo_floor_exit=true ⇒ المفتاح غائب)
    if not cfg.get("fibo_floor_exit", True):
        exits_view["stop_loss"] = sum(
            1 for tr in closed if tr["exit"]["reason"] == "stop_loss"
        )

    return {
        "entry_signals": counters,
        "trades_total": len(trades),
        "trades_closed": len(closed),
        "trades_open_at_end": len(open_end),
        "exits": exits_view,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(closed) * 100.0, 2) if closed else None,
        "pnl": {
            "realized_usd": round(realized, 6),
            "unrealized_usd_open_at_end": round(unrealized, 6),
            "total_usd": round(realized + unrealized, 6),
            "total_fees_usd": round(sum(tr["fees_usd"] for tr in trades), 6),
            "avg_per_trade_pct": _avg([tr["pnl_pct"] for tr in trades]),
            "best_trade_pct": round(max((tr["pnl_pct"] for tr in trades), default=0.0), 4),
            "worst_trade_pct": round(min((tr["pnl_pct"] for tr in trades), default=0.0), 4),
            "profit_factor": profit_factor,
        },
        "capital": {
            "position_size_usd": cfg["position_size_usd"],
            "max_entries_per_trade": cfg["max_entries"],
            "total_invested_usd": round(sum(tr["invested_usd"] for tr in trades), 6),
            "max_exposure_per_trade_usd": _max_exposure_usd,
            # ✅ R55 — شفافية السقف الرقمي: المفعّل فعلاً + أقصى تزامن لوحظ
            "max_concurrent_positions": cfg.get("max_concurrent_positions"),
            "overlap_mode": (
                "numeric" if cfg.get("max_concurrent_positions") is not None
                else ("legacy-unlimited" if cfg.get("allow_overlap") else "legacy-single")
            ),
            "max_open_positions_observed": int(max_open_observed),
            # ✅ R66 — توسعة الوضع التراكمي (تظهر فقط عند تفعيله — الحمولات
            # الثابتة تبقى بمفاتيحها التاريخية بت-بت حرفياً):
            #   position_size_usd فوق يُستبدل بحجم أول دورة (التوافق البنيوي —
            #   الأحجام الفعلية في trades[].entries[].usd).
            **(
                {
                    "position_sizing": cfg.get("position_sizing"),
                    "position_size_pct": cfg.get("position_size_pct"),
                    "initial_capital_usd": round(float(equity_state["initial"]), 6),
                    "final_equity_usd": round(float(equity_state["final"]), 6),
                    "equity_growth_pct": (
                        round((float(equity_state["final"]) / float(equity_state["initial"]) - 1.0) * 100.0, 6)
                        if float(equity_state["initial"]) > 0 else None
                    ),
                    "dust_floored_entries": int(equity_state["dust_floored"]),
                    "account_liquidated": bool(equity_state["liquidated"]),
                    "position_size_usd": (
                        round(float(equity_state["first_cycle_usd"]), 2)
                        if equity_state.get("first_cycle_usd") is not None else None
                    ),
                }
                if equity_state is not None else {}
            ),
        },
        "dca_usage": {
            "dca1_fired": sum(1 for tr in trades if "dca1" in tr["dca_fired"]),
            "dca2_fired": sum(1 for tr in trades if "dca2" in tr["dca_fired"]),
            "avg_bars_held": _avg([float(tr["bars_held"]) for tr in trades]),
        },
        "equity_curve": equity_curve,
    }


# ---------------------------------------------------------------------------
# 4) المُهايئات — من مخرجات استراتيجيات البطل إلى مدخلات المحرك
# ---------------------------------------------------------------------------
def _is_buy_entry(sig: Dict[str, Any]) -> bool:
    """إشارة دخول صالحة: side='buy' واسمها من عائلة Entry (يستثني Touch)."""
    return str(sig.get("side", "")).lower() == "buy" and "Entry" in str(sig.get("signal", ""))


def _floor_ratio_tag(p1: float, p2: float) -> str:
    """وسم المستوى الأدنى: '0' إذا كانت p1 الأرضية (ساق صاعدة) وإلا '1'."""
    return "0" if p1 <= p2 else "1"


def extract_entries_zzfib(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """من مخرجات zzfib (المحرك العادي) — الأرضية من ساق الزقزاق الحية عند الإشارة.

    المصدر: series.zzf_p1/zzf_p2 عند بار الإشارة (قيم سببية 100% — الساق
    كما كانت معروفة لحظة الإشارة). الأرضية = min(p1, p2) = أدنى مستويات
    فيبو (0 أو 1) للساق المرجعية.
    """
    series = payload.get("series") or {}
    p1s: List[Optional[float]] = list(series.get("zzf_p1") or [])
    p2s: List[Optional[float]] = list(series.get("zzf_p2") or [])
    dirs: List[Optional[float]] = list(series.get("zzf_dir") or [])
    out: List[Dict[str, Any]] = []
    for sig in payload.get("signals") or []:
        if not _is_buy_entry(sig):
            continue
        try:
            i = int(sig.get("bar"))
            price = float(sig.get("price"))
        except (TypeError, ValueError):
            continue
        if i < 0 or i >= len(p1s) or i >= len(p2s):
            continue
        a, b = p1s[i], p2s[i]
        if a is None or b is None:
            continue  # لا ساق مرجعية عند الإشارة — لا أرضية
        out.append({
            "bar": i,
            "time": sig.get("time"),
            "price": price,
            "floor": float(min(a, b)),
            "floor_meta": {
                "source": "zzfib-leg",
                "p1": a,
                "p2": b,
                "dir": dirs[i] if i < len(dirs) else None,
                "ratio_tag": _floor_ratio_tag(a, b),
            },
            "signal": sig,
        })
    return out


def extract_entries_zzfib_e2e(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """من مخرجات zzfib_e2e و zzfib_e2e_trendy — الأرضية من نطاق الإشارة نفسه.

    كل إشارة تحمل range_index؛ الأرضية = min(p1, p2) لنطاقها (المستوى 0
    للساق الصاعدة و1 للهابطة — أدنى مستويي الفيبو حرفياً).
    """
    ranges: Dict[int, Dict[str, Any]] = {}
    for rg in payload.get("ranges") or []:
        try:
            ranges[int(rg.get("index"))] = rg
        except (TypeError, ValueError):
            continue
    cur = (payload.get("current") or {}).get("range") or {}
    try:
        cur_idx = int(cur.get("index"))
    except (TypeError, ValueError):
        cur_idx = None
    if cur_idx is not None and cur_idx not in ranges:
        ranges[cur_idx] = cur

    out: List[Dict[str, Any]] = []
    for sig in payload.get("signals") or []:
        if not _is_buy_entry(sig):
            continue
        try:
            ri = int(sig.get("range_index"))
        except (TypeError, ValueError):
            ri = cur_idx
        rg = ranges.get(ri)
        if not rg:
            continue
        p1 = (rg.get("p1") or {}).get("price")
        p2 = (rg.get("p2") or {}).get("price")
        if p1 is None or p2 is None:
            continue
        try:
            price = float(sig.get("price"))
        except (TypeError, ValueError):
            continue
        out.append({
            "bar": int(sig.get("bar")),
            "time": sig.get("time"),
            "price": price,
            "floor": float(min(p1, p2)),
            "floor_meta": {
                "source": "range",
                "range_index": rg.get("index"),
                "dir": rg.get("dir"),
                "p1": rg.get("p1"),
                "p2": rg.get("p2"),
                "ratio_tag": _floor_ratio_tag(float(p1), float(p2)),
            },
            "signal": sig,
        })
    return out


def extract_entries_for_strategy(strategy: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """المُهايئ الموحد: اسم الاستراتيجية → مخرجاتها → مدخلات محرك الخروج."""
    s = str(strategy).strip().lower()
    if s == "zzfib":
        return extract_entries_zzfib(payload)
    # 🔥 R69: zzfib_e2e_blazing تحمل نفس شكل حمولة e2e/الترندية (ranges/signals)
    # — نفس المُهايئ (الأرضية = min(p1,p2) لنطاق الإشارة، ويشمل إشارات N5/N6).
    if s in ("zzfib_e2e", "zzfib_e2e_trendy", "zzfib_e2e_blazing"):
        return extract_entries_zzfib_e2e(payload)
    raise ValueError(
        f"استراتيجية غير مدعومة: {strategy!r} — المدعومة: zzfib · zzfib_e2e · "
        "zzfib_e2e_trendy · zzfib_e2e_blazing (الملتهبة — R69)"
    )
