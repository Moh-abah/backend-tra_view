# =============================================================================
# ✅ ROUND34 — ZLF-End-To-End فوق المحرك الموحد (لا محرك منفصل بعد اليوم)
# =============================================================================
# ⚠️ توجيه صاحب القرار (2026-11-05): «فاجعله موحد للجميع وكل استراتيجيه حسب
#   اهتمامها» — أُلغي الاستنساخ الذاتي الاكتفاء (4 نسخ luxalgo + 3 نسخ TV):
#   هذا الملف الآن طبقة سياسات رقيقة فوق zigzag_fib_core.py (المحرك الوحيد):
#     · الزقزاق والفيبوناتشي والنطاقات تُحسب بالمحرك الموحد — نفس السلوك
#       التاريخي المعتمد حرفياً (السلاسل والإشارات لم تتغير بايت-ببايت —
#       مثبت بلقطة ذهبية قبل/بعد في evidence/).
#     · ما يبقى هنا هو «اهتمام» استراتيجية E2E فقط: المصفوفة السيولية
#       S1/S2/S3 والمرجع الحي R داخل عمر النطاق (ROUND26) والانطلاقة.
#     · ✅ إصلاح جذر الرسومات العشوائية في شارت الباك تست: النسخة القديمة
#       المستنسخة كانت تفشل في تحليل timestamp كسلسلة ISO (ترجع 0) — الآن
#       التطبيع موحد عبر core.to_ms (دعم ISO كامل) فأزمنة الرسم صحيحة في
#       كل المسارات (DataFrame الحي · ms · ثوانٍ · ISO).
#     · ✅ ROUND34: كل نطاق في ranges[] يحمل الآن levels[] كاملة بحدود
#       الرسم (تبدأ من خط الولادة anchor وتنتهي عند نهاية عمر النطاق) —
#       «يجب أن يكون للفيبوناتشي نهاية كي لا يشوّه الشارت».
#
# --------------------------- المواصفة المصادقة (ZLF-End-To-End) --------------
# (محفوظة حرفياً — لم يتغير أي سلوك استراتيجي)
# 1) «النطاق = لحظة ظهور الزقزاق»: عند الشمعة التي جعلت الزقزاق يظهر
#    (confirmed_at_bar؛ في وضع luxalgo length=100 = تأكيد بعد 100 شمعة)
#    يُعتمد زوج الزقزاق المرسوم [الطرف الظاهر أولاً، الطرف الظاهر ثانياً]
#    نطاقاً جديداً، يُرسم عليه الفيبو، ويبدأ حساب الاستراتيجية من تلك الشمعة.
# 2) دورة الحياة: النطاق يُستبدل عند أول تغيّر في زوج الزقزاق المرسوم
#    (طرف جديد أو إحلال أقوى) — لحظة التغيّر = ميلاد الجديد وموتة السابق.
# 3) الفيبو يُرسم «من الطرف الظاهر أولاً إلى الطرف الظاهر ثانياً» — بمقياس
#    المحرك price(level) = q1 + diff × level (خط 0.618 للمستخدم = price(0.382)).
# 4) المرجع R = أكبر شمعة حمراء حجماً داخل عمر النطاق الحي نفسه (من شمعة
#    الظهور شاملة حتى الجاري فحصه — ROUND26؛ عند التعادل الأحدث يفوز).
# 5) نافذة «باقي الخضراء» = كل الخضراء داخل نافذة حياة النطاق الحي.
# 6) المصفوفة: S1 اختراق∧حجم أكبر · S2 اختراق∧حجم أقل أو مساوٍ ·
#    S3 رفض∧حجم أكبر · الرابعة = لا إشارة عمداً (ضوضاء).
#    الشروط المشتركة: خضراء + انطلاقة من 0.618 (بمقياس المستخدم) + هيمنة.
# 7) الدخول = شمعة الإشارة نفسها (next_open). 8) لا SFP.
# 9) الخروج = انقلاب النطاق إلى هابطة (zzfe_dir < 0).
# 10) عمودا ولادة النطاق: zzfe_anchor (1.0 عند الظهور) وzzfe_range_index.
#
# وضع الزقزاق: نفس الوضعين المعتمدين عبر المحرك الموحد — luxalgo length=100
# (الافتراضي — وضع شارت المنصة المُتحقق بالبكسل) أو tradingview
# depth/deviation/backstep (متاح — تغييره من القالب فقط بلا أي كود).
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

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
    "zigzag_fib_e2e",
    "ZLF_E2E_ENGINE_NAME",
    "ZLF_E2E_DEFAULT_LEVELS",
    "ZLF_E2E_LAUNCH_USER",
]

# ---------------------------------------------------------------------------
# هوية المحرك المنفصل (عقد التمايز — كل الأسماء مختلفة عن الأصل)
# ---------------------------------------------------------------------------
ZLF_E2E_ENGINE_NAME = "ZLF-End-To-End"
ZLF_E2E_SPEC = "ROUND26-end-to-end"

# مستويات الفيبو المرسومة (بمقياس المحرك 0..1 على المسار من الأول إلى الثاني).
# تشمل 0.85415 = نظير مستوى 0.14585 (0.236×0.618) بمقياس رسم المستخدم
# — الموجود على شارت المنصة — ليطابق الرسم الشارت حرفياً.
ZLF_E2E_DEFAULT_LEVELS: List[float] = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 0.85415, 1.0]

# خط الانطلاقة: «من 0.618 أو أعلى» بمقياس رسم المستخدم (1 عند الطرف الأول،
# 0 عند الثاني) = price(0.382) بمقياس المحرك — المصادق بالبكسل على شارت
# المنصة (63,011.6+0.382×720.9=63,287.0 و 53,223.5−0.382×3,668.4=51,822.2).
ZLF_E2E_LAUNCH_USER: float = 0.618
_ZLF_E2E_LAUNCH_ENGINE_LEVEL: float = 0.382

# ✅ تسامح ملامسة خط الانطلاقة: «قاعها ملتصق بخط 0.618 نفسه» — الأسعار
# مُكمّمة بتيك الرمز، فالقاع «الملتصق» قد يقع تيكاً واحداً تحت الخط المحسوب.
# التسامح = تيك واحد مُستنتَج من البيانات نفسها. 0 = صرامة تامة.
ZLF_E2E_LAUNCH_TOUCH_TICKS: float = 1.0


# ---------------------------------------------------------------------------
# المحرك الرئيسي — ZLF-End-To-End (طبقة سياسات فوق المحرك الموحد)
# ---------------------------------------------------------------------------
def zigzag_fib_e2e(
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
    launch_touch_ticks: float = ZLF_E2E_LAUNCH_TOUCH_TICKS,
) -> Dict[str, Any]:
    """ZLF-End-To-End — النطاق يُعتمد لحظة ظهور الزقزاق (محرك موحد ROUND34).

    المعاملات مطابقة للأصل (توافق مألوف): mode/length (luxalgo) · depth/
    deviation/backstep (tradingview) · reverse/levels/extend_right/
    extend_leg_to_live. لا liq_lookback ولا liq_arm_bars — التعريف لا يحتوي
    أي عدد شموع: نافذة الحساب = عمر النطاق الحي.

    المخرجات (كلها بأسماء عقد التمايز — لم تتغير):
      series: zzfe_dir/p1/p2/i1/i2 · zzfe_level_<L> · zzfe_liq_state/
              zzfe_liq_ref_high/zzfe_liq_ref_vol/zzfe_liq_vol_ok ·
              zzfe_signal_s1/s2/s3/any · zzfe_entry · zzfe_entry_s1/s2/s3 ·
              zzfe_anchor · zzfe_range_index
      signals: "ZLF-E2E Liquidity S1|S2|S3" و "ZLF-E2E Entry S1|S2|S3"
      ranges:  النطاقات المتعاقبة — أطرافها، لحظة الولادة (anchor)، لحظة
               الوفاة (death)، مستوياتها (levels بحدود رسم كاملة: من خط
               الولادة إلى نهاية العمر ✅ ROUND34)، مرجعها R، واتجاهها.
      legs:    أرجل الزقزاق (عقد الرسم الموحد — الرسم بـ time).
      current: النطاق الحي الآن + مستوياته الممتدة.
    """
    t, o, h, l, c = norm_candles(candles)
    N = len(c)
    length = max(2, int(length))
    lvls = [float(x) for x in (levels if levels is not None else ZLF_E2E_DEFAULT_LEVELS)]
    vols = norm_volume(candles)
    if len(vols) != N:
        vols = [None] * N

    # ✅ استنتاج تيك الرمز من البيانات نفسها (أصغر فرق موجب بين مستويات فعلية)
    _tick = infer_price_tick(o, h, l, c)
    try:
        _touch_tol = max(0.0, float(launch_touch_ticks)) * (_tick or 0.0)
    except (TypeError, ValueError):
        _touch_tol = 0.0

    lv_keys = [(r, f"zzfe_level_{level_tag(r)}") for r in lvls]

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
    # 2) النطاقات المتعاقبة من سجل تغيّرات الزوج — موحّدة بالمحرك core
    #    (الولادة = لحظة ظهور الزقزاق anchor · الموت = ولادة التالي)
    # ------------------------------------------------------------------
    ranges = build_ranges(pair_events, t, N, reverse, _ZLF_E2E_LAUNCH_ENGINE_LEVEL)

    # ------------------------------------------------------------------
    # 3) المسح الزمني السببي — سلاسل النطاق الحي + المصفوفة المصادقة
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
    # عمودا ولادة النطاق (ROUND26) — نقطة بداية النطاق للشارتين:
    s_anchor: List[float] = [0.0] * N
    s_range_idx: List[float] = [-1.0] * N
    liq_s1: List[float] = [0.0] * N
    liq_s2: List[float] = [0.0] * N
    liq_s3: List[float] = [0.0] * N
    liq_any: List[float] = [0.0] * N
    e_entry: List[float] = [0.0] * N
    e_entry_s1: List[float] = [0.0] * N
    e_entry_s2: List[float] = [0.0] * N
    e_entry_s3: List[float] = [0.0] * N
    signals: List[Dict[str, Any]] = []

    ri = -1
    green_max: Optional[float] = None   # أكبر حجم أخضر داخل نافذة النطاق الحي حتى الشمعة السابقة
    live_ref: Optional[Dict[str, Any]] = None   # المرجع الحي داخل عمر النطاق (يبدأ None عند الولادة)
    n_events = 0
    for i in range(N):
        # تقدّم إلى النطاق الذي ظهر عند هذه الشمعة أو قبلها (الميلاد = الظهور)
        while ri + 1 < len(ranges) and ranges[ri + 1]["anchor"] <= i:
            if ri >= 0:
                ranges[ri]["ref"] = live_ref   # المرجع النهائي لعمر النطاق المنتهي
            ri += 1
            green_max = None   # نافذة حياة جديدة — تصفير هيمنة الخضراء
            live_ref = None    # نافذة حياة جديدة — المرجع يبدأ من الصفر
        if ri < 0:
            continue
        r = ranges[ri]

        # --- سلاسل النطاق الحي (تُكتب عند كل شمعة من عمره) ---
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
        # ✅ ROUND35 (قرار المالك #R68): لا مانع من نوع الشمعة — الدوجي/الحمراء
        # مؤهلة للإشارة ما دامت تملك سيولة وتصرخ صعوداً (اختراق قمة المرجع).
        # «الخضراء» بمفهوم الاستراتيجية = شمعة بمنطقنا (سيولة + صرخة)، لا لونها.
        # هيمنة الخضراء (green_max) تظل على الخضراء الصريحة فقط.
        signal_ok = (c_n is not None and o_n is not None)
        green = (c_n is not None and o_n is not None and c_n > o_n)  # لهيمنة الخضراء فقط

        # المرجع الحي داخل عمر النطاق: كل حمراء (بحجم) من شمعة الولادة
        # حتى الجاري فحصه مرشحة؛ الأكبر حجماً يفوز (والأحدث عند التعادل).
        if c_n is not None and o_n is not None and c_n < o_n and v_n is not None:
            if live_ref is None or v_n >= live_ref["vol"]:
                live_ref = {"bar": i, "time": t[i], "high": hi_n, "vol": v_n}

        ref = live_ref
        if ref is not None:
            liq_ref_high[i] = clean_float(ref["high"])
            liq_ref_vol[i] = clean_float(ref["vol"])

        if ref is not None and v_n is not None:
            liq_vol_ok[i] = 1.0 if v_n > ref["vol"] else 0.0

        # --- المصفوفة المصادقة (تقسيم كامل بعلاقة الحجم مع الحمراء) ---
        cell = 0
        if signal_ok and v_n is not None and hi_n is not None and lo_n is not None \
                and ref is not None and not r["degenerate"] and r["launch"] is not None:
            breakout = hi_n > ref["high"]
            vol_dom = v_n > ref["vol"]
            dominance = (green_max is None) or (v_n > green_max)
            # «من 0.618 أو أعلى» + «قاعها ملتصق بالخط» — ملامسة التيك الواحد مسموحة
            launch_ok = lo_n >= (r["launch"] - _touch_tol)
            if breakout and vol_dom:
                cell = 1
            elif breakout:
                cell = 2
            elif vol_dom:
                cell = 3
            if cell and not (launch_ok and dominance):
                cell = 0   # الشروط المشتركة غير مكتملة → لا إشارة
        if cell:
            liq_state[i] = float(cell)
            liq_any[i] = 1.0
            n_events += 1
            sig_cols = {1: liq_s1, 2: liq_s2, 3: liq_s3}
            ent_cols = {1: e_entry_s1, 2: e_entry_s2, 3: e_entry_s3}
            sig_cols[cell][i] = 1.0
            anchor_bar = r["anchor"]
            signals.append({
                "bar": i, "time": t[i], "side": "liquidity",
                "signal": f"ZLF-E2E Liquidity S{cell}",
                "engine": ZLF_E2E_ENGINE_NAME,
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
            })
            # الدخول = شمعة الإشارة نفسها (الحدث = الدخول) — تنفيذ next_open في الباك
            e_entry[i] = 1.0
            ent_cols[cell][i] = 1.0
            signals.append({
                "bar": i, "time": t[i], "side": "buy",
                "signal": f"ZLF-E2E Entry S{cell}",
                "engine": ZLF_E2E_ENGINE_NAME,
                "states": [cell],
                "range_index": r["index"],
                "price": c_n, "launch_line": r["launch"],
                "fallback": False, "color": "#28cc95",
            })

        # تحديث هيمنة الخضراء بعد فحص الشمعة (لا تشمل G نفسها) — تظل على
        # الخضراء الصريحة فقط (قرار المالك: النوع حرّ للإشارة، الهيمنة للخضراء)
        if green and v_n is not None:
            green_max = v_n if green_max is None else max(green_max, v_n)

    # المرجع النهائي للنطاق الأخير (ما زال حياً حتى نهاية النافذة)
    if ri >= 0:
        ranges[ri]["ref"] = live_ref

    # ------------------------------------------------------------------
    # 4) النطاق الحي الآن + مستوياته (للرسم الحي) — نظير current في الأصل
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
        }

    signals.sort(key=lambda s: s.get("bar", 0))

    _e2e_series: Dict[str, List[Optional[float]]] = {
        "zzfe_dir": s_dir, "zzfe_p1": s_p1, "zzfe_p2": s_p2,
        "zzfe_i1": s_i1, "zzfe_i2": s_i2,
        "zzfe_anchor": s_anchor, "zzfe_range_index": s_range_idx,
        **level_series,
        "zzfe_liq_state": liq_state,
        "zzfe_liq_ref_high": liq_ref_high,
        "zzfe_liq_ref_vol": liq_ref_vol,
        "zzfe_liq_vol_ok": liq_vol_ok,
        "zzfe_signal_s1": liq_s1,
        "zzfe_signal_s2": liq_s2,
        "zzfe_signal_s3": liq_s3,
        "zzfe_signal_any": liq_any,
        "zzfe_entry": e_entry,
        "zzfe_entry_s1": e_entry_s1,
        "zzfe_entry_s2": e_entry_s2,
        "zzfe_entry_s3": e_entry_s3,
    }

    return {
        "name": "ZigZag Fib E2E (ZLF-End-To-End — Range-anchored)",
        "engine": ZLF_E2E_ENGINE_NAME,
        "spec": ZLF_E2E_SPEC,
        # ✅ ROUND34 — المحرك الموحد: هوية النواة المشتركة (شفافية كاملة)
        "core": {"spec": ZIGZAG_FIB_CORE_SPEC, "version": ZIGZAG_FIB_CORE_VERSION},
        # علم تشخيصي: هل وصل الحجم للمحرك؟ بدون الحجم لا مرجع R ولا إشارات
        "volume_available": any(v is not None for v in vols),
        "params": {"mode": mode, "length": length, "reverse": reverse, "levels": lvls,
                   "extend_right": extend_right, "extend_leg_to_live": extend_leg_to_live,
                   "depth": depth, "deviation": deviation, "backstep": backstep,
                   "launch_user": ZLF_E2E_LAUNCH_USER,
                   "launch_touch_ticks": ZLF_E2E_LAUNCH_TOUCH_TICKS,
                   "inferred_tick": _tick},
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
        "series": _e2e_series,
        "liquidity": {
            "enabled": True,
            "engine": ZLF_E2E_ENGINE_NAME,
            "spec": ZLF_E2E_SPEC,
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
            ],
            "excluded_cell": "الخلية الرابعة (لا اختراق + حجم أقل) = لا إشارة عمداً (ضوضاء)",
            "volume_rule": "S1/S3: volume_G > volume_R · S2: volume_G ≤ volume_R (تقسيم بعلاقة الحجم مع الحمراء)",
            "entry_rule": "الدخول عند شمعة الإشارة نفسها (الحدث = الدخول؛ تقييم الإغلاق وتنفيذ الافتتاح التالي next_open) — لا خطة بديلة: النطاق لا يوجد قبل ظهور الزقزاق",
            "range_lifecycle": "النطاق يُستبدل عند أول تغيّر في زوج الزقزاق المرسوم (طرف جديد أو إحلال أقوى) — لحظتها = ميلاد النطاق الجديد وموتة السابق؛ الأزواج تتناوب قمة→قاع ثم قاع→قمة",
            "sfp_enabled": False,
        },
        "notes": "ZLF-End-To-End — استنساخ منفصل ذاتي الاكتفاء لمحرك zigzag_fib (الزقزاق منطقه حرفي) "
                 "مع إعادة بناء النطاق والإشارات فوق المواصفة المصادقة: النطاق = لحظة ظهور الزقزاق، "
                 "المرجع = أكبر حمراء داخل عمر النطاق الحي (من شمعة الظهور — ما قبلها ليس نطاقاً — ROUND26)، "
                 "نافذة الهيمنة = عمر النطاق الحي، الدخول بشمعة الحدث نفسها، ولا عدد شموع في أي تعريف. "
                 "عمودا ولادة النطاق: zzfe_anchor (1.0 عند شمعة الظهور) و zzfe_range_index (رقم النطاق الحي) "
                 "— لتلفيف خط بداية النطاق في شارت الباك تست والشارت الحي. "
                 "كل المخرجات بأسماء جديدة (zzfe_*/ind_zzfe_*/ZLF-E2E).",
    }


# ---------------------------------------------------------------------------
# التسجيل الذاتي كمؤشر منفصل — zigzag_fib_e2e (اسم جديد تماماً)
#    يُستورد مرة واحدة من app/services/indicators/__init__.py
# ---------------------------------------------------------------------------
def _register_e2e_indicator() -> None:
    try:
        from .base import BaseIndicator, IndicatorResult, IndicatorType
        from .registry import IndicatorRegistry
        import pandas as pd

        class ZigZagFibE2EIndicator(BaseIndicator):
            """ZLF-End-To-End — المحرك الموحد (النطاق = لحظة ظهور الزقزاق)."""

            @classmethod
            def get_required_columns(cls):
                return ["open", "high", "low", "close"]

            def calculate(self, data: pd.DataFrame) -> IndicatorResult:
                from .overlay_columns import config_to_overlay_params
                conv = config_to_overlay_params({
                    "name": "zigzag_fib_e2e",
                    "params": dict(self.params or {}),
                }) or {"zzfib_e2e": {}}
                params = conv.get("zzfib_e2e") or {}
                res = zigzag_fib_e2e(data, **params)
                values = res["series"].get("zzfe_entry") or [None] * len(data)
                series = pd.Series(values, index=data.index, dtype=object)
                return IndicatorResult(
                    name=self.name,
                    values=series,
                    signals=None,
                    metadata={
                        "engine": ZLF_E2E_ENGINE_NAME,
                        "overlay": "zzfib_e2e",
                        "primary_column": "ind_zzfe_entry",
                        "available_columns": sorted(res["series"].keys()),
                    },
                )

        IndicatorRegistry.register(
            "zigzag_fib_e2e",
            display_name="ZLF-End-To-End — ZigZag Fib (Range-anchored)",
            description="المحرك الموحد (ROUND34): النطاق يُعتمد لحظة ظهور الزقزاق والفيبو يُرسم عليه "
                        "بحدود كاملة (ولادة → نهاية)، المرجع = أكبر حمراء داخل عمر النطاق الحي، ثلاث حالات "
                        "S1/S2/S3 باسم ZLF-E2E. العمود الأساسي: ind_zzfe_entry.",
            category=IndicatorType.SUPPORT_RESISTANCE,
        )(ZigZagFibE2EIndicator)

        # مرادف قصير — نفس الفئة
        info = IndicatorRegistry._indicators.get("zigzag_fib_e2e")
        if info is not None:
            IndicatorRegistry._indicators.setdefault("zzfib_e2e", info)
    except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
        import logging
        logging.getLogger(__name__).exception("ZLF-E2E indicator registration failed")


_register_e2e_indicator()

# # =============================================================================
# # ✅ ROUND34 — ZLF-End-To-End فوق المحرك الموحد (لا محرك منفصل بعد اليوم)
# # =============================================================================
# # ⚠️ توجيه صاحب القرار (2026-11-05): «فاجعله موحد للجميع وكل استراتيجيه حسب
# #   اهتمامها» — أُلغي الاستنساخ الذاتي الاكتفاء (4 نسخ luxalgo + 3 نسخ TV):
# #   هذا الملف الآن طبقة سياسات رقيقة فوق zigzag_fib_core.py (المحرك الوحيد):
# #     · الزقزاق والفيبوناتشي والنطاقات تُحسب بالمحرك الموحد — نفس السلوك
# #       التاريخي المعتمد حرفياً (السلاسل والإشارات لم تتغير بايت-ببايت —
# #       مثبت بلقطة ذهبية قبل/بعد في evidence/).
# #     · ما يبقى هنا هو «اهتمام» استراتيجية E2E فقط: المصفوفة السيولية
# #       S1/S2/S3 والمرجع الحي R داخل عمر النطاق (ROUND26) والانطلاقة.
# #     · ✅ إصلاح جذر الرسومات العشوائية في شارت الباك تست: النسخة القديمة
# #       المستنسخة كانت تفشل في تحليل timestamp كسلسلة ISO (ترجع 0) — الآن
# #       التطبيع موحد عبر core.to_ms (دعم ISO كامل) فأزمنة الرسم صحيحة في
# #       كل المسارات (DataFrame الحي · ms · ثوانٍ · ISO).
# #     · ✅ ROUND34: كل نطاق في ranges[] يحمل الآن levels[] كاملة بحدود
# #       الرسم (تبدأ من خط الولادة anchor وتنتهي عند نهاية عمر النطاق) —
# #       «يجب أن يكون للفيبوناتشي نهاية كي لا يشوّه الشارت».
# #
# # --------------------------- المواصفة المصادقة (ZLF-End-To-End) --------------
# # (محفوظة حرفياً — لم يتغير أي سلوك استراتيجي)
# # 1) «النطاق = لحظة ظهور الزقزاق»: عند الشمعة التي جعلت الزقزاق يظهر
# #    (confirmed_at_bar؛ في وضع luxalgo length=100 = تأكيد بعد 100 شمعة)
# #    يُعتمد زوج الزقزاق المرسوم [الطرف الظاهر أولاً، الطرف الظاهر ثانياً]
# #    نطاقاً جديداً، يُرسم عليه الفيبو، ويبدأ حساب الاستراتيجية من تلك الشمعة.
# # 2) دورة الحياة: النطاق يُستبدل عند أول تغيّر في زوج الزقزاق المرسوم
# #    (طرف جديد أو إحلال أقوى) — لحظة التغيّر = ميلاد الجديد وموتة السابق.
# # 3) الفيبو يُرسم «من الطرف الظاهر أولاً إلى الطرف الظاهر ثانياً» — بمقياس
# #    المحرك price(level) = q1 + diff × level (خط 0.618 للمستخدم = price(0.382)).
# # 4) المرجع R = أكبر شمعة حمراء حجماً داخل عمر النطاق الحي نفسه (من شمعة
# #    الظهور شاملة حتى الجاري فحصه — ROUND26؛ عند التعادل الأحدث يفوز).
# # 5) نافذة «باقي الخضراء» = كل الخضراء داخل نافذة حياة النطاق الحي.
# # 6) المصفوفة: S1 اختراق∧حجم أكبر · S2 اختراق∧حجم أقل أو مساوٍ ·
# #    S3 رفض∧حجم أكبر · الرابعة = لا إشارة عمداً (ضوضاء).
# #    الشروط المشتركة: خضراء + انطلاقة من 0.618 (بمقياس المستخدم) + هيمنة.
# # 7) الدخول = شمعة الإشارة نفسها (next_open). 8) لا SFP.
# # 9) الخروج = انقلاب النطاق إلى هابطة (zzfe_dir < 0).
# # 10) عمودا ولادة النطاق: zzfe_anchor (1.0 عند الظهور) وzzfe_range_index.
# #
# # وضع الزقزاق: نفس الوضعين المعتمدين عبر المحرك الموحد — luxalgo length=100
# # (الافتراضي — وضع شارت المنصة المُتحقق بالبكسل) أو tradingview
# # depth/deviation/backstep (متاح — تغييره من القالب فقط بلا أي كود).
# # =============================================================================

# from __future__ import annotations

# from typing import Any, Dict, List, Optional, Sequence

# # ✅ ROUND34 — المحرك الموحد: المصدر الوحيد للزقزاق/الفيبو/التطبيع
# from app.services.indicators.zigzag_fib_core import (
#     ZIGZAG_FIB_CORE_SPEC,
#     ZIGZAG_FIB_CORE_VERSION,
#     build_ranges,
#     clean_float,
#     infer_price_tick,
#     level_tag,
#     norm_candles,
#     norm_volume,
#     range_levels_geometry,
#     range_public,
#     zigzag_detect,
# )

# __all__ = [
#     "zigzag_fib_e2e",
#     "ZLF_E2E_ENGINE_NAME",
#     "ZLF_E2E_DEFAULT_LEVELS",
#     "ZLF_E2E_LAUNCH_USER",
# ]

# # ---------------------------------------------------------------------------
# # هوية المحرك المنفصل (عقد التمايز — كل الأسماء مختلفة عن الأصل)
# # ---------------------------------------------------------------------------
# ZLF_E2E_ENGINE_NAME = "ZLF-End-To-End"
# ZLF_E2E_SPEC = "ROUND26-end-to-end"

# # مستويات الفيبو المرسومة (بمقياس المحرك 0..1 على المسار من الأول إلى الثاني).
# # تشمل 0.85415 = نظير مستوى 0.14585 (0.236×0.618) بمقياس رسم المستخدم
# # — الموجود على شارت المنصة — ليطابق الرسم الشارت حرفياً.
# ZLF_E2E_DEFAULT_LEVELS: List[float] = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 0.85415, 1.0]

# # خط الانطلاقة: «من 0.618 أو أعلى» بمقياس رسم المستخدم (1 عند الطرف الأول،
# # 0 عند الثاني) = price(0.382) بمقياس المحرك — المصادق بالبكسل على شارت
# # المنصة (63,011.6+0.382×720.9=63,287.0 و 53,223.5−0.382×3,668.4=51,822.2).
# ZLF_E2E_LAUNCH_USER: float = 0.618
# _ZLF_E2E_LAUNCH_ENGINE_LEVEL: float = 0.382

# # ✅ تسامح ملامسة خط الانطلاقة: «قاعها ملتصق بخط 0.618 نفسه» — الأسعار
# # مُكمّمة بتيك الرمز، فالقاع «الملتصق» قد يقع تيكاً واحداً تحت الخط المحسوب.
# # التسامح = تيك واحد مُستنتَج من البيانات نفسها. 0 = صرامة تامة.
# ZLF_E2E_LAUNCH_TOUCH_TICKS: float = 1.0


# # ---------------------------------------------------------------------------
# # المحرك الرئيسي — ZLF-End-To-End (طبقة سياسات فوق المحرك الموحد)
# # ---------------------------------------------------------------------------
# def zigzag_fib_e2e(
#     candles: Any,
#     length: int = 100,
#     reverse: bool = False,
#     levels: Optional[Sequence[float]] = None,
#     extend_right: bool = True,
#     extend_leg_to_live: bool = True,
#     mode: str = "luxalgo",
#     depth: int = 12,
#     deviation: float = 20.0,
#     backstep: int = 3,
#     launch_touch_ticks: float = ZLF_E2E_LAUNCH_TOUCH_TICKS,
# ) -> Dict[str, Any]:
#     """ZLF-End-To-End — النطاق يُعتمد لحظة ظهور الزقزاق (محرك موحد ROUND34).

#     المعاملات مطابقة للأصل (توافق مألوف): mode/length (luxalgo) · depth/
#     deviation/backstep (tradingview) · reverse/levels/extend_right/
#     extend_leg_to_live. لا liq_lookback ولا liq_arm_bars — التعريف لا يحتوي
#     أي عدد شموع: نافذة الحساب = عمر النطاق الحي.

#     المخرجات (كلها بأسماء عقد التمايز — لم تتغير):
#       series: zzfe_dir/p1/p2/i1/i2 · zzfe_level_<L> · zzfe_liq_state/
#               zzfe_liq_ref_high/zzfe_liq_ref_vol/zzfe_liq_vol_ok ·
#               zzfe_signal_s1/s2/s3/any · zzfe_entry · zzfe_entry_s1/s2/s3 ·
#               zzfe_anchor · zzfe_range_index
#       signals: "ZLF-E2E Liquidity S1|S2|S3" و "ZLF-E2E Entry S1|S2|S3"
#       ranges:  النطاقات المتعاقبة — أطرافها، لحظة الولادة (anchor)، لحظة
#                الوفاة (death)، مستوياتها (levels بحدود رسم كاملة: من خط
#                الولادة إلى نهاية العمر ✅ ROUND34)، مرجعها R، واتجاهها.
#       legs:    أرجل الزقزاق (عقد الرسم الموحد — الرسم بـ time).
#       current: النطاق الحي الآن + مستوياته الممتدة.
#     """
#     t, o, h, l, c = norm_candles(candles)
#     N = len(c)
#     length = max(2, int(length))
#     lvls = [float(x) for x in (levels if levels is not None else ZLF_E2E_DEFAULT_LEVELS)]
#     vols = norm_volume(candles)
#     if len(vols) != N:
#         vols = [None] * N

#     # ✅ استنتاج تيك الرمز من البيانات نفسها (أصغر فرق موجب بين مستويات فعلية)
#     _tick = infer_price_tick(o, h, l, c)
#     try:
#         _touch_tol = max(0.0, float(launch_touch_ticks)) * (_tick or 0.0)
#     except (TypeError, ValueError):
#         _touch_tol = 0.0

#     lv_keys = [(r, f"zzfe_level_{level_tag(r)}") for r in lvls]

#     # ------------------------------------------------------------------
#     # 1) الزقزاق الموحد — نقاط مؤكدة + أرجل + سجل تغيّرات الزوج (pair_events)
#     #    (وضعان: luxalgo/tradingview — نفس السلوك التاريخي حرفياً)
#     # ------------------------------------------------------------------
#     zz = zigzag_detect(
#         t, o, h, l, c, N,
#         mode=mode, length=length, depth=depth, deviation=deviation,
#         backstep=backstep, reverse=reverse, lv_keys=lv_keys,
#         want_series=False,
#     )
#     confirmed = zz["confirmed"]
#     legs = zz["legs"]
#     pair_events = zz["pair_events"]

#     # ✅ ROUND39 (طلب وكيل الفرونت ج38-1أ): محاور الزقزاق المؤكدة عقد رسم
#     # موحد مع legs — نفس نقاط النواة حرفياً (صفر اشتقاق/اختراع): كل محور
#     # {bar, time, price, kind, confirmed_at_bar} وأطراف الساقات المتتالية
#     # تتشاركها (legs[k].x2 == legs[k+1].x1).
#     pivots: List[Dict[str, Any]] = [
#         {
#             "bar": int(p["bar"]),
#             "time": t[int(p["bar"])] if 0 <= int(p["bar"]) < N else None,
#             "price": clean_float(p["price"]),
#             "kind": p["kind"],
#             "confirmed_at_bar": int(p["confirmed_at_bar"]),
#         }
#         for p in confirmed
#     ]

#     # ------------------------------------------------------------------
#     # 2) النطاقات المتعاقبة من سجل تغيّرات الزوج — موحّدة بالمحرك core
#     #    (الولادة = لحظة ظهور الزقزاق anchor · الموت = ولادة التالي)
#     # ------------------------------------------------------------------
#     ranges = build_ranges(pair_events, t, N, reverse, _ZLF_E2E_LAUNCH_ENGINE_LEVEL)

#     # ------------------------------------------------------------------
#     # 3) المسح الزمني السببي — سلاسل النطاق الحي + المصفوفة المصادقة
#     # ------------------------------------------------------------------
#     s_dir: List[float] = [0.0] * N
#     s_p1: List[Optional[float]] = [None] * N
#     s_p2: List[Optional[float]] = [None] * N
#     s_i1: List[Optional[float]] = [None] * N
#     s_i2: List[Optional[float]] = [None] * N
#     level_series: Dict[str, List[Optional[float]]] = {key: [None] * N for _r, key in lv_keys}

#     liq_state: List[float] = [0.0] * N
#     liq_ref_high: List[Optional[float]] = [None] * N
#     liq_ref_vol: List[Optional[float]] = [None] * N
#     liq_vol_ok: List[float] = [0.0] * N
#     # عمودا ولادة النطاق (ROUND26) — نقطة بداية النطاق للشارتين:
#     s_anchor: List[float] = [0.0] * N
#     s_range_idx: List[float] = [-1.0] * N
#     liq_s1: List[float] = [0.0] * N
#     liq_s2: List[float] = [0.0] * N
#     liq_s3: List[float] = [0.0] * N
#     liq_any: List[float] = [0.0] * N
#     e_entry: List[float] = [0.0] * N
#     e_entry_s1: List[float] = [0.0] * N
#     e_entry_s2: List[float] = [0.0] * N
#     e_entry_s3: List[float] = [0.0] * N
#     signals: List[Dict[str, Any]] = []

#     ri = -1
#     green_max: Optional[float] = None   # أكبر حجم أخضر داخل نافذة النطاق الحي حتى الشمعة السابقة
#     live_ref: Optional[Dict[str, Any]] = None   # المرجع الحي داخل عمر النطاق (يبدأ None عند الولادة)
#     n_events = 0
#     for i in range(N):
#         # تقدّم إلى النطاق الذي ظهر عند هذه الشمعة أو قبلها (الميلاد = الظهور)
#         while ri + 1 < len(ranges) and ranges[ri + 1]["anchor"] <= i:
#             if ri >= 0:
#                 ranges[ri]["ref"] = live_ref   # المرجع النهائي لعمر النطاق المنتهي
#             ri += 1
#             green_max = None   # نافذة حياة جديدة — تصفير هيمنة الخضراء
#             live_ref = None    # نافذة حياة جديدة — المرجع يبدأ من الصفر
#         if ri < 0:
#             continue
#         r = ranges[ri]

#         # --- سلاسل النطاق الحي (تُكتب عند كل شمعة من عمره) ---
#         s_dir[i] = float(r["dir"])
#         s_p1[i] = clean_float(r["p1"]["price"])
#         s_p2[i] = clean_float(r["p2"]["price"])
#         s_i1[i] = float(r["p1"]["bar"])
#         s_i2[i] = float(r["p2"]["bar"])
#         s_anchor[i] = 1.0 if i == int(r["anchor"]) else 0.0
#         s_range_idx[i] = float(r["index"])
#         for rr, key in lv_keys:
#             level_series[key][i] = clean_float(r["p1"]["price"] + r["diff"] * rr)

#         o_n, c_n = clean_float(o[i]), clean_float(c[i])
#         hi_n, lo_n = clean_float(h[i]), clean_float(l[i])
#         v_n = clean_float(vols[i]) if i < len(vols) else None
#         green = (c_n is not None and o_n is not None and c_n > o_n)

#         # المرجع الحي داخل عمر النطاق: كل حمراء (بحجم) من شمعة الولادة
#         # حتى الجاري فحصه مرشحة؛ الأكبر حجماً يفوز (والأحدث عند التعادل).
#         if c_n is not None and o_n is not None and c_n < o_n and v_n is not None:
#             if live_ref is None or v_n >= live_ref["vol"]:
#                 live_ref = {"bar": i, "time": t[i], "high": hi_n, "vol": v_n}

#         ref = live_ref
#         if ref is not None:
#             liq_ref_high[i] = clean_float(ref["high"])
#             liq_ref_vol[i] = clean_float(ref["vol"])

#         if ref is not None and v_n is not None:
#             liq_vol_ok[i] = 1.0 if v_n > ref["vol"] else 0.0

#         # --- المصفوفة المصادقة (تقسيم كامل بعلاقة الحجم مع الحمراء) ---
#         cell = 0
#         if green and v_n is not None and hi_n is not None and lo_n is not None \
#                 and ref is not None and not r["degenerate"] and r["launch"] is not None:
#             breakout = hi_n > ref["high"]
#             vol_dom = v_n > ref["vol"]
#             dominance = (green_max is None) or (v_n > green_max)
#             # «من 0.618 أو أعلى» + «قاعها ملتصق بالخط» — ملامسة التيك الواحد مسموحة
#             launch_ok = lo_n >= (r["launch"] - _touch_tol)
#             if breakout and vol_dom:
#                 cell = 1
#             elif breakout:
#                 cell = 2
#             elif vol_dom:
#                 cell = 3
#             if cell and not (launch_ok and dominance):
#                 cell = 0   # الشروط المشتركة غير مكتملة → لا إشارة
#         if cell:
#             liq_state[i] = float(cell)
#             liq_any[i] = 1.0
#             n_events += 1
#             sig_cols = {1: liq_s1, 2: liq_s2, 3: liq_s3}
#             ent_cols = {1: e_entry_s1, 2: e_entry_s2, 3: e_entry_s3}
#             sig_cols[cell][i] = 1.0
#             anchor_bar = r["anchor"]
#             signals.append({
#                 "bar": i, "time": t[i], "side": "liquidity",
#                 "signal": f"ZLF-E2E Liquidity S{cell}",
#                 "engine": ZLF_E2E_ENGINE_NAME,
#                 "states": [cell], "state": float(cell),
#                 "range_index": r["index"],
#                 "range_anchor": {"bar": anchor_bar, "time": r["anchor_time"]},
#                 "range_p1": {"bar": r["p1"]["bar"],
#                              "time": t[r["p1"]["bar"]] if 0 <= r["p1"]["bar"] < N else None,
#                              "price": clean_float(r["p1"]["price"]), "kind": r["p1"]["kind"]},
#                 "range_p2": {"bar": r["p2"]["bar"],
#                              "time": t[r["p2"]["bar"]] if 0 <= r["p2"]["bar"] < N else None,
#                              "price": clean_float(r["p2"]["price"]), "kind": r["p2"]["kind"]},
#                 "ref_high": clean_float(ref["high"]), "ref_vol": clean_float(ref["vol"]),
#                 "ref_bar": ref["bar"], "ref_time": ref["time"],
#                 "launch_line": r["launch"],
#                 "price": hi_n if cell in (1, 2) else c_n,
#                 "volume": v_n,
#             })
#             # الدخول = شمعة الإشارة نفسها (الحدث = الدخول) — تنفيذ next_open في الباك
#             e_entry[i] = 1.0
#             ent_cols[cell][i] = 1.0
#             signals.append({
#                 "bar": i, "time": t[i], "side": "buy",
#                 "signal": f"ZLF-E2E Entry S{cell}",
#                 "engine": ZLF_E2E_ENGINE_NAME,
#                 "states": [cell],
#                 "range_index": r["index"],
#                 "price": c_n, "launch_line": r["launch"],
#                 "fallback": False, "color": "#28cc95",
#             })

#         # تحديث هيمنة الخضراء بعد فحص الشمعة (لا تشمل G نفسها)
#         if green and v_n is not None:
#             green_max = v_n if green_max is None else max(green_max, v_n)

#     # المرجع النهائي للنطاق الأخير (ما زال حياً حتى نهاية النافذة)
#     if ri >= 0:
#         ranges[ri]["ref"] = live_ref

#     # ------------------------------------------------------------------
#     # 4) النطاق الحي الآن + مستوياته (للرسم الحي) — نظير current في الأصل
#     # ------------------------------------------------------------------
#     current: Optional[Dict[str, Any]] = None
#     if ranges:
#         r = ranges[-1]
#         last_bar = N - 1
#         lv = range_levels_geometry(r, t, N, lvls, extend_right)
#         current = {
#             "range": range_public(r, t, N),
#             "levels": lv,
#             "launch_line": r["launch"],
#             "p1": clean_float(r["p1"]["price"]), "p2": clean_float(r["p2"]["price"]),
#             "dir": float(r["dir"]),
#             "i1": r["p1"]["bar"], "i2": r["p2"]["bar"],
#             "live_extension": {
#                 "enabled": extend_leg_to_live,
#                 "x1": r["p2"]["bar"], "t1": t[r["p2"]["bar"]] if 0 <= r["p2"]["bar"] < N else None,
#                 "y1": clean_float(r["p2"]["price"]),
#                 "x2": last_bar, "t2": t[last_bar], "y2": clean_float(c[last_bar]),
#             },
#         }

#     signals.sort(key=lambda s: s.get("bar", 0))

#     _e2e_series: Dict[str, List[Optional[float]]] = {
#         "zzfe_dir": s_dir, "zzfe_p1": s_p1, "zzfe_p2": s_p2,
#         "zzfe_i1": s_i1, "zzfe_i2": s_i2,
#         "zzfe_anchor": s_anchor, "zzfe_range_index": s_range_idx,
#         **level_series,
#         "zzfe_liq_state": liq_state,
#         "zzfe_liq_ref_high": liq_ref_high,
#         "zzfe_liq_ref_vol": liq_ref_vol,
#         "zzfe_liq_vol_ok": liq_vol_ok,
#         "zzfe_signal_s1": liq_s1,
#         "zzfe_signal_s2": liq_s2,
#         "zzfe_signal_s3": liq_s3,
#         "zzfe_signal_any": liq_any,
#         "zzfe_entry": e_entry,
#         "zzfe_entry_s1": e_entry_s1,
#         "zzfe_entry_s2": e_entry_s2,
#         "zzfe_entry_s3": e_entry_s3,
#     }

#     return {
#         "name": "ZigZag Fib E2E (ZLF-End-To-End — Range-anchored)",
#         "engine": ZLF_E2E_ENGINE_NAME,
#         "spec": ZLF_E2E_SPEC,
#         # ✅ ROUND34 — المحرك الموحد: هوية النواة المشتركة (شفافية كاملة)
#         "core": {"spec": ZIGZAG_FIB_CORE_SPEC, "version": ZIGZAG_FIB_CORE_VERSION},
#         # علم تشخيصي: هل وصل الحجم للمحرك؟ بدون الحجم لا مرجع R ولا إشارات
#         "volume_available": any(v is not None for v in vols),
#         "params": {"mode": mode, "length": length, "reverse": reverse, "levels": lvls,
#                    "extend_right": extend_right, "extend_leg_to_live": extend_leg_to_live,
#                    "depth": depth, "deviation": deviation, "backstep": backstep,
#                    "launch_user": ZLF_E2E_LAUNCH_USER,
#                    "launch_touch_ticks": ZLF_E2E_LAUNCH_TOUCH_TICKS,
#                    "inferred_tick": _tick},
#         "legs": legs,
#         # ✅ ROUND39 (طلبات وكيل الفرونت ج38): pivots[] (طلب 1-أ — نفس محاور
#         # النواة) + window (طلب 3 — هوية النافذة للمطابقة السريعة بالفهارس).
#         "pivots": pivots,
#         "window": {"bars": N, "time_from": t[0] if N else None,
#                    "time_to": t[N - 1] if N else None},
#         # ✅ ROUND34: كل نطاق يحمل levels[] بحدود رسم كاملة (ولادة → نهاية)
#         "ranges": [range_public(r, t, N, lvls, extend_right) for r in ranges],
#         "current": current,
#         "signals": signals,
#         "series": _e2e_series,
#         "liquidity": {
#             "enabled": True,
#             "engine": ZLF_E2E_ENGINE_NAME,
#             "spec": ZLF_E2E_SPEC,
#             "events": n_events,
#             "volume_available": any(v is not None for v in vols),
#             "volume_missing_warning": (
#                 None if any(v is not None for v in vols)
#                 else "لم يصل عمود الحجم للمحرك — لا يمكن بناء المرجع R ولا تصنيف S1/S2/S3 "
#                      "(تحقق من مصدر الشموع في المسار المستدعي: يجب تمرير volume مع كل شمعة)"
#             ),
#             "reference_rule": "R = أكبر شمعة حمراء (close<open) حجماً داخل عمر النطاق الحي (من شمعة ظهور الزقزاق "
#                               "إلى الشمعة الجاري فحصها — كل ما قبل الظهور ليس نطاقاً) ويتحدّث لحظياً مع كل حمراء أكبر "
#                               "(عند التعادل: الأحدث يفوز) — ref_high = قمة هذه الشمعة نفسها · لا حمراء في العمر بعد → لا مرجع",
#             "states": {
#                 "1": "S1 — الاختراق الكامل المؤكد: خضراء + انطلاقة من 0.618 أو أعلى + اختراق قمة الحمراء + حجم أكبر من الحمراء",
#                 "2": "S2 — الاختراق بدون هيمنة الحجم: خضراء + انطلاقة + اختراق القمة + حجم أقل أو مساوٍ للحمراء («ويبرغم عندها لفل حجم سيولتها»)",
#                 "3": "S3 — الامتصاص قبل الاختراق: خضراء + انطلاقة + بلا اختراق للقمة + حجم أكبر من الحمراء",
#             },
#             "common_conditions": [
#                 "النطاق يُعتمد لحظة ظهور الزقزاق (شمعتها تأكيداً) — الحساب يبدأ من شمعة الظهور",
#                 "الفيبو يُرسم من الطرف الظاهر أولاً (1) إلى الطرف الظاهر ثانياً (0) — خط 0.618 للمستخدم = price(0.382) بمقياس المحرك",
#                 "الانطلاقة: low_G ≥ خط 0.618 بمقياس رسم المستخدم",
#                 "هيمنة الخضراء: volume_G > حجم كل الشموع الخضراء داخل نافذة حياة النطاق الحي قبل شمعة الإشارة",
#                 "لا عدد شموع في التعريف — النافذة = عمر النطاق (من الظهور حتى ظهور الزوج التالي)",
#             ],
#             "excluded_cell": "الخلية الرابعة (لا اختراق + حجم أقل) = لا إشارة عمداً (ضوضاء)",
#             "volume_rule": "S1/S3: volume_G > volume_R · S2: volume_G ≤ volume_R (تقسيم بعلاقة الحجم مع الحمراء)",
#             "entry_rule": "الدخول عند شمعة الإشارة نفسها (الحدث = الدخول؛ تقييم الإغلاق وتنفيذ الافتتاح التالي next_open) — لا خطة بديلة: النطاق لا يوجد قبل ظهور الزقزاق",
#             "range_lifecycle": "النطاق يُستبدل عند أول تغيّر في زوج الزقزاق المرسوم (طرف جديد أو إحلال أقوى) — لحظتها = ميلاد النطاق الجديد وموتة السابق؛ الأزواج تتناوب قمة→قاع ثم قاع→قمة",
#             "sfp_enabled": False,
#         },
#         "notes": "ZLF-End-To-End — استنساخ منفصل ذاتي الاكتفاء لمحرك zigzag_fib (الزقزاق منطقه حرفي) "
#                  "مع إعادة بناء النطاق والإشارات فوق المواصفة المصادقة: النطاق = لحظة ظهور الزقزاق، "
#                  "المرجع = أكبر حمراء داخل عمر النطاق الحي (من شمعة الظهور — ما قبلها ليس نطاقاً — ROUND26)، "
#                  "نافذة الهيمنة = عمر النطاق الحي، الدخول بشمعة الحدث نفسها، ولا عدد شموع في أي تعريف. "
#                  "عمودا ولادة النطاق: zzfe_anchor (1.0 عند شمعة الظهور) و zzfe_range_index (رقم النطاق الحي) "
#                  "— لتلفيف خط بداية النطاق في شارت الباك تست والشارت الحي. "
#                  "كل المخرجات بأسماء جديدة (zzfe_*/ind_zzfe_*/ZLF-E2E).",
#     }


# # ---------------------------------------------------------------------------
# # التسجيل الذاتي كمؤشر منفصل — zigzag_fib_e2e (اسم جديد تماماً)
# #    يُستورد مرة واحدة من app/services/indicators/__init__.py
# # ---------------------------------------------------------------------------
# def _register_e2e_indicator() -> None:
#     try:
#         from .base import BaseIndicator, IndicatorResult, IndicatorType
#         from .registry import IndicatorRegistry
#         import pandas as pd

#         class ZigZagFibE2EIndicator(BaseIndicator):
#             """ZLF-End-To-End — المحرك الموحد (النطاق = لحظة ظهور الزقزاق)."""

#             @classmethod
#             def get_required_columns(cls):
#                 return ["open", "high", "low", "close"]

#             def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#                 from .overlay_columns import config_to_overlay_params
#                 conv = config_to_overlay_params({
#                     "name": "zigzag_fib_e2e",
#                     "params": dict(self.params or {}),
#                 }) or {"zzfib_e2e": {}}
#                 params = conv.get("zzfib_e2e") or {}
#                 res = zigzag_fib_e2e(data, **params)
#                 values = res["series"].get("zzfe_entry") or [None] * len(data)
#                 series = pd.Series(values, index=data.index, dtype=object)
#                 return IndicatorResult(
#                     name=self.name,
#                     values=series,
#                     signals=None,
#                     metadata={
#                         "engine": ZLF_E2E_ENGINE_NAME,
#                         "overlay": "zzfib_e2e",
#                         "primary_column": "ind_zzfe_entry",
#                         "available_columns": sorted(res["series"].keys()),
#                     },
#                 )

#         IndicatorRegistry.register(
#             "zigzag_fib_e2e",
#             display_name="ZLF-End-To-End — ZigZag Fib (Range-anchored)",
#             description="المحرك الموحد (ROUND34): النطاق يُعتمد لحظة ظهور الزقزاق والفيبو يُرسم عليه "
#                         "بحدود كاملة (ولادة → نهاية)، المرجع = أكبر حمراء داخل عمر النطاق الحي، ثلاث حالات "
#                         "S1/S2/S3 باسم ZLF-E2E. العمود الأساسي: ind_zzfe_entry.",
#             category=IndicatorType.SUPPORT_RESISTANCE,
#         )(ZigZagFibE2EIndicator)

#         # مرادف قصير — نفس الفئة
#         info = IndicatorRegistry._indicators.get("zigzag_fib_e2e")
#         if info is not None:
#             IndicatorRegistry._indicators.setdefault("zzfib_e2e", info)
#     except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
#         import logging
#         logging.getLogger(__name__).exception("ZLF-E2E indicator registration failed")


# _register_e2e_indicator()
