# =============================================================================
# 🔥 R69 — ZLF-End-To-End-Blazing — «الترندية الملتهبة»
# =============================================================================
# أمر صاحب القرار (2026-11-11): «اكتب لي الاستراتيجية الجديدة التي فيها
#   🔥 N5 — إشعال بلا مرجع — وسمّها استراتيجية الترندية الملتهبة … كمان أضف
#   +N6 — وأضف المسارات وإرجاع البيانات عشان يتم رسمها على الشارت باسمها
#   يعني بمثل نظامنا للترندية».
#
# هذا الملف = محرك معزول جديد كلياً (طبقة سياسات فوق المحرك الموحد
# zigzag_fib_core.py — نفس هندسة الترندية حرفياً):
#   · S1/S2/S3: نفس مصفوفة الترندية **بت-بت** (نفس المرجع R، نفس green_max،
#     نفس خط الانطلاقة، نفس بوابة الترند) — صفر تغيير على السلوك القائم.
#   · 🔥 N5 «إشعال بلا مرجع» (R68 — مُقاسة على 4 رموز × 6 نوافذ): نطاق حي
#     لم تظهر فيه أي شمعة حمراء منذ ولادته (بائعون غائبون = اندفاع خالص)
#     ∧ شمعة تصرخ فوق **قمة الجبل نفسها** (أعلى الطرفين المحوريين للنطاق)
#     ∧ حجم يهيمن على كل الخضراء ∧ انضباط الانطلاقة ∧ بوابة الترند.
#     — الترندية كانت عمياء عنها بنيوياً: بلا حمراء لا مرجع R ولا إشارة أصلاً.
#   · 🤫 N6 «الاختراق الهادئ» (R68 — مُقاسة): صرخة فوق سقف المرجع R ∧ انضباط
#     الانطلاقة ∧ **بلا هيمنة الخضراء** (v ≤ green_max) — ثقة بلا ضجيج.
#     — الترندية كانت تُصفّرها بشرط الهيمنة الخضراء العام.
#
# عقد التمايز (كل الأسماء جديدة كلياً — صفر تداخل مع zzf_*/zzfe_*/zzfet_*/trf_*):
#   سلاسل zzfb_* → أعمدة ind_zzfb_* · إشارات "ZLF-E2E-Blazing ..."
#   indicator: zigzag_fib_e2e_blazing · base: zzfib_e2e_blazing
#   بوابة الترند القالبية نفسها (فترات [7,15,25] majority — قالبية بالكامل)
#   و trend_gate يقبل s1/s2/s3/n5/n6 (أو none للتعطيل).
#
# العقد المحفوظ (ميراث الترندية حرفياً):
#   1) الترند = مؤشر مستقل (trend_fractals.py — وفاء Pine Auto Trendline)
#      يرسل إحداثياته ويُحسب هنا بناء عليها — سببية كاملة بلا استشراف.
#   2) النطاق/الفيبو/الزقزاق = المحرك الموحد zigzag_fib_core (المصدر الوحيد).
#   3) وضع الزقزاق: luxalgo length=100 (مواصفة شارت المنصة) — tradingview متاح.
#   4) كل نطاق في ranges[] يحمل levels[] بحدود رسم كاملة (ولادة → نهاية)
#      + legs + pivots + current + trend.lines — **نفس حمولة الترندية**
#      فيرسمها الفرونت بنفس مساره باسم الملتهبة.
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# المحرك الموحد — المصدر الوحيد للزقزاق/الفيبو/التطبيع
from app.services.indicators.zigzag_fib_core import (
    ZIGZAG_FIB_CORE_SPEC,
    ZIGZAG_FIB_CORE_VERSION,
    build_ranges,
    clean_float,
    infer_price_tick,
    level_tag,
    norm_candles,
    norm_volume,
    range_levels_geometry,
    range_public,
    zigzag_detect,
)

__all__ = [
    "zigzag_fib_e2e_blazing",
    "ZLF_E2E_BLAZING_ENGINE_NAME",
    "ZLF_E2E_BLAZING_SPEC",
    "ZLF_E2E_BLAZING_DEFAULT_LEVELS",
    "ZLF_E2E_BLAZING_LAUNCH_USER",
    "ZLF_E2E_BLAZING_DEFAULT_PERIODS",
]

# ---------------------------------------------------------------------------
# هوية المحرك المنفصل (عقد التمايز — أسماء جديدة كلياً عن كل المحركات)
# ---------------------------------------------------------------------------
ZLF_E2E_BLAZING_ENGINE_NAME = "ZLF-End-To-End-Blazing"
ZLF_E2E_BLAZING_SPEC = "R69-blazing"

# مستويات الفيبو — نفس مقياس المحرك الموحد (0..1 من الأول إلى الثاني)
ZLF_E2E_BLAZING_DEFAULT_LEVELS: List[float] = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 0.85415, 1.0]

# خط الانطلاقة: «من 0.618 أو أعلى» بمقياس رسم المستخدم = price(0.382) بالمحرك
ZLF_E2E_BLAZING_LAUNCH_USER: float = 0.618
_ZLF_E2E_BLAZING_LAUNCH_ENGINE_LEVEL: float = 0.382

# تسامح ملامسة خط الانطلاقة — تيك واحد مستنتج من البيانات (كما في E2E/الترندية)
ZLF_E2E_BLAZING_LAUNCH_TOUCH_TICKS: float = 1.0

# القالب الافتراضي لبوابة الترند — المرجع المعتمد يعيش في بريسِت الاستراتيجية
# (presets.py) وهذه وقوعة احتياطية عند الاستدعاء بلا معاملات — لا أرقام داخل أي منطق.
ZLF_E2E_BLAZING_DEFAULT_PERIODS: Tuple[int, ...] = (7, 15, 25)
ZLF_E2E_BLAZING_DEFAULT_CONFIRM: str = "majority"
ZLF_E2E_BLAZING_DEFAULT_GATE: Tuple[str, ...] = ("s1", "s2", "s3", "n5", "n6")

# ألوان الدخول للشارت (N5 نار · N6 كهرمان — S كما في الترندية)
ZLF_E2E_BLAZING_COLOR_S: str = "#28cc95"
ZLF_E2E_BLAZING_COLOR_N5: str = "#ff6b35"
ZLF_E2E_BLAZING_COLOR_N6: str = "#f7b32b"


def _norm_trend_gate(raw: Any) -> List[int]:
    """تطبيع أنواع الإشارات المبوّبة بالترند — الملتهبة تقبل s1/s2/s3/n5/n6.

    None            = البوابة على الخمسة كلها (الافتراضي).
    «none»/«off»    = البوابة معطلة كلياً.
    قائمة فارغة/قيم غير معروفة = معطلة كلياً (المُصرَّح لا يبوّب شيئاً).
    يقبل الصيغتين s1/1 · n5/5 · n6/6 بأيخلط.
    """
    if raw is None:
        return [1, 2, 3, 5, 6]
    if isinstance(raw, str):
        s_all = str(raw).strip().lower()
        if s_all in ("none", "off", "false", "0", ""):
            return []
        raw = [x for x in raw.replace(";", ",").split(",") if str(x).strip()]
    out = set()
    for x in raw:
        s = str(x).strip().lower()
        if s in ("s1", "1"):
            out.add(1)
        elif s in ("s2", "2"):
            out.add(2)
        elif s in ("s3", "3"):
            out.add(3)
        elif s in ("n5", "s5", "5"):
            out.add(5)
        elif s in ("n6", "s6", "6"):
            out.add(6)
    return sorted(out)


# ---------------------------------------------------------------------------
# المحرك الرئيسي — ZLF-End-To-End-Blazing «الترندية الملتهبة»
# ---------------------------------------------------------------------------
def zigzag_fib_e2e_blazing(
    candles: Any,
    length: int = 100,
    reverse: bool = False,
    levels: Optional[Sequence[float]] = None,
    extend_right: bool = True,
    extend_leg_to_live: bool = True,
    mode: str = "luxalgo",
    depth: int = 12,
    deviation: float = 20.0,
    backstep: int = 3,
    launch_touch_ticks: float = ZLF_E2E_BLAZING_LAUNCH_TOUCH_TICKS,
    trend_periods: Any = None,
    trend_confirm: Any = ZLF_E2E_BLAZING_DEFAULT_CONFIRM,
    trend_gate: Any = None,
) -> Dict[str, Any]:
    """ZLF-End-To-End-Blazing — «الترندية الملتهبة» (S1/S2/S3 + N5/N6 + بوابة الترند).

    المعاملات: نفس معاملات الترندية حرفياً (mode/length/depth/deviation/
    backstep/reverse/levels/extend_right/extend_leg_to_live/launch_touch_ticks)
    + ثلاثة قوالب ترند:
      trend_periods:  قائمة فترات الفراكتال — [7,15,25] افتراضياً (قالبية).
      trend_confirm:  majority | all | any | رقم صريح.
      trend_gate:     أنواع الإشارات المبوّبة — s1/s2/s3/n5/n6 (افتراضياً الخمسة).

    البوابة: إشارة الدخول لا تتحقق إلا بانحياز الترند الصاعد (close فوق الخط
    العلوي) بإجماع الفترات عند شمعة الإشارة نفسها. الخام والممنوع ظاهران.
    """
    t, o, h, l, c = norm_candles(candles)
    N = len(c)
    length = max(2, int(length))
    lvls = [float(x) for x in (levels if levels is not None else ZLF_E2E_BLAZING_DEFAULT_LEVELS)]
    vols = norm_volume(candles)
    if len(vols) != N:
        vols = [None] * N

    _tick = infer_price_tick(o, h, l, c)
    try:
        _touch_tol = max(0.0, float(launch_touch_ticks)) * (_tick or 0.0)
    except (TypeError, ValueError):
        _touch_tol = 0.0

    lv_keys = [(r, f"zzfb_level_{level_tag(r)}") for r in lvls]

    # ------------------------------------------------------------------
    # مؤشر الترند المستقل يُحسب أولاً (إحداثياته وسلاسله من محركه المعزول)
    # والبوابة تُطبَّق لحظة كل حدث أثناء المسح الزمني — سببية كاملة.
    # ------------------------------------------------------------------
    from app.services.indicators.trend_fractals import auto_trendlines_fractal, TRF_ENGINE_NAME
    trend = auto_trendlines_fractal(candles, periods=trend_periods, confirm_mode=trend_confirm)
    tr_series = trend.get("series") or {}
    trend_periods_eff = [int(x) for x in (trend.get("params") or {}).get("periods") or []]
    trend_threshold = int((trend.get("params") or {}).get("threshold") or 0)
    trend_confirm_eff = (trend.get("params") or {}).get("confirm_mode")
    gate_cells = _norm_trend_gate(trend_gate)
    s_tr_ok = tr_series.get("trf_trend_ok") or [0.0] * N
    s_tr_bias = tr_series.get("trf_bias") or [0.0] * N
    s_tr_bull = tr_series.get("trf_bull_votes") or [0.0] * N
    s_tr_bear = tr_series.get("trf_bear_votes") or [0.0] * N

    # ------------------------------------------------------------------
    # 1) الزقزاق الموحد — نقاط مؤكدة + أرجل + سجل تغيّرات الزوج (pair_events)
    # ------------------------------------------------------------------
    zz = zigzag_detect(
        t, o, h, l, c, N,
        mode=mode, length=length, depth=depth, deviation=deviation,
        backstep=backstep, reverse=reverse, lv_keys=lv_keys,
        want_series=False,
    )
    confirmed = zz["confirmed"]
    legs = zz["legs"]
    pair_events = zz["pair_events"]

    # محاور الزقزاق المؤكدة — عقد رسم موحد مع legs (نفس نقاط النواة حرفياً)
    pivots: List[Dict[str, Any]] = [
        {
            "bar": int(p["bar"]),
            "time": t[int(p["bar"])] if 0 <= int(p["bar"]) < N else None,
            "price": clean_float(p["price"]),
            "kind": p["kind"],
            "confirmed_at_bar": int(p["confirmed_at_bar"]),
        }
        for p in confirmed
    ]

    # ------------------------------------------------------------------
    # 2) النطاقات المتعاقبة — موحّدة بالمحرك core
    # ------------------------------------------------------------------
    ranges = build_ranges(pair_events, t, N, reverse, _ZLF_E2E_BLAZING_LAUNCH_ENGINE_LEVEL)

    # ------------------------------------------------------------------
    # 3) المسح الزمني السببي — المصفوفة S (كما في الترندية بت-بت)
    #    + إشارات الملتهبة N5/N6 + بوابة الترند لحظة كل حدث
    # ------------------------------------------------------------------
    s_dir: List[float] = [0.0] * N
    s_p1: List[Optional[float]] = [None] * N
    s_p2: List[Optional[float]] = [None] * N
    s_i1: List[Optional[float]] = [None] * N
    s_i2: List[Optional[float]] = [None] * N
    level_series: Dict[str, List[Optional[float]]] = {key: [None] * N for _r, key in lv_keys}

    liq_state: List[float] = [0.0] * N
    liq_ref_high: List[Optional[float]] = [None] * N
    liq_ref_vol: List[Optional[float]] = [None] * N
    liq_vol_ok: List[float] = [0.0] * N
    s_anchor: List[float] = [0.0] * N
    s_range_idx: List[float] = [-1.0] * N
    liq_s1: List[float] = [0.0] * N
    liq_s2: List[float] = [0.0] * N
    liq_s3: List[float] = [0.0] * N
    # 🔥 N5 / 🤫 N6 — إشارات الملتهبة (أعواد صامتة عند الترندية)
    liq_n5: List[float] = [0.0] * N
    liq_n6: List[float] = [0.0] * N
    liq_any: List[float] = [0.0] * N
    # أعمدة الدخول الثلاثية: الخام (شفافية) · المبوَّب (القرار) · الممنوع
    e_entry: List[float] = [0.0] * N            # الجامع بعد البوابة (S+N)
    e_entry_raw: List[float] = [0.0] * N        # الجامع الخام (S+N)
    e_entry_s1: List[float] = [0.0] * N         # بعد البوابة
    e_entry_s2: List[float] = [0.0] * N
    e_entry_s3: List[float] = [0.0] * N
    e_entry_n5: List[float] = [0.0] * N
    e_entry_n6: List[float] = [0.0] * N
    e_entry_raw_s1: List[float] = [0.0] * N     # خام
    e_entry_raw_s2: List[float] = [0.0] * N
    e_entry_raw_s3: List[float] = [0.0] * N
    e_entry_raw_n5: List[float] = [0.0] * N
    e_entry_raw_n6: List[float] = [0.0] * N
    e_blocked_s1: List[float] = [0.0] * N       # خام لكن الترند منعها
    e_blocked_s2: List[float] = [0.0] * N
    e_blocked_s3: List[float] = [0.0] * N
    e_blocked_n5: List[float] = [0.0] * N
    e_blocked_n6: List[float] = [0.0] * N
    s_trend_ok: List[float] = [float(x) for x in s_tr_ok[:N]] if len(s_tr_ok) >= N else [0.0] * N
    signals: List[Dict[str, Any]] = []

    ri = -1
    green_max: Optional[float] = None
    live_ref: Optional[Dict[str, Any]] = None
    n_events = 0
    n_raw = 0
    n_blocked = 0
    n_events_n5 = 0
    n_events_n6 = 0
    for i in range(N):
        while ri + 1 < len(ranges) and ranges[ri + 1]["anchor"] <= i:
            if ri >= 0:
                ranges[ri]["ref"] = live_ref
            ri += 1
            green_max = None
            live_ref = None
        if ri < 0:
            continue
        r = ranges[ri]

        s_dir[i] = float(r["dir"])
        s_p1[i] = clean_float(r["p1"]["price"])
        s_p2[i] = clean_float(r["p2"]["price"])
        s_i1[i] = float(r["p1"]["bar"])
        s_i2[i] = float(r["p2"]["bar"])
        s_anchor[i] = 1.0 if i == int(r["anchor"]) else 0.0
        s_range_idx[i] = float(r["index"])
        for rr, key in lv_keys:
            level_series[key][i] = clean_float(r["p1"]["price"] + r["diff"] * rr)

        o_n, c_n = clean_float(o[i]), clean_float(c[i])
        hi_n, lo_n = clean_float(h[i]), clean_float(l[i])
        v_n = clean_float(vols[i]) if i < len(vols) else None
        # لا مانع من نوع الشمعة (قرار #R68) — «الخضراء» بمفهوم الاستراتيجية =
        # شمعة بمنطقنا (سيولة + صرخة)؛ هيمنة الخضراء تظل لأحجام الخضراء الصريحة.
        signal_ok = (c_n is not None and o_n is not None)
        green = (c_n is not None and o_n is not None and c_n > o_n)  # لهيمنة الخضراء فقط

        if c_n is not None and o_n is not None and c_n < o_n and v_n is not None:
            if live_ref is None or v_n >= live_ref["vol"]:
                live_ref = {"bar": i, "time": t[i], "high": hi_n, "vol": v_n}

        ref = live_ref
        if ref is not None:
            liq_ref_high[i] = clean_float(ref["high"])
            liq_ref_vol[i] = clean_float(ref["vol"])

        if ref is not None and v_n is not None:
            liq_vol_ok[i] = 1.0 if v_n > ref["vol"] else 0.0

        # --- المصفوفة S (حرفياً كما في الترندية) + البوابة ---
        cell = 0
        if signal_ok and v_n is not None and hi_n is not None and lo_n is not None \
                and ref is not None and not r["degenerate"] and r["launch"] is not None:
            breakout = hi_n > ref["high"]
            vol_dom = v_n > ref["vol"]
            dominance = (green_max is None) or (v_n > green_max)
            launch_ok = lo_n >= (r["launch"] - _touch_tol)
            if breakout and vol_dom:
                cell = 1
            elif breakout:
                cell = 2
            elif vol_dom:
                cell = 3
            if cell and not (launch_ok and dominance):
                cell = 0
        if cell:
            # بوابة الترند: حالة الترند عند شمعة الإشارة نفسها (سببية كاملة)
            trend_ok_i = 1.0 if (i < len(s_tr_ok) and s_tr_ok[i] and s_tr_ok[i] >= 0.5) else 0.0
            gated_kind = cell in gate_cells
            passes = (not gated_kind) or trend_ok_i >= 0.5

            liq_state[i] = float(cell)
            liq_any[i] = 1.0
            n_events += 1
            sig_cols = {1: liq_s1, 2: liq_s2, 3: liq_s3}
            sig_cols[cell][i] = 1.0
            anchor_bar = r["anchor"]
            signals.append({
                "bar": i, "time": t[i], "side": "liquidity",
                "signal": f"ZLF-E2E-Blazing Liquidity S{cell}",
                "engine": ZLF_E2E_BLAZING_ENGINE_NAME,
                "states": [cell], "state": float(cell),
                "range_index": r["index"],
                "range_anchor": {"bar": anchor_bar, "time": r["anchor_time"]},
                "range_p1": {"bar": r["p1"]["bar"],
                             "time": t[r["p1"]["bar"]] if 0 <= r["p1"]["bar"] < N else None,
                             "price": clean_float(r["p1"]["price"]), "kind": r["p1"]["kind"]},
                "range_p2": {"bar": r["p2"]["bar"],
                             "time": t[r["p2"]["bar"]] if 0 <= r["p2"]["bar"] < N else None,
                             "price": clean_float(r["p2"]["price"]), "kind": r["p2"]["kind"]},
                "ref_high": clean_float(ref["high"]), "ref_vol": clean_float(ref["vol"]),
                "ref_bar": ref["bar"], "ref_time": ref["time"],
                "launch_line": r["launch"],
                "price": hi_n if cell in (1, 2) else c_n,
                "volume": v_n,
                "trend_ok": trend_ok_i,
                "trend_bias": float(s_tr_bias[i]) if i < len(s_tr_bias) else 0.0,
                "trend_votes": {"bull": float(s_tr_bull[i]) if i < len(s_tr_bull) else 0.0,
                                "bear": float(s_tr_bear[i]) if i < len(s_tr_bear) else 0.0},
                "gated": bool(gated_kind),
            })
            # الدخول = شمعة الإشارة نفسها — بعد البوابة
            raw_cols = {1: e_entry_raw_s1, 2: e_entry_raw_s2, 3: e_entry_raw_s3}
            blocked_cols = {1: e_blocked_s1, 2: e_blocked_s2, 3: e_blocked_s3}
            ent_cols = {1: e_entry_s1, 2: e_entry_s2, 3: e_entry_s3}
            raw_cols[cell][i] = 1.0
            e_entry_raw[i] = 1.0
            n_raw += 1
            if passes:
                e_entry[i] = 1.0
                ent_cols[cell][i] = 1.0
                signals.append({
                    "bar": i, "time": t[i], "side": "buy",
                    "signal": f"ZLF-E2E-Blazing Entry S{cell}",
                    "engine": ZLF_E2E_BLAZING_ENGINE_NAME,
                    "states": [cell],
                    "range_index": r["index"],
                    "price": c_n, "launch_line": r["launch"],
                    "fallback": False, "color": ZLF_E2E_BLAZING_COLOR_S,
                    "trend_ok": trend_ok_i,
                    "trend_gate_passed": True,
                })
            else:
                e_blocked_cols = blocked_cols[cell]
                e_blocked_cols[i] = 1.0
                n_blocked += 1
                signals.append({
                    "bar": i, "time": t[i], "side": "blocked",
                    "signal": f"ZLF-E2E-Blazing Blocked S{cell} (trend gate)",
                    "engine": ZLF_E2E_BLAZING_ENGINE_NAME,
                    "states": [cell],
                    "range_index": r["index"],
                    "price": c_n, "launch_line": r["launch"],
                    "trend_ok": trend_ok_i,
                    "trend_gate_passed": False,
                })

        # ===== 🔥 R69 — إشارات الملتهبة N5/N6 (أعواد صامتة عند الترندية) =====
        # نفس فلسفة الاستراتيجية: سيولة + هيكل + انضباط خط الانطلاقة + بوابة
        # الترند نفسها — ولا تغير أي سلوك قائم أعلاه. التقييم قبل تحديث
        # هيمنة الخضراء (لا تشمل الشمعة نفسها) وقبل تقدّم النطاق.
        n_cell = 0
        if signal_ok and v_n is not None and hi_n is not None and lo_n is not None \
                and not r["degenerate"] and r["launch"] is not None:
            _dominance = (green_max is None) or (v_n > green_max)
            _launch_ok = lo_n >= (r["launch"] - _touch_tol)
            _rng_top = max(clean_float(r["p1"]["price"]), clean_float(r["p2"]["price"]))
            if ref is None:
                # 🔥 N5 «إشعال بلا مرجع»: النطاق لم يرَ أي حمراء منذ ولادته
                #    (اندفاع خالص — البائعون غائبون) ∧ صرخة فوق قمة الجبل
                #    نفسها ∧ هيمنة حجم على الخضراء ∧ انضباط الانطلاقة.
                #    الترندية عمياء عنها بنيوياً: بلا حمراء لا مرجع R أصلاً.
                if hi_n > _rng_top and _dominance and _launch_ok:
                    n_cell = 5
            else:
                # 🤫 N6 «الاختراق الهادئ»: صرخة فوق سقف المرجع R ∧ انضباط
                #    الانطلاقة ∧ بلا هيمنة الخضراء (v ≤ green_max) — السوق
                #    اخترق ولم يحتج صراخ المشترين الأعلى. الترندية كانت
                #    تُصفّرها بشرط الهيمنة الخضراء العام.
                if (hi_n > ref["high"]) and (not _dominance) and _launch_ok:
                    n_cell = 6
        if n_cell:
            # بوابة الترند نفسها (قيمها من شموع ≤ i — سببية كاملة)
            trend_ok_i = 1.0 if (i < len(s_tr_ok) and s_tr_ok[i] and s_tr_ok[i] >= 0.5) else 0.0
            gated_kind = n_cell in gate_cells
            passes = (not gated_kind) or trend_ok_i >= 0.5

            liq_state[i] = float(n_cell)
            liq_any[i] = 1.0
            n_events += 1
            if n_cell == 5:
                n_events_n5 += 1
            else:
                n_events_n6 += 1
            n_sig_cols = {5: liq_n5, 6: liq_n6}
            n_sig_cols[n_cell][i] = 1.0
            anchor_bar = r["anchor"]
            _rng_top = max(clean_float(r["p1"]["price"]), clean_float(r["p2"]["price"]))
            _n_label = "N5" if n_cell == 5 else "N6"
            signals.append({
                "bar": i, "time": t[i], "side": "liquidity",
                "signal": f"ZLF-E2E-Blazing Liquidity {_n_label}",
                "engine": ZLF_E2E_BLAZING_ENGINE_NAME,
                "states": [n_cell], "state": float(n_cell),
                "range_index": r["index"],
                "range_anchor": {"bar": anchor_bar, "time": r["anchor_time"]},
                "range_p1": {"bar": r["p1"]["bar"],
                             "time": t[r["p1"]["bar"]] if 0 <= r["p1"]["bar"] < N else None,
                             "price": clean_float(r["p1"]["price"]), "kind": r["p1"]["kind"]},
                "range_p2": {"bar": r["p2"]["bar"],
                             "time": t[r["p2"]["bar"]] if 0 <= r["p2"]["bar"] < N else None,
                             "price": clean_float(r["p2"]["price"]), "kind": r["p2"]["kind"]},
                # N5: لا مرجع أصلاً (ref_*=None) — سقف الصراخ = قمة الجبل نفسها
                "ref_high": clean_float(ref["high"]) if ref is not None else None,
                "ref_vol": clean_float(ref["vol"]) if ref is not None else None,
                "ref_bar": ref["bar"] if ref is not None else None,
                "ref_time": ref["time"] if ref is not None else None,
                # قمة الجبل (أعلى الطرفين المحوريين) — سقف إشعال N5 وسياق N6
                "range_top": clean_float(_rng_top),
                "green_max": clean_float(green_max),
                "launch_line": r["launch"],
                "price": hi_n,
                "volume": v_n,
                "trend_ok": trend_ok_i,
                "trend_bias": float(s_tr_bias[i]) if i < len(s_tr_bias) else 0.0,
                "trend_votes": {"bull": float(s_tr_bull[i]) if i < len(s_tr_bull) else 0.0,
                                "bear": float(s_tr_bear[i]) if i < len(s_tr_bear) else 0.0},
                "gated": bool(gated_kind),
            })
            # الدخول = شمعة الإشارة نفسها — بعد البوابة
            n_raw_cols = {5: e_entry_raw_n5, 6: e_entry_raw_n6}
            n_blk_cols = {5: e_blocked_n5, 6: e_blocked_n6}
            n_ent_cols = {5: e_entry_n5, 6: e_entry_n6}
            n_raw_cols[n_cell][i] = 1.0
            e_entry_raw[i] = 1.0
            n_raw += 1
            if passes:
                e_entry[i] = 1.0
                n_ent_cols[n_cell][i] = 1.0
                signals.append({
                    "bar": i, "time": t[i], "side": "buy",
                    "signal": f"ZLF-E2E-Blazing Entry {_n_label}",
                    "engine": ZLF_E2E_BLAZING_ENGINE_NAME,
                    "states": [n_cell],
                    "range_index": r["index"],
                    "price": c_n, "launch_line": r["launch"],
                    "range_top": clean_float(_rng_top),
                    "fallback": False,
                    "color": ZLF_E2E_BLAZING_COLOR_N5 if n_cell == 5 else ZLF_E2E_BLAZING_COLOR_N6,
                    "trend_ok": trend_ok_i,
                    "trend_gate_passed": True,
                })
            else:
                n_blk_cols[n_cell][i] = 1.0
                n_blocked += 1
                signals.append({
                    "bar": i, "time": t[i], "side": "blocked",
                    "signal": f"ZLF-E2E-Blazing Blocked {_n_label} (trend gate)",
                    "engine": ZLF_E2E_BLAZING_ENGINE_NAME,
                    "states": [n_cell],
                    "range_index": r["index"],
                    "price": c_n, "launch_line": r["launch"],
                    "range_top": clean_float(_rng_top),
                    "trend_ok": trend_ok_i,
                    "trend_gate_passed": False,
                })

        # تحديث هيمنة الخضراء بعد فحص الشمعة (لا تشمل الشمعة نفسها) — تظل على
        # الخضراء الصريحة فقط (قرار المالك: النوع حرّ للإشارة، الهيمنة للخضراء)
        if green and v_n is not None:
            green_max = v_n if green_max is None else max(green_max, v_n)

    if ri >= 0:
        ranges[ri]["ref"] = live_ref

    # ------------------------------------------------------------------
    # 4) النطاق الحي الآن + مستوياته — فوق المحرك الموحد (حدود كاملة)
    # ------------------------------------------------------------------
    current: Optional[Dict[str, Any]] = None
    if ranges:
        r = ranges[-1]
        last_bar = N - 1
        lv = range_levels_geometry(r, t, N, lvls, extend_right)
        current = {
            "range": range_public(r, t, N),
            "levels": lv,
            "launch_line": r["launch"],
            "p1": clean_float(r["p1"]["price"]), "p2": clean_float(r["p2"]["price"]),
            "dir": float(r["dir"]),
            "i1": r["p1"]["bar"], "i2": r["p2"]["bar"],
            "live_extension": {
                "enabled": extend_leg_to_live,
                "x1": r["p2"]["bar"], "t1": t[r["p2"]["bar"]] if 0 <= r["p2"]["bar"] < N else None,
                "y1": clean_float(r["p2"]["price"]),
                "x2": last_bar, "t2": t[last_bar], "y2": clean_float(c[last_bar]),
            },
            # حالة بوابة الترند الآن (للشارت الحي)
            "trend": {
                "ok": float(s_trend_ok[last_bar]) if N and last_bar < len(s_trend_ok) else 0.0,
                "bias": float(s_tr_bias[last_bar]) if N and last_bar < len(s_tr_bias) else 0.0,
                "votes": {"bull": float(s_tr_bull[last_bar]) if N and last_bar < len(s_tr_bull) else 0.0,
                          "bear": float(s_tr_bear[last_bar]) if N and last_bar < len(s_tr_bear) else 0.0},
            },
        }

    signals.sort(key=lambda s: s.get("bar", 0))

    # ------------------------------------------------------------------
    # 5) السلاسل — أسماء عقد التمايز (zzfb_*) + مرايا الترند لكل فترة
    # ------------------------------------------------------------------
    _blazing_series: Dict[str, List[Optional[float]]] = {
        "zzfb_dir": s_dir, "zzfb_p1": s_p1, "zzfb_p2": s_p2,
        "zzfb_i1": s_i1, "zzfb_i2": s_i2,
        "zzfb_anchor": s_anchor, "zzfb_range_index": s_range_idx,
        **level_series,
        "zzfb_liq_state": liq_state,
        "zzfb_liq_ref_high": liq_ref_high,
        "zzfb_liq_ref_vol": liq_ref_vol,
        "zzfb_liq_vol_ok": liq_vol_ok,
        "zzfb_signal_s1": liq_s1,
        "zzfb_signal_s2": liq_s2,
        "zzfb_signal_s3": liq_s3,
        "zzfb_signal_n5": liq_n5,
        "zzfb_signal_n6": liq_n6,
        "zzfb_signal_any": liq_any,
        "zzfb_entry": e_entry,
        "zzfb_entry_raw": e_entry_raw,
        "zzfb_entry_s1": e_entry_s1,
        "zzfb_entry_s2": e_entry_s2,
        "zzfb_entry_s3": e_entry_s3,
        "zzfb_entry_n5": e_entry_n5,
        "zzfb_entry_n6": e_entry_n6,
        "zzfb_entry_raw_s1": e_entry_raw_s1,
        "zzfb_entry_raw_s2": e_entry_raw_s2,
        "zzfb_entry_raw_s3": e_entry_raw_s3,
        "zzfb_entry_raw_n5": e_entry_raw_n5,
        "zzfb_entry_raw_n6": e_entry_raw_n6,
        "zzfb_entry_blocked_s1": e_blocked_s1,
        "zzfb_entry_blocked_s2": e_blocked_s2,
        "zzfb_entry_blocked_s3": e_blocked_s3,
        "zzfb_entry_blocked_n5": e_blocked_n5,
        "zzfb_entry_blocked_n6": e_blocked_n6,
        "zzfb_trend_ok": s_trend_ok,
        "zzfb_trend_bias": list(s_tr_bias[:N]) if len(s_tr_bias) >= N else [0.0] * N,
        "zzfb_trend_votes_bull": list(s_tr_bull[:N]) if len(s_tr_bull) >= N else [0.0] * N,
        "zzfb_trend_votes_bear": list(s_tr_bear[:N]) if len(s_tr_bear) >= N else [0.0] * N,
    }
    # مرايا الترند لكل فترة (لرسم خطوط الترند فوق شارت الاستراتيجية نفسها) —
    # الحلقة عامة على الفترات الفعلية (قالبية — ترند رابع يظهر تلقائياً)
    for p in trend_periods_eff:
        for src, dst in (("upper", "upper"), ("lower", "lower"), ("bias", "bias")):
            vals = tr_series.get(f"trf_p{p}_{src}")
            if vals is not None:
                _blazing_series[f"zzfb_tr_p{p}_{dst}"] = list(vals[:N]) if len(vals) >= N else list(vals) + [None] * (N - len(vals))

    return {
        "name": "ZigZag Fib E2E Blazing (ZLF-End-To-End-Blazing — الترندية الملتهبة · S1/S2/S3 + N5/N6)",
        "engine": ZLF_E2E_BLAZING_ENGINE_NAME,
        "spec": ZLF_E2E_BLAZING_SPEC,
        # المحرك الموحد: هوية النواة المشتركة (شفافية كاملة)
        "core": {"spec": ZIGZAG_FIB_CORE_SPEC, "version": ZIGZAG_FIB_CORE_VERSION},
        "volume_available": any(v is not None for v in vols),
        "params": {"mode": mode, "length": length, "reverse": reverse, "levels": lvls,
                   "extend_right": extend_right, "extend_leg_to_live": extend_leg_to_live,
                   "depth": depth, "deviation": deviation, "backstep": backstep,
                   "launch_user": ZLF_E2E_BLAZING_LAUNCH_USER,
                   "launch_touch_ticks": ZLF_E2E_BLAZING_LAUNCH_TOUCH_TICKS,
                   "inferred_tick": _tick,
                   # القوالب الترندية (كلها قالبية — بلا أرقام داخل الكود)
                   "trend_periods": trend_periods_eff,
                   "trend_confirm": trend_confirm_eff,
                   "trend_gate": [f"s{x}" if x in (1, 2, 3) else f"n{x}" for x in gate_cells],
                   "trend_threshold": trend_threshold},
        "legs": legs,
        # pivots[] (نفس محاور النواة — عقد رسم موحد مع legs) + window (هوية النافذة)
        "pivots": pivots,
        "window": {"bars": N, "time_from": t[0] if N else None,
                   "time_to": t[N - 1] if N else None},
        # كل نطاق يحمل levels[] بحدود رسم كاملة (ولادة → نهاية)
        "ranges": [range_public(r, t, N, lvls, extend_right) for r in ranges],
        "current": current,
        "signals": signals,
        "series": _blazing_series,
        # قسم الترند الكامل: الإحداثيات التي يحسب منها الباك اند الإشارة
        "trend": {
            "enabled": True,
            "engine": TRF_ENGINE_NAME,
            "periods": trend_periods_eff,
            "confirm_mode": trend_confirm_eff,
            "threshold": trend_threshold,
            "gate": [f"s{x}" if x in (1, 2, 3) else f"n{x}" for x in gate_cells],
            "gate_rule": "إشارة الدخول المبوّبة لا تتحقق إلا بانحياز الترند الصاعد "
                         "(close فوق الخط العلوي — وصل آخر فراكتالَي قمة) بإجماع الفترات "
                         "(majority = أكثر من النصف) عند شمعة الإشارة نفسها — "
                         "الأنواع المبوّبة للملتهبة: s1/s2/s3/n5/n6",
            "counts": {"raw_entries": n_raw, "gated_entries": n_raw - n_blocked,
                       "blocked_entries": n_blocked},
            "lines": trend.get("lines") or {},
            "current": trend.get("current") or {},
        },
        "liquidity": {
            "enabled": True,
            "engine": ZLF_E2E_BLAZING_ENGINE_NAME,
            "spec": ZLF_E2E_BLAZING_SPEC,
            "events": n_events,
            "events_n5": n_events_n5,
            "events_n6": n_events_n6,
            "volume_available": any(v is not None for v in vols),
            "volume_missing_warning": (
                None if any(v is not None for v in vols)
                else "لم يصل عمود الحجم للمحرك — لا يمكن بناء المرجع R ولا تصنيف "
                     "S1/S2/S3/N6 (N5 تعمل بلا مرجع لكن بلا أثر هيمنة كامل) "
                     "(تحقق من مصدر الشموع في المسار المستدعي: يجب تمرير volume مع كل شمعة)"
            ),
            "reference_rule": "R = أكبر شمعة حمراء (close<open) حجماً داخل عمر النطاق الحي (من شمعة ظهور الزقزاق "
                              "إلى الشمعة الجاري فحصها — كل ما قبل الظهور ليس نطاقاً) ويتحدّث لحظياً مع كل حمراء أكبر "
                              "(عند التعادل: الأحدث يفوز) — ref_high = قمة هذه الشمعة نفسها · لا حمراء في العمر بعد → لا مرجع "
                              "(وهنا تُشعل N5 فوق قمة الجبل نفسها)",
            "states": {
                "1": "S1 — الاختراق الكامل المؤكد: انطلاقة من 0.618 أو أعلى + اختراق قمة الحمراء + حجم أكبر من الحمراء",
                "2": "S2 — الاختراق بدون هيمنة الحجم: انطلاقة + اختراق القمة + حجم أقل أو مساوٍ للحمراء («ويبرغم عندها لفل حجم سيولتها»)",
                "3": "S3 — الامتصاص قبل الاختراق: انطلاقة + بلا اختراق للقمة + حجم أكبر من الحمراء",
                "5": "N5 🔥 — إشعال بلا مرجع: النطاق لم يرَ أي حمراء منذ ولادته (اندفاع خالص) + صرخة فوق قمة الجبل "
                     "نفسها (range_top) + هيمنة حجم على كل الخضراء + انضباط الانطلاقة — أعواد كانت صامتة بنيوياً عند "
                     "الترندية (بلا حمراء لا يوجد مرجع R ولا إشارة ممكنة)",
                "6": "N6 🤫 — الاختراق الهادئ: صرخة فوق سقف المرجع R + انضباط الانطلاقة + حجم لا يهيمن على أكبر خضراء "
                     "النطاق (v ≤ green_max) — ثقة بلا ضجيج؛ أعواد كانت مُصفَّرة عند الترندية بشرط الهيمنة الخضراء العام",
            },
            "common_conditions": [
                "النطاق يُعتمد لحظة ظهور الزقزاق (شمعتها تأكيداً) — الحساب يبدأ من شمعة الظهور",
                "الفيبو يُرسم من الطرف الظاهر أولاً (1) إلى الطرف الظاهر ثانياً (0) — خط 0.618 للمستخدم = price(0.382) بمقياس المحرك",
                "الانطلاقة: low_G ≥ خط 0.618 بمقياس رسم المستخدم (تكلفة الشمعة فوق خط الانطلاقة)",
                "هيمنة الخضراء: volume_G > حجم كل الشموع الخضراء داخل نافذة حياة النطاق الحي قبل شمعة الإشارة",
                "لا عدد شموع في التعريف — النافذة = عمر النطاق (من الظهور حتى ظهور الزوج التالي)",
                "إشارات الدخول المبوّبة تُشترط عليها موافقة الترند (انحياز صاعد بإجماع الفترات) — "
                "الخام والممنوع ظاهران في أعمدة entry_raw_*/entry_blocked_*",
                "🔥 R69: N5/N6 عائلتان جديدتان مُضافتان فوق S1/S2/S3 — أعوادهما صامتة حكماً عند الترندية "
                "(N5: بلا مرجع · N6: بلا هيمنة خضراء) فلا تداخل معها إطلاقاً (مثبت بالمقياس)",
            ],
            "excluded_cell": "الخلية الرابعة (لا اختراق + حجم أقل) = لا إشارة عمداً (ضوضاء) — "
                             "وN6 تستثني صراحةً هيمنة الخضراء بتصميمها (هذا هو تعريفها)",
            "volume_rule": "S1/S3: volume_G > volume_R · S2: volume_G ≤ volume_R · N5: volume_G > green_max (بلا R أصلاً) "
                           "· N6: volume_G ≤ green_max مع اختراق ref_high",
            "entry_rule": "الدخول عند شمعة الإشارة نفسها (الحدث = الدخول؛ تقييم الإغلاق وتنفيذ الافتتاح التالي next_open) "
                          "بعد موافقة بوابة الترند للأنواع المبوّبة (s1/s2/s3/n5/n6)",
            "range_lifecycle": "النطاق يُستبدل عند أول تغيّر في زوج الزقزاق المرسوم (طرف جديد أو إحلال أقوى) — لحظتها = ميلاد "
                               "النطاق الجديد وموتة السابق؛ الأزواج تتناوب قمة→قاع ثم قاع→قمة",
            "sfp_enabled": False,
        },
        "notes": "ZLF-End-To-End-Blazing — «الترندية الملتهبة» (R69): محرك موحّد فوق zigzag_fib_core "
                 "بنفس هندسة الترندية حرفياً — S1/S2/S3 كما هي بت-بت + إشارتا R68 المُقاستان: "
                 "N5 «إشعال بلا مرجع» (نطاق بلا أي حمراء + صرخة فوق قمة الجبل بهيمنة حجم) و "
                 "N6 «الاختراق الهادئ» (اختراق سقف المرجع بلا هيمنة الخضراء) — كلتاهما فوق بوابة "
                 "الترند القالبية نفسها (فترات قالبية — أضف ترنداً رابعاً 30 من القالب بلا كود). "
                 "كل المخرجات بأسماء عقد التمايز (zzfb_*/ind_zzfb_*/ZLF-E2E-Blazing) — صفر تداخل "
                 "مع zzf_*/zzfe_*/zzfet_*/trf_*.",
    }


# ---------------------------------------------------------------------------
# ✅ التسجيل الذاتي كمؤشر منفصل — zigzag_fib_e2e_blazing (اسم جديد تماماً)
#    يُستورد مرة واحدة من app/services/indicators/__init__.py
# ---------------------------------------------------------------------------
def _register_blazing_indicator() -> None:
    try:
        from .base import BaseIndicator, IndicatorResult, IndicatorType
        from .registry import IndicatorRegistry
        import pandas as pd

        class ZigZagFibE2EBlazingIndicator(BaseIndicator):
            """ZLF-End-To-End-Blazing — «الترندية الملتهبة» (S1/S2/S3 + N5/N6 + بوابة الترند)."""

            @classmethod
            def get_required_columns(cls):
                return ["open", "high", "low", "close"]

            def calculate(self, data: pd.DataFrame) -> IndicatorResult:
                from .overlay_columns import config_to_overlay_params
                conv = config_to_overlay_params({
                    "name": "zigzag_fib_e2e_blazing",
                    "params": dict(self.params or {}),
                }) or {"zzfib_e2e_blazing": {}}
                params = conv.get("zzfib_e2e_blazing") or {}
                res = zigzag_fib_e2e_blazing(data, **params)
                values = res["series"].get("zzfb_entry") or [None] * len(data)
                series = pd.Series(values, index=data.index, dtype=object)
                return IndicatorResult(
                    name=self.name,
                    values=series,
                    signals=None,
                    metadata={
                        "engine": ZLF_E2E_BLAZING_ENGINE_NAME,
                        "overlay": "zzfib_e2e_blazing",
                        "primary_column": "ind_zzfb_entry",
                        "available_columns": sorted(res["series"].keys()),
                    },
                )

        IndicatorRegistry.register(
            "zigzag_fib_e2e_blazing",
            display_name="ZLF-End-To-End-Blazing — الترندية الملتهبة (S1/S2/S3 + N5/N6)",
            description="المحرك الموحّد (R69) فوق نواة zigzag_fib_core بنفس هندسة الترندية: "
                        "S1/S2/S3 بت-بت + N5 «إشعال بلا مرجع» (نطاق بلا أي حمراء + صرخة فوق قمة الجبل "
                        "بهيمنة حجم — عمياء بنيوياً عند الترندية) + N6 «الاختراق الهادئ» (اختراق سقف "
                        "المرجع بلا هيمنة الخضراء) — كلها خلف بوابة ترند قالبية (فراكتالات 7/15/25 "
                        "قابلة للتغيير والتوسيع من القالب بلا أي كود؛ trend_gate يقبل s1/s2/s3/n5/n6). "
                        "العمود الأساسي: ind_zzfb_entry · الخام ind_zzfb_entry_raw · الممنوع "
                        "ind_zzfb_entry_blocked_s1|s2|s3|n5|n6.",
            category=IndicatorType.SUPPORT_RESISTANCE,
        )(ZigZagFibE2EBlazingIndicator)

        # مرادف قصير — نفس الفئة
        info = IndicatorRegistry._indicators.get("zigzag_fib_e2e_blazing")
        if info is not None:
            IndicatorRegistry._indicators.setdefault("zzfib_e2e_blazing", info)
    except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
        import logging
        logging.getLogger(__name__).exception("ZLF-E2E-Blazing indicator registration failed")


_register_blazing_indicator()
