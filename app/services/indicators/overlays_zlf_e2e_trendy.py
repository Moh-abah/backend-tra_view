# =============================================================================
# ✅ ROUND34 — ZLF-End-To-End-Trendy فوق المحرك الموحد (لا استنساخ بعد اليوم)
# =============================================================================
# ⚠️ توجيه صاحب القرار (2026-11-05): «سويه محرك الزقزاق واحد لكل الاستراتيجيات
#   ومحرك الفيبوناتشي واحد أيضاً للثلاث الاستراتيجيات... وكل استراتيجيه حسب
#   اهتمامها وواحده منضاف اليها النطاق وواحد النطاق مع الترندات» —
#   هذا الملف الآن طبقة سياسات رقيقة فوق zigzag_fib_core.py (المحرك الوحيد):
#     · الزقزاق والفيبوناتشي والنطاقات = المحرك الموحد — نفس السلوك
#       التاريخي المعتمد حرفياً (السلاسل والإشارات لم تتغير — مثبت بلقطة ذهبية).
#     · «اهتمام» الترندية فوق E2E: بوابة الترند القالبية على إشارات الدخول
#       (فراكتالات 7/15/25 قابلة للتغيير والتوسيع من القالب بلا أي كود) +
#       حراس الدخول (entry_raw/entry/entry_blocked — شفافية ثلاثية).
#     · ✅ إصلاح جذر الرسومات العشوائية: التطبيع الموحد عبر core.to_ms
#       (دعم ISO كامل) — أزمنة الرسم صحيحة في كل المسارات.
#     · ✅ ROUND34: كل نطاق في ranges[] يحمل levels[] كاملة بحدود الرسم
#       (تبدأ من خط الولادة anchor وتنتهي عند نهاية عمر النطاق).
#
# العقد المحفوظ (ROUND32) — لم يتغير أي سلوك:
#   1) الترند = مؤشر مستقل (trend_fractals.py — وفاء سكربت Pine
#      «Auto Trendline [DojiEmoji]» حرفياً) يُنتج إحداثيات الخطوط وسلاسلها،
#      وهذا المحرك يستقبلها ويحسب الإشارة بناء عليها.
#   2) بوابة الترند: إشارات الدخول المبوّبة (trend_gate) لا تتحقق دخولاً إلا
#      بانحياز الترند الصاعد (close فوق الخط العلوي) بإجماع الفترات المبيّح
#      (majority = أكثر من النصف — 2 من 3 افتراضياً):
#        zzfet_entry_raw_s{n}     = إشارة E2E الخام (قبل البوابة)
#        zzfet_entry_s{n}         = بعد البوابة (الخام ∧ الترند موافق)
#        zzfet_entry_blocked_s{n} = خام لكن الترند منعها (مرئية للفرونت)
#   3) الفترات قالبية بالكامل: trend_periods=[7,15,25] في القالب — إضافة ترند
#      رابع 30 أو تغيير الأرقام = تعديل القالب فقط، لا كود.
#   4) كل الأسماء عقد تمايز كامل: zzfet_* → ind_zzfet_*، إشارات
#      "ZLF-E2E-Trendy ..." — صفر تداخل مع zzfe_*/zzf_*/trf_*.
#   5) وضع الزقزاق: luxalgo length=100 افتراضياً (مواصفة شارت المنصة المُتحقق
#      منه بالبكسل) — وtradingview متاح من القالب.
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# ✅ ROUND34 — المحرك الموحد: المصدر الوحيد للزقزاق/الفيبو/التطبيع
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
    "zigzag_fib_e2e_trendy",
    "ZLF_E2E_TRENDY_ENGINE_NAME",
    "ZLF_E2E_TRENDY_SPEC",
    "ZLF_E2E_TRENDY_DEFAULT_LEVELS",
    "ZLF_E2E_TRENDY_LAUNCH_USER",
    "ZLF_E2E_TRENDY_DEFAULT_PERIODS",
]

# ---------------------------------------------------------------------------
# هوية المحرك المنفصل (عقد التمايز — كل الأسماء مختلفة عن كل المحركات القائمة)
# ---------------------------------------------------------------------------
ZLF_E2E_TRENDY_ENGINE_NAME = "ZLF-End-To-End-Trendy"
ZLF_E2E_TRENDY_SPEC = "ROUND32-e2e-trendy"

# مستويات الفيبو — نفس مقياس المحرك الموحد (0..1 من الأول إلى الثاني)
ZLF_E2E_TRENDY_DEFAULT_LEVELS: List[float] = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 0.85415, 1.0]

# خط الانطلاقة: «من 0.618 أو أعلى» بمقياس رسم المستخدم = price(0.382) بالمحرك
ZLF_E2E_TRENDY_LAUNCH_USER: float = 0.618
_ZLF_E2E_TRENDY_LAUNCH_ENGINE_LEVEL: float = 0.382

# تسامح ملامسة خط الانطلاقة — تيك واحد مستنتج من البيانات (كما في E2E)
ZLF_E2E_TRENDY_LAUNCH_TOUCH_TICKS: float = 1.0

# القالب الافتراضي لبوابة الترند (فترات/إجماع/أنواع مبوّبة) — المرجع المعتمد
# يعيش في بريسِت الاستراتيجية (presets.py) وهذه مجرد وقوعة احتياطية عند
# الاستدعاء بلا معاملات — لا أرقام فترات داخل أي منطق.
ZLF_E2E_TRENDY_DEFAULT_PERIODS: Tuple[int, ...] = (7, 15, 25)
ZLF_E2E_TRENDY_DEFAULT_CONFIRM: str = "majority"
ZLF_E2E_TRENDY_DEFAULT_GATE: Tuple[str, ...] = ("s1", "s2", "s3")


def _norm_trend_gate(raw: Any) -> List[int]:
    """تطبيع أنواع الإشارات المبوّبة بالترند — يقبل s1/s2/s3 أو 1/2/3 بأي صيغة.

    None            = البوابة على الثلاثة كلها (الافتراضي).
    «none»/«off»    = البوابة معطلة كلياً (المحرك = E2E حرفياً — مفتاح A/B).
    قائمة فارغة/قيم غير معروفة = معطلة كلياً أيضاً (المُصرَّح لا يبوّب شيئاً).
    """
    if raw is None:
        return [1, 2, 3]
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
    return sorted(out)


# ---------------------------------------------------------------------------
# المحرك الرئيسي — ZLF-End-To-End-Trendy (طبقة سياسات فوق المحرك الموحد)
# ---------------------------------------------------------------------------
def zigzag_fib_e2e_trendy(
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
    launch_touch_ticks: float = ZLF_E2E_TRENDY_LAUNCH_TOUCH_TICKS,
    trend_periods: Any = None,
    trend_confirm: Any = ZLF_E2E_TRENDY_DEFAULT_CONFIRM,
    trend_gate: Any = None,
) -> Dict[str, Any]:
    """ZLF-End-To-End-Trendy — E2E الموحد + بوابة الترند (محرك موحد ROUND34).

    المعاملات: نفس معاملات E2E حرفياً (mode/length/depth/deviation/backstep/
    reverse/levels/extend_right/extend_leg_to_live/launch_touch_ticks) + ثلاثة
    قوالب ترند:
      trend_periods:  قائمة فترات الفراكتال — [7,15,25] افتراضياً (قالبية:
                      أضف ترنداً رابعاً 30 من القالب بلا أي كود).
      trend_confirm:  majority (2 من 3) | all | any | رقم صريح.
      trend_gate:     أنواع الإشارات المبوّبة — s1/s2/s3 (افتراضياً الثلاثة).

    البوابة: إشارة الدخول لا تتحقق إلا بانحياز الترند الصاعد (close فوق الخط
    العلوي) بإجماع الفترات. الإشارات الخام والممنوعة كلها ظاهرة بالأعمدة.
    """
    t, o, h, l, c = norm_candles(candles)
    N = len(c)
    length = max(2, int(length))
    lvls = [float(x) for x in (levels if levels is not None else ZLF_E2E_TRENDY_DEFAULT_LEVELS)]
    vols = norm_volume(candles)
    if len(vols) != N:
        vols = [None] * N

    _tick = infer_price_tick(o, h, l, c)
    try:
        _touch_tol = max(0.0, float(launch_touch_ticks)) * (_tick or 0.0)
    except (TypeError, ValueError):
        _touch_tol = 0.0

    lv_keys = [(r, f"zzfet_level_{level_tag(r)}") for r in lvls]

    # ------------------------------------------------------------------
    # مؤشر الترند المستقل يُحسب أولاً (إحداثياته وسلاسله تصل من محركه
    # المعزول trend_fractals.py) والبوابة تُطبَّق لحظة كل حدث أثناء المسح
    # الزمني — سببية كاملة (قيم الشمعة i من الشموع ≤ i فقط).
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
    #    (وضعان: luxalgo/tradingview — نفس السلوك التاريخي حرفياً)
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

    # ✅ ROUND39 (طلب وكيل الفرونت ج38-1أ): محاور الزقزاق المؤكدة عقد رسم
    # موحد مع legs — نفس نقاط النواة حرفياً (صفر اشتقاق/اختراع): كل محور
    # {bar, time, price, kind, confirmed_at_bar} وأطراف الساقات المتتالية
    # تتشاركها (legs[k].x2 == legs[k+1].x1).
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
    # 2) النطاقات المتعاقبة — موحّدة بالمحرك core (ROUND26 كما هي)
    # ------------------------------------------------------------------
    ranges = build_ranges(pair_events, t, N, reverse, _ZLF_E2E_TRENDY_LAUNCH_ENGINE_LEVEL)

    # ------------------------------------------------------------------
    # 3) المسح الزمني السببي — المصفوفة المصادقة + بوابة الترند لحظة كل حدث
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
    liq_any: List[float] = [0.0] * N
    # أعمدة الدخول الثلاثية: الخام (شفافية) · المبوَّب (القرار) · الممنوع
    e_entry: List[float] = [0.0] * N            # الجامع بعد البوابة
    e_entry_raw: List[float] = [0.0] * N        # الجامع الخام (قبل البوابة)
    e_entry_s1: List[float] = [0.0] * N         # بعد البوابة
    e_entry_s2: List[float] = [0.0] * N
    e_entry_s3: List[float] = [0.0] * N
    e_entry_raw_s1: List[float] = [0.0] * N     # خام
    e_entry_raw_s2: List[float] = [0.0] * N
    e_entry_raw_s3: List[float] = [0.0] * N
    e_blocked_s1: List[float] = [0.0] * N       # خام لكن الترند منعها
    e_blocked_s2: List[float] = [0.0] * N
    e_blocked_s3: List[float] = [0.0] * N
    s_trend_ok: List[float] = [float(x) for x in s_tr_ok[:N]] if len(s_tr_ok) >= N else [0.0] * N
    signals: List[Dict[str, Any]] = []

    ri = -1
    green_max: Optional[float] = None
    live_ref: Optional[Dict[str, Any]] = None
    n_events = 0
    n_raw = 0
    n_blocked = 0
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
        green = (c_n is not None and o_n is not None and c_n > o_n)

        if c_n is not None and o_n is not None and c_n < o_n and v_n is not None:
            if live_ref is None or v_n >= live_ref["vol"]:
                live_ref = {"bar": i, "time": t[i], "high": hi_n, "vol": v_n}

        ref = live_ref
        if ref is not None:
            liq_ref_high[i] = clean_float(ref["high"])
            liq_ref_vol[i] = clean_float(ref["vol"])

        if ref is not None and v_n is not None:
            liq_vol_ok[i] = 1.0 if v_n > ref["vol"] else 0.0

        # --- المصفوفة المصادقة (حرفياً كما في E2E) + البوابة ---
        cell = 0
        if green and v_n is not None and hi_n is not None and lo_n is not None \
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
            # بوابة الترند: حالة الترند عند شمعة الإشارة نفسها
            # (قيمها حُسبت من شموع ≤ i فقط — سببية كاملة بلا استشراف)
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
                "signal": f"ZLF-E2E-Trendy Liquidity S{cell}",
                "engine": ZLF_E2E_TRENDY_ENGINE_NAME,
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
                # شفافية البوابة على سجل الحالة نفسه
                "trend_ok": trend_ok_i,
                "trend_bias": float(s_tr_bias[i]) if i < len(s_tr_bias) else 0.0,
                "trend_votes": {"bull": float(s_tr_bull[i]) if i < len(s_tr_bull) else 0.0,
                                "bear": float(s_tr_bear[i]) if i < len(s_tr_bear) else 0.0},
                "gated": bool(gated_kind),
            })
            # الدخول = شمعة الإشارة نفسها (كما في E2E) — بعد البوابة
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
                    "signal": f"ZLF-E2E-Trendy Entry S{cell}",
                    "engine": ZLF_E2E_TRENDY_ENGINE_NAME,
                    "states": [cell],
                    "range_index": r["index"],
                    "price": c_n, "launch_line": r["launch"],
                    "fallback": False, "color": "#28cc95",
                    "trend_ok": trend_ok_i,
                    "trend_gate_passed": True,
                })
            else:
                e_blocked_cols = blocked_cols[cell]
                e_blocked_cols[i] = 1.0
                n_blocked += 1
                signals.append({
                    "bar": i, "time": t[i], "side": "blocked",
                    "signal": f"ZLF-E2E-Trendy Blocked S{cell} (trend gate)",
                    "engine": ZLF_E2E_TRENDY_ENGINE_NAME,
                    "states": [cell],
                    "range_index": r["index"],
                    "price": c_n, "launch_line": r["launch"],
                    "trend_ok": trend_ok_i,
                    "trend_gate_passed": False,
                })

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
    # 5) السلاسل — أسماء عقد التمايز (zzfet_*) + مرايا الترند لكل فترة
    # ------------------------------------------------------------------
    _trendy_series: Dict[str, List[Optional[float]]] = {
        "zzfet_dir": s_dir, "zzfet_p1": s_p1, "zzfet_p2": s_p2,
        "zzfet_i1": s_i1, "zzfet_i2": s_i2,
        "zzfet_anchor": s_anchor, "zzfet_range_index": s_range_idx,
        **level_series,
        "zzfet_liq_state": liq_state,
        "zzfet_liq_ref_high": liq_ref_high,
        "zzfet_liq_ref_vol": liq_ref_vol,
        "zzfet_liq_vol_ok": liq_vol_ok,
        "zzfet_signal_s1": liq_s1,
        "zzfet_signal_s2": liq_s2,
        "zzfet_signal_s3": liq_s3,
        "zzfet_signal_any": liq_any,
        "zzfet_entry": e_entry,
        "zzfet_entry_raw": e_entry_raw,
        "zzfet_entry_s1": e_entry_s1,
        "zzfet_entry_s2": e_entry_s2,
        "zzfet_entry_s3": e_entry_s3,
        "zzfet_entry_raw_s1": e_entry_raw_s1,
        "zzfet_entry_raw_s2": e_entry_raw_s2,
        "zzfet_entry_raw_s3": e_entry_raw_s3,
        "zzfet_entry_blocked_s1": e_blocked_s1,
        "zzfet_entry_blocked_s2": e_blocked_s2,
        "zzfet_entry_blocked_s3": e_blocked_s3,
        "zzfet_trend_ok": s_trend_ok,
        "zzfet_trend_bias": list(s_tr_bias[:N]) if len(s_tr_bias) >= N else [0.0] * N,
        "zzfet_trend_votes_bull": list(s_tr_bull[:N]) if len(s_tr_bull) >= N else [0.0] * N,
        "zzfet_trend_votes_bear": list(s_tr_bear[:N]) if len(s_tr_bear) >= N else [0.0] * N,
    }
    # مرايا الترند لكل فترة (لرسم خطوط الترند فوق شارت الاستراتيجية نفسها) —
    # الحلقة عامة على الفترات الفعلية (قالبية — ترند رابع يظهر تلقائياً)
    for p in trend_periods_eff:
        for src, dst in (("upper", "upper"), ("lower", "lower"), ("bias", "bias")):
            vals = tr_series.get(f"trf_p{p}_{src}")
            if vals is not None:
                _trendy_series[f"zzfet_tr_p{p}_{dst}"] = list(vals[:N]) if len(vals) >= N else list(vals) + [None] * (N - len(vals))

    return {
        "name": "ZigZag Fib E2E Trendy (ZLF-End-To-End-Trendy — Range-anchored + Trend gate)",
        "engine": ZLF_E2E_TRENDY_ENGINE_NAME,
        "spec": ZLF_E2E_TRENDY_SPEC,
        # ✅ ROUND34 — المحرك الموحد: هوية النواة المشتركة (شفافية كاملة)
        "core": {"spec": ZIGZAG_FIB_CORE_SPEC, "version": ZIGZAG_FIB_CORE_VERSION},
        "volume_available": any(v is not None for v in vols),
        "params": {"mode": mode, "length": length, "reverse": reverse, "levels": lvls,
                   "extend_right": extend_right, "extend_leg_to_live": extend_leg_to_live,
                   "depth": depth, "deviation": deviation, "backstep": backstep,
                   "launch_user": ZLF_E2E_TRENDY_LAUNCH_USER,
                   "launch_touch_ticks": ZLF_E2E_TRENDY_LAUNCH_TOUCH_TICKS,
                   "inferred_tick": _tick,
                   # القوالب الترندية (كلها قالبية — بلا أرقام داخل الكود)
                   "trend_periods": trend_periods_eff,
                   "trend_confirm": trend_confirm_eff,
                   "trend_gate": [f"s{x}" for x in gate_cells],
                   "trend_threshold": trend_threshold},
        "legs": legs,
        # ✅ ROUND39 (طلبات وكيل الفرونت ج38): pivots[] (طلب 1-أ — نفس محاور
        # النواة) + window (طلب 3 — هوية النافذة للمطابقة السريعة بالفهارس).
        "pivots": pivots,
        "window": {"bars": N, "time_from": t[0] if N else None,
                   "time_to": t[N - 1] if N else None},
        # ✅ ROUND34: كل نطاق يحمل levels[] بحدود رسم كاملة (ولادة → نهاية)
        "ranges": [range_public(r, t, N, lvls, extend_right) for r in ranges],
        "current": current,
        "signals": signals,
        "series": _trendy_series,
        # قسم الترند الكامل: الإحداثيات التي يحسب منها الباك اند الإشارة
        # (خطوط كل فترة بأطرافها وأميلها ولحظات ولادتها) + عدّادات البوابة
        "trend": {
            "enabled": True,
            "engine": TRF_ENGINE_NAME,
            "periods": trend_periods_eff,
            "confirm_mode": trend_confirm_eff,
            "threshold": trend_threshold,
            "gate": [f"s{x}" for x in gate_cells],
            "gate_rule": "إشارة الدخول المبوّبة لا تتحقق إلا بانحياز الترند الصاعد "
                         "(close فوق الخط العلوي — وصل آخر فراكتالَي قمة) بإجماع الفترات "
                         "(majority = أكثر من النصف) عند شمعة الإشارة نفسها",
            "counts": {"raw_entries": n_raw, "gated_entries": n_raw - n_blocked,
                       "blocked_entries": n_blocked},
            "lines": trend.get("lines") or {},
            "current": trend.get("current") or {},
        },
        "liquidity": {
            "enabled": True,
            "engine": ZLF_E2E_TRENDY_ENGINE_NAME,
            "spec": ZLF_E2E_TRENDY_SPEC,
            "events": n_events,
            "volume_available": any(v is not None for v in vols),
            "volume_missing_warning": (
                None if any(v is not None for v in vols)
                else "لم يصل عمود الحجم للمحرك — لا يمكن بناء المرجع R ولا تصنيف S1/S2/S3 "
                     "(تحقق من مصدر الشموع في المسار المستدعي: يجب تمرير volume مع كل شمعة)"
            ),
            "reference_rule": "R = أكبر شمعة حمراء (close<open) حجماً داخل عمر النطاق الحي (من شمعة ظهور الزقزاق "
                              "إلى الشمعة الجاري فحصها — كل ما قبل الظهور ليس نطاقاً) ويتحدّث لحظياً مع كل حمراء أكبر "
                              "(عند التعادل: الأحدث يفوز) — ref_high = قمة هذه الشمعة نفسها · لا حمراء في العمر بعد → لا مرجع",
            "states": {
                "1": "S1 — الاختراق الكامل المؤكد: خضراء + انطلاقة من 0.618 أو أعلى + اختراق قمة الحمراء + حجم أكبر من الحمراء",
                "2": "S2 — الاختراق بدون هيمنة الحجم: خضراء + انطلاقة + اختراق القمة + حجم أقل أو مساوٍ للحمراء («ويبرغم عندها لفل حجم سيولتها»)",
                "3": "S3 — الامتصاص قبل الاختراق: خضراء + انطلاقة + بلا اختراق للقمة + حجم أكبر من الحمراء",
            },
            "common_conditions": [
                "النطاق يُعتمد لحظة ظهور الزقزاق (شمعتها تأكيداً) — الحساب يبدأ من شمعة الظهور",
                "الفيبو يُرسم من الطرف الظاهر أولاً (1) إلى الطرف الظاهر ثانياً (0) — خط 0.618 للمستخدم = price(0.382) بمقياس المحرك",
                "الانطلاقة: low_G ≥ خط 0.618 بمقياس رسم المستخدم",
                "هيمنة الخضراء: volume_G > حجم كل الشموع الخضراء داخل نافذة حياة النطاق الحي قبل شمعة الإشارة",
                "لا عدد شموع في التعريف — النافذة = عمر النطاق (من الظهور حتى ظهور الزوج التالي)",
                "✅ ROUND32 (الترندية): إشارات الدخول المبوّبة تُشترط عليها موافقة الترند (انحياز صاعد بإجماع الفترات) — "
                "الخام والممنوع ظاهران في أعمدة entry_raw_*/entry_blocked_*",
            ],
            "excluded_cell": "الخلية الرابعة (لا اختراق + حجم أقل) = لا إشارة عمداً (ضوضاء)",
            "volume_rule": "S1/S3: volume_G > volume_R · S2: volume_G ≤ volume_R (تقسيم بعلاقة الحجم مع الحمراء)",
            "entry_rule": "الدخول عند شمعة الإشارة نفسها (الحدث = الدخول؛ تقييم الإغلاق وتنفيذ الافتتاح التالي next_open) "
                          "بعد موافقة بوابة الترند للأنواع المبوّبة",
            "range_lifecycle": "النطاق يُستبدل عند أول تغيّر في زوج الزقزاق المرسوم (طرف جديد أو إحلال أقوى) — لحظتها = ميلاد النطاق الجديد وموتة السابق؛ الأزواج تتناوب قمة→قاع ثم قاع→قمة",
            "sfp_enabled": False,
        },
        "notes": "ZLF-End-To-End-Trendy — «الزقزاق البطل e2e الترنديه» — محرك موحد (ROUND34): الزقزاق والفيبو "
                 "والنطاقات من zigzag_fib_core (المصدر الوحيد للاستراتيجيات الثلاث) + بوابة ترند فوق إشارات "
                 "الدخول: الترند مؤشر مستقل (trend_fractals — وفاء سكربت Auto Trendline [DojiEmoji]) يرسل "
                 "إحداثياته للباك اند وهذا المحرك يحسب الإشارة بناء عليها. الفترات قالبية بالكامل — أضف ترنداً "
                 "رابعاً 30 من القالب بلا كود. كل نطاق يحمل levels[] بحدود رسم كاملة (ولادة → نهاية). "
                 "كل المخرجات بأسماء عقد التمايز (zzfet_*/ind_zzfet_*/ZLF-E2E-Trendy).",
    }


# ---------------------------------------------------------------------------
# ✅ التسجيل الذاتي كمؤشر منفصل — zigzag_fib_e2e_trendy (اسم جديد تماماً)
#    يُستورد مرة واحدة من app/services/indicators/__init__.py
# ---------------------------------------------------------------------------
def _register_trendy_indicator() -> None:
    try:
        from .base import BaseIndicator, IndicatorResult, IndicatorType
        from .registry import IndicatorRegistry
        import pandas as pd

        class ZigZagFibE2ETrendyIndicator(BaseIndicator):
            """ZLF-End-To-End-Trendy — الترندية (E2E الموحد + بوابة الترند القالبية)."""

            @classmethod
            def get_required_columns(cls):
                return ["open", "high", "low", "close"]

            def calculate(self, data: pd.DataFrame) -> IndicatorResult:
                from .overlay_columns import config_to_overlay_params
                conv = config_to_overlay_params({
                    "name": "zigzag_fib_e2e_trendy",
                    "params": dict(self.params or {}),
                }) or {"zzfib_e2e_trendy": {}}
                params = conv.get("zzfib_e2e_trendy") or {}
                res = zigzag_fib_e2e_trendy(data, **params)
                values = res["series"].get("zzfet_entry") or [None] * len(data)
                series = pd.Series(values, index=data.index, dtype=object)
                return IndicatorResult(
                    name=self.name,
                    values=series,
                    signals=None,
                    metadata={
                        "engine": ZLF_E2E_TRENDY_ENGINE_NAME,
                        "overlay": "zzfib_e2e_trendy",
                        "primary_column": "ind_zzfet_entry",
                        "available_columns": sorted(res["series"].keys()),
                    },
                )

        IndicatorRegistry.register(
            "zigzag_fib_e2e_trendy",
            display_name="ZLF-End-To-End-Trendy — الزقزاق البطل e2e الترنديه",
            description="المحرك الموحد (ROUND34): E2E حرفياً (النطاق لحظة ظهور الزقزاق + المصفوفة S1/S2/S3) "
                        "+ بوابة ترند قالبية على الدخول (فراكتالات 7/15/25 قابلة للتغيير والتوسيع من القالب — تقاطع/انحياز "
                        "خطوط Pine Auto Trendline). العمود الأساسي: ind_zzfet_entry · الخام ind_zzfet_entry_raw · "
                        "الممنوع ind_zzfet_entry_blocked_s1|s2|s3.",
            category=IndicatorType.SUPPORT_RESISTANCE,
        )(ZigZagFibE2ETrendyIndicator)

        # مرادف قصير — نفس الفئة
        info = IndicatorRegistry._indicators.get("zigzag_fib_e2e_trendy")
        if info is not None:
            IndicatorRegistry._indicators.setdefault("zzfib_e2e_trendy", info)
    except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
        import logging
        logging.getLogger(__name__).exception("ZLF-E2E-Trendy indicator registration failed")


_register_trendy_indicator()
