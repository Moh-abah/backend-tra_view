# =============================================================================
# ✅ الجولة 12 — قوالب الاستراتيجيات الرسمية (presets)
# =============================================================================
# المصدر: حمولة البطل المُثبَّتة بحيا من الواجهة (backtest1/run → backtest/run):
#   ZigZag HL v2 — ZERO FEE · BTCUSDT · 1h · دخول قاع زيجزاق مؤكد أعلى من سابقه
#   (Higher Low Structure) · الخروج عند تأكيد قمة · SL 2% · عمولة 0.
#
# ملاحظات مثبتة بهذا التشغيل (العقد):
#   - ✅ R58 — في وضع percentage أصبحت القيمة نسبة مئوية حقيقية: رأس المال
#     الكامل = 100 (كانت 1.0 كسراً — نفس السلوك تماماً، صيغة جديدة بلا لبس
#     «1%» في الواجهة = 1 فعلاً).
#   - الشكل الصحيح للدمج المنطقي: {"type": "and", "conditions": [...]}
#     وليس {"type":"composite","logic":"and"} (الآن يُوحَّد تلقائياً مع تحذير،
#     وأي شكل غير معروف يُرفض برسالة واضحة).
#   - fill_model: "next_open" (الافتراضي — نفس سلوك الإصدارات السابقة، أعاد
#     10 صفقات · −1.86% على حمولة البطل) أو "signal_close" (تنفيذ عند إغلاق
#     شمعة الإشارة — أقرب لمحاكاة الواجهة المحلية التي أعطت ~+112%).
#   - ✅ الجولة 13 — إبادة العمولة (سياسة Zero-Fee): لا عمولة ولا انزلاق في النظام نهائياً.
#     الحقلان commission_rate و slippage_percent deprecated — غيابهما أو 0 يُقبل بصمت،
#     وأي قيمة > 0 تُرفض بـ 422 برسالة عربية صريحة (لا تطبيق صامت إطلاقاً).
#   - ✅ الجولة 13 — عقد الدقة المتناهية: بلا أي تقريب (float64 كاملة)،
#     price_delta_pct = (exit − entry) / entry × 100 × direction،
#     result_pct = price_delta_pct، pnl = (exit − entry) × units × direction − 0،
#     total_pnl_percent = Σpnl / initial_capital × 100، تسامح math_audit = 1e-9.
# =============================================================================

from typing import Any, Dict, List

__all__ = ["CHAMPION_ZIGZAG_HL_V2", "ZLF_TRIPLE_SIGNAL", "ZLF_E2E_TRIPLE_SIGNAL",
           "ZLF_E2E_TRENDY_TRIPLE_SIGNAL", "ZLF_E2E_BLAZING_QUINT_SIGNAL",
           "TRENDY_MACDIZED", "BLAZING_MACDIZED",
           "TRENDY_MACDIZED_RSI_LIGHT", "BLAZING_MACDIZED_RSI_LIGHT",
           "RSI_LIGHT_INSTANCES", "ZLF_ALMIGHTY_QUANTUM_EMA_TRIPLE_SIGNAL",
           "QMOM1_TRIPLE_SIGNAL",
           "get_presets", "PRESET_NOTES"]


CHAMPION_ZIGZAG_HL_V2: Dict[str, Any] = {
    "name": "ZigZag HL v2 — ZERO FEE",
    "timeframe": "1h",
    "market": "crypto",
    "symbols": ["BTCUSDT"],
    "strategy_config": {
        "name": "ZigZag HL v2",
        "base_timeframe": "1h",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_channels",
                "type": "support_resistance",
                "params": {"length": 100},
                "enabled": True,
                "timeframe": "1h",
            }
        ],
        "entry_rules": [
            {
                "name": "Higher Low Structure",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_channels:zz_pivot_low",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_channels:zz_pivot_low",
                            "right_value": "indicator:zigzag_channels:zz_prev_pivot_low",
                        },
                    ],
                },
                "position_side": "long",
                "weight": 1,
                "enabled": True,
            }
        ],
        "exit_rules": [
            {
                "name": "Confirmed Top",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_channels:zz_pivot_high",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 10000,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}

# =============================================================================
# ✅ الجولة 13.2 — الاستراتيجية الواحدة بثلاث إشارات دخول (ZLF v13.2)
# =============================================================================
# المصدر: صور المستخدم الثلاث — إعادة تعريف الإشارات الثلاث حرفياً حسب النص
# المصدَّق من المستخدم (المصفوفة المصادقة من ثلاث جهات: قراءة الوكيلين +
# تصديق المستخدم). هذه رقعة v13.2 — عقد Round 13.0 (Zero-Fee والدقة) لم يُلمس.
#
# القرار الحرفي للمستخدم: «هي تعتبر ثلاث اشارات وكل اشاره تعتبر اشاره دخول —
#  استراتيجية واحدة وثلاث شروط دخول» + «اذا اجت اشاره واحد نعرف ان النظام دخل
#  عبر الاشاره واحد...» (كل صفقة تحمل اسم إشارتها في decision_reason).
#
# البنية (المصفوفة المصادقة):
#   R (المرجع) = الشمعة صاحبة أكبر حجم في النافذة [i−liq_lookback, i−1]
#     بشرط أنها حمراء (close<open) — «أكبر بار سيولة أحمر حجمًا».
#     أكبر شمعة خضراء → لا مرجع (state 0) · لا مرجع → state 0.
#   ref_high = أعلى high لشمعة حمراء داخل النافذة نفسه — محور الاختراق الموحد.
#   G (شمعة الإشارة) = خضراء (close>open) + شرطان مشتركان:
#     1) الانطلاقة: low_G ≥ price(0.382) لآخر ساق مؤكدة (أي اتجاه) —
#        خط 0.618 بمقياس المستخدم (0 عند نهاية المسار) = price(0.382) بالمحرك.
#     2) هيمنة الخضراء: volume_G > حجم كل الشموع الخضراء الواقعة حصرياً بين R وG.
#
# الإشارات الثلاث (تقسيم كامل بعلاقة الحجم مع الحمراء — لا بالإغلاق):
#   S1 — الحالة الأولى: high_G > ref_high  و  volume_G > volume_R
#   S2 — الحالة الثانية: high_G > ref_high  و  volume_G ≤ volume_R
#        («ويبرغم عندها لفل حجم سيولتها من شمعة أكبر بار سيولة أحمر حجمًا»)
#   S3 — الحالة الثالثة: high_G ≤ ref_high  و  volume_G > volume_R
#   الرابعة (لا اختراق + حجم أقل) = لا إشارة عمداً (ضوضاء).
#
# الدخول = عند شمعة الإشارة نفسها (الحدث = الدخول؛ تقييم عند الإغلاق وتنفيذ
#   عند افتتاح التالية — next_open) على أي اتجاه للساق (أُلغي اشتراط الصاعدة —
#   الصورة الثالثة على ساق هابطة). خطة بديلة وحيدة: إن لم تكن الساق مؤكدة لحظة
#   الحدث → أول شمعة تحقق الانطلاقة خلال liq_arm_bars (FIFO).
# SFP = إشارة رابعة اختيارية مطفأة افتراضياً (liq_sfp_signals=false) — لا تلوث
#   decision_reason إطلاقاً في الإعداد المعتمد.
#
# الخروج: افتراضي مؤقت (provisional) — انقلاب الساق إلى هابطة (تأكيد قمة،
#   نفس روح البطل) + SL 2% · خيار مقترح من الصور نفسها (هدف = قمة الحركة
#   الحمراء) — القرار النهائي للمستخدم.
# =============================================================================

ZLF_TRIPLE_SIGNAL: Dict[str, Any] = {
    "name": "ZLF — ZigZag Liquidity Fib · 3 Entry Signals — ZERO FEE",
    "timeframe": "1h",
    "market": "crypto",
    "symbols": ["BTCUSDT"],
    "strategy_config": {
        "name": "ZLF — ZigZag Liquidity Fibonacci (3 Entry Signals)",
        "base_timeframe": "1h",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib",
                "type": "support_resistance",
                "params": {
                    # ✅ الجولة 19 (ROUND19): زقزاق TradingView/MT4 الكلاسيكي —
                    # الأطراف على القصوى الحقيقية (high/low) بعتبة انحراف نسبية —
                    # مطابقة شكل TV (طلب صاحب القرار — إثبات التشخيص:
                    # verify/ROUND19-DIAGNOSIS.py). الوضع القديم luxalgo
                    # متاح بمعامل mode="luxalgo" (توافق رجعي، غير مستخدم هنا).
                    "mode": "tradingview",
                    "depth": 12,          # نافذة القصوى حول الطرف (TV الافتراضي)
                    "deviation": 20,      # وحدات TV (أعشار المئة) ⇒ 2.0% انعكاس أدنى
                    "backstep": 3,        # TV الافتراضي
                    "length": 100,        # للوضع luxalgo الاحتياطي فقط — لا يأثر TV
                    "touch_level": 0.618,
                    # ✅ ROUND21-v2 (2026-11-03): 20 → 240 — نافذة المرجع 4 ساعات
                    # على فريم الدقيقة (إعداد البطل المُختبَر من المستخدم نفسه).
                    # الفحص الجنائي المشترك أثبت أن 20 تولّد «اختراقات» شكلية على
                    # قمم حمراء محلية عمرها دقيقتان (S2 @ 0.585 على 13:16 ضد
                    # ref_high=0.583) بينما 240 تمنعها (ref_high=0.599). القيمة
                    # قابلة للتجاوز صراحةً (إعدادات الاستراتيجية أو معاملات الاستعلام).
                    "liq_lookback": 240,
                    "liq_signals": True,
                    "liq_arm_bars": 60,
                },
                "enabled": True,
                "timeframe": "1h",
            }
        ],
        "entry_rules": [
            {
                "name": "S1 · الحالة الأولى: اختراق قمة الحمراء بحجم أكبر (Breakout + Higher Volume)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib:zzf_entry_s1",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.34,
                "enabled": True,
            },
            {
                "name": "S2 · الحالة الثانية: اختراق قمة الحمراء بحجم أقل (Breakout + Lower Volume) — «ويبرغم عندها لفل حجم سيولتها»",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib:zzf_entry_s2",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
            {
                "name": "S3 · الحالة الثالثة: رفض بلا اختراق بحجم أكبر (No Break + Higher Volume)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib:zzf_entry_s3",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "تأكيد قمة — انقلاب الساق إلى هابطة (Confirmed Top → Down Leg) · افتراضي مؤقت provisional",
                "condition": {
                    "type": "indicator_value",
                    "operator": "<",
                    "left_value": "indicator:zigzag_fib:zzf_dir",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 10000,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


# =============================================================================
# ✅ الجولة 22 (ROUND22) — ZLF-End-To-End — الاستراتيجية الجديدة المنفصلة
# =============================================================================
# صاحب القرار: «اكتب نسخة بدون أن تعدل على النظام الحالي — استنسخها في محرك
# منفصل اسمه ZLF-End-To-End، وإشاراتها تظهر باسم مختلف، وكل شيء حاليا يبقى
# كما هو — هذه استراتيجية جديدة». هذا القالب يعتمد:
#   - المؤشر المنفصل: zigzag_fib_e2e (overlays_zlf_e2e.py — ملف مستقل)
#   - النطاق يُعتمد لحظة ظهور الزقزاق (لا نافذة منزلقة بعدد شموع إطلاقاً)
#   - R = أكبر حمراء حجماً في ساق النطاق (قمة هي خط الاختراق وحجمها المرجع)
#   - S1 اختراق∧حجم أكبر · S2 اختراق∧حجم أقل أو مساوٍ · S3 رفض∧حجم أكبر
#   - الدخول بشمعة الإشارة نفسها (next_open) — لا خطة بديلة (النطاق لا يوجد
#     قبل ظهور الزقزاق)
#   - الخروج: انقلاب النطاق إلى هابطة (zzfe_dir < 0) + SL 2% (نفس روح البطل)
# أسماء الإشارات في decision_reason تحمل «ZLF-E2E» لتمييزها عن محرك ZLF الأصلي.
ZLF_E2E_TRIPLE_SIGNAL: Dict[str, Any] = {
    "name": "ZLF-End-To-End — ZigZag Liquidity Fib (Range-anchored) · 3 Entry Signals — ZERO FEE",
    "timeframe": "1h",
    "market": "crypto",
    "symbols": ["BTCUSDT"],
    "strategy_config": {
        "name": "ZLF-End-To-End (3 Entry Signals — Range-anchored)",
        "base_timeframe": "1h",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib_e2e",
                "type": "support_resistance",
                "params": {
                    # ✅ وضع شارت المنصة المُتحقق منه بالبكسل (luxalgo length=100):
                    # تأكيد الزقزاق بعد 100 شمعة = لحظة «ظهور الزقزاق» المتأخرة
                    # التي بُنيت عليها المواصفة (قمة 15:14 → قاع 15:28 → ظهور 17:08).
                    "mode": "luxalgo",
                    "length": 100,
                    "touch_level": 0.618,
                },
                "enabled": True,
                "timeframe": "1h",
            }
        ],
        "entry_rules": [
            {
                "name": "ZLF-E2E S1 · الحالة الأولى: الاختراق الكامل المؤكد (اختراق قمة الحمراء بحجم أكبر)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e:zzfe_entry_s1",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.34,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E S2 · الحالة الثانية: الاختراق بدون هيمنة الحجم على الحمراء (اختراق القمة وحجم أقل أو مساوٍ) — «ويبرغم عندها لفل حجم سيولتها»",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e:zzfe_entry_s2",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E S3 · الحالة الثالثة: الامتصاص قبل الاختراق (بلا اختراق للقمة وحجم أكبر)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e:zzfe_entry_s3",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "ZLF-E2E · تأكيد قمة — انقلاب النطاق إلى هابطة (نطاق جديد قمة→قاع) · افتراضي مؤقت provisional",
                "condition": {
                    "type": "indicator_value",
                    "operator": "<",
                    "left_value": "indicator:zigzag_fib_e2e:zzfe_dir",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 10000,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


# =============================================================================
# ✅ الجولة 32 (ROUND32) — ZLF-End-To-End-Trendy — «الزقزاق البطل e2e الترنديه»
# =============================================================================
# أمر صاحب القرار: «نريد نسوّي استنساخ لاستراتيجيتنا زقزاق e2e نفسها التي فيها
# النطاق ونضع فوقها إضافة الترند — الباك اند هو من يحسبها — والترند يرسل
# إحداثياته للباك اند ويُحسب الإشارة بناء عليه — والترند مؤشر يُضاف إلى قائمة
# المؤشرات ويكون ضمن شروط الاستراتيجية — بمحرك معزول منفصل للباك تست وللشارت
# الحي — والاعدادات ثلاث ترندات 7 و 15 و 25 بحيث لا تُكتب الأرقام داخل الكود
# ونكون قادرين على استخدام القالب وتغيير الأرقام حتى إضافة ترند رابع 30».
#
# هذا القالب يعتمد:
#   - المحرك المعزول: zigzag_fib_e2e_trendy (overlays_zlf_e2e_trendy.py — ملف
#     مستقل: E2E حرفياً + بوابة الترند) والمؤشر المستقل trend_fractal
#     (trend_fractals.py — وفاء سكربت Auto Trendline [DojiEmoji] حرفياً).
#   - ✅ الأرقام قالبية بالكامل: trend_periods=[7,15,25] هنا في القالب —
#     إضافة ترند رابع 30 = تعديل هذه القائمة فقط ("trend_periods": [7,15,25,30])
#     بلا أي كود. صيغة الإجماع majority = أكثر من النصف (2 من 3).
#   - البوابة ضمن شروط الاستراتيجية صراحةً: كل قاعدة دخول = شرط مركّب AND
#     (إشارة الدخول بعد بوابة المحرك ∧ ind_zzfet_trend_ok > 0).
#   - الشفافية الكاملة: ind_zzfet_entry_raw_* (الخام) و ind_zzfet_entry_blocked_*
#     (الخام الذي منعه الترند) بجانب ind_zzfet_entry_* (المعتمد).
#   - الخروج كما في E2E حرفياً (انقلاب النطاق zzfet_dir < 0 + SL القالب).
ZLF_E2E_TRENDY_TRIPLE_SIGNAL: Dict[str, Any] = {
    "name": "ZLF-End-To-End-Trendy — الزقزاق البطل e2e الترنديه · 3 Entry Signals — ZERO FEE",
    "timeframe": "1h",
    "market": "crypto",
    "symbols": ["BTCUSDT"],
    "strategy_config": {
        "name": "ZLF-End-To-End-Trendy (3 Entry Signals — Range-anchored + Trend gate)",
        "base_timeframe": "1h",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib_e2e_trendy",
                "type": "support_resistance",
                "params": {
                    # ✅ وضع شارت المنصة المُتحقق منه بالبكسل — كما في E2E حرفياً
                    "mode": "luxalgo",
                    "length": 100,
                    "touch_level": 0.618,
                    # ✅✅ ROUND32 — قوالب الترند (الأرقام هنا لا في الكود):
                    # غيّرها/أضف ترنداً رابعاً 30 أو خامساً 50 بحرية — المحرك
                    # عام على القائمة. trend_confirm: majority|all|any|رقم.
                    # trend_gate: الإشارات المبوّبة (s1/s2/s3) أو "none" للتعطيل.
                    "trend_periods": [7, 15, 25],
                    "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3"],
                },
                "enabled": True,
                "timeframe": "1h",
            }
        ],
        "entry_rules": [
            {
                "name": "ZLF-E2E-Trendy S1 · الحالة الأولى: الاختراق الكامل المؤكد + موافقة الترند (7/15/25)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy:zzfet_entry_s1",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy:zzfet_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.34,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Trendy S2 · الحالة الثانية: الاختراق بدون هيمنة الحجم («ويبرغم عندها لفل حجم سيولتها») + موافقة الترند (7/15/25)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy:zzfet_entry_s2",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy:zzfet_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Trendy S3 · الحالة الثالثة: الامتصاص قبل الاختراق + موافقة الترند (7/15/25)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy:zzfet_entry_s3",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy:zzfet_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "ZLF-E2E-Trendy · تأكيد قمة — انقلاب النطاق إلى هابطة (نطاق جديد قمة→قاع) · افتراضي مؤقت provisional",
                "condition": {
                    "type": "indicator_value",
                    "operator": "<",
                    "left_value": "indicator:zigzag_fib_e2e_trendy:zzfet_dir",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 10000,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


# =============================================================================
# ✅ QUANTUM1 — ZLF-End-To-End-Trendy-Quantum — «الاستراتيجية الترندية الكمومية»
# =============================================================================
# مواصفة صاحب القرار: الترندية بحذافيرها + بوابة المنطقة الكمومية فوق إشارات
# الدخول: زقزاق مؤكد HH+HL (قمة أعلى + قاع أعلى) يفتح منطقة الدخول المسموحة،
# وLL+LH (قمة أدنى + قاع أدنى) يغلقها ويُخرج أي صفقة مفتوحة (next_open).
#
# هذا القالب يعتمد:
#   - المحرك المعزول: zigzag_fib_e2e_trendy_quantum (overlays_zlf_e2e_trendy_quantum.py
#     — طبقة فوق المحرك الترندي نفسه: أعمدة الترندية zzfet_* تُمرَّر بت-بت
#     + أعمدة الكمومية zzfetq_* — 109 أعمدة لكل شمعة: بيانات الرسم الكاملة
#     كما كانت الترندية ترجعها + بيانات الكمومية نفسها).
#   - ✅ الأرقام قالبية بالكامل: trend_periods=[7,15,25] وzone_gate=[s1,s2,s3]
#     هنا في القالب — لا أرقام داخل أي كود.
#   - الشفافية الرباعية الكاملة: entry_raw_* (خام) / entry_blocked_* (منعه
#     الترند) / entry_zblocked_* (منعته المنطقة) / entry_* (النهائي).
#   - الخروج: خروج المنطقة الكمومية LL+LH (zone_exit — أي صفقة مفتوحة تخرج
#     next_open) + SL القالب.
ZLF_E2E_TRENDY_QUANTUM_TRIPLE_SIGNAL: Dict[str, Any] = {
    "name": "ZLF-End-To-End-Trendy-Quantum — الاستراتيجية الترندية الكمومية · 3 Entry Signals — ZERO FEE",
    "timeframe": "1h",
    "market": "crypto",
    "symbols": ["BTCUSDT"],
    "strategy_config": {
        "name": "ZLF-End-To-End-Trendy-Quantum (3 Entry Signals — Trend+Zone gated)",
        "base_timeframe": "1h",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib_e2e_trendy_quantum",
                "type": "support_resistance",
                "params": {
                    # ✅ وضع شارت المنصة المُتحقق منه بالبكسل — كما في الترندية حرفياً
                    "mode": "luxalgo",
                    "length": 100,
                    "touch_level": 0.618,
                    # ✅ قوالب الترند (الأرقام هنا لا في الكود)
                    "trend_periods": [7, 15, 25],
                    "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3"],
                    # ✅ QUANTUM1 — قالب المنطقة: الأنواع المبوّبة بالمنطقة
                    # (s1/s2/s3 أو "none" لتعطيل بوابة الدخول — البيانات تبقى).
                    "zone_gate": ["s1", "s2", "s3"],
                },
                "enabled": True,
                "timeframe": "1h",
            }
        ],
        "entry_rules": [
            {
                "name": "ZLF-E2E-Trendy-Quantum S1 · الاختراق الكامل المؤكد + الترند (7/15/25) + المنطقة الكمومية (HH+HL)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum:zzfetq_entry_s1",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.34,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Trendy-Quantum S2 · الاختراق بدون هيمنة الحجم («ويبرغم عندها لفل حجم سيولتها») + الترند + المنطقة الكمومية (HH+HL)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum:zzfetq_entry_s2",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Trendy-Quantum S3 · الامتصاص قبل الاختراق + الترند + المنطقة الكمومية (HH+HL)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum:zzfetq_entry_s3",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "ZLF-E2E-Trendy-Quantum · خروج المنطقة الكمومية — LL+LH (أي صفقة مفتوحة يجب أن تخرج)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum:zzfetq_zone_exit",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 10000,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


# =============================================================================
# ✅ QUANTUMEMA1 — ZLF-End-To-End-Trendy-Quantum-EMA — «الاستراتيجية الترندية
# الكمومية المتوسطة المتحركة الأسية»
# =============================================================================
# مواصفة صاحب القرار: استنساخ كامل من «الاستراتيجية الترندية الكمومية» +
# **بوابة ثانية جوار بوابة المنطقة** (قمّة أعلى من قمّة + قاع أعلى من قاع
# HH+HL): الشرط الثاني للمنطقة المسموحة أن يتخطى السعر المتوسطات الستة
# لأعلى بترتيب تنازلي تحت السعر — EMA 21 أولاً ثم EMA 50 ثم EMA 100 ثم
# EMA 200 ثم EMA 350 ثم أسفلهم جميعاً EMA 500 — والمتوسطات تُحسب على
# فريم الساعة (resolution «60» دائماً في الافتراضي — قابل للتخصيص من
# الواجهة) عبر نواة MTF EMA (MTFEMA1 — سكربت Pine بحذافيره بلا استشراف).
#
# هذا القالب يعتمد:
#   - المحرك المعزول: zigzag_fib_e2e_trendy_quantum_ema
#     (overlays_zlf_e2e_trendy_quantum_ema.py — طبقة فوق المحرك الكمي نفسه:
#     أعمدة الكمومية zzfetq_* والترندية zzfet_* تُمرَّر بت-بت + الخطوط الستة
#     zzfetqe_ema_* وحالة الرصة والشفافية entry_eblocked — كل بيانات
#     الكمومية بحذافيرها + بيانات EMA الجديدة).
#   - ✅ الأرقام قالبية بالكامل: trend_periods=[7,15,25] وzone_gate=[s1,s2,s3]
#     وema_lengths=[21,50,100,200,350,500] وema_resolution=«60» وema_gate=
#     [s1,s2,s3] هنا في القالب — لا أرقام داخل أي كود.
#   - الخروج: خروج المنطقة الكمومية LL+LH (zone_exit — أي صفقة مفتوحة تخرج
#     next_open) + SL القالب — كما في الكمومية حرفياً.
ZLF_E2E_TRENDY_QUANTUM_EMA_TRIPLE_SIGNAL: Dict[str, Any] = {
    "name": "ZLF-End-To-End-Trendy-Quantum-EMA — الاستراتيجية الترندية الكمومية المتوسطة المتحركة الأسية · 3 Entry Signals — ZERO FEE",
    "timeframe": "1h",
    "market": "crypto",
    "symbols": ["BTCUSDT"],
    "strategy_config": {
        "name": "ZLF-End-To-End-Trendy-Quantum-EMA (3 Entry Signals — Trend+Zone+EMA-stack gated)",
        "base_timeframe": "1h",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib_e2e_trendy_quantum_ema",
                "type": "support_resistance",
                "params": {
                    # ✅ وضع شارت المنصة المُتحقق منه بالبكسل — كما في الكمومية حرفياً
                    "mode": "luxalgo",
                    "length": 100,
                    "touch_level": 0.618,
                    # ✅ قوالب الترند (الأرقام هنا لا في الكود)
                    "trend_periods": [7, 15, 25],
                    "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3"],
                    # ✅ QUANTUM1 — قالب المنطقة (كما في الكمومية حرفياً)
                    "zone_gate": ["s1", "s2", "s3"],
                    # ✅ QUANTUMEMA1 — قالب EMA الستة على فريم الساعة:
                    # رصة تنازلية تحت السعر (EMA21 أعلى ← EMA500 أسفل) —
                    # فريم الحساب «60» (ساعة) دائماً في الافتراضي (قرار
                    # صاحب القرار) وقابل للتخصيص من الواجهة.
                    "ema_lengths": [21, 50, 100, 200, 350, 500],
                    "ema_resolution": "60",
                    "ema_source": "close",
                    "ema_offset": 0,
                    # الأنواع المبوّبة برصة EMA (أو "none" لتعطيل البوابة —
                    # بيانات الرصة والخطوط تبقى محسوبة ومُرجعة).
                    "ema_gate": ["s1", "s2", "s3"],
                    # ✅ EMAGATE-UNIFIED — الرصة الهرمية الموحدة (الشروط السبعة)
                    # صريحة في القالب (تُركّب/تُعدّل/تُحذف من الواجهة).
                    "ema_stack_mode": "hierarchical",
                    "ema_stack_base": 21,
                },
                "enabled": True,
                "timeframe": "1h",
            }
        ],
        "entry_rules": [
            {
                "name": "ZLF-E2E-Trendy-Quantum-EMA S1 · الاختراق الكامل المؤكد + الترند (7/15/25) + المنطقة الكمومية (HH+HL) + رصة EMA الستة على الساعة",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema:zzfetqe_entry_s1",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.34,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Trendy-Quantum-EMA S2 · الاختراق بدون هيمنة الحجم + الترند + المنطقة الكمومية (HH+HL) + رصة EMA الستة على الساعة",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema:zzfetqe_entry_s2",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Trendy-Quantum-EMA S3 · الامتصاص قبل الاختراق + الترند + المنطقة الكمومية (HH+HL) + رصة EMA الستة على الساعة",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema:zzfetqe_entry_s3",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "ZLF-E2E-Trendy-Quantum-EMA · خروج المنطقة الكمومية — LL+LH (أي صفقة مفتوحة يجب أن تخرج)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema:zzfetqe_zone_exit",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 10000,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


# =============================================================================
# 👑 ALMIGHTY1 — «الاستراتيجية الجبّارة» — ZLF-End-To-End-Trendy-Quantum-EMA
# (نسخة البطولة A226 — من بحث EMA-SEARCH)
# =============================================================================
# أمر صاحب القرار (2026-11-17): «اكتب تكوين الاستراتيجية الجبّارة بتكوينها
# وإعدادها كامل في قالب الاستراتيجيات مع وصفها الكامل والنتائج والفريم
# التي تدعمه بطلاقة».
#
# أصل التكوين: بحث EMA-SEARCH — 7 مراحل · 77 تجربة معزولة العمليات على
# سيرفر الإنتاج الحي (SOLUSDT · 15m · كامل التاريخ 2020-03-16 → 2026-11-17
# · 219,657 شمعة) — انطلاقًا من قالب المستخدم #10000439 (+820.44%) ووصولًا
# إلى المهمة الحية #10000493 (+9402.449654% · تطابق بت-بت مع النسخة
# المحلية المعزولة).
#
# الفروقات الثلاثة عن القالب الأم (ZLF_E2E_TRENDY_QUANTUM_EMA_TRIPLE_SIGNAL
# أعلاه — عزو نظيف، بُعد واحد لكل تجربة):
#   1) length: 100 → 226 — «عيار رادار الزقزاق»: يرصد الموجات الكبرى فقط
#      (~80 موجة عملاقة في 6 سنوات بدل 139 متوسطة). أعلى بُعد منفرد
#      تأثيرًا (820% → 5528% وحده). خريطة الزقزاق مصدر كل شيء: مستويات
#      الاختراق (الدخول) وبنية HH+HL/LL+LH (فتح/إغلاق المنطقة =
#      الدخول والخروج معًا) — فتغييره يمسّ الدخول والخروج عبر حجم
#      الموجة المرسومة (الرابحة تركض أطول · الخروج لاحقًا).
#   2) ema_lengths: حذف خط EMA-21 (كان [21,50,100,200,350,500]) — نقص
#      شرط «close > EMA21» من رصة الدخول: أسرع خط (يقف على ظهر السعر)
#      كان يُغلق بوابة الرصة عند كل تراجعة تنفس صغيرة فتُمنع الصفقة
#      الرابحة من الولادة؛ بدونه يبقى الدخول متاحًا خلال التراجعات
#      الصغيرة (فلتر دخول فقط — منطق الخروج لا يقرأ الرصة أبدًا).
#      ملاحظة مثبتة: خط EMA-200 خامل فعليًا في هذا التكوين (حذفه لا
#      يغيّر شيئًا) — أُبقي بحذافيره.
#   3) zone_gate: ["s1","s2","s3"] → ["s1"] — فحص «المنطقة مفتوحة»
#      (HH+HL) يُشترط على إشارة s1 (الاختراق الكامل) فقط؛ s2 و s3
#      يدخلان بلا فحص المنطقة (توزيع بوابة دخول — zone_exit يشتغل
#      دائمًا غير مبالٍ بالبوابة).
#
# الخروج لم يُلمس في أي تجربة من الـ77: باب واحد منذ اليوم الأول —
# zone_exit (إغلاق المنطقة ببنية LL+LH) — لا SL ولا TP ولا trailing
# (حقول الجذر الثلاثة غير مُرسَلة إطلاقًا — None = غير مقدَّم).
# إدارة رأس المال: 300$ · 3 مراكز · تراكم مضاعف (multi_position) ·
# عمولة وانزلاق صفر · تنفيذ next_open.
ZLF_ALMIGHTY_QUANTUM_EMA_TRIPLE_SIGNAL: Dict[str, Any] = {
    "name": "ALMIGHTY — الاستراتيجية الجبّارة · ZLF-End-To-End-Trendy-Quantum-EMA (A226 Championship) · 3 Entry Signals — ZERO FEE",
    "timeframe": "15m",
    "market": "crypto",
    "symbols": ["SOLUSDT"],
    "strategy_config": {
        "name": "ALMIGHTY — الاستراتيجية الجبّارة (A226: 3 Entry Signals — Trend + Zone[s1]-gated + EMA-stack[5]-gated)",
        "version": "1.0.0",
        "description": "نسخة البطولة A226 من الاستراتيجية الترندية الكمومية المتوسطة المتحركة الأسية: "
                       "ثلاث إشارات دخول (s1 الاختراق الكامل بحجم مهيمن · s2 اختراق بلا هيمنة حجم · "
                       "s3 امتصاص) فوق بوابة ترند قالبية (7/15/25 majority) + بوابة منطقة كمومية "
                       "HH+HL مُشترطة على s1 فقط + رصة خمسة متوسطات EMA على فريم الساعة "
                       "(50>100>200>350>500 تنازليًا تحت السعر — بلا خط 21). الخروج باب واحد: "
                       "إغلاق المنطقة ببنية LL+LH (zone_exit) — بلا SL/TP/trailing.",
        "base_timeframe": "15m",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib_e2e_trendy_quantum_ema",
                "type": "support_resistance",
                "params": {
                    # ✅ وضع شارت المنصة المُتحقق منه بالبكسل — كما في الكمومية حرفياً
                    "mode": "luxalgo",
                    # 👑 A226 — عيار رادار الموجات الكبرى (كان 100)
                    "length": 226,
                    "touch_level": 0.618,
                    # ✅ قوالب الترند (الأرقام هنا لا في الكود)
                    "trend_periods": [7, 15, 25],
                    "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3"],
                    # 👑 A226 — بوابة المنطقة على الاختراق الكامل s1 فقط
                    "zone_gate": ["s1"],
                    # 👑 A226 — رصة خمسة خطوط (حُذف خط 21 الأسرع):
                    # بلا شرط close>EMA21 تولد الرابحة خلال تراجعات التنفس
                    "ema_lengths": [50, 100, 200, 350, 500],
                    "ema_resolution": "60",
                    "ema_source": "close",
                    "ema_offset": 0,
                    "ema_gate": ["s1", "s2", "s3"],
                    # ✅ EMAGATE-UNIFIED — الرصة الهرمية الموحدة (الشروط السبعة)
                    # صريحة في القالب (تُركّب/تُعدّل/تُحذف من الواجهة).
                    "ema_stack_mode": "hierarchical",
                    "ema_stack_base": 21,
                },
                "enabled": True,
                "timeframe": "15m",
            }
        ],
        "entry_rules": [
            {
                "name": "ALMIGHTY S1 · الاختراق الكامل المؤكد + الترند (7/15/25) + المنطقة الكمومية (HH+HL · بوابة s1 فقط) + رصة EMA الخمسة على الساعة",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema:zzfetqe_entry_s1",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.34,
                "enabled": True,
            },
            {
                "name": "ALMIGHTY S2 · الاختراق بدون هيمنة الحجم + الترند + رصة EMA الخمسة على الساعة (بلا فحص المنطقة)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema:zzfetqe_entry_s2",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
            {
                "name": "ALMIGHTY S3 · الامتصاص قبل الاختراق + الترند + رصة EMA الخمسة على الساعة (بلا فحص المنطقة)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema:zzfetqe_entry_s3",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "ALMIGHTY · خروج المنطقة الكمومية — LL+LH (أي صفقة مفتوحة يجب أن تخرج · الباب الوحيد)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema:zzfetqe_zone_exit",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 300,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 3,
    "compounding": True,
    "multi_position_compounding": True,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


# =============================================================================
# 🔥 QMOM1 — «كموميه الزخم الاولى» — ZLF-End-To-End-Trendy-Quantum-EMA-Mom
# (بوابة الشروط المرنة للموشرات متعددة الفريمات فوق الكمومية-EMA)
# =============================================================================
# أمر صاحب القرار (2026-11-18): «سنقوم باضافه بوابه جديده للشروط وتكون مرنه
#   وقابله للتعديل والاضافه ع اي استراتيجيه ... ونسوي من
#   ZLF-End-To-End-Trendy-Quantum-EMA نسخه باسم: كموميه الزخم الاولى».
#
# الأساس: تكوين المحرك الافتراضي المعتمد (ملاحظتا صاحب القرار 2026-11-19:
#   «اجعله ع الديفولت 100» + «اذكر ema_lengths كاملة مع الجديدة»):
#   length=100 (الديفولت) + رصة الستة الكاملة [21,50,100,200,350,500]
#   مع EMA21 الجديدة (قمة السلّم — زوج 21>50 هو الشرط 2) — مطابقة تماماً
#   للحمولة المرجعية الموثقة #10000604 (التحقق الحي #10000617: بوابة الزخم
#   46 خام → 11 نهائي → 35 محجوب بت-بت) + بوابة الزخم بالشروط الأربعة المطلوبة:
#   الشرط الأول — MACD 4h (12/26/4) فوق الصفر ∧ إيجابي (الخط فوق الإشارة).
#   الشرط الثاني — MACD 3d (5/11/4) متجاوزاً لأعلى فوق MACD 1d (12/26/4).
#   الشرط الثالث — RSI 1h (14/14/2) و RSI 4h (14/14/2) فوق RSI اليومي (14/14/2).
#   الشرط الرابع — RSI اليومي (10/14/2) أو (14/14/2) فوق مستوى 50 (يكفي أحدهما).
# ✅ SPLIT-ZZ1 (2026-11-19 — طلب صاحب القرار الحرفي: «بالنسبة لrsi اليومي
#   ذو الااعداد 14/14/2 يجب ان لا يتجاوز مستوى 60 اي بمعنى حدوده بين
#   مستوى 50 و 60 فقط»):
#   الشرط الخامس — RSI اليومي (14/14/2) لا يتجاوز 60 (≤ 60) — حدوده بين
#   مستوى 50 و 60 فقط (مع الشرط الرابع: النطاق الفعلي 50 < RSI ≤ 60).
# الخروج باب واحد كما في البطل: zone_exit (LL+LH) — بلا أي تغيير.
#
# ✅ EMAGATE-UNIFIED (2026-11-19): قالب الرصة الهرمي الموحد صريح الآن في
# الحمولة (ema_stack_mode/ema_stack_base) — الشروط السبعة لمتوسطات EMA
# (السعر فوق الكل + السلّم مرتب تماماً + الأسرع من القاعدة 21 معفاة من
# الترتيب) — قابل للتركيب/الإضافة/الحذف/التعديل كله من الفرونت-اند.
QMOM1_TRIPLE_SIGNAL: Dict[str, Any] = {
    "name": "QMOM1 — كموميه الزخم الاولى · ZLF-End-To-End-Trendy-Quantum-EMA-Mom (Trend+Zone+EMA-stack+Momentum-gate) · 3 Entry Signals — ZERO FEE",
    "timeframe": "15m",
    "market": "crypto",
    "symbols": ["SOLUSDT"],
    "start_date": "2020-03-16T00:00:00Z",
    "end_date": "2026-11-17T20:59:59Z",
    "timezone": "UTC",
    "tz_offset_minutes": 0,
    "mode": "standard",
    "strategy_config": {
        "name": "كموميه الزخم الاولى (Quantum-Momentum-1 — 3 Entry Signals · Trend+Zone+EMA-stack+Momentum-gate)",
        "version": "1.0.0",
        "description": "نسخة من ZLF-End-To-End-Trendy-Quantum-EMA على تكوينها الافتراضي "
                       "المعتمد (length=100 + رصة الستة الكاملة مع EMA21 — الحمولة "
                       "المرجعية الموثقة #10000604) مضافًا إليها بوابة الشروط المرنة QMOM1 "
                       "بموشراتها السبعة: الشرط الأول MACD 4h "
                       "(12/26/4) فوق الصفر وإيجابي · الشرط الثاني MACD 3d (5/11/4) فوق MACD 1d "
                       "(12/26/4) · الشرط الثالث RSI الساعة و4 ساعات (14/14/2) فوق RSI اليومي · "
                       "الشرط الرابع RSI اليومي (10/14/2) أو (14/14/2) فوق 50 · الشرط الخامس "
                       "(✅ SPLIT-ZZ1): RSI اليومي (14/14/2) لا يتجاوز 60 — حدوده بين 50 و 60 "
                       "فقط — الخروج باب واحد كما هو: zone_exit (LL+LH).",
        "author": "QMOM1 — طلب صاحب القرار (2026-11-18): بوابة شروط مرنة قابلة للتعديل "
                  "والتفعيل/التعطيل من الفرونت-اند",
        "base_timeframe": "15m",
        "allowed_timeframes": ["15m"],
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib_e2e_trendy_quantum_ema_mom",
                "type": "support_resistance",
                "params": {
                    # ✅ وضع شارت المنصة المُتحقق منه بالبكسل — الديفولت 100
                    # (ملاحظة صاحب القرار: «اجعله ع الديفولت 100» — قابل للتعديل
                    # من الواجهة إلى 226 أو أي عيار آخر في أي وقت).
                    "mode": "luxalgo",
                    "length": 100,
                    "touch_level": 0.618,
                    # ✅ قوالب الترند (الأرقام هنا لا في الكود)
                    "trend_periods": [7, 15, 25],
                    "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3"],
                    # ✅ قالب المنطقة الكمومية (HH+HL تفتح · LL+LH تغلق وتخرج)
                    "zone_gate": ["s1", "s2", "s3"],
                    # ✅ رصة EMA الكاملة الستة على الساعة — «كامله مع الجديده»:
                    # [21,50,100,200,350,500] مع EMA21 الجديدة (قمة السلّم —
                    # زوج 21>50 هو الشرط 2) +
                    # ✅ EMAGATE-UNIFIED: الوضع الهرمي الموحد صريحاً (الشروط
                    # السبعة — السعر فوق الكل + السلّم مرتب + الأسرع من 21
                    # معفاة؛ قابل للتعديل/الإضافة/الحذف من الواجهة كله).
                    "ema_lengths": [21, 50, 100, 200, 350, 500],
                    "ema_resolution": "60",
                    "ema_source": "close",
                    "ema_offset": 0,
                    "ema_gate": ["s1", "s2", "s3"],
                    "ema_stack_mode": "hierarchical",
                    "ema_stack_base": 21,
                    # ✅ ZONE-EXIT-LTF1 — دقة 5 دقائق لهيكل الخروج (كما في
                    # البطل المُتحقق: إغلاق المنطقة LL+LH على 5m).
                    "zone_exit_resolution": "5",
                    "zone_exit_length": 100,
                    # ---- قالب بوابة الشروط المرنة (نواة PRO76) ----
                    "osc_instances": [
                        {"kind": "macd", "id": "macd_4h_12_26_4", "timeframe": "4h",
                         "fast": 12, "slow": 26, "signal": 4, "enabled": True,
                         "doc": "الشرط الأول — MACD فريم 4 ساعات (12/26/4)"},
                        {"kind": "macd", "id": "macd_3d_5_11_4", "timeframe": "3d",
                         "fast": 5, "slow": 11, "signal": 4, "enabled": True,
                         "doc": "الشرط الثاني — MACD فريم 3 يوم (5/11/4)"},
                        {"kind": "macd", "id": "macd_1d_12_26_4", "timeframe": "1d",
                         "fast": 12, "slow": 26, "signal": 4, "enabled": True,
                         "doc": "الشرط الثاني — MACD فريم 1 يوم (12/26/4)"},
                        {"kind": "rsi", "id": "rsi_1h_14_14", "timeframe": "1h",
                         "period": 14, "ma_length": 14, "bb_std": 2, "enabled": True,
                         "doc": "الشرط الثالث — RSI فريم ساعه (14/14/2)"},
                        {"kind": "rsi", "id": "rsi_4h_14_14", "timeframe": "4h",
                         "period": 14, "ma_length": 14, "bb_std": 2, "enabled": True,
                         "doc": "الشرط الثالث — RSI فريم 4 ساعات (14/14/2)"},
                        {"kind": "rsi", "id": "rsi_1d_14_14", "timeframe": "1d",
                         "period": 14, "ma_length": 14, "bb_std": 2, "enabled": True,
                         "doc": "الشرط الثالث + الرابع + الخامس — RSI الفريم اليومي (14/14/2) "
                                "لا يتجاوز 60"},
                        {"kind": "rsi", "id": "rsi_1d_10_14", "timeframe": "1d",
                         "period": 10, "ma_length": 14, "bb_std": 2, "enabled": True,
                         "doc": "الشرط الرابع — RSI اليومي (10/14/2)"},
                    ],
                    "osc_conditions": {
                        "logic": "and",
                        "conditions": [
                            {"name": "الشرط الأول — MACD 4h (12/26/4) فوق الصفر + "
                                     "إيجابي (السريع فوق البطيء)",
                             "enabled": True,
                             "logic": "and",
                             "conditions": [
                                 {"left": "osc:macd_4h_12_26_4.line", "op": ">", "right": 0},
                                 {"left": "osc:macd_4h_12_26_4.line", "op": ">",
                                  "right": "osc:macd_4h_12_26_4.signal"},
                             ]},
                            {"name": "الشرط الثاني — MACD 3d (5/11/4) متجاوز لأعلى "
                                     "فوق MACD 1d (12/26/4)",
                             "enabled": True,
                             "left": "osc:macd_3d_5_11_4.line", "op": ">",
                             "right": "osc:macd_1d_12_26_4.line"},
                            {"name": "الشرط الثالث — RSI الساعه و 4 ساعات (14/14/2) "
                                     "فوق RSI اليومي (14/14/2)",
                             "enabled": True,
                             "logic": "and",
                             "conditions": [
                                 {"left": "osc:rsi_1h_14_14.value", "op": ">",
                                  "right": "osc:rsi_1d_14_14.value"},
                                 {"left": "osc:rsi_4h_14_14.value", "op": ">",
                                  "right": "osc:rsi_1d_14_14.value"},
                             ]},
                            {"name": "الشرط الرابع — RSI اليومي (10/14/2) أو (14/14/2) "
                                     "فوق مستوى 50 — يكفي أحدهما",
                             "enabled": True,
                             "logic": "or",
                             "conditions": [
                                 {"left": "osc:rsi_1d_10_14.value", "op": ">", "right": 50},
                                 {"left": "osc:rsi_1d_14_14.value", "op": ">", "right": 50},
                             ]},
                            # ✅ SPLIT-ZZ1 — الشرط الخامس (طلب صاحب القرار
                            # 2026-11-19): «بالنسبة لrsi اليومي ذو الااعداد
                            # 14/14/2 يجب ان لا يتجاوز مستوى 60 اي بمعنى
                            # حدوده بين مستوى 50 و 60 فقط» — مع الشرط الرابع
                            # النطاق الفعلي للـ 14/14/2: 50 < قيمة ≤ 60.
                            {"name": "الشرط الخامس — RSI اليومي (14/14/2) "
                                     "لا يتجاوز مستوى 60 (حدوده بين 50 "
                                     "و 60 فقط)",
                             "enabled": True,
                             "left": "osc:rsi_1d_14_14.value",
                             "op": "<=",
                             "right": 60},
                        ],
                    },
                },
                "enabled": True,
                "timeframe": "15m",
            }
        ],
        "entry_rules": [
            {
                "name": "كموميه الزخم الاولى · S1 — الاختراق الكامل المؤكد + الترند "
                        "(7/15/25) + المنطقة الكمومية (HH+HL) + رصة EMA الستة "
                        "الكاملة على الساعة (هرمية موحدة) + بوابة الزخم (MACD "
                        "4h/3d/1d + RSI 1h/4h/1d)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema_mom:zzfetqem_entry_s1",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.34,
                "enabled": True,
            },
            {
                "name": "كموميه الزخم الاولى · S2 — الاختراق بدون هيمنة الحجم + الترند "
                        "+ المنطقة + رصة الستة الهرمية + بوابة الزخم",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema_mom:zzfetqem_entry_s2",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
            {
                "name": "كموميه الزخم الاولى · S3 — الامتصاص قبل الاختراق + الترند "
                        "+ المنطقة + رصة الستة الهرمية + بوابة الزخم",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema_mom:zzfetqem_entry_s3",
                    "right_value": 0,
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "كموميه الزخم الاولى · خروج المنطقة الكمومية — LL+LH "
                        "(الباب الوحيد كما في البطل — بلا أي تغيير)",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_quantum_ema_mom:zzfetqem_zone_exit",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "filter_rules": [],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 300.0,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 3,
    "compounding": True,
    "multi_position_compounding": True,
    "commission_rate": 0,
    "slippage_percent": 0,
    "fill_model": "next_open",
    "max_daily_loss_percent": 5.0,
    "enable_short_selling": False,
    "enable_margin": False,
    "leverage": 1.0,
    "require_confirmation": False,
}


# =============================================================================
# 🔥 R69 — ZLF-End-To-End-Blazing — «الترندية الملتهبة»
# =============================================================================
# أمر صاحب القرار (2026-11-11): «اكتب لي الاستراتيجية الجديدة التي فيها 🔥 N5 —
# إشعال بلا مرجع — وسمّها استراتيجية الترندية الملتهبة … كمان أضف +N6».
#
# هذا القالب يعتمد:
#   - المحرك المعزول الجديد كلياً: zigzag_fib_e2e_blazing
#     (overlays_zlf_e2e_blazing.py — الترندية بت-بت + N5/N6).
#   - 🔥 N5 «إشعال بلا مرجع» (مُقاسة R68 على 4 رموز × 6 نوافذ — منها سنتان
#     خارج العينة): نطاق لم يرَ أي حمراء منذ ولادته ∧ صرخة فوق قمة الجبل
#     نفسها ∧ هيمنة حجم على الخضراء ∧ انضباط الانطلاقة. نافذة البطل:
#     أضافت الصفقة 64 الرابحة (+4.7%) — 64 · +1638.16% مقابل 63 · +1560.14%.
#   - 🤫 N6 «الاختراق الهادئ» (مُقاسة): اختراق سقف المرجع R بلا هيمنة
#     الخضراء — مضخّم الأسواق المتعبة (INIT: 47 · +295% → 55 · +432%).
#   - S1/S2/S3 كما في الترندية **بت-بت** (مثبت بمطابقة أعمدة الإنتاج) —
#     بوابة الترند القالبية نفسها (7/15/25 majority) والأنواع المبوّبة
#     الآن خمسة: s1/s2/s3/n5/n6 (كلها قالبية — لا أرقام داخل الكود).
#   - الخروج كما في الترندية حرفياً (انقلاب النطاق zzfb_dir < 0 + SL القالب).
ZLF_E2E_BLAZING_QUINT_SIGNAL: Dict[str, Any] = {
    "name": "ZLF-End-To-End-Blazing — الترندية الملتهبة · 5 Entry Signals (S1/S2/S3 + N5/N6) — ZERO FEE",
    "timeframe": "1h",
    "market": "crypto",
    "symbols": ["BTCUSDT"],
    "strategy_config": {
        "name": "ZLF-End-To-End-Blazing (الترندية الملتهبة — 5 Entry Signals: S1/S2/S3 + N5 إشعال بلا مرجع + N6 الاختراق الهادئ)",
        "base_timeframe": "1h",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib_e2e_blazing",
                "type": "support_resistance",
                "params": {
                    # ✅ وضع شارت المنصة المُتحقق منه بالبكسل — كما في الترندية حرفياً
                    "mode": "luxalgo",
                    "length": 100,
                    "touch_level": 0.618,
                    # 🔥 قوالب الترند (الأرقام هنا لا في الكود) — غيّرها/أضف
                    # ترنداً رابعاً 30 بحرية — المحرك عام على القائمة.
                    # trend_confirm: majority|all|any|رقم.
                    # trend_gate: الأنواع المبوّبة s1/s2/s3/n5/n6 أو "none" للتعطيل.
                    "trend_periods": [7, 15, 25],
                    "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3", "n5", "n6"],
                },
                "enabled": True,
                "timeframe": "1h",
            }
        ],
        "entry_rules": [
            {
                "name": "ZLF-E2E-Blazing S1 · الحالة الأولى: الاختراق الكامل المؤكد + موافقة الترند (7/15/25)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_entry_s1",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Blazing S2 · الحالة الثانية: الاختراق بدون هيمنة الحجم («ويبرغم عندها لفل حجم سيولتها») + موافقة الترند",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_entry_s2",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Blazing S3 · الحالة الثالثة: الامتصاص قبل الاختراق + موافقة الترند",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_entry_s3",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Blazing N5 🔥 · إشعال بلا مرجع: النطاق لم يرَ أي حمراء منذ ولادته (اندفاع خالص) + صرخة فوق قمة الجبل نفسها بهيمنة حجم + موافقة الترند",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_entry_n5",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
            {
                "name": "ZLF-E2E-Blazing N6 🤫 · الاختراق الهادئ: صرخة فوق سقف المرجع R بلا هيمنة الخضراء (ثقة بلا ضجيج) + موافقة الترند",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_entry_n6",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "ZLF-E2E-Blazing · تأكيد قمة — انقلاب النطاق إلى هابطة (نطاق جديد قمة→قاع) · افتراضي مؤقت provisional",
                "condition": {
                    "type": "indicator_value",
                    "operator": "<",
                    "left_value": "indicator:zigzag_fib_e2e_blazing:zzfb_dir",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 10000,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


# =============================================================================
# ✅ PRO73 — «الترندية الماكدية» (ZLF-End-To-End-Trendy-MACD)
# =============================================================================
# أمر صاحب القرار (2026-11-13): «سوي استراتيجية مستنبطة من الترندية البطل
#   والملتهبة وادمج عليها الموشرات (RSI/MACD/Momentum — نسخ متعددة فريمات
#   متعددة: RSI×10 وMACD×10 والمومنتم نسخ متعددة، لكل نسخة فريمها الخاص
#   وسرعتها وبطيئتها)… وسمّ إصداراً "ترنديه ماكديه"… تكون فيها كل البيانات —
#   المحرك عباره عن الترندية ولكن مع الدمج والبيانات المرجعة كاملة مع
#   الجديدة… والشروط قابلة للتركيب (مثلاً S1 AND مع انطباق كل شروط الماكد
#   والمومنتم والآر إس آي)… وكل الإعدادات مضبوطة وقابلة للتعديل».
#
# هذا القالب يعتمد:
#   - المحرك المعزول الجديد كلياً: zigzag_fib_e2e_trendy_macd
#     (overlays_zlf_e2e_trendy_macd.py — الترندية بت-بت + طبقة الدمج) على
#     نواة mtf_oscillator_core.py (الموشرات متعددة النسخ/الفريمات).
#   - ✅ القالب الافتراضي: 10 نسخ RSI + 10 نسخ MACD + 5 نسخ مومنتم موزعة
#     على فريمات متعددة (5m/15m/1h/4h/1d/1w) — كل نسخة بمعاملاتها الخاصة
#     وكلها قابلة للتعديل/الحذف/الإضافة من هنا بلا أي كود (المحرك يقبل أي
#     عدد نسخ وأي فريم من الـ14: 1s·5s·30s·1m·5m·15m·1h·4h·1d·2d·3d·1w·2w·1M).
#   - ✅ بوابة الشروط القابلة للتركيب (osc_conditions): شجرة and/or/not بأي
#     عمق — الافتراضي هنا: S1/S2/S3 AND (RSI 1h و4h فوق 50 ∧ MACD 1h hist
#     موجب ∧ MACD 1d line موجب ∧ مومنتم 1h موجب). عدّل/وسّع/بدّل بحرية —
#     مثال: إضافة كل النسخ العشر = روس 10 أوراق AND.
#   - الشفافية الرباعية: ind_zzfetm_entry_raw_* (خام) / entry_blocked_*
#     (منعها الترند) / entry_iblocked_* (منعتها الموشرات) / entry_* (النهائي).
#   - الخروج كما في الترندية حرفياً (انقلاب النطاق zzfetm_dir < 0 + SL قالب).
# =============================================================================

# 🔥 PRO73-R3 — نسخ المستند الكاملة + بوابة الحالات الافتراضية (2026-11-13):
#    «ويعمل وبكامل الاعدادات والموشرات كامله هذي الي في المستند» — المستند:
#    https://docs.google.com/document/d/1NAQOuiniJ6yFBApLmiYruxeJFp3JnMra2Aqs_TwPcvo
#    القالبان الرسميان (ترنديه ماكديه / ملتهبه ماكديه) يستعملان الآن:
#      · OSC_INSTANCES_TEMPLATE = مجموعة المستند الكاملة (67 نسخة: 28 MACD
#        + 16 RSI مع EMA وبولينجر StdDev 2 + 23 Momentum على الفريمات الـ14)
#        بمعرفات وصفّية (macd_1d_6_13_4 · rsi_1d_10_14 · mom_1w_5 ...).
#      · OSC_CONDITIONS_TEMPLATE = MASTER_ANY_CASE — «أي حالة لحظية» من
#        الحالات الخاصة الـ11 المسمّاة بنص المالك (كل حالة تعطي إشارة
#        ايجابية وفرصة شراء لحظية — OR)، والحالتان 5 (إنذار مبكر) خارجها.
#        البدائل الجاهزة: MASTER_STRICT (ماكد ∧ آر إس آي ∧ مومنتم) ·
#        EARLY_WATCH — كلها في app/services/indicators/osc_cases.py والفرونت
#        إند يبدّل بينها بنقرة.
from app.services.indicators.osc_cases import (  # noqa: E402
    OSC_DOC_INSTANCES as OSC_INSTANCES_TEMPLATE,
    MASTER_ANY_CASE as OSC_CONDITIONS_TEMPLATE,
    OSC_CASE_LIBRARY,
    OSC_DOC_URL,
)

# (النسخة السابقة PRO73-R1 — توزيع متوازن 25 نسخة قبل تبنّي المستند —
#  محفوظة للرجوع/المقارنة، لا يستعملها أي قالب رسمي)
_OSC_INSTANCES_R1: List[Dict[str, Any]] = [
    # — RSI ×10 نسخ (فريمات ومعاملات متنوعة) —
    {"kind": "rsi", "id": "rsi1", "timeframe": "5m",  "period": 14},
    {"kind": "rsi", "id": "rsi2", "timeframe": "15m", "period": 14},
    {"kind": "rsi", "id": "rsi3", "timeframe": "1h",  "period": 14},
    {"kind": "rsi", "id": "rsi4", "timeframe": "4h",  "period": 14},
    {"kind": "rsi", "id": "rsi5", "timeframe": "1d",  "period": 14},
    {"kind": "rsi", "id": "rsi6", "timeframe": "1h",  "period": 7},
    {"kind": "rsi", "id": "rsi7", "timeframe": "4h",  "period": 21},
    {"kind": "rsi", "id": "rsi8", "timeframe": "15m", "period": 28},
    {"kind": "rsi", "id": "rsi9", "timeframe": "1d",  "period": 10},
    {"kind": "rsi", "id": "rsi10", "timeframe": "1w", "period": 14},
    # — MACD ×10 نسخ (مجموعات 12/26/9 و 6/13/4 و 5/34/5 عبر الفريمات) —
    {"kind": "macd", "id": "macd1", "timeframe": "15m", "fast": 12, "slow": 26, "signal": 9},
    {"kind": "macd", "id": "macd2", "timeframe": "1h",  "fast": 12, "slow": 26, "signal": 9},
    {"kind": "macd", "id": "macd3", "timeframe": "4h",  "fast": 12, "slow": 26, "signal": 9},
    {"kind": "macd", "id": "macd4", "timeframe": "1d",  "fast": 12, "slow": 26, "signal": 9},
    {"kind": "macd", "id": "macd5", "timeframe": "1h",  "fast": 6,  "slow": 13, "signal": 4},
    {"kind": "macd", "id": "macd6", "timeframe": "4h",  "fast": 6,  "slow": 13, "signal": 4},
    {"kind": "macd", "id": "macd7", "timeframe": "15m", "fast": 6,  "slow": 13, "signal": 4},
    {"kind": "macd", "id": "macd8", "timeframe": "1d",  "fast": 5,  "slow": 34, "signal": 5},
    {"kind": "macd", "id": "macd9", "timeframe": "5m",  "fast": 12, "slow": 26, "signal": 9},
    {"kind": "macd", "id": "macd10", "timeframe": "1w", "fast": 12, "slow": 26, "signal": 9},
    # — Momentum ×5 نسخ —
    {"kind": "mom", "id": "mom1", "timeframe": "15m", "length": 10},
    {"kind": "mom", "id": "mom2", "timeframe": "1h",  "length": 10},
    {"kind": "mom", "id": "mom3", "timeframe": "4h",  "length": 14},
    {"kind": "mom", "id": "mom4", "timeframe": "1d",  "length": 10},
    {"kind": "mom", "id": "mom5", "timeframe": "1h",  "length": 5},
]

_OSC_CONDITIONS_R1: Dict[str, Any] = {
    "logic": "and",
    "conditions": [
        {"left": "osc:rsi3.value", "op": ">", "right": 50},
        {"left": "osc:rsi4.value", "op": ">", "right": 50},
        {"left": "osc:macd2.hist", "op": ">", "right": 0},
        {"left": "osc:macd4.line", "op": ">", "right": 0},
        {"left": "osc:mom2.line", "op": ">", "right": 0},
    ],
}

TRENDY_MACDIZED: Dict[str, Any] = {
    "name": "Trendy-MACDized — الترندية الماكدية (S1/S2/S3 + بوابة الموشرات) — ZERO FEE",
    "timeframe": "1m",
    "market": "crypto",
    "symbols": ["SOLUSDT"],
    "strategy_config": {
        "name": "Trendy-MACDized (الترندية الماكدية — S1/S2/S3 + نسخ المستند الكاملة 67 + الحالات الـ13 المسمّاة)",
        "base_timeframe": "1m",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib_e2e_trendy_macd",
                "type": "support_resistance",
                "params": {
                    # نفس معاملات الترندية حرفياً (المحرك يمرّرها إليها كما هي)
                    "mode": "luxalgo",
                    "length": 100,
                    "trend_periods": [7, 15, 25],
                    "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3"],
                    # ✅ PRO73 — قالبا الموشرات (كل سطر قابل للتعديل بلا كود):
                    "osc_instances": OSC_INSTANCES_TEMPLATE,
                    "osc_conditions": OSC_CONDITIONS_TEMPLATE,
                },
                "enabled": True,
                "timeframe": "1m",
            }
        ],
        "entry_rules": [
            {
                "name": "Trendy-MACD S1 · الاختراق الكامل المؤكد + الترند (7/15/25) + بوابة الحالات الخاصة (أي حالة لحظية — OR)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy_macd:zzfetm_entry_s1",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy_macd:zzfetm_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.34,
                "enabled": True,
            },
            {
                "name": "Trendy-MACD S2 · الاختراق بدون هيمنة الحجم + الترند + بوابة الحالات الخاصة",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy_macd:zzfetm_entry_s2",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy_macd:zzfetm_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
            {
                "name": "Trendy-MACD S3 · الامتصاص قبل الاختراق + الترند + بوابة الحالات الخاصة",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy_macd:zzfetm_entry_s3",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_trendy_macd:zzfetm_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.33,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "Trendy-MACD · تأكيد قمة — انقلاب النطاق إلى هابطة (نفس روح الترندية)",
                "condition": {
                    "type": "indicator_value",
                    "operator": "<",
                    "left_value": "indicator:zigzag_fib_e2e_trendy_macd:zzfetm_dir",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 10000,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


# =============================================================================
# 🔥 PRO73 — «الملتهبة الماكدية» (ZLF-End-To-End-Blazing-MACD)
# =============================================================================
# أمر صاحب القرار: «وسوي إصداراً سمّه "ملتهبه ماكديه" — وهذا يكون فيه كل
#   البيانات… المحرك عباره عن الملتهبة ولكن مع الدمج والبيانات المرجعة
#   كاملة مع الجديدة». نفس هندسة الترندية الماكدية لكن فوق الملتهبة:
#   الأنواع الخمسة s1/s2/s3/n5/n6 (كلها عبر بوابة الترند ثم بوابة الموشرات).
# =============================================================================
BLAZING_MACDIZED: Dict[str, Any] = {
    "name": "Blazing-MACDized — الملتهبة الماكدية (S1/S2/S3 + N5/N6 + بوابة الموشرات) — ZERO FEE",
    "timeframe": "1m",
    "market": "crypto",
    "symbols": ["SOLUSDT"],
    "strategy_config": {
        "name": "Blazing-MACDized (الملتهبة الماكدية — S1/S2/S3 + N5/N6 + نسخ المستند الكاملة 67 + الحالات الـ13 المسمّاة)",
        "base_timeframe": "1m",
        "position_side": "long",
        "indicators": [
            {
                "name": "zigzag_fib_e2e_blazing_macd",
                "type": "support_resistance",
                "params": {
                    # نفس معاملات الملتهبة حرفياً (المحرك يمرّرها إليها كما هي)
                    "mode": "luxalgo",
                    "length": 100,
                    "trend_periods": [7, 15, 25],
                    "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3", "n5", "n6"],
                    # ✅ PRO73 — نفس قالبا الموشرات (مشتركان — عدّل بحرية)
                    "osc_instances": OSC_INSTANCES_TEMPLATE,
                    "osc_conditions": OSC_CONDITIONS_TEMPLATE,
                },
                "enabled": True,
                "timeframe": "1m",
            }
        ],
        "entry_rules": [
            {
                "name": "Blazing-MACD S1 · الاختراق الكامل المؤكد + الترند + بوابة الحالات الخاصة (أي حالة لحظية — OR)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_entry_s1",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
            {
                "name": "Blazing-MACD S2 · الاختراق بدون هيمنة الحجم + الترند + بوابة الحالات الخاصة (أي حالة لحظية — OR)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_entry_s2",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
            {
                "name": "Blazing-MACD S3 · الامتصاص قبل الاختراق + الترند + بوابة الحالات الخاصة (أي حالة لحظية — OR)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_entry_s3",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
            {
                "name": "Blazing-MACD N5 🔥 · إشعال بلا مرجع (نطاق بلا أي حمراء + صرخة فوق قمة الجبل) + الترند + بوابة الحالات الخاصة (أي حالة لحظية — OR)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_entry_n5",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
            {
                "name": "Blazing-MACD N6 🤫 · الاختراق الهادئ (اختراق سقف المرجع بلا هيمنة الخضراء) + الترند + بوابة الحالات الخاصة (أي حالة لحظية — OR)",
                "condition": {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_entry_n6",
                            "right_value": 0,
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_trend_ok",
                            "right_value": 0,
                        },
                    ],
                },
                "position_side": "long",
                "weight": 0.20,
                "enabled": True,
            },
        ],
        "exit_rules": [
            {
                "name": "Blazing-MACD · تأكيد قمة — انقلاب النطاق إلى هابطة (نفس روح الملتهبة)",
                "condition": {
                    "type": "indicator_value",
                    "operator": "<",
                    "left_value": "indicator:zigzag_fib_e2e_blazing_macd:zzfbm_dir",
                    "right_value": 0,
                },
                "exit_type": "signal_exit",
                "enabled": True,
            }
        ],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    },
    "initial_capital": 10000,
    "position_sizing": "percentage",
    "position_size_percent": 100.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


# =============================================================================
# ✅ PRO74 — قالبا «الخفيفة» (تسليم 2026-11-14): نفس المحركين الماكديين
#    ببوابة RSI (rsi_any — حالات الآر إس آي بنص المالك) وسبع نسخ RSI فقط
#    (1h/4h/1d/2d/3d/1w بمعاملات المستند) — ذاكرة أقل بكثير، تشغيل النوافذ
#    الكاملة (665,099 شمعة) بلا SIGKILL، مع حياد الإحماء (PRO74 في
#    mtf_oscillator_core): قبل جاهزية كل أوراق الشجرة البوابة مفتوحة — لا
#    يُحجب دخول بحكم موشرٍ لم تتوفر بياناته بعد.
#
#    البرهان (نافذة البطل #10000265 — ملتهبة S|N5 · 64 صفقة/+1638.16%):
#    القالب الخفيف المصلَّح يحفظ البطل تامًا (صفر من 64 إشارة محجوبة) في
#    حين كانت النسخة غير المصلَّحة تحجب 11 صفقة زورًا (إحماء) → +998.05%.
# =============================================================================
def _osc_refs(tree: Any, acc: Any = None) -> set:
    if acc is None:
        acc = set()
    if isinstance(tree, dict):
        for k in ("left", "right"):
            v = tree.get(k)
            if isinstance(v, str) and v.startswith("osc:"):
                acc.add(v.split(":")[1].split(".")[0])
        for c in (tree.get("conditions") or []):
            _osc_refs(c, acc)
    return acc


from app.services.indicators.osc_cases import RSI_ANY as _RSI_ANY_GATE  # noqa: E402

_RSI_LIGHT_IDS = _osc_refs(_RSI_ANY_GATE)
RSI_LIGHT_INSTANCES: List[Dict[str, Any]] = [
    inst for inst in OSC_INSTANCES_TEMPLATE if inst.get("id") in _RSI_LIGHT_IDS
]


def _macdized_light_payload(base: Dict[str, Any], *, gate_tag: str, rule_tag: str) -> Dict[str, Any]:
    """بناء قالب خفيف من قالب ماكدي كامل: 7 نسخ RSI + بوابة rsi_any + تسمية R74."""
    import copy as _copy
    out = _copy.deepcopy(base)
    sc = out["strategy_config"]
    sc["name"] = f"{rule_tag} (R74 — خفيفة: 7 نسخ RSI + بوابة الحالات + حياد الإحماء)"
    ind = sc["indicators"][0]
    ind["params"]["osc_instances"] = RSI_LIGHT_INSTANCES
    ind["params"]["osc_conditions"] = _RSI_ANY_GATE
    for r in sc.get("entry_rules", []):
        if isinstance(r.get("name"), str) and "·" in r["name"]:
            r["name"] = f"{rule_tag} R74 · {r['name'].split('·', 1)[-1].strip()}"
    for r in sc.get("exit_rules", []):
        if isinstance(r.get("name"), str):
            r["name"] = f"{rule_tag} R74 · {r['name']}"
    out["name"] = f"{gate_tag} — ZERO FEE · R74 خفيفة"
    out["description"] = (
        "PRO74 — نسخة الذاكرة الخفيفة من الماكدية: نفس المحرك بت-بت لكن بسبع نسخ RSI "
        "فقط (1h/4h/1d/2d/3d/1w بمعاملات المستند) وبوابة «حالات الآر إس آي» (rsi_any) — "
        "تشغّل النوافذ الكاملة (665 ألف شمعة) بلا قتل OOM، وتحفظ نتيجة البطل بت-بت مع "
        "حياد الإحماء (لا حجب قبل جاهزية بيانات الشجرة). تبديل البوابة أو إضافة نسخ "
        "من الفرونت إند بنقرة."
    )
    return out


TRENDY_MACDIZED_RSI_LIGHT: Dict[str, Any] = _macdized_light_payload(
    TRENDY_MACDIZED,
    gate_tag="Trendy-MACDized-RSI-Light · الترندية الماكدية الخفيفة",
    rule_tag="Trendy-MACD-RSI",
)
BLAZING_MACDIZED_RSI_LIGHT: Dict[str, Any] = _macdized_light_payload(
    BLAZING_MACDIZED,
    gate_tag="Blazing-MACDized-RSI-Light · الملتهبة الماكدية الخفيفة",
    rule_tag="Blazing-MACD-RSI",
)


PRESET_NOTES: List[str] = [
    "✅ EMAGATE-UNIFIED (الشروط السبعة لمتوسطات EMA — شرح صاحب القرار 2026-11-19): "
    "بوابة الرصة الهرمية الموحدة في كل استراتيجية فيها البوابة (الكمومية المتوسطة "
    "نفسها + الجبارة + كموميه الزخم الاولى) — (1) السعر فوق كل المتوسطات «"
    "(2-7) السلّم مرتب تماماً بالأطوال: الأصغر فوق الأكبر (EMA21>EMA50>EMA100>"
    "EMA200>EMA350>EMA500 — أي مجموعة جزئية «إن وجد» تكيف نفسها) ولا أكبر فوق "
    "أي زوج + الأسرع من القاعدة (ema_stack_base=21 افتراضياً — مثل 8/13) معفى "
    "من الترتيب يجوز أن يعلو فوق EMA21 تحت السعر. الوضعان قالبان من الواجهة: "
    "hierarchical (الافتراضي) / strict (الوضع التاريخي للتراجع/A-B) — وللتكوينات "
    "القياسية الاثنان بت-بت (بطارية التحقق). التشخيص المرجع: ema_stack_price_ok "
    "(الشرط 1) · ema_stack_ladder_ok (الشروط 2-7) · ema_stack_pair_ok_{a}_{b} "
    "(عمود لكل زوج متجاور — مؤشر إنذار أي زوج انكسر).",
    "✅ R58 — وضع percentage: القيمة نسبة مئوية حقيقية (1 = 1%، 100 = رأس مال كامل). الوضع fixed يبقى كسراً تاريخياً (1.0 = 100%).",
    "الشكل الصحيح للدمج المنطقي: {\"type\": \"and\", \"conditions\": [...]} — وليس {\"type\":\"composite\",\"logic\":\"and\"}؛ "
    "الشكل القديم يُوحَّد تلقائياً الآن مع تحذير، وأي شكل غير معروف يُرفض برسالة واضحة بدل 0 صفقات صامتة.",
    "commission_rate و slippage_percent DEPRECATED (الجولة 13 — سياسة Zero-Fee الإبادية): النظام يعمل بلا عمولات ولا انزلاق نهائياً. "
    "غيابهما أو 0 يُقبل بصمت (توافق خلفي)، وأي قيمة > 0 تُرفض بـ 422: «النظام يعمل بلا عمولات ولا انزلاق نهائياً (سياسة Zero-Fee)…» — لا تطبيق صامت إطلاقاً.",
    "fill_model: \"next_open\" (الافتراضي — تنفيذ عند فتح الشمعة التالية، نفس سلوك الإصدارات السابقة) "
    "أو \"signal_close\" (تنفيذ عند إغلاق شمعة الإشارة — أقرب لمحاكاة الواجهة المحلية). "
    "أرقام المحرك بنموذج next_open: 10 صفقات · −1.86% (عمولة 0) مقابل محاكاة محلية بـ signal_close أعطت ~+112% — الفرق هو نموذج التنفيذ وليس خطأً.",
    "كل صفقة/نقطة خروج تعيد الآن: price_delta و price_delta_pct و direction و result_pct و pnl_gross و commission (DEPRECATED ثابت 0.0) و fill_entry/fill_exit، "
    "مع كائن math_audit في الملخص (تدقيق حسابي ذاتي لكل صفقة).",
    "✅ الجولة 13 — عقد الدقة المتناهية (الصيغة الموحدة الموثقة، بلا أي تقريب — float64 كاملة): "
    "price_delta_pct = (exit − entry) / entry × 100 × direction · result_pct = price_delta_pct (نفس القيمة بلا اختلاف) · "
    "pnl = (exit − entry) × units × direction − 0 (بلا خصم إطلاقاً) · pnl_gross = pnl دائماً · total_pnl_percent = Σpnl / initial_capital × 100.",
    "✅ الجولة 13 — math_audit: الصيغة الصافية "
    "pnl == (exit_price - entry_price) * units * (long? +1 : -1) "
    "بلا أي ذكر للعمولة/الانزلاق، تسامح مشدّد max_abs_error ≤ 1e-9 (كان 0.01)، وحقل precision_report = {formula_tolerance: 1e-9, float64: true, rounded_fields: []}.",
    "⚠️ عقد تشغيل البطل المرجعي (الجولة 13.2.1 — مثبت بستة تشغيلات حية محلياً + الإنتاج): "
    "(1) strategy_config.risk_management **توثيقي** — المحرك لا يقرأه؛ الحاكم الفعلي = حقول BacktestConfig العليا "
    "stop_loss_percent/take_profit_percent وافتراضياتهما 5.0/10.0 (app/backtest/schemas.py — سطرا 110-111). "
    "(2) التشغيل المرجعي الذي يعيد −1.8561111466784315% حرفياً (محلياً وعلى الإنتاج) = حمولة VERIFY-R13.sh: "
    "days=200 **بلا أي حقول مخاطر عليا** — الافتراضيات 5%/10% خاملة على نافذة البيانات المرجعية "
    "(لا صفقة تلمسها قبل خروجها بإشارة تأكيد القمة). "
    "(3) تحذير: تمرير stop_loss_percent=2.0 يفعّل وقف خسارة حقيقياً ويغيّر النتائج عن المرجع "
    "(على نفس النافذة محلياً: +5.544579948129267%) — لا تمرّره إلا إذا أردت SL فعلياً. "
    "(4) تحذير: إغفال days يجعل النافذة غير مشتقة — محلياً يعيد 0 صفقات — مرّر days=200 دائماً. "
    "(5) خلاصة إعادة الإنتاج: خذ حمولة هذا القالب + أضف days=200 + لا تضف حقول مخاطر عليا. "
    "الأدلة: RISK-CONTRACT-DOC-EVIDENCE.txt (ستة تشغيلات موثقة).",
    "✅ الجولة 13.2 (ZLF v13.2 — المصفوفة المصادقة من ثلاث جهات) — الاستراتيجية الواحدة بثلاث إشارات دخول (صور المستخدم): "
    "R = الشمعة صاحبة أكبر حجم في النافذة [i−liq_lookback, i−1] بشرط أنها حمراء (close<open) — أكبر شمعة خضراء → لا مرجع؛ "
    "ref_high = أعلى high لشمعة حمراء داخل النافذة (محور الاختراق الموحد)؛ "
    "G = خضراء + الانطلاقة low_G ≥ price(0.382) لآخر ساق مؤكدة (أي اتجاه — خط 0.618 بمقياس المستخدم = price(0.382) بالمحرك) "
    "+ هيمنة الخضراء (volume_G > حجم كل الخضراء حصرياً بين R وG). "
    "المصفوفة: S1 اختراق∧حجم أكبر · S2 اختراق∧حجم أقل أو مساوٍ («ويبرغم عندها لفل حجم سيولتها») · S3 رفض∧حجم أكبر · "
    "الرابعة (لا اختراق∧حجم أقل) = لا إشارة. "
    "الدخول = عند شمعة الإشارة نفسها (تقييم الإغلاق/تنفيذ الافتتاح التالي next_open) على أي اتجاه للساق؛ "
    "خطة بديلة وحيدة: أول شمعة تحقق الانطلاقة خلال liq_arm_bars إن لم تكن الساق مؤكدة لحظة الحدث (FIFO). "
    "SFP = إشارة رابعة اختيارية مطفأة افتراضياً (liq_sfp_signals=false) — لا تظهر في أي مخرجات افتراضياً. "
    "الأعمدة: ind_zzf_liq_state / ind_zzf_liq_ref_high / ind_zzf_liq_ref_vol / ind_zzf_liq_vol_ok / "
    "ind_zzf_signal_s1|s2|s3|any / ind_zzf_entry_s1|s2|s3 / ind_zzf_entry (25 عمود ind_zzf_* كما هي). "
    "الخروج: افتراضي مؤقت provisional — انقلاب الساق إلى هابطة (zzf_dir < 0) + SL 2%، وخيار مقترح من الصور: "
    "الهدف = قمة الحركة الحمراء (القرار النهائي للمستخدم). "
    "على فريم الدقيقة يُنصح برفع liq_lookback (مثل 240) لتغطية النطاق المرسوم. "
    "القواعد الثلاث بوزن 0.34/0.33/0.33 — أي إشارة تكفي للدخول (OR داخل المحرك) وكل صفقة تحمل اسم إشارتها في decision_reason.",
]


# ✅ B9 — «ماكد 9B + ترند 100» (2026-11-22): MACD Buy Strategy 9B محوّلة من
# Pine حرفياً (7 نسخ MACD على 4H/1D/1W — إسقاط سببي confirmed + إحماء
# فشل-إغلاق + نافذة تفعيل) ومدمجة مع ترند 100: الدخول = شروط B9 الأربعة
# ∧ الإغلاق فوق خط الترند 100 · الخروج = استجد خط ترند-100 في رسم جديد.
B9_TREND100: Dict[str, Any] = { 'name': '👑 B9-T100 · ETHUSDT · 15m · دخول B9 (ماكد متعدد الفريمات) + فوق ترند 100 — خروج عند '
          'استجد ترند 100 (رسم جديد)',
  'description': '«ماكد 9B» (MACD Buy Strategy 9B) محوّلة من Pine ومدمجة مع ترند 100: الدخول = '
                 'شروط B9 الأربعة (إيجابية الماكد الأسبوعي A/B/C + اليومي B/C + نواة 4H B فوق '
                 'إشارته وفوق الصفر + أي ماكد أعلى فوق إشارته وفوق خط 4H B) مع الإغلاق فوق خط '
                 'الترند 100. الخروج = استجد خط ترند 100 في رسم جديد (ولادة خط جديد علوي أو سفلي). '
                 'إدارة نقية بإشارات فقط (بلا SL/TP/تريلينق/جني مقسم/تعزيز). البيانات من '
                 '2024-08-08 (إحماء MACD الأسبوعي كما يراه TradingView) والصفقات محصورة في نافذة '
                 'التقييم 2026-02-08 → 2026-11-09 عبر active_start/active_end.',
  'mode': 'standard',
  'start_date': '2024-08-08T00:00:00Z',
  'end_date': '2026-11-09T00:00:00Z',
  'days': None,
  'timeframe': '15m',
  'timezone': 'UTC',
  'tz_offset_minutes': 0,
  'market': 'crypto',
  'symbols': ['ETHUSDT'],
  'strategy_config': { 'name': 'B9-Trend100 (MACD multi-TF gates + trend-100 gate & new-line exit)',
                       'base_timeframe': '15m',
                       'position_side': 'long',
                       'indicators': [ { 'name': 'b9_macd_gates',
                                         'type': 'momentum',
                                         'params': { 'instances': [ { 'id': 'macd_4h_12_26_6',
                                                                      'timeframe': '240',
                                                                      'fast': 12,
                                                                      'slow': 26,
                                                                      'signal': 6,
                                                                      'doc': '4H B (12/26/6) — '
                                                                             'نواة الشرط المؤكدة '
                                                                             '(confirmed on 4h '
                                                                             'close)'},
                                                                    { 'id': 'macd_1d_6_13_4',
                                                                      'timeframe': '1D',
                                                                      'fast': 6,
                                                                      'slow': 13,
                                                                      'signal': 4,
                                                                      'doc': '1D A (6/13/4)'},
                                                                    { 'id': 'macd_1d_12_26_6',
                                                                      'timeframe': '1D',
                                                                      'fast': 12,
                                                                      'slow': 26,
                                                                      'signal': 6,
                                                                      'doc': '1D B (12/26/6)'},
                                                                    { 'id': 'macd_1d_18_39_4',
                                                                      'timeframe': '1D',
                                                                      'fast': 18,
                                                                      'slow': 39,
                                                                      'signal': 4,
                                                                      'doc': '1D C (18/39/4)'},
                                                                    { 'id': 'macd_1w_6_13_4',
                                                                      'timeframe': '1W',
                                                                      'fast': 6,
                                                                      'slow': 13,
                                                                      'signal': 4,
                                                                      'doc': '1W A (6/13/4)'},
                                                                    { 'id': 'macd_1w_12_26_4',
                                                                      'timeframe': '1W',
                                                                      'fast': 12,
                                                                      'slow': 26,
                                                                      'signal': 4,
                                                                      'doc': '1W B (12/26/4)'},
                                                                    { 'id': 'macd_1w_18_39_4',
                                                                      'timeframe': '1W',
                                                                      'fast': 18,
                                                                      'slow': 39,
                                                                      'signal': 4,
                                                                      'doc': '1W C (18/39/4)'}],
                                                     'conditions': { 'logic': 'and',
                                                                     'conditions': [ { 'name': 'condW_pos '
                                                                                               '— '
                                                                                               'الماكد '
                                                                                               'الأسبوعي '
                                                                                               'الثلاثة '
                                                                                               'فوق '
                                                                                               'إشاراتها '
                                                                                               '(1W '
                                                                                               'A/B/C)',
                                                                                       'logic': 'and',
                                                                                       'conditions': [ { 'left': 'osc:macd_1w_6_13_4.line',
                                                                                                         'op': '>',
                                                                                                         'right': 'osc:macd_1w_6_13_4.signal'},
                                                                                                       { 'left': 'osc:macd_1w_12_26_4.line',
                                                                                                         'op': '>',
                                                                                                         'right': 'osc:macd_1w_12_26_4.signal'},
                                                                                                       { 'left': 'osc:macd_1w_18_39_4.line',
                                                                                                         'op': '>',
                                                                                                         'right': 'osc:macd_1w_18_39_4.signal'}]},
                                                                                     { 'name': 'condD_pos '
                                                                                               '— '
                                                                                               'الماكد '
                                                                                               'اليومي '
                                                                                               'B/C '
                                                                                               'فوق '
                                                                                               'إشارتيهما',
                                                                                       'logic': 'and',
                                                                                       'conditions': [ { 'left': 'osc:macd_1d_12_26_6.line',
                                                                                                         'op': '>',
                                                                                                         'right': 'osc:macd_1d_12_26_6.signal'},
                                                                                                       { 'left': 'osc:macd_1d_18_39_4.line',
                                                                                                         'op': '>',
                                                                                                         'right': 'osc:macd_1d_18_39_4.signal'}]},
                                                                                     { 'name': 'cond4H_core '
                                                                                               '— '
                                                                                               '4H '
                                                                                               'B '
                                                                                               'فوق '
                                                                                               'إشارته '
                                                                                               'وفوق '
                                                                                               'الصفر '
                                                                                               '(مؤكد)',
                                                                                       'logic': 'and',
                                                                                       'conditions': [ { 'left': 'osc:macd_4h_12_26_6.line',
                                                                                                         'op': '>',
                                                                                                         'right': 'osc:macd_4h_12_26_6.signal'},
                                                                                                       { 'left': 'osc:macd_4h_12_26_6.line',
                                                                                                         'op': '>',
                                                                                                         'right': 0}]},
                                                                                     { 'name': 'condAnyAbove4H '
                                                                                               '— '
                                                                                               'أي '
                                                                                               'ماكد '
                                                                                               'أعلى '
                                                                                               '(1D '
                                                                                               'A/B/C '
                                                                                               '· '
                                                                                               '1W '
                                                                                               'A/B/C) '
                                                                                               'فوق '
                                                                                               'إشارته '
                                                                                               'وفوق '
                                                                                               'خط '
                                                                                               '4H '
                                                                                               'B',
                                                                                       'logic': 'or',
                                                                                       'conditions': [ { 'logic': 'and',
                                                                                                         'conditions': [ { 'left': 'osc:macd_1d_6_13_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_1d_6_13_4.signal'},
                                                                                                                         { 'left': 'osc:macd_1d_6_13_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_4h_12_26_6.line'}]},
                                                                                                       { 'logic': 'and',
                                                                                                         'conditions': [ { 'left': 'osc:macd_1d_12_26_6.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_1d_12_26_6.signal'},
                                                                                                                         { 'left': 'osc:macd_1d_12_26_6.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_4h_12_26_6.line'}]},
                                                                                                       { 'logic': 'and',
                                                                                                         'conditions': [ { 'left': 'osc:macd_1d_18_39_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_1d_18_39_4.signal'},
                                                                                                                         { 'left': 'osc:macd_1d_18_39_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_4h_12_26_6.line'}]},
                                                                                                       { 'logic': 'and',
                                                                                                         'conditions': [ { 'left': 'osc:macd_1w_6_13_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_1w_6_13_4.signal'},
                                                                                                                         { 'left': 'osc:macd_1w_6_13_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_4h_12_26_6.line'}]},
                                                                                                       { 'logic': 'and',
                                                                                                         'conditions': [ { 'left': 'osc:macd_1w_12_26_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_1w_12_26_4.signal'},
                                                                                                                         { 'left': 'osc:macd_1w_12_26_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_4h_12_26_6.line'}]},
                                                                                                       { 'logic': 'and',
                                                                                                         'conditions': [ { 'left': 'osc:macd_1w_18_39_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_1w_18_39_4.signal'},
                                                                                                                         { 'left': 'osc:macd_1w_18_39_4.line',
                                                                                                                           'op': '>',
                                                                                                                           'right': 'osc:macd_4h_12_26_6.line'}]}]}]},
                                                     'sub_labels': [ 'w_pos',
                                                                     'd_pos',
                                                                     '4h_core',
                                                                     'any_above_4h'],
                                                     'active_start': '2026-02-08T00:00:00Z',
                                                     'active_end': '2026-11-09T00:00:00Z'},
                                         'enabled': True,
                                         'timeframe': '15m'},
                                       { 'name': 'trend_fractal',
                                         'type': 'support_resistance',
                                         'params': {'periods': [100], 'confirm_mode': 'all'},
                                         'enabled': True,
                                         'timeframe': '15m'}],
                       'entry_rules': [ { 'name': 'دخول B9 + الإغلاق فوق خط الترند 100 (شراء B9 '
                                                  'حرفياً مع بوابة ترند 100)',
                                          'condition': { 'type': 'and',
                                                         'conditions': [ { 'type': 'indicator_value',
                                                                           'operator': '>',
                                                                           'left_value': 'indicator:b9_macd_gates:b9g_buy',
                                                                           'right_value': 0},
                                                                         { 'type': 'indicator_value',
                                                                           'operator': '>',
                                                                           'left_value': 'indicator:trend_fractal:trf_p100_bias',
                                                                           'right_value': 0}]},
                                          'position_side': 'long',
                                          'weight': 1.0,
                                          'enabled': True}],
                       'exit_rules': [ { 'name': 'خروج عند ولادة خط ترند-100 علوي جديد فقط '
                                                '(الخط فوق السعر — أعلى من الإغلاق)',
                                         'condition': { 'type': 'and',
                                                        'conditions': [ { 'type': 'indicator_value',
                                                                          'operator': '>',
                                                                          'left_value': 'indicator:trend_fractal:trf_p100_new_upper',
                                                                          'right_value': 0},
                                                                        { 'type': 'indicator_value',
                                                                          'operator': '>',
                                                                          'left_value': 'indicator:trend_fractal:trf_p100_upper',
                                                                          'right_value': 'price:close'}]},
                                         'exit_type': 'signal_exit',
                                         'enabled': True}],
                       'risk_management': { 'stop_loss_percentage': 2,
                                            'take_profit_percentage': 99}},
  'initial_capital': 300.0,
  'position_sizing': 'percentage',
  'position_size_percent': 100.0,
  'max_positions': 1,
  'compounding': True,
  'multi_position_compounding': False,
  'commission_rate': 0.0,
  'slippage_percent': 0.0,
  'fill_model': 'next_open',
  'stop_loss_percent': None,
  'take_profit_percent': None,
  'take_profit_splits': None,
  'structure_split_exits': None,
  'dca_rebuy_drops_pct': None,
  'trailing_stop_percent': None,
  'trailing_stop_mode': None,
  'max_daily_loss_percent': None,
  'enable_short_selling': False,
  'enable_margin': False,
  'leverage': 1.0,
  'require_confirmation': False,
  'exit_strategy': None}


def get_presets() -> List[Dict[str, Any]]:
    """قائمة القوالب الرسمية — كل قالب حمولة كاملة جاهزة لـ POST /backtest/run."""
    return [
        {
            "id": "zigzag_hl_v2_zero_fee",
            "title": "ZigZag HL v2 — ZERO FEE",
            "description": "الاستراتيجية البطلة: دخول عند قاع زيجزاق مؤكد أعلى من القاع السابق "
                           "(Higher Low Structure)، خروج عند تأكيد قمة، SL 2%، عمولة صفرية.",
            "source": "مثبَّتة بحيا من تشغيل الواجهة 2026-10-31 (backtest1/run → backtest/run)",
            "reference_result_next_open": "10 صفقات · −1.86% · عمولة 0 · BTCUSDT 1h",
            "payload": CHAMPION_ZIGZAG_HL_V2,
            "notes": PRESET_NOTES,
        },
        {
            "id": "zlf_triple_signal_zero_fee",
            "title": "ZLF — ZigZag Liquidity Fib · 3 Entry Signals — ZERO FEE",
            "description": "الاستراتيجية الواحدة بثلاث إشارات دخول (المصفوفة المصادقة v13.2): "
                           "R = أكبر حجم أحمر بالنافذة · ref_high = أعلى قمة حمراء · G = خضراء بانطلاقة 0.382 وهيمنة الخضراء · "
                           "S1 اختراق بحجم أكبر · S2 اختراق بحجم أقل («ويبرغم عندها لفل حجم سيولتها») · S3 رفض بحجم أكبر — "
                           "الدخول بشمعة الإشارة نفسها على أي اتجاه للساق، والخروج افتراضي مؤقت (انقلاب الساق + SL 2%).",
            "source": "الجولة 13.2 — إعادة تعريف حرفية بنص الصور المصدَّق من المستخدم (قراءة الوكيلين + تصديق المستخدم)",
            "reference_result": "يُعاد التحقق منه حياً بعد النشر — عقد Round 13.0 (Zero-Fee/الدقة/البطل) لم يُلمس",
            "payload": ZLF_TRIPLE_SIGNAL,
            "notes": PRESET_NOTES,
        },
        # ✅ الجولة 22 (ROUND22) — الاستراتيجية الجديدة المنفصلة (إضافة — القوالب السابقة كما هي)
        {
            "id": "zlf_e2e_triple_signal_zero_fee",
            "title": "ZLF-End-To-End — ZigZag Liquidity Fib (Range-anchored) · 3 Entry Signals — ZERO FEE",
            "description": "المحرك المنفصل الجديد (استنساخ بلا مساس بالأصل): النطاق يُعتمد لحظة ظهور الزقزاق "
                           "ويُرسم الفيبو عليه ويبدأ الحساب من شمعة الظهور (الشموع بين القاع وظهوره مستبعدة)؛ "
                           "R = أكبر حمراء حجماً في ساق النطاق (قمة = خط الاختراق، حجمها = المرجع)؛ "
                           "S1 اختراق بحجم أكبر · S2 اختراق بحجم أقل أو مساوٍ («ويبرغم عندها لفل حجم سيولتها») · "
                           "S3 امتصاص بلا اختراق بحجم أكبر — الدخول بشمعة الإشارة نفسها (next_open)، "
                           "والخروج بانقلاب النطاق إلى هابطة + SL 2%.",
            "source": "الجولة 22 — مواصفة صاحب القرار المصادقة (الحالات الثلاث حرفياً + دورة حياة النطاق بلحظة ظهور الزقزاق)",
            "reference_result": "يُعاد التحقق منه حياً بعد النشر — عقد Zero-Fee/الدقة لم يُلمس",
            "payload": ZLF_E2E_TRIPLE_SIGNAL,
            "notes": PRESET_NOTES,
        },
        # ✅ الجولة 32 (ROUND32) — «الزقزاق البطل e2e الترنديه» (إضافة — القوالب السابقة كما هي)
        {
            "id": "zlf_e2e_trendy_triple_signal_zero_fee",
            "title": "ZLF-E2E-Trendy — الزقزاق البطل e2e الترنديه · 3 Entry Signals — ZERO FEE",
            "description": "استنساخ معزول لاستراتيجية E2E (النطاق والمصفوفة S1/S2/S3 حرفياً) + بوابة ترند على الدخول: "
                           "ثلاث ترندات فراكتالية 7/15/25 (قالبية — غيّرها أو أضف ترنداً رابعاً 30 من القالب بلا كود) "
                           "بمنطق سكربت Auto Trendline (وصل آخر فراكتالَين + تمديد أيمن + تقاطعات ta.cross) — "
                           "الترند يرسل إحداثياته للباك اند ويُحسب الإشارة بناء عليه: الدخول يستلزم انحيازاً صاعداً "
                           "بإجماع majority (2 من 3). الخام والممنوع ظاهران (entry_raw_*/entry_blocked_*) — "
                           "والخروج كما في E2E (انقلاب النطاق + SL 2%).",
            "source": "الجولة 32 — أمر صاحب القرار: استنساخ E2E + إضافة الترند بمحرك معزول للباك تست والشارت الحي "
                     "وفترات قالبية لا تُكتب داخل الكود",
            "reference_result": "يُعاد التحقق منه حياً بعد النشر — عقد Zero-Fee/الدقة لم يُلمس",
            "payload": ZLF_E2E_TRENDY_TRIPLE_SIGNAL,
            "notes": PRESET_NOTES,
        },
        # 🔥 R69 — «الترندية الملتهبة» (إضافة — القوالب السابقة كما هي)
        {
            "id": "zlf_e2e_blazing_quint_signal_zero_fee",
            "title": "ZLF-E2E-Blazing — الترندية الملتهبة · 5 Entry Signals (S1/S2/S3 + N5/N6) — ZERO FEE",
            "description": "المحرك المعزول الجديد كلياً (R69): الترندية بت-بت (S1/S2/S3 بنفس المرجع R وهيمنة الخضراء "
                           "وخط الانطلاقة وبوابة الترند) + إشارتا R68 المُقاستان على 4 رموز × 6 نوافذ (منها سنتان "
                           "خارج العينة): N5 «إشعال بلا مرجع» — نطاق لم يرَ أي حمراء منذ ولادته + صرخة فوق قمة الجبل "
                           "نفسها بهيمنة حجم (أعواد عمياء بنيوياً عند الترندية؛ نافذة البطل: أضافت الصفقة 64 الرابحة "
                           "+4.7% — 64 صفقة · +1638% مقابل 63 · +1560%) · N6 «الاختراق الهادئ» — اختراق سقف المرجع "
                           "R بلا هيمنة الخضراء (ثقة بلا ضجيج؛ مضخّم الأسواق المتعبة: INIT 47→55 صفقة · +295%→+432%). "
                           "بوابة الترند القالبية نفسها (7/15/25 majority — قالبية بلا أرقام في الكود) والأنواع المبوّبة "
                           "خمسة s1/s2/s3/n5/n6 — والخروج كما في الترندية (انقلاب النطاق + SL 2%).",
            "source": "R69 — أمر صاحب القرار: «اكتب لي الاستراتيجية الجديدة التي فيها 🔥 N5 — إشعال بلا مرجع — "
                      "وسمّها استراتيجية الترندية الملتهبة … كمان أضف +N6» فوق قياسات R68 المخبرية "
                      "(lab/trendy_x.py + results/x_signals_r68.json)",
            "reference_result": "نافذة البطل #10000233 (SOLUSDT · 1m): الأرضية 63 صفقة · +1560.14% → "
                                "الملتهبة 64 صفقة · +1638.16% — يُعاد التحقق منه حياً بعد الدمج",
            "payload": ZLF_E2E_BLAZING_QUINT_SIGNAL,
            "notes": PRESET_NOTES,
        },
        # ✅ PRO73 — «الترندية الماكدية» (إضافة — القوالب السابقة كما هي)
        {
            "id": "trendy_macdized_zero_fee",
            "title": "Trendy-MACDized — الترندية الماكدية (S1/S2/S3 + بوابة الموشرات) — ZERO FEE",
            "description": "المحرك المعزول الجديد كلياً (PRO73): الترندية بت-بت (S1/S2/S3 + بوابة الترند "
                           "القالبية 7/15/25 majority) + **نسخ المستند الكاملة** (Google Doc — 67 نسخة: "
                           "28 MACD + 16 RSI مع EMA وبولينجر StdDev 2 + 23 Momentum على الفريمات الـ14) "
                           "+ **الحالات الخاصة الثلاث عشرة المسمّاة بنص المالك** (ماكد 1-5 · آر إس آي 1-5 · "
                           "مومنتم 1-3) كأشجار شروط جاهزة قابلة للتركيب (and/or/not) والتعديل الكامل من "
                           "الفرونت إند — البوابة الافتراضية «أي حالة لحظية» (OR) والبدائل: انطباق العائلات "
                           "الثلاث / الإنذار المبكر. الشفافية الرباعية: entry_raw (خام) / entry_blocked (منعها "
                           "الترند) / entry_iblocked (منعتها الموشرات) / entry (النهائي) — وإيقاف البوابة = "
                           "هوية الترندية بت-بت.",
            "source": "PRO73 — أمر صاحب القرار (2026-11-13): استراتيجية مستنبطة من الترندية البطل "
                      "مع دمج الموشرات الثلاثة متعددة النسخ/الفريمات وشروط قابلة للتركيب",
            "reference_result": "يُعاد التحقق منه حياً بعد النشر — عقد Zero-Fee/الدقة لم يُلمس",
            "payload": TRENDY_MACDIZED,
            "notes": PRESET_NOTES,
        },
        # 🔥 PRO73 — «الملتهبة الماكدية» (إضافة — القوالب السابقة كما هي)
        {
            "id": "blazing_macdized_zero_fee",
            "title": "Blazing-MACDized — الملتهبة الماكدية (S1/S2/S3 + N5/N6 + بوابة الموشرات) — ZERO FEE",
            "description": "المحرك المعزول الجديد كلياً (PRO73): الملتهبة بت-بت (S1/S2/S3 + N5 «إشعال بلا "
                           "مرجع» + N6 «الاختراق الهادئ» + بوابة الترند القالبية) + **نسخ المستند "
                           "الكاملة** (Google Doc — 67 نسخة على الفريمات الـ14) + **الحالات الخاصة الـ13 "
                           "المسمّاة** بنص المالك كأشجار شروط قابلة للتركيب والتعديل من الفرونت إند — "
                           "الدخول النهائي لكل نوع من الخمسة = إشارته المبوّبة ∧ انطباق بوابة الحالات "
                           "(الافتراض: أي حالة لحظية OR). الحمولة كاملة: كل بيانات الملتهبة المرجعة "
                           "(نطاقات/أرجل/محاور/ترند/سيولة/current) + سلاسل الموشرات كلها — الشفافية "
                           "الرباعية لكل نوع، وإيقاف البوابة = هوية الملتهبة بت-بت.",
            "source": "PRO73 — أمر صاحب القرار (2026-11-13): «وسوي إصداراً سمّه ملتهبه ماكديه — وهذا "
                      "يكون فيه كل البيانات… المحرك عباره عن الملتهبة ولكن مع الدمج والبيانات "
                      "المرجعة كاملة مع الجديدة»",
            "reference_result": "يُعاد التحقق منه حياً بعد النشر — عقد Zero-Fee/الدقة لم يُلمس",
            "payload": BLAZING_MACDIZED,
            "notes": PRESET_NOTES,
        },
        # ✅ PRO74 — «الترندية الماكدية الخفيفة» (إضافة — القوالب السابقة كما هي)
        {
            "id": "trendy_macdized_rsi_light_zero_fee",
            "title": "Trendy-MACDized-RSI-Light — الترندية الماكدية الخفيفة (R74) — ZERO FEE",
            "description": "PRO74: نفس محرك الترندية الماكدية بت-بت لكن بسبع نسخ RSI فقط (بوابة "
                           "حالات الآر إس آي rsi_any) — ذاكرة آمنة للنوافذ الكاملة (665 ألف شمعة) "
                           "بلا قتل OOM + حياد الإحماء (لا حجب قبل جاهزية بيانات الشجرة). "
                           "البرهان على نافذة البطل: حفظ تام لكل الصفقات (صفر محجوبة) مقابل "
                           "11 محجوبة زورًا في النسخة غير المصلّحة.",
            "source": "PRO74 — تسليم 2026-11-14: اختبار مباشر على الباك اند الحي "
                      "(161.97.73.254:8000) لتكويني البطل #10000233/#10000265 كشف قتل OOM "
                      "للنسخ الكاملة المتوازية وعيب إحماء البوابة — فأُصلحا",
            "reference_result": "نافذة البطل (SOLUSDT · 1m · 665,099 شمعة): بوابة RSI المصلّحة "
                                "لا تحجب أي إشارة من إشارات البطل (حفظ تام بت-بت)",
            "payload": TRENDY_MACDIZED_RSI_LIGHT,
            "notes": PRESET_NOTES,
        },
        # 🔥 PRO74 — «الملتهبة الماكدية الخفيفة» (إضافة — القوالب السابقة كما هي)
        {
            "id": "blazing_macdized_rsi_light_zero_fee",
            "title": "Blazing-MACDized-RSI-Light — الملتهبة الماكدية الخفيفة (R74) — ZERO FEE",
            "description": "PRO74: نفس محرك الملتهبة الماكدية بت-بت (S1/S2/S3+N5/N6) لكن بسبع "
                           "نسخ RSI فقط (بوابة rsi_any) — ذاكرة آمنة للنوافذ الكاملة + حياد "
                           "الإحماء. تُرجع كل بيانات الملتهبة (256 عمودًا: زقزاق/فيبو 8 مستويات/"
                           "سيولة/إشارات بطبقاتها الأربع/ترند 7-15-25) + سلاسل RSI السبع بحقولها الأربعة.",
            "source": "PRO74 — تسليم 2026-11-14 (نفس جلسة الاختبار الحي)",
            "reference_result": "تشغيل حي فعلي على الباك اند المنشور (المهمة 10000286→8d52a695): "
                                "اكتملت على كامل نافذة البطل وأرجعت 256 عمودًا لكل شمعة",
            "payload": BLAZING_MACDIZED_RSI_LIGHT,
            "notes": PRESET_NOTES,
        },
        # ✅ QUANTUM1 — «الاستراتيجية الترندية الكمومية» (إضافة — القوالب السابقة كما هي)
        {
            "id": "zlf_e2e_trendy_quantum_triple_signal_zero_fee",
            "title": "ZLF-E2E-Trendy-Quantum — الاستراتيجية الترندية الكمومية · 3 Entry Signals — ZERO FEE",
            "description": "المحرك المعزول (QUANTUM1): الترندية بحذافيرها (S1/S2/S3 + بوابة الترند "
                           "القالبية 7/15/25 majority) + بوابة المنطقة الكمومية: زقزاق مؤكد HH+HL "
                           "(قمة أعلى + قاع أعلى) يفتح منطقة الدخول المسموحة، وLL+LH يغلقها ويُخرج "
                           "أي صفقة مفتوحة (next_open). تُرجع 109 أعمدة لكل شمعة: كل بيانات الترندية "
                           "الأصلية zzfet_* ممرَّرة بت-بت (بيانات الرسم الكاملة: زقزاق/فيبو 8 مستويات/"
                           "خطوط ترند 7-15-25/سيولة/إشارات) + أعمدة الكمومية zzfetq_* (المنطقة "
                           "zone_on/enter/exit/struct/hh/hl/lh/ll/last/prev + الشفافية الرباعية "
                           "entry_raw/entry_blocked ترند/entry_zblocked منطقة/entry النهائي). "
                           "zone_gate قالب — s1/s2/s3 أو \"none\" (بيانات المنطقة تبقى محسوبة).",
            "source": "QUANTUM1 — مواصفة صاحب القرار (جلسة الكمومية): «الترندية بحذافيرها + "
                      "المنطقة الكمومية فوق إشارات الدخول» + إصلاح بيانات الرسم الكاملة "
                      "(بيانات الترندية الأصلية يجب أن تكون موجودة في استجابة الكمومية "
                      "بالإضافة إلى بيانات الكمومية نفسها)",
            "reference_result": "المهمة الحية #10000375 (SOLUSDT · 15m · نافذة القاعدة): "
                                "+69.338535% · 31 صفقة · WR 87.1% · PF 1.978684 · "
                                "MaxDD 39.08% — تطابق بت-بت مع تشغيل التحقق",
            "payload": ZLF_E2E_TRENDY_QUANTUM_TRIPLE_SIGNAL,
            "notes": PRESET_NOTES,
        },
        # ✅ QUANTUMEMA1 — «الاستراتيجية الترندية الكمومية المتوسطة المتحركة
        # الأسية» (إضافة — القوالب السابقة كما هي)
        {
            "id": "zlf_e2e_trendy_quantum_ema_triple_signal_zero_fee",
            "title": "ZLF-E2E-Trendy-Quantum-EMA — الاستراتيجية الترندية الكمومية المتوسطة المتحركة الأسية · 3 Entry Signals — ZERO FEE",
            "description": "المحرك المعزول (QUANTUMEMA1): الكمومية بحذافيرها (S1/S2/S3 + بوابة "
                           "الترند القالبية 7/15/25 majority + بوابة المنطقة الكمومية HH+HL/"
                           "LL+LH) + **بوابة رصة المتوسطات الستة على فريم الساعة**: الشرط "
                           "الثاني للمنطقة المسموحة أن يتخطى السعر المتوسطات الستة لأعلى "
                           "بترتيب تنازلي تحت السعر — EMA 21 أولاً ثم EMA 50 ثم EMA 100 ثم "
                           "EMA 200 ثم EMA 350 ثم أسفلهم جميعاً EMA 500 — محسوبة على فريم "
                           "الساعة (resolution «60» افتراضياً — MTF EMA بلا استشراف: قيمة "
                           "كل شمعة = EMA لآخر شمعة ساعة مغلقة فقط). إذا تحقق الترتيب "
                           "بالتزامن مع HH+HL يُسمح بالتقاط إشارات الشراء. تُرجع كل "
                           "بيانات الكمومية (zzfetq_* + zzfet_* — بت-بت: زقزاق/فيبو/ترند/"
                           "سيولة/منطقة) + الخطوط الستة zzfetqe_ema_{21,50,100,200,350,500} "
                           "(رسم على فريم الشارت بألوان العقد: أخضر/بنفسجي/أصفر/أحمر/أزرق/"
                           "رمادي) + حالة الرصة (stack_ok/ready/enter/exit) + الشفافية "
                           "الخماسية (entry_raw خام / entry_blocked ترند / entry_zblocked "
                           "منطقة / entry_eblocked رصة / entry النهائي). ema_gate قالب — "
                           "s1/s2/s3 أو \"none\" (بيانات الرصة تبقى محسوبة).",
            "source": "QUANTUMEMA1 — مواصفة صاحب القرار (جلسة EMA): «استنساخ من الترندية "
                      "الكمومية + بوابة ثانية جوار بوابة قمة أعلى من قمة وقاع أعلى من "
                      "قاع — الشرط الثاني للمنطقة المسموحة أن يتخطى السعر المتوسطات "
                      "الستة لأعلى بترتيب تنازلي: EMA 21 ثم 50 ثم 100 ثم 200 ثم 350 ثم "
                      "500 (محسوبة على فريم الساعة عبر MTF EMA)»",
            "reference_result": "المهمة الحية #10000407 (SOLUSDT · 15m · نافذة القاعدة "
                                "كموميه حتا شهر 1): الأرضية +38.58% · 6 صفقات · WR 50% · "
                                "MaxDD 45.48% — مقارنة QUANTUMEMA1 المرجعية تُعاد بعد "
                                "النشر (بوابة الرصة تعزل صفقات غير الرصة)",
            "payload": ZLF_E2E_TRENDY_QUANTUM_EMA_TRIPLE_SIGNAL,
            "notes": PRESET_NOTES,
        },
        # ✅ ALMIGHTY1 — «الاستراتيجية الجبّارة» (إضافة — القوالب السابقة كما هي)
        {
            "id": "zlf_almighty_quantum_ema_a226_zero_fee",
            "title": "ALMIGHTY — الاستراتيجية الجبّارة · ZLF-End-To-End-Trendy-Quantum-EMA (A226 Championship) · 3 Entry Signals — ZERO FEE",
            "description": "نسخة البطولة A226 من المحرك المعزول (QUANTUMEMA1) — محسّنة ببحث "
                           "EMA-SEARCH (7 مراحل · 77 تجربة معزولة على سيرفر الإنتاج): "
                           "(1) رادار زقزاق عيار 226 يرصد الموجات الكبرى فقط (~80 موجة "
                           "عملاقة في 6 سنوات بدل 139 متوسطة — من خريطته تُشتق مستويات "
                           "الاختراق وفتح/إغلاق المنطقة)؛ (2) رصة EMA بخمسة خطوط على فريم "
                           "الساعة (50>100>200>350>500) — حُذف خط 21 الأسرع فبقي الدخول "
                           "متاحًا خلال تراجعات التنفس؛ (3) بوابة المنطقة الكمومية HH+HL "
                           "على إشارة s1 فقط (s2/s3 بلا فحص المنطقة). الخروج باب واحد "
                           "لم يُلمس: zone_exit (LL+LH) — بلا SL/TP/trailing. إدارة رأس "
                           "المال: 300$ · 3 مراكز · تراكم مضاعف · عمولة/انزلاق صفر · "
                           "تنفيذ next_open. ⚠ تحذيرات العرض: أقصى تراجع 44.98% · "
                           "80 صفقة فقط (عينة صغيرة) · الحقبة الأولى (2020-2023) أعطت "
                           "+2145% مقابل +248% للثانية (2023-2026) · أرقام بعمولة/انزلاق صفر.",
            "source": "EMA-SEARCH — بحث صاحب القرار (2026-11-17): «اختبر وابحث أفضل "
                      "تكوين للاستراتيجية على كامل تاريخ سولانا» — الفروقات الثلاثة "
                      "مُعزولة بُعد-واحد-في-كل-تجربة وموثقة بتطابق بت-بت محلي/حي",
            "reference_result": "المهمة الحية #10000493 (SOLUSDT · 15m · كامل التاريخ "
                                "2020-03-16 → 2026-11-17): +9402.449654% · 80 صفقة "
                                "(41R/39L) · WR 51.25% · PF 2.0746 · MaxDD 44.98% · "
                                "Sharpe 3.2805 · Sortino 20.84 · SQN 3.15 · Kelly "
                                "0.444 · رصيد نهائي $28,507.35 من $300 · math_audit "
                                "بلا خطأ (تطابق بت-بت)",
            "payload": ZLF_ALMIGHTY_QUANTUM_EMA_TRIPLE_SIGNAL,
            "notes": PRESET_NOTES,
        },
        # 🔥 QMOM1 — «كموميه الزخم الاولى» (إضافة — القوالب السابقة كما هي)
        {
            "id": "qmom1_quantum_momentum_zero_fee",
            "title": "QMOM1 — كموميه الزخم الاولى · Trend+Zone+EMA-stack(هرمية)+Momentum-gate · 3 Entry Signals — ZERO FEE",
            "description": "المحرك المعزول (QMOM1) على تكوينه الافتراضي المعتمد "
                           "(S1/S2/S3 + بوابة الترند 7/15/25 + المنطقة الكمومية + "
                           "رصة EMA الستة الكاملة مع EMA21 — الديفولت length=100 "
                           "قابل للتعديل من الواجهة) + "
                           "✅ EMAGATE-UNIFIED رصة EMA الهرمية الموحدة (الشروط "
                           "السبعة: السعر فوق الكل + السلّم مرتب تماماً بالأطوال "
                           "+ الأسرع من القاعدة 21 معفاة من الترتيب — عمود تشخيص "
                           "لكل زوج) + بوابة الشروط المرنة للموشرات متعددة "
                           "الفريمات (7 نسخ: MACD 4h/3d/1d + RSI 1h/4h/1d×2 — شجرة "
                           "and/or/not قابلة للتركيب والتعديل من الفرونت-اند كله): "
                           "الشرط 1 MACD 4h فوق الصفر ∧ إيجابي · الشرط 2 MACD 3d فوق "
                           "MACD 1d · الشرط 3 RSI 1h و4h فوق اليومي · الشرط 4 RSI "
                           "اليومي (10 أو 14) فوق 50. الشفافية الرباعية: entry_raw «"
                           "الخام/entry_eblocked الرصة/entry_iblocked الزخم/entry "
                           "النهائي — والخروج باب واحد كما في البطل: zone_exit "
                           "(LL+LH) على دقة 5 دقائق (ZONE-EXIT-LTF1).",
            "source": "QMOM1 — طلب صاحب القرار (2026-11-18): «سنقوم باضافه بوابه "
                      "جديده للشروط وتكون مرنه وقابله للتعديل والاضافه ع اي "
                      "استراتيجيه ... ونسوي من ZLF-End-To-End-Trendy-Quantum-EMA "
                      "نسخه باسم: كموميه الزخم الاولى» + EMAGATE-UNIFIED "
                      "(2026-11-19): «تطبيق التعديل على اي مكان فيه البوابه — موحد "
                      "ومركزي ومنظم»",
            "reference_result": "الحمولة المرجعية الموثقة #10000604 (نفس تكوين القالب "
                                "بت-بت: ديفولت 100 + رصة الستة الكاملة) · التحقق "
                                "الحي #10000617 (MMT · 15m · مع اغلاق 5 دقايق): "
                                "بوابة الزخم 46 خام → 11 نهائي → 35 محجوب · PnL من "
                                "−26.53% إلى −20.99% · MaxDD من 29.49% إلى 17.98% · "
                                "العدادات بت-بت مع التشغيل المحلي — تُعاد المقارنة "
                                "المرجعية بعد النشر",
            "payload": QMOM1_TRIPLE_SIGNAL,
            "notes": PRESET_NOTES,
        },
        # ✅ B9 (2026-11-22) — «ماكد 9B + ترند 100» (إضافة — القوالب السابقة كما هي)
        {
            "id": "b9_trend100_zero_fee",
            "title": "B9-T100 — ماكد 9B + ترند 100 · خروج ولادة خط علوي فقط + الخط فوق السعر — ZERO FEE",
            "description": "«MACD Buy Strategy 9B» محوّلة من Pine ومدمجة مع ترند 100: "
                           "الدخول = شروط B9 الأربعة (إيجابية الماكد الأسبوعي A/B/C "
                           "6-13-4/12-26-4/18-39-4 + اليومي B/C 12-26-6/18-39-4 + نواة "
                           "4H B 12-26-6 فوق إشارته وفوق الصفر + أي ماكد أعلى فوق إشارته "
                           "وفوق خط 4H B) ∧ الإغلاق فوق خط الترند 100 (fractal فترة 100). "
                           "الخروج = ولادة خط ترند-100 علوي جديد فقط ∧ الخط العلوي فوق "
                           "السعر (قيمته أعلى من الإغلاق) — تصحيح صاحب القرار. إدارة نقية بإشارات فقط — بلا SL/TP/تريلينق/جني "
                           "مقسم/تعزيز. الإسقاط سببي (آخر شريط HTF مكتمل — confirmed) "
                           "والإحماء فشل-إغلاق ونافذة تفعيل active_start/active_end تحصر "
                           "الصفقات داخل نافذة التقييم بينما تُحسب القيم على البيانات "
                           "الممتدة قبلها (إحماء MACD الأسبوعي كما يراه TradingView).",
            "source": "B9 — طلب صاحب القرار (2026-11-22): «استراتيجيه جديده مبنيه "
                      "باستخدام بين سكربت اريد منك ان تحولها وتدمجها في النظام "
                      "ونختبرها ع العملات eth,xrp,mbl ... سندمج عليها ترند 100 هنا "
                      "يتحقق شرط الشراء · الخروج او البيع يكون اذا استجد ترند 100 "
                      "في رسم جديد»",
            "reference_result": "التحقق المحلي الكامل (2026-11-22): مطابقة قيم MACD "
                                "للنسخ السبع بمرجع مستقل بت-بت (خطأ 0.00e+00 على "
                                "~500 ألف نقطة) · ETHUSDT (نافذة 2026-02-08→2026-11-09): "
                                "5 صفقات · +20.50% · MaxDD 4.31% · XRPUSDT "
                                "(2025-12-18→2026-11-09): صفقة واحدة · −1.52% · "
                                "MBLUSDT (2025-03-13→2026-11-11): 14 صفقة · +1.24% · "
                                "كل الصفقات داخل نافذتها وكل المخارج بشرط ولادة خط "
                                "الترند-100 حصراً (تحقق شمعة-بشمعة 20/20)",
            "payload": B9_TREND100,
            "notes": "قالب B9: عدّل symbols/start_date/end_date و active_start/"
                     "active_end معًا (نافذة التقييم) — أزل active_start/active_end "
                     "لتشغيل الإشارات على كامل نافذة البيانات. بيانات ما قبل "
                     "start_date في الحمولة = إحماء MACD الأسبوعي (≈18 شهراً) — "
                     "احتفظ بها لنتائج مطابقة لـ TradingView.",
        },
    ]
