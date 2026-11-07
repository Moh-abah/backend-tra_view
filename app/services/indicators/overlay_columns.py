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
    "trend_fractal": "trend_fractal",
    "fractal_trendlines": "trend_fractal",
}

KNOWN_OVERLAY_BASES = ("zigzag", "fib", "trendline", "zzfib", "zzfib_e2e",
                       "zzfib_e2e_trendy", "trend_fractal")  # ✅ ROUND32: الترندية + مؤشر الترند

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
    elif base == "trend_fractal":
        # ✅ ROUND32 — مؤشر الترند المستقل: فترات قالبية بأي طول + صيغة الإجماع.
        tp = p.get("periods", p.get("trend_periods"))
        if tp is not None:
            out["periods"] = tp
        if "confirm_mode" in p:
            out["confirm_mode"] = p["confirm_mode"]
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
        out["ind_" + k] = list(vals or [])
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
        out["ind_" + k] = list(vals or [])
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
        out["ind_" + k] = list(vals or [])
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
    trf = ovl.get("trend_fractal")
    if isinstance(trf, dict) and trf.get("series"):
        out.update(_trf_columns(trf))
    return out


def columns_for_configs(
    candles: Any,
    indicator_configs: Sequence[Any],
) -> Dict[str, List[Optional[float]]]:
    """تكوينات الاستراتيجية + الشموع → أعمدة ind_* جاهزة للحقن في DataFrame.

    تجمع معاملات كل مؤشرات البنية المفعّلة، تحسب المطلوب منها مرة واحدة
    (نوع واحد لكل base — آخر تكرار مفعّل يفوز مع تحذير)، وتعيد الأعمدة.
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
        return {}

    try:
        res = compute_overlays(candles, types=wanted, params=merged_params)
    except Exception:
        logger.exception("compute_overlays failed for types=%s", wanted)
        return {}

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
            cols[k] = v[:n]
    return cols
