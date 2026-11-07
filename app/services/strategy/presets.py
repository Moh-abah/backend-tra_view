# =============================================================================
# ✅ الجولة 12 — قوالب الاستراتيجيات الرسمية (presets)
# =============================================================================
# المصدر: حمولة البطل المُثبَّتة بحيا من الواجهة (backtest1/run → backtest/run):
#   ZigZag HL v2 — ZERO FEE · BTCUSDT · 1h · دخول قاع زيجزاق مؤكد أعلى من سابقه
#   (Higher Low Structure) · الخروج عند تأكيد قمة · SL 2% · عمولة 0.
#
# ملاحظات مثبتة بهذا التشغيل (العقد):
#   - position_size_percent عشري بحد أقصى 1.0 = رأس مال كامل (100%).
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

__all__ = ["CHAMPION_ZIGZAG_HL_V2", "ZLF_TRIPLE_SIGNAL", "get_presets", "PRESET_NOTES"]


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
    "position_size_percent": 1.0,
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
    "position_size_percent": 1.0,
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
    "position_size_percent": 1.0,
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
    "position_size_percent": 1.0,
    "max_positions": 1,
    "commission_rate": 0,
    "slippage_percent": 0,
    "leverage": 1,
}


PRESET_NOTES: List[str] = [
    "position_size_percent عشري بحد أقصى 1.0 = رأس مال كامل (100%) — لا يُرسل كنسبة مئوية (100).",
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
    ]
