# =============================================================================
# ✅ الجولة 11 (v2) — أعمدة مؤشرات البنية ind_* — العقد الملزم مع الفرونت
# =============================================================================
# مصدر الحقيقة الوحيد لتحويل نتائج compute_overlays إلى أعمدة مسطّحة لكل شمعة
# تُستهلك في: محرك الاستراتيجيات (_prepare_indicators)، الباك-تست، chart-data.
#
# العقد (نهائي ملزم — الواجهة بُنيت عليه):
#
#   Zig Zag Channels:
#     ind_zz_state           : 0 = نظام قمم، 1 = نظام قيعان (None قبل التمهيد)
#     ind_zz_pivot           : +1 = قمة مؤكدة عند هذه الشمعة، -1 = قاع مؤكد، 0 لا شيء
#     ind_zz_pivot_high      : سعر القمة المؤكدة (عند شمعة التأكيد فقط، وإلا None)
#     ind_zz_pivot_low       : سعر القاع المؤكد (عند شمعة التأكيد فقط، وإلا None)
#     ind_zz_prev_pivot_low  : سعر القاع المؤكد السابق (يبقى حتى القاع التالي)
#     ind_zz_prev_pivot_high : سعر القمة المؤكدة السابقة
#
#   ZigZag Fib Retracement (الجولة 12 — فيبو مركّب على الساق الأخيرة للزيجزاق):
#     ind_zzf_dir            : +1 ساق صاعدة (قاع→قمة) / -1 هابطة / 0 لا ساق بعد
#     ind_zzf_p1             : سعر بداية الساق
#     ind_zzf_p2             : سعر نهاية الساق
#     ind_zzf_i1 / ind_zzf_i2: فهما شمعتا بداية/نهاية الساق
#     ind_zzf_level_<LEVEL>  : سعر كل مستوى مفعّل (0.236 → level_0236)
#     ind_zzf_touch          : +1 أول لمس للمستوى الهدف 0.618 في ساق صاعدة /
#                              -1 عكسها في الهابطة / 0 (لمس واحد لكل ساق —
#                              إعادة تسليح عند تغيّر الساق)
#
#   ✅ الجولة 13.2 (ZLF v13.2) — الأعمدة الـ12 بدلالات المصفوفة المصادقة
#     (ثلاث جهات: قراءة الوكيلين + تصديق المستخدم — تقسيم بعلاقة الحجم مع
#      الحمراء لا بالإغلاق):
#     ind_zzf_liq_state      : 0 لا إشارة (لا مرجع / غير أخضر / الخلية الرابعة)
#                              / 1 = S1 اختراق قمة الحمراء بحجم أكبر
#                              / 2 = S2 اختراق قمة الحمراء بحجم أقل أو مساوٍ
#                              / 3 = S3 رفض بلا اختراق بحجم أكبر
#                              (الحالة توصف للشموع الخضراء ذات المرجع فقط؛
#                               الإشارة تتطلب أيضاً الهيمنة والانطلاقة)
#     ind_zzf_liq_ref_high   : أعلى high لشمعة حمراء داخل النافذة [i−lookback, i−1]
#                              (محور الاختراق الموحد) — None عند لا مرجع
#     ind_zzf_liq_ref_vol    : حجم شمعة المرجع R (أكبر حجم بالنافذة بشرط أنها حمراء)
#     ind_zzf_liq_vol_ok     : 1 إذا volume[i] > حجم المرجع (علاقة S1/S3) وإلا 0
#     ind_zzf_signal_s1      : 1 حدث S1 (اختراق + حجم أكبر + خضراء + هيمنة + انطلاقة/تسليح)
#     ind_zzf_signal_s2      : 1 حدث S2 (اختراق + حجم أقل أو مساوٍ + خضراء + هيمنة + انطلاقة/تسليح)
#     ind_zzf_signal_s3      : 1 حدث S3 (رفض + حجم أكبر + خضراء + هيمنة + انطلاقة/تسليح)
#     ind_zzf_signal_any     : 1 أي حدث سيولي (s1|s2|s3)
#     ind_zzf_entry_s1       : 1 دخول مُسند لـS1 — بشمعة الحدث نفسها (المثالي)
#                              أو أول شمعة انطلاقة خلال liq_arm_bars (الخطة البديلة)
#     ind_zzf_entry_s2       : 1 نفسه للإشارة S2
#     ind_zzf_entry_s3       : 1 نفسه للإشارة S3
#     ind_zzf_entry          : 1 عند أي دخول (الجامع)
#     ملحوظات العقد:
#       - الدخول على أي اتجاه لآخر ساق مؤكدة (أُلغي اشتراط الساق الصاعدة — v13.2).
#       - الانطلاقة: low ≥ price(0.382) لآخر ساق مؤكدة = خط 0.618 بمقياس
#         المستخدم (0 عند نهاية المسار) — المصادقة من ثلاث جهات.
#       - SFP (إشارة رابعة اختيارية مطفأة افتراضياً بـ liq_sfp_signals=True):
#         عمودا امتداد ind_zzf_signal_sfp / ind_zzf_entry_sfp يظهران فقط عند
#         التفعيل — خارج عدّاد الأعمدة الـ25 أعلاه.
#
#   Auto Fib Retracement:
#     ind_fib_dir      : +1 ساق صاعدة / -1 هابطة / 0
#     ind_fib_start    : بداية الساق (p1)
#     ind_fib_end      : نهاية الساق (p2)
#     ind_fib_target   : مستوى الهدف (0.618 افتراضياً) عند كل شمعة
#     ind_fib_signal   : +1 = Buy Retrace · -1 = Sell Retrace · 0
#                        (منطق أول لمس + إعادة تسليح مطابق للسكربت — موجود
#                         أصلاً في signals[] من compute_overlays)
#
#   Auto Trendline:
#     ind_atl_upper       : سعر مسقط الخط العلوي عند الشمعة (None إن لا خط)
#     ind_atl_lower       : سعر مسقط الخط السفلي
#     ind_atl_signal      : +1 = إغلاق قطع العلوي لأعلى · -1 = إغلاق قطع السفلي
#                           لأسفل · 0 (اتجاها over-السفلي/under-العلوي لا يُعدان)
#     ind_atl_cross_upper : 1/0 (تقاطع بأي اتجاه مع العلوي)
#     ind_atl_cross_lower : 1/0
#
# ملاحظة repaint: أعمدة الزيجزاج تُكتب عند شمعة التأكيد (confirmed_at_bar =
# نقطة + length) لا عند شمعة النقطة — لذا القراءة عند شمعة التأكيد بلا repaint.
#
# الأسماء المقبولة في strategy_config.indicators[].name (كلها مرادفات):
#   zigzag | zigzag_channels           → base "zigzag"
#   fib | auto_fib_retracement         → base "fib"
#   trendline | auto_trendline         → base "trendline"
# =============================================================================

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "OVERLAY_ALIASES",
    "CONTRACT_COLUMNS",
    "KNOWN_OVERLAY_BASES",
    "normalize_overlay_name",
    "is_known_indicator_name",
    "config_to_overlay_params",
    "columns_from_overlays_result",
    "columns_for_configs",
]

# ---------------------------------------------------------------- الأسماء ---

# اسم وارد من الواجهة → base الدالة في overlays.py
OVERLAY_ALIASES: Dict[str, str] = {
    "zigzag": "zigzag",
    "zigzag_channels": "zigzag",
    "fib": "fib",
    "auto_fib_retracement": "fib",
    "trendline": "trendline",
    "auto_trendline": "trendline",
    # الجولة 12: فيبو الزيجزاق المدمج
    "zigzag_fib": "zzfib",
    "zzfib": "zzfib",
    # ✅ ROUND22: ZLF-End-To-End — المحرك المنفصل الجديد (أسماء جديدة تماماً)
    "zigzag_fib_e2e": "zzfib_e2e",
    "zzfib_e2e": "zzfib_e2e",
    # ✅ ROUND32: «الزقزاق البطل e2e الترنديه» — الاستنساخ المعزول + مؤشر الترند المستقل
    "zigzag_fib_e2e_trendy": "zzfib_e2e_trendy",
    "zzfib_e2e_trendy": "zzfib_e2e_trendy",
    # 🔥 R69: «الترندية الملتهبة» — الترندية بت-بت + N5/N6 (محرك معزول جديد كلياً)
    "zigzag_fib_e2e_blazing": "zzfib_e2e_blazing",
    "zzfib_e2e_blazing": "zzfib_e2e_blazing",
    # ✅ PRO73: «الترندية الماكدية» — الترندية بت-بت + موشرات متعددة النسخ/
    # الفريمات + بوابة شروط قابلة للتركيب (محرك معزول جديد كلياً)
    "zigzag_fib_e2e_trendy_macd": "zzfib_e2e_trendy_macd",
    "zzfib_e2e_trendy_macd": "zzfib_e2e_trendy_macd",
    # ✅ PRO73: «الملتهبة الماكدية» — الملتهبة بت-بت + نفس الموشرات والبوابة
    "zigzag_fib_e2e_blazing_macd": "zzfib_e2e_blazing_macd",
    "zzfib_e2e_blazing_macd": "zzfib_e2e_blazing_macd",
    # ✅ QUANTUM1: «الاستراتيجية الترندية الكمومية» — الترندية بحذافيرها +
    # بوابة المنطقة الكمومية (HH+HL يفتح · LL+LH يغلق ويخرج next_open).
    "zigzag_fib_e2e_trendy_quantum": "zzfib_e2e_trendy_quantum",
    "zzfib_e2e_trendy_quantum": "zzfib_e2e_trendy_quantum",
    # ✅ QUANTUMEMA1: «الاستراتيجية الترندية الكمومية المتوسطة المتحركة الأسية» —
    # الكمومية بحذافيرها + بوابة رصة EMA الستة على فريم الساعة (EMA 21/50/
    # 100/200/350/500 تنازلياً تحت السعر — MTF EMA بلا استشراف).
    "zigzag_fib_e2e_trendy_quantum_ema": "zzfib_e2e_trendy_quantum_ema",
    "zzfib_e2e_trendy_quantum_ema": "zzfib_e2e_trendy_quantum_ema",
    # QMOM1: "quantum momentum first" (كموميه الزخم الاولى) — quantum-EMA
    # verbatim + the flexible multi-timeframe oscillator conditions gate.
    "zigzag_fib_e2e_trendy_quantum_ema_mom": "zzfib_e2e_trendy_quantum_ema_mom",
    "zzfib_e2e_trendy_quantum_ema_mom": "zzfib_e2e_trendy_quantum_ema_mom",
    # ✅ MTFEMA1: «MTF EMA» — المتوسط الأسي متعدد الفريمات (Pine بحذافيره
    # بلا استشراف — قابل للتخصيص من الواجهة، رسم الآن وشروط لاحقاً).
    "mtf_ema": "mtf_ema",
    "mtfema": "mtf_ema",
    "multi_timeframe_ema": "mtf_ema",
    "multi_timeframe_exponential_moving_average": "mtf_ema",
    "trend_fractal": "trend_fractal",
    "fractal_trendlines": "trend_fractal",
    # ✅ B9: «ماكد 9B» — بوابات MACD متعددة الفريمات (MACD Buy Strategy 9B).
    "b9_macd_gates": "b9_macd_gates",
    "b9": "b9_macd_gates",
    "b9_macd": "b9_macd_gates",
}

KNOWN_OVERLAY_BASES = ("zigzag", "fib", "trendline", "zzfib", "zzfib_e2e",
                       "zzfib_e2e_trendy", "zzfib_e2e_blazing",  # ✅ ROUND32 + 🔥 R69
                       "zzfib_e2e_trendy_macd", "zzfib_e2e_blazing_macd",  # ✅ PRO73
                       "zzfib_e2e_trendy_quantum",  # ✅ QUANTUM1 — الاستراتيجية الترندية الكمومية
                       "zzfib_e2e_trendy_quantum_ema",  # ✅ QUANTUMEMA1 — الكمومية المتوسطة المتحركة الأسية
                       "zzfib_e2e_trendy_quantum_ema_mom",  # QMOM1 — quantum momentum first: quantum-EMA + flexible conditions gate
                       "mtf_ema",  # ✅ MTFEMA1 — MTF EMA متعدد الفريمات
                       "trend_fractal",  # ✅ ROUND32 — مؤشر الترند المستقل (فراكتالات)
                       "b9_macd_gates")  # ✅ B9 — «ماكد 9B» بوابات MACD متعددة الفريمات

# أسماء الأعمدة التعاقدية لكل base (للتوثيق والفحص)
CONTRACT_COLUMNS: Dict[str, List[str]] = {
    "zigzag": [
        "ind_zz_state", "ind_zz_pivot", "ind_zz_pivot_high", "ind_zz_pivot_low",
        "ind_zz_prev_pivot_low", "ind_zz_prev_pivot_high",
    ],
    "fib": [
        "ind_fib_dir", "ind_fib_start", "ind_fib_end", "ind_fib_target", "ind_fib_signal",
    ],
    "trendline": [
        "ind_atl_upper", "ind_atl_lower", "ind_atl_signal",
        "ind_atl_cross_upper", "ind_atl_cross_lower",
    ],
    "zzfib": [
        "ind_zzf_dir", "ind_zzf_p1", "ind_zzf_p2", "ind_zzf_i1", "ind_zzf_i2",
        "ind_zzf_level_0", "ind_zzf_level_0236", "ind_zzf_level_0382",
        "ind_zzf_level_05", "ind_zzf_level_0618", "ind_zzf_level_0786",
        "ind_zzf_level_1", "ind_zzf_touch",
        # ✅ الجولة 13.1 (ZLF) — السيولة والدخول بثلاث إشارات
        "ind_zzf_liq_state", "ind_zzf_liq_ref_high", "ind_zzf_liq_ref_vol",
        "ind_zzf_liq_vol_ok", "ind_zzf_signal_s1", "ind_zzf_signal_s2",
        "ind_zzf_signal_s3", "ind_zzf_signal_any", "ind_zzf_entry",
        "ind_zzf_entry_s1", "ind_zzf_entry_s2", "ind_zzf_entry_s3",
    ],
    # ✅ ROUND22 (ZLF-End-To-End) — عقد المحرك المنفصل الجديد — كل الأسماء مختلفة
    # (zzfe_* → ind_zzfe_*). النطاق = لحظة ظهور الزقزاق؛ لا liq_lookback
    # (نافذة الحساب = عمر النطاق الحي)؛ R = أكبر حمراء في ساق النطاق.
    "zzfib_e2e": [
        "ind_zzfe_dir", "ind_zzfe_p1", "ind_zzfe_p2", "ind_zzfe_i1", "ind_zzfe_i2",
        "ind_zzfe_level_0", "ind_zzfe_level_0236", "ind_zzfe_level_0382",
        "ind_zzfe_level_05", "ind_zzfe_level_0618", "ind_zzfe_level_0786",
        "ind_zzfe_level_085415", "ind_zzfe_level_1",
        "ind_zzfe_liq_state", "ind_zzfe_liq_ref_high", "ind_zzfe_liq_ref_vol",
        "ind_zzfe_liq_vol_ok", "ind_zzfe_signal_s1", "ind_zzfe_signal_s2",
        "ind_zzfe_signal_s3", "ind_zzfe_signal_any", "ind_zzfe_entry",
        "ind_zzfe_entry_s1", "ind_zzfe_entry_s2", "ind_zzfe_entry_s3",
    ],
    # ✅ ROUND32 (ZLF-End-To-End-Trendy) — عقد «الترندية» — كل الأسماء جديدة كلياً
    # (zzfet_* → ind_zzfet_*): E2E حرفياً + ثلاثية البوابة الشفافة (الخام/المبوّب/
    # الممنوع) + حالة الترند والمجاميع. مرايا الفترات (ind_zzfet_tr_p{n}_*) ديناميكية
    # حسب قالب الفترات — المذكور هنا للفترات الافتراضية [7,15,25].
    "zzfib_e2e_trendy": [
        "ind_zzfet_dir", "ind_zzfet_p1", "ind_zzfet_p2", "ind_zzfet_i1", "ind_zzfet_i2",
        "ind_zzfet_anchor", "ind_zzfet_range_index",
        "ind_zzfet_liq_state", "ind_zzfet_liq_ref_high", "ind_zzfet_liq_ref_vol",
        "ind_zzfet_liq_vol_ok", "ind_zzfet_signal_s1", "ind_zzfet_signal_s2",
        "ind_zzfet_signal_s3", "ind_zzfet_signal_any",
        "ind_zzfet_entry", "ind_zzfet_entry_raw",
        "ind_zzfet_entry_s1", "ind_zzfet_entry_s2", "ind_zzfet_entry_s3",
        "ind_zzfet_entry_raw_s1", "ind_zzfet_entry_raw_s2", "ind_zzfet_entry_raw_s3",
        "ind_zzfet_entry_blocked_s1", "ind_zzfet_entry_blocked_s2", "ind_zzfet_entry_blocked_s3",
        "ind_zzfet_trend_ok", "ind_zzfet_trend_bias",
        "ind_zzfet_trend_votes_bull", "ind_zzfet_trend_votes_bear",
        "ind_zzfet_tr_p7_upper", "ind_zzfet_tr_p7_lower", "ind_zzfet_tr_p7_bias",
        "ind_zzfet_tr_p15_upper", "ind_zzfet_tr_p15_lower", "ind_zzfet_tr_p15_bias",
        "ind_zzfet_tr_p25_upper", "ind_zzfet_tr_p25_lower", "ind_zzfet_tr_p25_bias",
    ],
    # ✅ QUANTUM1 (ZLF-End-To-End-Trendy-Quantum) — عقد «الاستراتيجية الترندية
    # الكمومية»: مرآة كاملة لعقد الترندية (zzfetq_* → ind_zzfetq_*) + أعمدة
    # المنطقة (zone_on/enter/exit/struct/hh/hl/lh/ll/last/prev — 12) + الشفافية
    # الرباعية (entry_raw/entry_blocked ترند/entry_zblocked منطقة/entry نهائي)
    # + ✅ التمرير الكامل: أعمدة الترندية الأصلية zzfet_* (47) تُرجع أيضاً
    # (ind_zzfet_* — بيانات الرسم: زقزاق/فيبو/خطوط ترند/سيولة/إشارات/ترند)
    # كما كانت الترندية ترجعها بحذافيرها بالقيم نفسها بت-بت.
    "zzfib_e2e_trendy_quantum": [
        "ind_zzfetq_dir", "ind_zzfetq_p1", "ind_zzfetq_p2", "ind_zzfetq_i1", "ind_zzfetq_i2",
        "ind_zzfetq_anchor", "ind_zzfetq_range_index",
        "ind_zzfetq_liq_state", "ind_zzfetq_liq_ref_high", "ind_zzfetq_liq_ref_vol",
        "ind_zzfetq_liq_vol_ok", "ind_zzfetq_signal_s1", "ind_zzfetq_signal_s2",
        "ind_zzfetq_signal_s3", "ind_zzfetq_signal_any",
        "ind_zzfetq_entry", "ind_zzfetq_entry_raw",
        "ind_zzfetq_entry_s1", "ind_zzfetq_entry_s2", "ind_zzfetq_entry_s3",
        "ind_zzfetq_entry_raw_s1", "ind_zzfetq_entry_raw_s2", "ind_zzfetq_entry_raw_s3",
        "ind_zzfetq_entry_blocked_s1", "ind_zzfetq_entry_blocked_s2", "ind_zzfetq_entry_blocked_s3",
        "ind_zzfetq_entry_zblocked_s1", "ind_zzfetq_entry_zblocked_s2", "ind_zzfetq_entry_zblocked_s3",
        "ind_zzfetq_trend_ok", "ind_zzfetq_trend_bias",
        "ind_zzfetq_trend_votes_bull", "ind_zzfetq_trend_votes_bear",
        "ind_zzfetq_tr_p7_upper", "ind_zzfetq_tr_p7_lower", "ind_zzfetq_tr_p7_bias",
        "ind_zzfetq_tr_p15_upper", "ind_zzfetq_tr_p15_lower", "ind_zzfetq_tr_p15_bias",
        "ind_zzfetq_tr_p25_upper", "ind_zzfetq_tr_p25_lower", "ind_zzfetq_tr_p25_bias",
        "ind_zzfetq_zone_last_high", "ind_zzfetq_zone_prev_high",
        "ind_zzfetq_zone_last_low", "ind_zzfetq_zone_prev_low",
        "ind_zzfetq_zone_hh", "ind_zzfetq_zone_hl",
        "ind_zzfetq_zone_lh", "ind_zzfetq_zone_ll",
        "ind_zzfetq_zone_on", "ind_zzfetq_zone_struct",
        "ind_zzfetq_zone_enter", "ind_zzfetq_zone_exit",
        # ✅ ZONE-EXIT-TF1 — أعمدة فريم هيكل الخروج (CHoCH على أي فريم)
        "ind_zzfetq_zone_exit_base", "ind_zzfetq_zone_exit_htf_enter",
        "ind_zzfetq_zone_exit_htf_on",
        # ✅ التمرير — عقد الترندية الأصلي مُرجع أيضاً (بيانات الرسم الكاملة):
        "ind_zzfet_dir", "ind_zzfet_p1", "ind_zzfet_p2", "ind_zzfet_i1", "ind_zzfet_i2",
        "ind_zzfet_anchor", "ind_zzfet_range_index",
        "ind_zzfet_level_0", "ind_zzfet_level_0236", "ind_zzfet_level_0382",
        "ind_zzfet_level_05", "ind_zzfet_level_0618", "ind_zzfet_level_0786",
        "ind_zzfet_level_085415", "ind_zzfet_level_1",
        "ind_zzfet_liq_state", "ind_zzfet_liq_ref_high", "ind_zzfet_liq_ref_vol",
        "ind_zzfet_liq_vol_ok", "ind_zzfet_signal_s1", "ind_zzfet_signal_s2",
        "ind_zzfet_signal_s3", "ind_zzfet_signal_any",
        "ind_zzfet_entry", "ind_zzfet_entry_raw",
        "ind_zzfet_entry_s1", "ind_zzfet_entry_s2", "ind_zzfet_entry_s3",
        "ind_zzfet_entry_raw_s1", "ind_zzfet_entry_raw_s2", "ind_zzfet_entry_raw_s3",
        "ind_zzfet_entry_blocked_s1", "ind_zzfet_entry_blocked_s2", "ind_zzfet_entry_blocked_s3",
        "ind_zzfet_trend_ok", "ind_zzfet_trend_bias",
        "ind_zzfet_trend_votes_bull", "ind_zzfet_trend_votes_bear",
        "ind_zzfet_tr_p7_upper", "ind_zzfet_tr_p7_lower", "ind_zzfet_tr_p7_bias",
        "ind_zzfet_tr_p15_upper", "ind_zzfet_tr_p15_lower", "ind_zzfet_tr_p15_bias",
        "ind_zzfet_tr_p25_upper", "ind_zzfet_tr_p25_lower", "ind_zzfet_tr_p25_bias",
    ],
    # ✅ QUANTUMEMA1 (ZLF-End-To-End-Trendy-Quantum-EMA) — عقد «الاستراتيجية
    # الترندية الكمومية المتوسطة المتحركة الأسية»: مرآة كاملة لعقد الكمومية
    # (zzfetqe_* → ind_zzfetqe_*) + ✅ التمرير الكامل لعقدَي الكمومية نفسها
    # (ind_zzfetq_* + ind_zzfet_* — بيانات الرسم الكاملة بت-بت) + الخطوط
    # الستة ind_zzfetqe_ema_{21,50,100,200,350,500} (رسم على فريم الشارت —
    # محسوبة على فريم الساعة 60) + حالة الرصة (stack_ok/ready/enter/exit)
    # + الشفافية الخماسية (entry_raw خام / entry_blocked ترند /
    # entry_zblocked منطقة / entry_eblocked رصة EMA / entry النهائي).
    # QMOM1 (ZLF-End-To-End-Trendy-Quantum-EMA-Mom — "quantum momentum first") —
    # the quantum-EMA mirror (zzfetqem_X -> ind_zzfetqem_X) + the momentum-gate
    # transparency (entry_iblocked + osc_gate) + the dynamic oscillator series
    # ind_zzfetqem_osc_<id>_<field> (macd: line/signal/hist · rsi: value/ma/
    # bb_upper/bb_lower · mom: line/pct — one column per instance field, any
    # count, 22 timeframes) + full pass-through of the quantum and trendy
    # contracts (ind_zzfetq_* + ind_zzfet_* — verbatim drawing data).
    "zzfib_e2e_trendy_quantum_ema_mom": [
        "ind_zzfetqem_entry", "ind_zzfetqem_entry_iblocked",
        "ind_zzfetqem_entry_s1", "ind_zzfetqem_entry_s2", "ind_zzfetqem_entry_s3",
        "ind_zzfetqem_entry_iblocked_s1", "ind_zzfetqem_entry_iblocked_s2",
        "ind_zzfetqem_entry_iblocked_s3", "ind_zzfetqem_osc_gate",
        "ind_zzfetqem_zone_exit",
        # dynamic: ind_zzfetqem_osc_<id>_{line,signal,hist} for macd instances
        # dynamic: ind_zzfetqem_osc_<id>_{value,ma,bb_upper,bb_lower} for rsi
        # dynamic: ind_zzfetqem_osc_<id>_{line,pct} for mom
        # + full mirror of every zzfetqe_* column (entry_raw/blocked/zblocked/
        # eblocked · trend · zone · ema lines · stack state · liq · zigzag)
        # + pass-through ind_zzfetq_* (62) + ind_zzfet_* (47).
    ],
    "zzfib_e2e_trendy_quantum_ema": [
        "ind_zzfetqe_dir", "ind_zzfetqe_p1", "ind_zzfetqe_p2", "ind_zzfetqe_i1", "ind_zzfetqe_i2",
        "ind_zzfetqe_anchor", "ind_zzfetqe_range_index",
        "ind_zzfetqe_liq_state", "ind_zzfetqe_liq_ref_high", "ind_zzfetqe_liq_ref_vol",
        "ind_zzfetqe_liq_vol_ok", "ind_zzfetqe_signal_s1", "ind_zzfetqe_signal_s2",
        "ind_zzfetqe_signal_s3", "ind_zzfetqe_signal_any",
        "ind_zzfetqe_entry", "ind_zzfetqe_entry_raw",
        "ind_zzfetqe_entry_s1", "ind_zzfetqe_entry_s2", "ind_zzfetqe_entry_s3",
        "ind_zzfetqe_entry_raw_s1", "ind_zzfetqe_entry_raw_s2", "ind_zzfetqe_entry_raw_s3",
        "ind_zzfetqe_entry_blocked_s1", "ind_zzfetqe_entry_blocked_s2", "ind_zzfetqe_entry_blocked_s3",
        "ind_zzfetqe_entry_zblocked_s1", "ind_zzfetqe_entry_zblocked_s2", "ind_zzfetqe_entry_zblocked_s3",
        "ind_zzfetqe_entry_eblocked_s1", "ind_zzfetqe_entry_eblocked_s2", "ind_zzfetqe_entry_eblocked_s3",
        "ind_zzfetqe_trend_ok", "ind_zzfetqe_trend_bias",
        "ind_zzfetqe_trend_votes_bull", "ind_zzfetqe_trend_votes_bear",
        "ind_zzfetqe_tr_p7_upper", "ind_zzfetqe_tr_p7_lower", "ind_zzfetqe_tr_p7_bias",
        "ind_zzfetqe_tr_p15_upper", "ind_zzfetqe_tr_p15_lower", "ind_zzfetqe_tr_p15_bias",
        "ind_zzfetqe_tr_p25_upper", "ind_zzfetqe_tr_p25_lower", "ind_zzfetqe_tr_p25_bias",
        "ind_zzfetqe_zone_last_high", "ind_zzfetqe_zone_prev_high",
        "ind_zzfetqe_zone_last_low", "ind_zzfetqe_zone_prev_low",
        "ind_zzfetqe_zone_hh", "ind_zzfetqe_zone_hl",
        "ind_zzfetqe_zone_lh", "ind_zzfetqe_zone_ll",
        "ind_zzfetqe_zone_on", "ind_zzfetqe_zone_struct",
        "ind_zzfetqe_zone_enter", "ind_zzfetqe_zone_exit",
        # ✅ ZONE-EXIT-TF1 — أعمدة فريم هيكل الخروج (CHoCH على أي فريم):
        # النسخة الأصلية على فريم الشارت + أحداث/حالة HTF المسقطة سببياً.
        "ind_zzfetqe_zone_exit_base", "ind_zzfetqe_zone_exit_htf_enter",
        "ind_zzfetqe_zone_exit_htf_on",
        # ✅ STRUCT1 — أعمدة الهيكل الكبير (صرامة حرفية: القمة>القمة ∧
        # القاع>القاع على المحاور الكبرى المتبادلة المؤكدة سببياً) — العلم
        # struct_hh_hl = 1.0 فقط عند تحقق الشرطين معاً عند الشمعة نفسها.
        "ind_zzfetqe_struct_last_high", "ind_zzfetqe_struct_prev_high",
        "ind_zzfetqe_struct_last_low", "ind_zzfetqe_struct_prev_low",
        "ind_zzfetqe_struct_hh_hl",
        # الخطوط الستة (رصة EMA — محسوبة على فريم الساعة «60» افتراضياً)
        "ind_zzfetqe_ema_21", "ind_zzfetqe_ema_50", "ind_zzfetqe_ema_100",
        "ind_zzfetqe_ema_200", "ind_zzfetqe_ema_350", "ind_zzfetqe_ema_500",
        # حالة الرصة وأحداثها وجاهزيتها
        "ind_zzfetqe_ema_stack_ok", "ind_zzfetqe_ema_stack_ready",
        "ind_zzfetqe_ema_stack_enter", "ind_zzfetqe_ema_stack_exit",
        # ✅ EMAGATE-UNIFIED — تشخيص الشروط السبعة (عمود لكل شرط):
        # price_ok = الشرط 1 (السعر فوق الكل) · ladder_ok = الشروط 2-7
        # (السلّم مرتب) · pair_ok_{a}_{b} = كل زوج متجاور على حدة (ديناميكي
        # حسب الأطوال المكونة — مثل ind_zzfetqe_ema_stack_pair_ok_21_50).
        "ind_zzfetqe_ema_stack_price_ok", "ind_zzfetqe_ema_stack_ladder_ok",
        # dynamic: ind_zzfetqe_ema_stack_pair_ok_{a}_{b} per adjacent ladder pair
        # ✅ التمرير — عقد الكمومية الكامل مُرجع أيضاً (بيانات الرسم الكاملة):
        "ind_zzfetq_dir", "ind_zzfetq_p1", "ind_zzfetq_p2", "ind_zzfetq_i1", "ind_zzfetq_i2",
        "ind_zzfetq_anchor", "ind_zzfetq_range_index",
        "ind_zzfetq_liq_state", "ind_zzfetq_liq_ref_high", "ind_zzfetq_liq_ref_vol",
        "ind_zzfetq_liq_vol_ok", "ind_zzfetq_signal_s1", "ind_zzfetq_signal_s2",
        "ind_zzfetq_signal_s3", "ind_zzfetq_signal_any",
        "ind_zzfetq_entry", "ind_zzfetq_entry_raw",
        "ind_zzfetq_entry_s1", "ind_zzfetq_entry_s2", "ind_zzfetq_entry_s3",
        "ind_zzfetq_entry_raw_s1", "ind_zzfetq_entry_raw_s2", "ind_zzfetq_entry_raw_s3",
        "ind_zzfetq_entry_blocked_s1", "ind_zzfetq_entry_blocked_s2", "ind_zzfetq_entry_blocked_s3",
        "ind_zzfetq_entry_zblocked_s1", "ind_zzfetq_entry_zblocked_s2", "ind_zzfetq_entry_zblocked_s3",
        "ind_zzfetq_trend_ok", "ind_zzfetq_trend_bias",
        "ind_zzfetq_trend_votes_bull", "ind_zzfetq_trend_votes_bear",
        "ind_zzfetq_tr_p7_upper", "ind_zzfetq_tr_p7_lower", "ind_zzfetq_tr_p7_bias",
        "ind_zzfetq_tr_p15_upper", "ind_zzfetq_tr_p15_lower", "ind_zzfetq_tr_p15_bias",
        "ind_zzfetq_tr_p25_upper", "ind_zzfetq_tr_p25_lower", "ind_zzfetq_tr_p25_bias",
        "ind_zzfetq_zone_last_high", "ind_zzfetq_zone_prev_high",
        "ind_zzfetq_zone_last_low", "ind_zzfetq_zone_prev_low",
        "ind_zzfetq_zone_hh", "ind_zzfetq_zone_hl",
        "ind_zzfetq_zone_lh", "ind_zzfetq_zone_ll",
        "ind_zzfetq_zone_on", "ind_zzfetq_zone_struct",
        "ind_zzfetq_zone_enter", "ind_zzfetq_zone_exit",
        "ind_zzfet_dir", "ind_zzfet_p1", "ind_zzfet_p2", "ind_zzfet_i1", "ind_zzfet_i2",
        "ind_zzfet_anchor", "ind_zzfet_range_index",
        "ind_zzfet_level_0", "ind_zzfet_level_0236", "ind_zzfet_level_0382",
        "ind_zzfet_level_05", "ind_zzfet_level_0618", "ind_zzfet_level_0786",
        "ind_zzfet_level_085415", "ind_zzfet_level_1",
        "ind_zzfet_liq_state", "ind_zzfet_liq_ref_high", "ind_zzfet_liq_ref_vol",
        "ind_zzfet_liq_vol_ok", "ind_zzfet_signal_s1", "ind_zzfet_signal_s2",
        "ind_zzfet_signal_s3", "ind_zzfet_signal_any",
        "ind_zzfet_entry", "ind_zzfet_entry_raw",
        "ind_zzfet_entry_s1", "ind_zzfet_entry_s2", "ind_zzfet_entry_s3",
        "ind_zzfet_entry_raw_s1", "ind_zzfet_entry_raw_s2", "ind_zzfet_entry_raw_s3",
        "ind_zzfet_entry_blocked_s1", "ind_zzfet_entry_blocked_s2", "ind_zzfet_entry_blocked_s3",
        "ind_zzfet_trend_ok", "ind_zzfet_trend_bias",
        "ind_zzfet_trend_votes_bull", "ind_zzfet_trend_votes_bear",
        "ind_zzfet_tr_p7_upper", "ind_zzfet_tr_p7_lower", "ind_zzfet_tr_p7_bias",
        "ind_zzfet_tr_p15_upper", "ind_zzfet_tr_p15_lower", "ind_zzfet_tr_p15_bias",
        "ind_zzfet_tr_p25_upper", "ind_zzfet_tr_p25_lower", "ind_zzfet_tr_p25_bias",
    ],
    # (zzfb_* → ind_zzfb_*): الترندية بت-بت + N5/N6 + ثلاثية البوابة الشفافة
    # (الخام/المبوّب/الممنوع) لكل الأنواع الخمسة. مرايا الفترات ديناميكية حسب
    # قالب الفترات — المذكور هنا للفترات الافتراضية [7,15,25].
    "zzfib_e2e_blazing": [
        "ind_zzfb_dir", "ind_zzfb_p1", "ind_zzfb_p2", "ind_zzfb_i1", "ind_zzfb_i2",
        "ind_zzfb_anchor", "ind_zzfb_range_index",
        "ind_zzfb_liq_state", "ind_zzfb_liq_ref_high", "ind_zzfb_liq_ref_vol",
        "ind_zzfb_liq_vol_ok", "ind_zzfb_signal_s1", "ind_zzfb_signal_s2",
        "ind_zzfb_signal_s3", "ind_zzfb_signal_n5", "ind_zzfb_signal_n6",
        "ind_zzfb_signal_any",
        "ind_zzfb_entry", "ind_zzfb_entry_raw",
        "ind_zzfb_entry_s1", "ind_zzfb_entry_s2", "ind_zzfb_entry_s3",
        "ind_zzfb_entry_n5", "ind_zzfb_entry_n6",
        "ind_zzfb_entry_raw_s1", "ind_zzfb_entry_raw_s2", "ind_zzfb_entry_raw_s3",
        "ind_zzfb_entry_raw_n5", "ind_zzfb_entry_raw_n6",
        "ind_zzfb_entry_blocked_s1", "ind_zzfb_entry_blocked_s2", "ind_zzfb_entry_blocked_s3",
        "ind_zzfb_entry_blocked_n5", "ind_zzfb_entry_blocked_n6",
        "ind_zzfb_trend_ok", "ind_zzfb_trend_bias",
        "ind_zzfb_trend_votes_bull", "ind_zzfb_trend_votes_bear",
        "ind_zzfb_tr_p7_upper", "ind_zzfb_tr_p7_lower", "ind_zzfb_tr_p7_bias",
        "ind_zzfb_tr_p15_upper", "ind_zzfb_tr_p15_lower", "ind_zzfb_tr_p15_bias",
        "ind_zzfb_tr_p25_upper", "ind_zzfb_tr_p25_lower", "ind_zzfb_tr_p25_bias",
    ],
    # ✅ PRO73 (ZLF-End-To-End-Trendy-MACD) — عقد «الترندية الماكدية»: مرآة
    # كاملة لعقد الترندية (zzfetm_* → ind_zzfetm_*) + الشفافية الرباعية
    # (خام/ترند-ممنوع/موشرات-ممنوع/نهائي) + سلاسل الموشرات والبوابة.
    # مرايا الفترات وسلاسل الموشرات (osc_<id>_<field>) ديناميكية حسب القالب.
    "zzfib_e2e_trendy_macd": [
        "ind_zzfetm_dir", "ind_zzfetm_p1", "ind_zzfetm_p2", "ind_zzfetm_i1", "ind_zzfetm_i2",
        "ind_zzfetm_anchor", "ind_zzfetm_range_index",
        "ind_zzfetm_liq_state", "ind_zzfetm_liq_ref_high", "ind_zzfetm_liq_ref_vol",
        "ind_zzfetm_liq_vol_ok", "ind_zzfetm_signal_s1", "ind_zzfetm_signal_s2",
        "ind_zzfetm_signal_s3", "ind_zzfetm_signal_any",
        "ind_zzfetm_entry", "ind_zzfetm_entry_raw", "ind_zzfetm_entry_iblocked",
        "ind_zzfetm_entry_s1", "ind_zzfetm_entry_s2", "ind_zzfetm_entry_s3",
        "ind_zzfetm_entry_raw_s1", "ind_zzfetm_entry_raw_s2", "ind_zzfetm_entry_raw_s3",
        "ind_zzfetm_entry_blocked_s1", "ind_zzfetm_entry_blocked_s2", "ind_zzfetm_entry_blocked_s3",
        "ind_zzfetm_entry_iblocked_s1", "ind_zzfetm_entry_iblocked_s2", "ind_zzfetm_entry_iblocked_s3",
        "ind_zzfetm_osc_gate",
        "ind_zzfetm_trend_ok", "ind_zzfetm_trend_bias",
        "ind_zzfetm_trend_votes_bull", "ind_zzfetm_trend_votes_bear",
        "ind_zzfetm_tr_p7_upper", "ind_zzfetm_tr_p7_lower", "ind_zzfetm_tr_p7_bias",
        "ind_zzfetm_tr_p15_upper", "ind_zzfetm_tr_p15_lower", "ind_zzfetm_tr_p15_bias",
        "ind_zzfetm_tr_p25_upper", "ind_zzfetm_tr_p25_lower", "ind_zzfetm_tr_p25_bias",
    ],
    # 🔥 PRO73 (ZLF-End-To-End-Blazing-MACD) — عقد «الملتهبة الماكدية»: مرآة
    # كاملة لعقد الملتهبة (zzfbm_* → ind_zzfbm_*) للأنواع الخمسة + الشفافية
    # الرباعية + سلاسل الموشرات والبوابة — كلها ديناميكية حسب القالب.
    "zzfib_e2e_blazing_macd": [
        "ind_zzfbm_dir", "ind_zzfbm_p1", "ind_zzfbm_p2", "ind_zzfbm_i1", "ind_zzfbm_i2",
        "ind_zzfbm_anchor", "ind_zzfbm_range_index",
        "ind_zzfbm_liq_state", "ind_zzfbm_liq_ref_high", "ind_zzfbm_liq_ref_vol",
        "ind_zzfbm_liq_vol_ok", "ind_zzfbm_signal_s1", "ind_zzfbm_signal_s2",
        "ind_zzfbm_signal_s3", "ind_zzfbm_signal_n5", "ind_zzfbm_signal_n6",
        "ind_zzfbm_signal_any",
        "ind_zzfbm_entry", "ind_zzfbm_entry_raw", "ind_zzfbm_entry_iblocked",
        "ind_zzfbm_entry_s1", "ind_zzfbm_entry_s2", "ind_zzfbm_entry_s3",
        "ind_zzfbm_entry_n5", "ind_zzfbm_entry_n6",
        "ind_zzfbm_entry_raw_s1", "ind_zzfbm_entry_raw_s2", "ind_zzfbm_entry_raw_s3",
        "ind_zzfbm_entry_raw_n5", "ind_zzfbm_entry_raw_n6",
        "ind_zzfbm_entry_blocked_s1", "ind_zzfbm_entry_blocked_s2", "ind_zzfbm_entry_blocked_s3",
        "ind_zzfbm_entry_blocked_n5", "ind_zzfbm_entry_blocked_n6",
        "ind_zzfbm_entry_iblocked_s1", "ind_zzfbm_entry_iblocked_s2", "ind_zzfbm_entry_iblocked_s3",
        "ind_zzfbm_entry_iblocked_n5", "ind_zzfbm_entry_iblocked_n6",
        "ind_zzfbm_osc_gate",
        "ind_zzfbm_trend_ok", "ind_zzfbm_trend_bias",
        "ind_zzfbm_trend_votes_bull", "ind_zzfbm_trend_votes_bear",
        "ind_zzfbm_tr_p7_upper", "ind_zzfbm_tr_p7_lower", "ind_zzfbm_tr_p7_bias",
        "ind_zzfbm_tr_p15_upper", "ind_zzfbm_tr_p15_lower", "ind_zzfbm_tr_p15_bias",
        "ind_zzfbm_tr_p25_upper", "ind_zzfbm_tr_p25_lower", "ind_zzfbm_tr_p25_bias",
    ],
    # ✅ MTFEMA1 — عقد «MTF EMA»: خط النسخة الأساسية + خط كل نسخة (ديناميكي
    # حسب معرفات instances — البسيطة بلا instances معرفها "main").
    # ملاحظة رسم: القيمة null أثناء الإحماء (أول length شرائط HTF) — عقد
    # شموع الباك-تست: null لا مفقود.
    "mtf_ema": [
        "ind_mtfema_value",
        # الديناميكية: ind_mtfema_<id> لكل نسخة (البسيطة: ind_mtfema_main)
    ],
    # ✅ ROUND32 — عقد مؤشر الترند المستقل: قيم الخطوط والانحياز والتقاطعات لكل فترة
    # (ديناميكية حسب القالب — المذكور للفترات الافتراضية) + المجاميع والبوابة.
    "trend_fractal": [
        "ind_trf_p7_upper", "ind_trf_p7_lower", "ind_trf_p7_bias",
        "ind_trf_p7_cross_upper", "ind_trf_p7_cross_lower",
        "ind_trf_p15_upper", "ind_trf_p15_lower", "ind_trf_p15_bias",
        "ind_trf_p15_cross_upper", "ind_trf_p15_cross_lower",
        "ind_trf_p25_upper", "ind_trf_p25_lower", "ind_trf_p25_bias",
        "ind_trf_p25_cross_upper", "ind_trf_p25_cross_lower",
        "ind_trf_bull_votes", "ind_trf_bear_votes", "ind_trf_bias",
        "ind_trf_trend_ok", "ind_trf_threshold",
    ],
    # ✅ B9 — عقد «ماكد 9B»: الإشارة النهائية + شفافية الشجرة وفروعها
    # الأربعة + أحداث ولادة خط الترند (قيم النسخ ديناميكية حسب معرفات
    # instances — ind_b9g_osc_<id>_line|signal|hist).
    "b9_macd_gates": [
        "ind_b9g_buy", "ind_b9g_cond",
        "ind_b9g_sub_w_pos", "ind_b9g_sub_d_pos",
        "ind_b9g_sub_4h_core", "ind_b9g_sub_any_above_4h",
        # الديناميكية: ind_b9g_osc_<id>_line|signal|hist لكل نسخة
    ],
}


def normalize_overlay_name(raw: str) -> Optional[str]:
    """اسم مؤشر (قد يحوي نقطة فرعية) → base إن كان من مؤشرات البنية وإلا None.

    أمثلة: 'zigzag_channels' → 'zigzag' · 'zigzag.zz_state' → 'zigzag'
           'auto_fib_retracement' → 'fib' · 'zigzag_fib' → 'zzfib' · 'rsi' → None
    """
    if not raw:
        return None
    base = str(raw).split(".")[0].strip().lower()
    return OVERLAY_ALIASES.get(base)


def is_known_indicator_name(raw: str) -> bool:
    """هل الاسم معروف للمحرك؟ (مؤشرات البنية أو سجل المؤشرات الكلاسيكي)"""
    if not raw:
        return False
    name = str(raw).strip()
    if normalize_overlay_name(name) is not None:
        return True
    try:
        from app.services.indicators.registry import IndicatorRegistry
        return IndicatorRegistry.get_indicator_info(name.lower()) is not None
    except Exception:
        return False


def config_to_overlay_params(cfg: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    """تكوين مؤشر من الاستراتيجية → {base: params} لـ compute_overlays.

    يقبل كائن pydantic (IndicatorConfig) أو dict. يعيد None إن لم يكن من البنية.
    المرادفات المدعومة في params:
      zigzag: length
      fib: depth, dev_threshold (dev/deviation/deviation_threshold),
           retracement (ret/target_ratio), level_ratios (levels),
           reverse, extend_left, extend_right
      trendline: period (n/fractal_period), max_pairs (pairs/max_tl), extend
      zzfib (الجولة 12 + 13.2 + ROUND19): length, reverse, levels (level_ratios),
           extend_right, extend_leg_to_live, touch_level, liq_lookback,
           liq_arm_bars, liq_signals, liq_sfp_signals (اختيارية مطفأة),
           mode ("tradingview"|"luxalgo" — ROUND19), depth, deviation, backstep
    """
    base = normalize_overlay_name(str((cfg or {}).get("name", "") if isinstance(cfg, dict) else getattr(cfg, "name", "") or ""))
    if base is None:
        return None
    raw_params = (cfg or {}).get("params", {}) if isinstance(cfg, dict) else (getattr(cfg, "params", None) or {})
    p = dict(raw_params or {})
    out: Dict[str, Any] = {}

    def _num(key_aliases: Sequence[str], cast=float, default=None):
        for k in key_aliases:
            if k in p:
                try:
                    return cast(p[k])
                except (TypeError, ValueError):
                    continue
        return default

    if base == "zigzag":
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
    elif base == "fib":
        depth = _num(("depth",), int)
        if depth is not None:
            out["depth"] = max(1, depth)
        dev = _num(("dev_threshold", "dev", "deviation", "deviation_threshold"))
        if dev is not None:
            out["dev_threshold"] = dev
        ret = _num(("retracement", "ret", "target_ratio"))
        if ret is not None:
            out["retracement"] = ret
        lv = p.get("level_ratios", p.get("levels"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["level_ratios"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("reverse", "extend_left", "extend_right"):
            if k in p:
                out[k] = bool(p[k])
    elif base == "zzfib":
        # الجولة 12: فيبو الزيجزاق المدمج
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
        if "reverse" in p:
            out["reverse"] = bool(p["reverse"])
        lv = p.get("levels", p.get("level_ratios"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["levels"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("extend_right", "extend_leg_to_live"):
            if k in p:
                out[k] = bool(p[k])
        tl_ = _num(("touch_level", "touch", "target"))
        if tl_ is not None:
            out["touch_level"] = tl_
        # ✅ الجولة 13.1 (ZLF) — معاملات السيولة
        lb_ = _num(("liq_lookback", "liquidity_lookback", "lookback"), int)
        if lb_ is not None:
            out["liq_lookback"] = max(1, lb_)
        ab_ = _num(("liq_arm_bars", "liquidity_arm_bars", "arm_bars"), int)
        if ab_ is not None:
            out["liq_arm_bars"] = max(1, ab_)
        if "liq_signals" in p or "liquidity_signals" in p:
            out["liq_signals"] = bool(p.get("liq_signals", p.get("liquidity_signals")))
        # ✅ الجولة 13.2 (ZLF) — الإشارة الرابعة الاختيارية (SFP) مطفأة افتراضياً
        if "liq_sfp_signals" in p or "sfp_signals" in p:
            out["liq_sfp_signals"] = bool(p.get("liq_sfp_signals", p.get("sfp_signals")))
        # ✅ ROUND19 — وضع زقزاق TradingView ومعاملاته (depth/deviation/backstep).
        if "mode" in p:
            out["mode"] = str(p["mode"]).strip().lower()
        d_ = _num(("depth",), int)
        if d_ is not None:
            out["depth"] = max(2, d_)
        dv_ = _num(("deviation",))
        if dv_ is not None:
            out["deviation"] = float(dv_)
        bs_ = _num(("backstep",), int)
        if bs_ is not None:
            out["backstep"] = max(1, bs_)
        # ✅ ROUND31 — افتراضيات البطل للمفاتيح الغائبة (اتساق الطبقات الثلاث).
        #
        # العللة المثبتة (تشخيص ROUND31): مسار chart-data بالاسم فقط
        # ({"name": "zigzag_fib"} بلا params) كان يُسقط المسار على قيم الخدمة
        # الافتراضية (mode="luxalgo" + liq_lookback=20) بينما محرك البث الحي
        # والبريسِت يعملان منذ ج19/j21-v2 بـ (tradingview + liq_lookback=240)
        # — فتُبنى إشارات الشارت لكل شمعة على زقزاق ومرجع R مختلفَين كلياً عن
        # زقزاق محرك القرار (إثبات: انقلابات dir عند 04:48/13:26/13:55/16:57
        # على luxalgo مقابل 21:44/02:58/04:50 فقط على tradingview — نفس البيانات
        # BTCUSDT 1m) — فيرى المستخدم إشارات على الشارت لا يصدقها البث الحي
        # والعكس. القاعدة الآن: كل مفتاح غائب يأخذ قيمة قالب البطل، والمفاتيح
        # الصريحة تفوز دائماً كما كانت (صفر تغيير للمحمولات المصرّح بها).
        # E2E (zzfib_e2e) خارج هذا — وضع luxalgo هو مواصفته التعاقدية.
        if "mode" not in out:
            out["mode"] = "tradingview"
        if "depth" not in out:
            out["depth"] = 12
        if "deviation" not in out:
            out["deviation"] = 20.0
        if "backstep" not in out:
            out["backstep"] = 3
        if "liq_lookback" not in out:
            out["liq_lookback"] = 240
    elif base == "zzfib_e2e":
        # ✅ ROUND22 (ZLF-End-To-End) — المحرك المنفصل: نفس معاملات الزقزاق
        # (+ launch_touch_ticks). لا liq_* — النطاق يعتمد لحظة ظهور الزقزاق
        # ونافذة الحساب = عمر النطاق (لا عدد شموع في التعريف).
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
        if "reverse" in p:
            out["reverse"] = bool(p["reverse"])
        lv = p.get("levels", p.get("level_ratios"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["levels"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("extend_right", "extend_leg_to_live"):
            if k in p:
                out[k] = bool(p[k])
        if "mode" in p:
            out["mode"] = str(p["mode"]).strip().lower()
        d_ = _num(("depth",), int)
        if d_ is not None:
            out["depth"] = max(2, d_)
        dv_ = _num(("deviation",))
        if dv_ is not None:
            out["deviation"] = float(dv_)
        bs_ = _num(("backstep",), int)
        if bs_ is not None:
            out["backstep"] = max(1, bs_)
        tt_ = _num(("launch_touch_ticks",))
        if tt_ is not None:
            out["launch_touch_ticks"] = float(tt_)
    elif base == "zzfib_e2e_trendy":
        # ✅ ROUND32 — الترندية: نفس معاملات E2E حرفياً + القوالب الترندية الثلاثة
        # (trend_periods قائمة بأي طول — إضافة ترند رابع 30 = تعديل القالب بلا كود).
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
        if "reverse" in p:
            out["reverse"] = bool(p["reverse"])
        lv = p.get("levels", p.get("level_ratios"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["levels"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("extend_right", "extend_leg_to_live"):
            if k in p:
                out[k] = bool(p[k])
        if "mode" in p:
            out["mode"] = str(p["mode"]).strip().lower()
        d_ = _num(("depth",), int)
        if d_ is not None:
            out["depth"] = max(2, d_)
        dv_ = _num(("deviation",))
        if dv_ is not None:
            out["deviation"] = float(dv_)
        bs_ = _num(("backstep",), int)
        if bs_ is not None:
            out["backstep"] = max(1, bs_)
        tt_ = _num(("launch_touch_ticks",))
        if tt_ is not None:
            out["launch_touch_ticks"] = float(tt_)
        # القوالب الترندية — تُمرَّر كما هي (المحرك يطبّع القوائم/النصوص)
        tp = p.get("trend_periods", p.get("periods"))
        if tp is not None:
            out["trend_periods"] = tp
        if "trend_confirm" in p:
            out["trend_confirm"] = p["trend_confirm"]
        tg = p.get("trend_gate", p.get("gate"))
        if tg is not None:
            out["trend_gate"] = tg
    elif base == "zzfib_e2e_trendy_quantum":
        # ✅ QUANTUM1 — الكمومية: نفس معاملات الترندية حرفياً + قالب المنطقة
        # (zone_gate: s1/s2/s3 أو "none" لتعطيل بوابة الدخول — بيانات المنطقة
        # تبقى محسوبة ومُرجعة في الحالتين — شفافية بنائية مثل trend_gate=none).
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
        if "reverse" in p:
            out["reverse"] = bool(p["reverse"])
        lv = p.get("levels", p.get("level_ratios"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["levels"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("extend_right", "extend_leg_to_live"):
            if k in p:
                out[k] = bool(p[k])
        if "mode" in p:
            out["mode"] = str(p["mode"]).strip().lower()
        d_ = _num(("depth",), int)
        if d_ is not None:
            out["depth"] = max(2, d_)
        dv_ = _num(("deviation",))
        if dv_ is not None:
            out["deviation"] = float(dv_)
        bs_ = _num(("backstep",), int)
        if bs_ is not None:
            out["backstep"] = max(1, bs_)
        tt_ = _num(("launch_touch_ticks",))
        if tt_ is not None:
            out["launch_touch_ticks"] = float(tt_)
        # القوالب الترندية — كما هي
        tp = p.get("trend_periods", p.get("periods"))
        if tp is not None:
            out["trend_periods"] = tp
        if "trend_confirm" in p:
            out["trend_confirm"] = p["trend_confirm"]
        tg = p.get("trend_gate", p.get("gate"))
        if tg is not None:
            out["trend_gate"] = tg
        # قالب المنطقة — كما هو (المحرك يطبّعه)
        zg = p.get("zone_gate")
        if zg is not None:
            out["zone_gate"] = zg
        # ✅ ZONE-EXIT-TF1 — فريم هيكل الخروج (CHoCH LL+LH على أي فريم)
        zxr = p.get("zone_exit_resolution",
                    p.get("exit_resolution", p.get("zone_exit_tf")))
        if zxr is not None:
            out["zone_exit_resolution"] = zxr
        zxl_ = _num(("zone_exit_length", "exit_length"), int)
        if zxl_ is not None:
            out["zone_exit_length"] = max(2, zxl_)
        # ✅ ZONE-ENTRY-MTF1 — فريم المنطقة المسموحة للدخول (HH+HL على أي
        # فريم — فارغ/none/base/chart = فريم الشارت بت-بت)
        zr = p.get("zone_resolution",
                   p.get("entry_zone_resolution", p.get("zone_tf")))
        if zr is not None:
            out["zone_resolution"] = zr
        zl_ = _num(("zone_length", "entry_zone_length"), int)
        if zl_ is not None:
            out["zone_length"] = max(2, zl_)
    elif base == "zzfib_e2e_trendy_quantum_ema":
        # ✅ QUANTUMEMA1 — الكمومية المتوسطة المتحركة الأسية: نفس معاملات
        # الكمومية حرفياً + قالب EMA (الأطوال الستة/فريم الساعة/المصدر/
        # الإزافة/بوابة الرصة ema_gate: s1/s2/s3 أو "none" لتعطيل بوابة
        # الدخول — بيانات الرصة والخطوط تبقى محسوبة ومُرجعة في الحالتين).
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
        if "reverse" in p:
            out["reverse"] = bool(p["reverse"])
        lv = p.get("levels", p.get("level_ratios"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["levels"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("extend_right", "extend_leg_to_live"):
            if k in p:
                out[k] = bool(p[k])
        if "mode" in p:
            out["mode"] = str(p["mode"]).strip().lower()
        d_ = _num(("depth",), int)
        if d_ is not None:
            out["depth"] = max(2, d_)
        dv_ = _num(("deviation",))
        if dv_ is not None:
            out["deviation"] = float(dv_)
        bs_ = _num(("backstep",), int)
        if bs_ is not None:
            out["backstep"] = max(1, bs_)
        tt_ = _num(("launch_touch_ticks",))
        if tt_ is not None:
            out["launch_touch_ticks"] = float(tt_)
        # القوالب الترندية — كما هي
        tp = p.get("trend_periods", p.get("periods"))
        if tp is not None:
            out["trend_periods"] = tp
        if "trend_confirm" in p:
            out["trend_confirm"] = p["trend_confirm"]
        tg = p.get("trend_gate", p.get("gate"))
        if tg is not None:
            out["trend_gate"] = tg
        # قالب المنطقة — كما هو (المحرك يطبّعه)
        zg = p.get("zone_gate")
        if zg is not None:
            out["zone_gate"] = zg
        # ✅ قالب EMA — الأطوال/الفريم/المصدر/الإزاحة/بوابة الرصة
        el = p.get("ema_lengths", p.get("ema_length", p.get("lengths")))
        if el is not None:
            out["ema_lengths"] = el
        if "ema_resolution" in p or "res" in p or "htf" in p:
            out["ema_resolution"] = p.get(
                "ema_resolution", p.get("res", p.get("htf")))
        if "ema_source" in p or "src" in p:
            out["ema_source"] = p.get("ema_source", p.get("src"))
        eo_ = _num(("ema_offset", "offset", "ma_offset"), int)
        if eo_ is not None:
            out["ema_offset"] = eo_
        eg = p.get("ema_gate")
        if eg is not None:
            out["ema_gate"] = eg
        # ✅ EMAGATE-UNIFIED — وضع الرصة الهرمي (الشروط السبعة):
        # hierarchical (الافتراضي) / strict (الوضع التاريخي) + قاعدة
        # الإعفاء (افتراضي 21 — الأصغر منها سريعة معفاة من الترتيب).
        esm = p.get("ema_stack_mode")
        if esm is not None:
            out["ema_stack_mode"] = esm
        esb = _num(("ema_stack_base",), int)
        if esb is not None:
            out["ema_stack_base"] = max(1, esb)
        # ✅ ZONE-EXIT-TF1 — فريم هيكل الخروج (CHoCH LL+LH على أي فريم):
        # الدخول والمنطقة المسموحة يبقيان على فريم الشارت دائماً.
        zxr = p.get("zone_exit_resolution",
                    p.get("exit_resolution", p.get("zone_exit_tf")))
        if zxr is not None:
            out["zone_exit_resolution"] = zxr
        zxl_ = _num(("zone_exit_length", "exit_length"), int)
        if zxl_ is not None:
            out["zone_exit_length"] = max(2, zxl_)
        # ✅ ZONE-ENTRY-MTF1 — فريم المنطقة المسموحة للدخول (HH+HL على أي
        # فريم — فارغ/none/base/chart = فريم الشارت بت-بت)
        zr = p.get("zone_resolution",
                   p.get("entry_zone_resolution", p.get("zone_tf")))
        if zr is not None:
            out["zone_resolution"] = zr
        zl_ = _num(("zone_length", "entry_zone_length"), int)
        if zl_ is not None:
            out["zone_length"] = max(2, zl_)
        # ✅ STRUCT1 — نسبة انعكاس تأكيد محاور الهيكل الكبير (صرامة
        # القمة>القمة ∧ القاع>القاع على المحاور الكبرى المتبادلة).
        srp = _num(("struct_reversal_pct", "macro_reversal_pct"), float)
        if srp is not None:
            out["struct_reversal_pct"] = max(2.0, srp)
    elif base == "zzfib_e2e_trendy_quantum_ema_mom":
        # QMOM1 — "quantum momentum first" (كموميه الزخم الاولى): same
        # quantum-EMA params verbatim (all of them) + the flexible conditions
        # gate template: osc_instances (macd/rsi/mom copies — any count, 22
        # timeframes) and osc_conditions (composable and/or/not tree) — both
        # passed through as-is to the engine (same pattern as PRO73 macd
        # family). With neither template key = bit-identical mirror mode.
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
        if "reverse" in p:
            out["reverse"] = bool(p["reverse"])
        lv = p.get("levels", p.get("level_ratios"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["levels"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("extend_right", "extend_leg_to_live"):
            if k in p:
                out[k] = bool(p[k])
        if "mode" in p:
            out["mode"] = str(p["mode"]).strip().lower()
        d_ = _num(("depth",), int)
        if d_ is not None:
            out["depth"] = max(2, d_)
        dv_ = _num(("deviation",))
        if dv_ is not None:
            out["deviation"] = float(dv_)
        bs_ = _num(("backstep",), int)
        if bs_ is not None:
            out["backstep"] = max(1, bs_)
        tt_ = _num(("launch_touch_ticks",))
        if tt_ is not None:
            out["launch_touch_ticks"] = float(tt_)
        # trend template — verbatim (engine normalizes)
        tp = p.get("trend_periods", p.get("periods"))
        if tp is not None:
            out["trend_periods"] = tp
        if "trend_confirm" in p:
            out["trend_confirm"] = p["trend_confirm"]
        tg = p.get("trend_gate", p.get("gate"))
        if tg is not None:
            out["trend_gate"] = tg
        # zone template — verbatim (engine normalizes)
        zg = p.get("zone_gate")
        if zg is not None:
            out["zone_gate"] = zg
        # EMA template — lengths/resolution/source/offset/stack gate
        el = p.get("ema_lengths", p.get("ema_length", p.get("lengths")))
        if el is not None:
            out["ema_lengths"] = el
        if "ema_resolution" in p or "res" in p or "htf" in p:
            out["ema_resolution"] = p.get(
                "ema_resolution", p.get("res", p.get("htf")))
        if "ema_source" in p or "src" in p:
            out["ema_source"] = p.get("ema_source", p.get("src"))
        eo_ = _num(("ema_offset", "offset", "ma_offset"), int)
        if eo_ is not None:
            out["ema_offset"] = eo_
        eg = p.get("ema_gate")
        if eg is not None:
            out["ema_gate"] = eg
        # ✅ EMAGATE-UNIFIED — وضع الرصة الهرمي (الشروط السبعة) — نفس
        # تمرير الكمومية-EMA (البوابة واحدة مركزية في المحرك الأساسي).
        esm = p.get("ema_stack_mode")
        if esm is not None:
            out["ema_stack_mode"] = esm
        esb = _num(("ema_stack_base",), int)
        if esb is not None:
            out["ema_stack_base"] = max(1, esb)
        # ZONE-EXIT-TF1 — exit structure resolution (CHoCH LL+LH any tf)
        zxr = p.get("zone_exit_resolution",
                    p.get("exit_resolution", p.get("zone_exit_tf")))
        if zxr is not None:
            out["zone_exit_resolution"] = zxr
        zxl_ = _num(("zone_exit_length", "exit_length"), int)
        if zxl_ is not None:
            out["zone_exit_length"] = max(2, zxl_)
        # ✅ ZONE-ENTRY-MTF1 — فريم المنطقة المسموحة للدخول (HH+HL على أي
        # فريم — فارغ/none/base/chart = فريم الشارت بت-بت)
        zr = p.get("zone_resolution",
                   p.get("entry_zone_resolution", p.get("zone_tf")))
        if zr is not None:
            out["zone_resolution"] = zr
        zl_ = _num(("zone_length", "entry_zone_length"), int)
        if zl_ is not None:
            out["zone_length"] = max(2, zl_)
        # QMOM1 — the flexible conditions gate template (passed as-is)
        oi = p.get("osc_instances", p.get("instances"))
        if oi is not None:
            out["osc_instances"] = oi
        oc = p.get("osc_conditions", p.get("conditions"))
        if oc is not None:
            out["osc_conditions"] = oc
    elif base == "mtf_ema":
        # ✅ MTFEMA1 — MTF EMA: معاملات Pine بحذافيرها + النسخ المتعددة
        # (instances — أي عدد نسخ لكل نسخة معاملاتها؛ البسيطة بلا instances
        # = نسخة واحدة من المعاملات العلوية — نفس نمط osc_instances في PRO73).
        ln_ = _num(("length", "ma_len", "len"), int)
        if ln_ is not None:
            out["length"] = max(1, ln_)
        if "source" in p or "src" in p:
            out["source"] = str(p.get("source", p.get("src")))
        off_ = _num(("offset", "ma_offset", "plot_offset"), int)
        if off_ is not None:
            out["offset"] = off_
        if "resolution" in p or "res" in p or "tf" in p or "timeframe" in p:
            out["resolution"] = p.get(
                "resolution", p.get("res", p.get("tf", p.get("timeframe"))))
        ins_ = p.get("instances", p.get("mtf_instances"))
        if ins_ is not None:
            out["instances"] = ins_
    elif base == "zzfib_e2e_blazing":
        # 🔥 R69 — الملتهبة: نفس معاملات الترندية حرفياً (بوابة ترند على
        # s1/s2/s3/n5/n6 — المحرك يطبّعها ويقبل n5/n6 إضافة إلى s1/s2/s3).
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
        if "reverse" in p:
            out["reverse"] = bool(p["reverse"])
        lv = p.get("levels", p.get("level_ratios"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["levels"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("extend_right", "extend_leg_to_live"):
            if k in p:
                out[k] = bool(p[k])
        if "mode" in p:
            out["mode"] = str(p["mode"]).strip().lower()
        d_ = _num(("depth",), int)
        if d_ is not None:
            out["depth"] = max(2, d_)
        dv_ = _num(("deviation",))
        if dv_ is not None:
            out["deviation"] = float(dv_)
        bs_ = _num(("backstep",), int)
        if bs_ is not None:
            out["backstep"] = max(1, bs_)
        tt_ = _num(("launch_touch_ticks",))
        if tt_ is not None:
            out["launch_touch_ticks"] = float(tt_)
        # القوالب الترندية — تُمرَّر كما هي (المحرك يطبّعها ويقبل n5/n6 بالبوابة)
        tp = p.get("trend_periods", p.get("periods"))
        if tp is not None:
            out["trend_periods"] = tp
        if "trend_confirm" in p:
            out["trend_confirm"] = p["trend_confirm"]
        tg = p.get("trend_gate", p.get("gate"))
        if tg is not None:
            out["trend_gate"] = tg
    elif base == "zzfib_e2e_trendy_macd":
        # ✅ PRO73 — الترندية الماكدية: نفس معاملات الترندية حرفياً + قالبا
        # الموشرات: osc_instances (نسخ rsi/macd/mom — أي عدد و14 فريماً)
        # و osc_conditions (شجرة and/or/not قابلة للتركيب) — تُمرّران كما هما.
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
        if "reverse" in p:
            out["reverse"] = bool(p["reverse"])
        lv = p.get("levels", p.get("level_ratios"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["levels"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("extend_right", "extend_leg_to_live"):
            if k in p:
                out[k] = bool(p[k])
        if "mode" in p:
            out["mode"] = str(p["mode"]).strip().lower()
        d_ = _num(("depth",), int)
        if d_ is not None:
            out["depth"] = max(2, d_)
        dv_ = _num(("deviation",))
        if dv_ is not None:
            out["deviation"] = float(dv_)
        bs_ = _num(("backstep",), int)
        if bs_ is not None:
            out["backstep"] = max(1, bs_)
        tt_ = _num(("launch_touch_ticks",))
        if tt_ is not None:
            out["launch_touch_ticks"] = float(tt_)
        tp = p.get("trend_periods", p.get("periods"))
        if tp is not None:
            out["trend_periods"] = tp
        if "trend_confirm" in p:
            out["trend_confirm"] = p["trend_confirm"]
        tg = p.get("trend_gate", p.get("gate"))
        if tg is not None:
            out["trend_gate"] = tg
        oi = p.get("osc_instances", p.get("instances"))
        if oi is not None:
            out["osc_instances"] = oi
        oc = p.get("osc_conditions", p.get("conditions"))
        if oc is not None:
            out["osc_conditions"] = oc
    elif base == "zzfib_e2e_blazing_macd":
        # 🔥 PRO73 — الملتهبة الماكدية: نفس معاملات الملتهبة حرفياً + القالبان
        # نفسيهما (نسخ الموشرات + شجرة الشروط القابلة للتركيب).
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
        if "reverse" in p:
            out["reverse"] = bool(p["reverse"])
        lv = p.get("levels", p.get("level_ratios"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["levels"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("extend_right", "extend_leg_to_live"):
            if k in p:
                out[k] = bool(p[k])
        if "mode" in p:
            out["mode"] = str(p["mode"]).strip().lower()
        d_ = _num(("depth",), int)
        if d_ is not None:
            out["depth"] = max(2, d_)
        dv_ = _num(("deviation",))
        if dv_ is not None:
            out["deviation"] = float(dv_)
        bs_ = _num(("backstep",), int)
        if bs_ is not None:
            out["backstep"] = max(1, bs_)
        tt_ = _num(("launch_touch_ticks",))
        if tt_ is not None:
            out["launch_touch_ticks"] = float(tt_)
        tp = p.get("trend_periods", p.get("periods"))
        if tp is not None:
            out["trend_periods"] = tp
        if "trend_confirm" in p:
            out["trend_confirm"] = p["trend_confirm"]
        tg = p.get("trend_gate", p.get("gate"))
        if tg is not None:
            out["trend_gate"] = tg
        oi = p.get("osc_instances", p.get("instances"))
        if oi is not None:
            out["osc_instances"] = oi
        oc = p.get("osc_conditions", p.get("conditions"))
        if oc is not None:
            out["osc_conditions"] = oc
    elif base == "trend_fractal":
        # ✅ ROUND32 — مؤشر الترند المستقل: فترات قالبية بأي طول + صيغة الإجماع.
        tp = p.get("periods", p.get("trend_periods"))
        if tp is not None:
            out["periods"] = tp
        if "confirm_mode" in p:
            out["confirm_mode"] = p["confirm_mode"]
    elif base == "b9_macd_gates":
        # ✅ B9 — «ماكد 9B»: نسخ MACD متعددة الفريمات + شجرة شروط قابلة
        # للتركيب (مقارنات قيم عابرة للفريمات) + تسميات فروع الشفافية +
        # نافذة تفعيل الإشارة (تحصر b9g_buy داخل نافذة التداول بينما
        # تُحسب القيم على كامل البيانات الممتدة — إحماء MACD الأسبوعي).
        inst = p.get("instances", p.get("osc_instances"))
        if inst is not None:
            out["instances"] = inst
        cond = p.get("conditions", p.get("osc_conditions"))
        if cond is not None:
            out["conditions"] = cond
        sl = p.get("sub_labels", p.get("labels"))
        if sl is not None:
            out["sub_labels"] = sl
        for k in ("active_start", "active_end"):
            if p.get(k) is not None:
                out[k] = p[k]
        # ✅ v4 (LIVE1) — وضع إسقاط الفريم الأعلى: confirmed (افتراضي) | live
        hm = p.get("htf_mode", p.get("projection_mode"))
        if hm is not None:
            out["htf_mode"] = str(hm).strip().lower()
    else:  # trendline
        period = _num(("period", "n", "fractal_period"), int)
        if period is not None:
            out["period"] = max(2, period)
        pairs = _num(("max_pairs", "pairs", "max_tl"), int)
        if pairs is not None:
            out["max_pairs"] = max(1, pairs)
        if "extend" in p:
            out["extend"] = str(p["extend"])

    return {base: out}


# ------------------------------------------------------- بناء الأعمدة ---


def _zigzag_columns(zz: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    s = zz.get("series") or {}
    state = list(s.get("zz_state") or [])
    n = len(state)
    zz_state: List[Optional[float]] = [None if v is None else float(v) for v in state]
    zz_pivot: List[float] = [0.0] * n
    zz_ph: List[Optional[float]] = [None] * n
    zz_pl: List[Optional[float]] = [None] * n

    # الأحداث من pivots — تُكتب عند شمعة التأكيد confirmed_at_bar (بلا repaint)
    for pv in zz.get("pivots") or []:
        try:
            c = int(pv.get("confirmed_at_bar"))
        except (TypeError, ValueError):
            continue
        if not (0 <= c < n):
            continue
        price = pv.get("price")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        if str(pv.get("kind")) == "top":
            zz_pivot[c] = 1.0
            zz_ph[c] = price
        else:
            zz_pivot[c] = -1.0
            zz_pl[c] = price

    # prev: آخر قمة/قاع مؤكدة قبل الشمعة الحالية (عند شمعة التأكيد نفسها
    # تبقى القيمة القديمة — يجعل شرط HL/HH صحيحاً: الجديد > السابق)
    prev_pl: List[Optional[float]] = [None] * n
    prev_ph: List[Optional[float]] = [None] * n
    cur_btm: Optional[float] = None
    cur_top: Optional[float] = None
    for i in range(n):
        if zz_pl[i] is not None:
            prev_pl[i] = cur_btm
            cur_btm = zz_pl[i]
        else:
            prev_pl[i] = cur_btm
        if zz_ph[i] is not None:
            prev_ph[i] = cur_top
            cur_top = zz_ph[i]
        else:
            prev_ph[i] = cur_top

    return {
        "ind_zz_state": zz_state,
        "ind_zz_pivot": zz_pivot,
        "ind_zz_pivot_high": zz_ph,
        "ind_zz_pivot_low": zz_pl,
        "ind_zz_prev_pivot_low": prev_pl,
        "ind_zz_prev_pivot_high": prev_ph,
    }


def _fib_columns(fib: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    s = fib.get("series") or {}
    n = len(s.get("fib_start") or [])
    direction: List[float] = [0.0] * n
    start: List[Optional[float]] = [None] * n
    end: List[Optional[float]] = [None] * n
    target: List[Optional[float]] = [None] * n

    try:
        retr = float((fib.get("params") or {}).get("retracement", 0.618) or 0.618)
    except (TypeError, ValueError):
        retr = 0.618

    # رجل صالحة = غير التركيبية (anchor من سعر 0). امتداد الرجل الزمني =
    # من بدايتها حتى بداية الرجل التالية (آخر رجل حتى نهاية البيانات).
    legs = [lg for lg in (fib.get("legs") or []) if not lg.get("synthetic_anchor")]
    for k, leg in enumerate(legs):
        try:
            x1 = int(leg.get("x1"))
            y1 = float(leg.get("y1"))
            y2 = float(leg.get("y2"))
        except (TypeError, ValueError):
            continue
        if k + 1 < len(legs):
            try:
                span_end = int(legs[k + 1].get("x1"))
            except (TypeError, ValueError):
                span_end = n
        else:
            span_end = n
        span_end = max(x1 + 1, min(n, span_end))
        if not (0 <= x1 < n):
            continue
        diff = y2 - y1
        sign = 1.0 if diff > 0 else (-1.0 if diff < 0 else 0.0)
        tgt = (y1 + sign * abs(diff) * retr) if sign != 0.0 else None
        for i in range(x1, span_end):
            direction[i] = sign
            start[i] = y1
            end[i] = y2
            target[i] = tgt

    # الإشارات: منطق أول لمس + إعادة تسليح مطابق للسكربت (محسوب أصلاً في compute)
    sig: List[float] = [0.0] * n
    for ev in fib.get("signals") or []:
        try:
            bar = int(ev.get("bar"))
        except (TypeError, ValueError):
            continue
        if not (0 <= bar < n):
            continue
        side = str(ev.get("side") or "").strip().lower()
        sig_name = str(ev.get("signal") or "").strip().lower()
        if side == "buy" or sig_name.startswith("buy"):
            sig[bar] = 1.0
        elif side == "sell" or sig_name.startswith("sell"):
            sig[bar] = -1.0

    return {
        "ind_fib_dir": direction,
        "ind_fib_start": start,
        "ind_fib_end": end,
        "ind_fib_target": target,
        "ind_fib_signal": sig,
    }


def _trendline_columns(tl: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    s = tl.get("series") or {}
    upper_raw = list(s.get("tl_upper") or [])
    lower_raw = list(s.get("tl_lower") or [])
    cross_up_raw = list(s.get("tl_cross_upper") or [])
    cross_dn_raw = list(s.get("tl_cross_lower") or [])
    n = len(upper_raw)

    upper: List[Optional[float]] = [None] * n
    lower: List[Optional[float]] = [None] * n
    for i in range(n):
        v = upper_raw[i]
        if v is not None:
            try:
                upper[i] = float(v)
            except (TypeError, ValueError):
                pass
        v = lower_raw[i]
        if v is not None:
            try:
                lower[i] = float(v)
            except (TypeError, ValueError):
                pass

    cross_up: List[float] = [1.0 if bool(x) else 0.0 for x in cross_up_raw[:n]]
    cross_up += [0.0] * (n - len(cross_up))
    cross_dn: List[float] = [1.0 if bool(x) else 0.0 for x in cross_dn_raw[:n]]
    cross_dn += [0.0] * (n - len(cross_dn))

    # الإشارة التعاقدية: قطع العلوي لأعلى = +1 · كسر السفلي لأسفل = -1
    sig: List[float] = [0.0] * n
    for cr in tl.get("crosses") or []:
        try:
            bar = int(cr.get("bar"))
        except (TypeError, ValueError):
            continue
        if not (0 <= bar < n):
            continue
        line = str(cr.get("type") or "").strip().lower()
        direction = str(cr.get("direction") or "").strip().lower()
        if line == "upper" and direction == "over":
            sig[bar] += 1.0
        elif line == "lower" and direction == "under":
            sig[bar] -= 1.0
    sig = [max(-1.0, min(1.0, v)) for v in sig]

    return {
        "ind_atl_upper": upper,
        "ind_atl_lower": lower,
        "ind_atl_signal": sig,
        "ind_atl_cross_upper": cross_up,
        "ind_atl_cross_lower": cross_dn,
    }


def _zzfib_columns(zzf: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """نتيجة zigzag_fib → أعمدة ind_zzf_* (مفتاح السلسلة zzf_X → عمود ind_zzf_X)."""
    out: Dict[str, List[Optional[float]]] = {}
    s = zzf.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if not k.startswith("zzf_"):
            continue
        col = "ind_" + k  # zzf_dir → ind_zzf_dir · zzf_level_0618 → ind_zzf_level_0618
        out[col] = list(vals or [])
    return out


def _zzfe_columns(zzfe: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """✅ ROUND22: نتيجة zigzag_fib_e2e → أعمدة ind_zzfe_* (zzfe_X → ind_zzfe_X).

    ZLF-End-To-End — المحرك المنفصل: كل الأسماء مختلفة عن الأصل (عقد التمايز).
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = zzfe.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if not k.startswith("zzfe_"):
            continue
        out["ind_" + k] = vals if vals is not None else []
    return out


def _zzfet_columns(zzfet: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """✅ ROUND32: نتيجة zigzag_fib_e2e_trendy → أعمدة ind_zzfet_* (zzfet_X → ind_zzfet_X).

    «الزقزاق البطل e2e الترنديه» — عقد تمايز ثالث: صفر تداخل مع zzf_*/zzfe_*/trf_*.
    مرايا الفترات zzfet_tr_p{n}_* تمر تلقائياً بنفس القاعدة العامة (أي طول قالب).
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = zzfet.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if not k.startswith("zzfet_"):
            continue
        out["ind_" + k] = vals if vals is not None else []
    return out


def _zzfetq_columns(zzfetq: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """✅ QUANTUM1: نتيجة zigzag_fib_e2e_trendy_quantum → أعمدة ind_*.

    «الاستراتيجية الترندية الكمومية» — عقد تمايز سابع (zzfetq_X → ind_zzfetq_X)
    + ✅ التمرير الكامل: أعمدة الترندية الأصلية zzfet_X (47) تُرجع أيضاً كما هي
    (ind_zzfet_X — بيانات الرسم الكاملة: زقزاق/فيبو/خطوط ترند/سيولة/إشارات/
    ترند — نفس ما كانت الترندية ترجع بحذافيرها، بت-بت من المحرك نفسه).
    مرايا الفترات zzfetq_tr_p{n}_* وzzfet_tr_p{n}_* تمر تلقائياً بنفس القاعدة.
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = zzfetq.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if k.startswith("zzfetq_") or k.startswith("zzfet_"):
            out["ind_" + k] = vals if vals is not None else []
    return out


def _zzfetqe_columns(zzfetqe: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """✅ QUANTUMEMA1: نتيجة zigzag_fib_e2e_trendy_quantum_ema → أعمدة ind_*.

    «الاستراتيجية الترندية الكمومية المتوسطة المتحركة الأسية» — عقد تمايز
    تاسع (zzfetqe_X → ind_zzfetqe_X): مرآة كاملة للكمومية + الشفافية الخماسية
    (entry_raw خام / entry_blocked ترند / entry_zblocked منطقة / entry_eblocked
    رصة EMA / entry النهائي) + الخطوط الستة zzfetqe_ema_{21,50,100,200,350,500}
    (رسم على فريم الشارت — محسوبة على فريم الساعة «60») + حالة الرصة
    (stack_ok/ready/enter/exit).
    + ✅ التمرير الكامل: أعمدة الكمومية zzfetq_X (62) والترندية zzfet_X (47)
    تُرجع أيضاً كما هي (ind_zzfetq_X + ind_zzfet_X — بيانات الرسم الكاملة
    بت-بت من المحرك الكمي الواحد نفسه).
    مرايا الفترات zzfetqe_tr_p{n}_* وzzfetq_tr_p{n}_* وzzfet_tr_p{n}_* تمر
    تلقائياً بنفس القاعدة العامة.
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = zzfetqe.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if k.startswith("zzfetqe_") or k.startswith("zzfetq_") or k.startswith("zzfet_"):
            out["ind_" + k] = vals if vals is not None else []
    return out


def _zzfetqem_columns(zzfetqem: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """QMOM1: result of zigzag_fib_e2e_trendy_quantum_ema_mom -> ind_* columns.

    "كموميه الزخم الاولى" (quantum momentum first) — tenth differentiation
    contract (zzfetqem_X -> ind_zzfetqem_X): full mirror of the quantum-EMA
    (every zzfetqe_* column kept under BOTH names — ✅ R78 pure-addition
    contract: the baseline family ind_zzfetqe_* stays exactly as the champion
    #10000604 returned it, so existing frontend drawing — the six EMA lines
    ind_zzfetqe_ema_*, zone, stack, zigzag/fib — keeps working verbatim,
    while the gated mirror ind_zzfetqem_* rides on top) + final entries after
    the momentum gate, iblocked transparency, EMA lines, stack state, zone,
    trend, liquidity, zigzag/fib drawing data + the dynamic oscillator
    series zzfetqem_osc_<id>_<field> (macd/rsi/mom — per instance fields)
    + the gate column zzfetqem_osc_gate + full pass-through of the quantum
    (zzfetq_*) and trendy (zzfet_*) contracts — verbatim bit-identical
    + ✅ R78 the two aggregate value columns (classic indicator-values
    contract "same as the quantum champion"): ind_zigzag_fib_e2e_trendy_
    quantum_ema (raw 0/1 — champion values) and ind_zigzag_fib_e2e_trendy_
    quantum_ema_mom (gated final 0/1).
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = zzfetqem.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if (k.startswith("zzfetqem_") or k.startswith("zzfetqe_")
                or k.startswith("zzfetq_")
                or k.startswith("zzfet_")
                or k in ("zigzag_fib_e2e_trendy_quantum_ema",
                         "zigzag_fib_e2e_trendy_quantum_ema_mom")):
            out["ind_" + k] = vals if vals is not None else []
    return out


def _zzfb_columns(zzfb: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """🔥 R69: نتيجة zigzag_fib_e2e_blazing → أعمدة ind_zzfb_* (zzfb_X → ind_zzfb_X).

    «الترندية الملتهبة» — عقد تمايز رابع: صفر تداخل مع zzf_*/zzfe_*/zzfet_*/trf_*.
    مرايا الفترات zzfb_tr_p{n}_* تمر تلقائياً بنفس القاعدة العامة (أي طول قالب).
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = zzfb.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if not k.startswith("zzfb_"):
            continue
        out["ind_" + k] = vals if vals is not None else []
    return out


def _zzfetm_columns(zzfetm: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """✅ PRO73: نتيجة zigzag_fib_e2e_trendy_macd → أعمدة ind_zzfetm_* (zzfetm_X → ind_zzfetm_X).

    «الترندية الماكدية» — عقد تمايز خامس: مرآة كاملة للترندية + الشفافية
    الرباعية + سلاسل الموشرات (osc_<id>_<field>) والبوابة — كلها ديناميكية
    حسب القالب (أي عدد نسخ وأي فريمات).
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = zzfetm.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if not k.startswith("zzfetm_"):
            continue
        out["ind_" + k] = vals if vals is not None else []
    return out


def _zzfbm_columns(zzfbm: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """🔥 PRO73: نتيجة zigzag_fib_e2e_blazing_macd → أعمدة ind_zzfbm_* (zzfbm_X → ind_zzfbm_X).

    «الملتهبة الماكدية» — عقد تمايز سادس: مرآة كاملة للملتهبة للأنواع الخمسة
    + الشفافية الرباعية + سلاسل الموشرات والبوابة — كلها ديناميكية.
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = zzfbm.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if not k.startswith("zzfbm_"):
            continue
        out["ind_" + k] = vals if vals is not None else []
    return out


def _trf_columns(trf: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """✅ ROUND32: نتيجة auto_trendlines_fractal → أعمدة ind_trf_* (trf_X → ind_trf_X).

    مؤشر الترند المستقل: قيم الخطوط/الانحياز/التقاطعات لكل فترة (قالبية) + المجاميع.
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = trf.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if not k.startswith("trf_"):
            continue
        out["ind_" + k] = vals if vals is not None else []
    return out


def _b9g_columns(b9: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """✅ B9: نتيجة b9_macd_gates → أعمدة ind_b9g_* (b9g_X → ind_b9g_X).

    «ماكد 9B» — الإشارة النهائية ind_b9g_buy + شفافية الشجرة ind_b9g_cond
    وفروعها ind_b9g_sub_* + قيم نسخ MACD ind_b9g_osc_<id>_* (ديناميكية).
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = b9.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if not k.startswith("b9g_"):
            continue
        out["ind_" + k] = vals if vals is not None else []
    return out


def _mtfema_columns(mte: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """✅ MTFEMA1: نتيجة mtf_ema_engine → أعمدة ind_mtfema_* (mtfema_X → ind_mtfema_X).

    «MTF EMA» — عقد تمايز ثامن: خط النسخة الأساسية ind_mtfema_value + خط كل
    نسخة ind_mtfema_<id> (ديناميكي حسب معرفات instances — البسيطة "main").
    """
    out: Dict[str, List[Optional[float]]] = {}
    s = mte.get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if not k.startswith("mtfema_"):
            continue
        out["ind_" + k] = vals if vals is not None else []
    return out


def columns_from_overlays_result(res: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """نتيجة compute_overlays → أعمدة ind_* التعاقدية (فقط للأنواع المحسوبة)."""
    out: Dict[str, List[Optional[float]]] = {}
    ovl = (res or {}).get("overlays") if isinstance(res, dict) else None
    if ovl is None and isinstance(res, dict):
        # يقبل أيضاً القاموس المجرّد {zigzag:..., fib:..., trendline:..., zzfib:...}
        ovl = {k: v for k, v in res.items() if k in KNOWN_OVERLAY_BASES and isinstance(v, dict)}
    if not ovl:
        return out
    zz = ovl.get("zigzag")
    if isinstance(zz, dict) and zz.get("series"):
        out.update(_zigzag_columns(zz))
    fb = ovl.get("fib")
    if isinstance(fb, dict) and fb.get("series"):
        out.update(_fib_columns(fb))
    tl = ovl.get("trendline")
    if isinstance(tl, dict) and tl.get("series"):
        out.update(_trendline_columns(tl))
    zzf = ovl.get("zzfib")
    if isinstance(zzf, dict) and zzf.get("series"):
        out.update(_zzfib_columns(zzf))
    # ✅ ROUND22 (ZLF-End-To-End) — أعمدة المحرك المنفصل zzfe_* → ind_zzfe_*
    zzfe = ovl.get("zzfib_e2e")
    if isinstance(zzfe, dict) and zzfe.get("series"):
        out.update(_zzfe_columns(zzfe))
    # ✅ ROUND32 — أعمدة الترندية zzfet_* → ind_zzfet_* + مؤشر الترند trf_* → ind_trf_*
    zzfet = ovl.get("zzfib_e2e_trendy")
    if isinstance(zzfet, dict) and zzfet.get("series"):
        out.update(_zzfet_columns(zzfet))
    # ✅ QUANTUM1 — أعمدة الكمومية zzfetq_* → ind_zzfetq_* + التمرير الكامل
    # لأعمدة الترندية zzfet_* → ind_zzfet_* (بيانات الرسم كما كانت الترندية
    # ترجعها + بيانات الكمومية نفسها — من نتيجة المحرك الكمي الواحدة).
    zzfetq = ovl.get("zzfib_e2e_trendy_quantum")
    if isinstance(zzfetq, dict) and zzfetq.get("series"):
        out.update(_zzfetq_columns(zzfetq))
    # ✅ QUANTUMEMA1 — أعمدة الكمومية المتوسطة المتحركة الأسية zzfetqe_* →
    # ind_zzfetqe_* + التمرير الكامل لعقدَي الكمومية نفسها (ind_zzfetq_* +
    # ind_zzfet_* — بيانات الرسم كما كانت الكمومية ترجعها + الخطوط الستة
    # وحالة الرصة — من نتيجة المحرك الواحدة).
    zzfetqe = ovl.get("zzfib_e2e_trendy_quantum_ema")
    if isinstance(zzfetqe, dict) and zzfetqe.get("series"):
        out.update(_zzfetqe_columns(zzfetqe))
    # QMOM1 — quantum momentum first columns zzfetqem_* -> ind_zzfetqem_*
    # (momentum-gate transparency + dynamic oscillator series + full mirror
    # of the quantum-EMA contract + pass-through ind_zzfetq_* + ind_zzfet_*).
    zzfetqem = ovl.get("zzfib_e2e_trendy_quantum_ema_mom")
    if isinstance(zzfetqem, dict) and zzfetqem.get("series"):
        out.update(_zzfetqem_columns(zzfetqem))
    # 🔥 R69 — أعمدة الملتهبة zzfb_* → ind_zzfb_* (بما فيها n5/n6 ومرايا الفترات)
    zzfb = ovl.get("zzfib_e2e_blazing")
    if isinstance(zzfb, dict) and zzfb.get("series"):
        out.update(_zzfb_columns(zzfb))
    # ✅ PRO73 — أعمدة الترندية الماكدية zzfetm_* → ind_zzfetm_* (الشفافية
    # الرباعية + سلاسل الموشرات والبوابة + مرايا الترند كاملة)
    zzfetm = ovl.get("zzfib_e2e_trendy_macd")
    if isinstance(zzfetm, dict) and zzfetm.get("series"):
        out.update(_zzfetm_columns(zzfetm))
    # 🔥 PRO73 — أعمدة الملتهبة الماكدية zzfbm_* → ind_zzfbm_* (الأنواع الخمسة
    # بالشفافية الرباعية + سلاسل الموشرات والبوابة)
    zzfbm = ovl.get("zzfib_e2e_blazing_macd")
    if isinstance(zzfbm, dict) and zzfbm.get("series"):
        out.update(_zzfbm_columns(zzfbm))
    trf = ovl.get("trend_fractal")
    if isinstance(trf, dict) and trf.get("series"):
        out.update(_trf_columns(trf))
    # ✅ B9 — أعمدة «ماكد 9B» b9g_* → ind_b9g_* (الإشارة النهائية +
    # شفافية الشجرة وفروعها + قيم نسخ MACD المسقطة سببياً).
    b9g = ovl.get("b9_macd_gates")
    if isinstance(b9g, dict) and b9g.get("series"):
        out.update(_b9g_columns(b9g))
    # ✅ MTFEMA1 — أعمدة MTF EMA (mtfema_X → ind_mtfema_X — خط النسخة
    # الأساسية + خط كل نسخة)
    mte = ovl.get("mtf_ema")
    if isinstance(mte, dict) and mte.get("series"):
        out.update(_mtfema_columns(mte))
    return out


# ✅ R77 — قواعد المحركات التي تحمل قسم osc (بوابة الشروط المرنة) —
# صدى أقسامها يُعاد للتقرير (summary.math_audit.momentum_gate) عبر
# return_sections=True من strategy_engine1 ثم engine1.
_OSC_SECTION_BASES = (
    "zzfib_e2e_trendy_quantum_ema_mom",  # QMOM1 — كموميه الزخم الاولى
    "zzfib_e2e_trendy_macd",             # PRO73 — الترندية الماكدية
    "zzfib_e2e_blazing_macd",            # PRO73 — الملتهبة الماكدية
)


def columns_for_configs(
    candles: Any,
    indicator_configs: Sequence[Any],
    return_sections: bool = False,
):
    """تكوينات الاستراتيجية + الشموع → أعمدة ind_* جاهزة للحقن في DataFrame.

    تجمع معاملات كل مؤشرات البنية المفعّلة، تحسب المطلوب منها مرة واحدة
    (نوع واحد لكل base — آخر تكرار مفعّل يفوز مع تحذير)، وتعيد الأعمدة.

    ✅ R77 (عقد التقرير الكامل): return_sections=True ⇒ يعيد
    (cols, sections) حيث sections = {base: {"engine", "name", "osc"}} —
    قسم osc (عدادات خام/نهائي/ممنوع + حالات النسخ + التحذيرات + مصدر
    الأزمنة + حياد الإحماء) للمحركات المبوّبة، كي يصل إلى نتيجة
    الباك-تست (summary.math_audit.momentum_gate) بدل ضياعه هنا. الوضع
    الافتراضي False = العقد القديم بت-بت (لا تأثير على أي مستدعٍ قائم).
    """
    from app.services.indicators.overlays import compute_overlays

    merged_params: Dict[str, Dict[str, Any]] = {}
    wanted: List[str] = []
    for cfg in indicator_configs or []:
        conv = config_to_overlay_params(cfg)
        if conv is None:
            continue
        base, params = next(iter(conv.items()))
        if base not in merged_params:
            wanted.append(base)
        elif params != merged_params[base]:
            name = str((cfg or {}).get("name", "") if isinstance(cfg, dict) else getattr(cfg, "name", ""))
            logger.warning("overlay duplicate base '%s' with different params (from '%s') — last enabled wins", base, name)
        merged_params[base] = params

    if not wanted:
        return ({}, {}) if return_sections else {}

    try:
        res = compute_overlays(candles, types=wanted, params=merged_params)
    except Exception:
        logger.exception("compute_overlays failed for types=%s", wanted)
        return ({}, {}) if return_sections else {}

    cols = columns_from_overlays_result(res)
    # سلامة: أعِد الأعمدة بطول موحّد (طول الشموع)
    try:
        n = len(candles)
    except TypeError:
        n = 0
    if n:
        for k, v in cols.items():
            if len(v) < n:
                v = v + [None] * (n - len(v))
            # PRO73-R3 (ذاكرة): عند تساوي الطول نُحيل بالمرجع — لا نسخة كاملة
            # لكل عمود (يوفر ~700MB على النوافذ الكبيرة مع نسخ المستند الـ67).
            cols[k] = v if len(v) == n else v[:n]
    if return_sections:
        # ✅ R77 — صدى أقسام الموشرات (عقد التقرير: التقرير يصف كل شيء)
        sections: Dict[str, Dict[str, Any]] = {}
        ovl_res = (res or {}).get("overlays") if isinstance(res, dict) else None
        if isinstance(ovl_res, dict):
            for _base in _OSC_SECTION_BASES:
                _o = ovl_res.get(_base)
                if isinstance(_o, dict):
                    sections[_base] = {
                        "engine": _o.get("engine"),
                        "name": _o.get("name"),
                        "osc": _o.get("osc"),
                    }
            # ✅ B9-T100-GATE1 — قسم رسومات الترند (إحداثيات كل خط وُلد):
            # trend_fractal يُنتج أصلاً في نتيجته قسماً كاملاً lines لكل فترة
            # (x/t/y للطرفين + الميل + لحظة الولادة + الإحلال) لكن كانت تُهمل
            # عند التسوية إلى أعمدة ind_trf_* — الآن تصل عبر sections إلى
            # indicator_sections لمحرك الاستراتيجية ومنه إلى نتيجة الباك-تست
            # (chart_data.trend_lines) كي يرسمها الفرونت اند. عقد إضافي بحت:
            # استراتيجيات بلا trend_fractal لا يظهر عندها القسم بت-بت.
            _trf = ovl_res.get("trend_fractal")
            if isinstance(_trf, dict) and _trf.get("lines"):
                sections["trend_fractal"] = {
                    "engine": _trf.get("engine"),
                    "name": _trf.get("name"),
                    "spec": _trf.get("spec"),
                    "params": _trf.get("params"),
                    "lines": _trf.get("lines"),
                    "current": _trf.get("current"),
                    "events": _trf.get("events"),
                }
        return cols, sections
    return cols
