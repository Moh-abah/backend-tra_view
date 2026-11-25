# =============================================================================
# ✅ QUANTUM1 — ZLF-End-To-End-Trendy-Quantum «الاستراتيجية الترندية الكمومية»
# =============================================================================
# مواصفة صاحب القرار: الترندية بحذافيرها (زقزاق/فيبو/نطاقات/سيولة/ترند +
# المصفوفة S1/S2/S3 + بوابة الترند) + **بوابة المنطقة الكمومية** فوق إشارات
# الدخول: زقزاق مؤكد HH+HL يفتح منطقة الدخول المسموحة، وLL+LH يغلقها
# ويُخرج أي صفقة مفتوحة (next_open).
#
# ✅ إصلاح هذه النسخة (بيانات الرسم الكاملة): المحرك الآن يُرجع في سلاسله
#   عقدَي التمايز معاً — أعمدة zzfetq_* الكمية (62) **وأعمدة zzfet_*
#   الترندية الأصلية (47) ممرَّرة حرفياً** (زقزاق p1/p2/dir/i1/i2/anchor/
#   range_index · فيبو level_* بحدود رسمها · خطوط الترند tr_p* · السيولة
#   liq_* · الإشارات signals · الترند trend_*) — فيصل الشارت كل ما كانت
#   الترندية ترجعه بحذافيره، بالقيم نفسها بت-بت، **بالإضافة إلى بيانات
#   الكمومية نفسها** (المنطقة والبوابة والشفافية الرباعية).
#
# البنية (طبقة سياسات رقيقة فوق المحرك الترندي — لا استنساخ):
#   1) يُحسب المحرك الترندي zigzag_fib_e2e_trendy حرفياً (نفس المعاملات)
#      → كل أعمدته تُمرَّر كما هي (عقد zzfet_*) + تُنسخ بمرايا zzfetq_*.
#   2) منطق المنطقة يُبنى من محاور الزقزاق المؤكدة (pivots) — عند كل
#      محور (confirmed_at_bar): قارن بسابقه من نفس النوع:
#        قمة > قمة سابقة → hh · قمة < → lh · قاع > → hl · قاع < → ll
#      حالة كل نوع (صاعد/هابط) تنعش آخر مقارنة، والبنية المجمعة:
#        zone_struct = +1 (الاثنان صاعدان) · −1 (الاثنان هابطان) · 0 (مختلط)
#      آلة المنطقة: HH+HL → zone_on=1 (zone_enter) · LL+LH → zone_on=0
#      (zone_exit) — الأحداث على شمعة المحور المكمِّل للزوج.
#   3) البوابة الرباعية على الدخول (شفافية كاملة):
#        zzfetq_entry_raw_s{n}   = خام (من الترندية كما هو)
#        zzfetq_entry_blocked_s{n} = منعه الترند (من الترندية كما هو)
#        zzfetq_entry_s{n}        = خام ∧ ترند موافق ∧ المنطقة مفتوحة (نهائي)
#        zzfetq_entry_zblocked_s{n} = خام ∧ ترند موافق ∧ المنطقة مغلقة
#      zone_gate: [s1,s2,s3] افتراضياً · "none" = تعطيل بوابة المنطقة
#      (بيانات المنطقة تظل تُحتسب وتُرجع — شفافية بنائية مثل trend_gate).
#
# العقد: كل الأسماء الجديدة zzfetq_* → ind_zzfetq_* لا تتداخل مع zzfet_*
# (الترندية) ولا zzfe_*/zzf_*/trf_*/zzfb_*/zzfetm_*/zzfbm_*.
# عقد الرسم: نفس عقد الترندية (legs/pivots/ranges/levels بحدود ولادة→موت)
# + قسم zone (حالة المنطقة وأحداثها وأعلامها).
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# المحرك الموحد (المصدر الوحيد للزقزاق/الفيبو/التطبيع) + المحرك الترندي
from app.services.indicators.zigzag_fib_core import (
    ZIGZAG_FIB_CORE_SPEC,
    ZIGZAG_FIB_CORE_VERSION,
    clean_float,
    norm_candles,
)
from app.services.indicators.overlays_zlf_e2e_trendy import (
    ZLF_E2E_TRENDY_ENGINE_NAME,
    ZLF_E2E_TRENDY_SPEC,
    ZLF_E2E_TRENDY_DEFAULT_PERIODS,
    zigzag_fib_e2e_trendy,
)
# ✅ ZONE-EXIT-TF1 — فريم هيكل الخروج (CHoCH على أي فريم)
from app.services.indicators.overlays_zone_exit_mtf import (
    ZONE_EXIT_TF_SPEC,
    compute_zone_exit_mtf,
    norm_zone_exit_resolution,
)
# ✅ ZONE-ENTRY-MTF1 — فريم المنطقة المسموحة للدخول (HH+HL على أي فريم):
# بناء شموع الفريم المستقل + الإسقاط السببي — نفس نواة MTFEMA1 المثبتة
# (لا استيراد دائري: overlays_mtf_ema لا يستورد شيئًا من حزمة المؤشرات
# على مستوى الوحدة).
from app.services.indicators.overlays_mtf_ema import (
    _build_htf_bars,
    _norm_candles_arrays,
    _parse_resolution,
)

__all__ = [
    "zigzag_fib_e2e_trendy_quantum",
    "ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME",
    "ZLF_E2E_TRENDY_QUANTUM_SPEC",
    "ZLF_E2E_TRENDY_QUANTUM_DEFAULT_ZONE_GATE",
    "ZONE_ENTRY_MTF_SPEC",
    "norm_zone_entry_resolution",
]

# ---------------------------------------------------------------------------
# هوية المحرك المنفصل (عقد التمايز الكامل)
# ---------------------------------------------------------------------------
ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME = "ZLF-End-To-End-Trendy-Quantum"
ZLF_E2E_TRENDY_QUANTUM_SPEC = "QUANTUM1-e2e-trendy-quantum"

# بوابة المنطقة الافتراضية: الثلاثة كلها (وقوعة احتياطية عند الاستدعاء بلا
# معاملات — المرجع المعتمد يعيش في بريسِت الاستراتيجية، لا أرقام داخل الكود)
ZLF_E2E_TRENDY_QUANTUM_DEFAULT_ZONE_GATE: Tuple[str, ...] = ("s1", "s2", "s3")

# ✅ ZONE-ENTRY-MTF1 — مواصفة فريم المنطقة المسموحة للدخول (HH+HL على أي
# فريم). فارغ/«none»/«base»/«chart» = فريم الشارت (السلوك التاريخي بت-بت).
ZONE_ENTRY_MTF_SPEC = "ZONE-ENTRY-MTF1-entry-zone-timeframe"

# القيم المفسَّرة كـ «معطَّل» — نفس عقد ZONE-EXIT-TF1 حرفياً
_ZONE_ENTRY_DISABLED_TOKENS = {
    "", "none", "off", "false", "0", "no", "base", "chart", "current", "same",
}


_ZONE_GATE_KIND = {"s1": 1, "1": 1, "s2": 2, "2": 2, "s3": 3, "3": 3}


def _norm_zone_gate(raw: Any) -> List[int]:
    """تطبيع أنواع الإشارات المبوّبة بالمنطقة — يقبل s1/s2/s3 أو 1/2/3 بأي صيغة.

    None            = البوابة على الثلاثة كلها (الافتراضي).
    «none»/«off»    = بوابة الدخول معطلة كلياً (مفتاح عزل A/B — بيانات المنطقة
                     تظل تُحتسب وتُرجع كما يظل trend_ok محسوباً مع trend_gate=none).
    قائمة فارغة/قيم غير معروفة = معطلة كلياً أيضاً.
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
        if s in _ZONE_GATE_KIND:
            out.add(_ZONE_GATE_KIND[s])
    return sorted(out)


def norm_zone_entry_resolution(raw: Any) -> Optional[str]:
    """✅ ZONE-ENTRY-MTF1 — تطبيع فريم المنطقة المسموحة للدخول.

    يرجع None عند التعطيل (السلوك التاريخي بت-بت على فريم الشارت).
    يقبل كل صيغ فريمات Pine/الواجهة («60»/«1h»/«240»/«4h»/«1D»/«1W»/«1M»...)
    عبر _parse_resolution نفسها التي تستخدمها رصة EMA. القيم الفارغة
    والمرادفات الصريحة للتعطيل («none»/«off»/«base»/«chart»...) ترجع None.
    (نفس عقد norm_zone_exit_resolution حرفياً.)
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        # قيمة منطقية ليست فريماً — التعطيل الآمن (السلوك التاريخي)
        return None
    s = str(raw).strip()
    if s.lower() in _ZONE_ENTRY_DISABLED_TOKENS:
        return None
    return s


def _zone_entry_machine_on_pivots(
    pivots: List[Dict[str, Any]],
    n_bars: int,
) -> Dict[str, List[Any]]:
    """آلة المنطقة الكمية على محاور الفريم المستقل — نسخة حرفية من منطق
    الكمومية على فريم الشارت، تُخرج كل أعمدة الحالة (لا الأعلام فقط).

    المخرجات (كلها بأطوال n_bars):
      on/struct          : حالة المنطقة والبنية (استمرائية)
      enter/exit         : أعلام أحداث الفتح/الإغلاق (لمرة واحدة)
      hh/hl/lh/ll        : أعلام مقارنات المحاور (لمرة واحدة)
      last_high/prev_high/last_low/prev_low : قيم آخر/سابق قمة/قاع
    """
    m_last_high: List[Any] = [None] * n_bars
    m_prev_high: List[Any] = [None] * n_bars
    m_last_low: List[Any] = [None] * n_bars
    m_prev_low: List[Any] = [None] * n_bars
    m_hh: List[float] = [0.0] * n_bars
    m_hl: List[float] = [0.0] * n_bars
    m_lh: List[float] = [0.0] * n_bars
    m_ll: List[float] = [0.0] * n_bars
    m_on: List[float] = [0.0] * n_bars
    m_struct: List[float] = [0.0] * n_bars
    m_enter: List[float] = [0.0] * n_bars
    m_exit: List[float] = [0.0] * n_bars

    last_high: Optional[float] = None
    last_low: Optional[float] = None
    prev_high: Optional[float] = None
    prev_low: Optional[float] = None
    high_state: Optional[float] = None
    low_state: Optional[float] = None
    zone_on = False
    zone_struct = 0.0

    pi = 0
    for j in range(n_bars):
        while pi < len(pivots) and int(pivots[pi]["confirmed_at_bar"]) <= j:
            p = pivots[pi]
            pi += 1
            price = clean_float(p.get("price"))
            kind = str(p.get("kind") or "")
            if price is None:
                continue
            if kind in ("top", "high"):
                prev_high = last_high
                last_high = price
                if prev_high is not None:
                    up = price > prev_high
                    high_state = 1.0 if up else -1.0
                    if up:
                        m_hh[j] = 1.0
                    else:
                        m_lh[j] = 1.0
            else:
                prev_low = last_low
                last_low = price
                if prev_low is not None:
                    up = price > prev_low
                    low_state = 1.0 if up else -1.0
                    if up:
                        m_hl[j] = 1.0
                    else:
                        m_ll[j] = 1.0
            both_up = high_state == 1.0 and low_state == 1.0
            both_down = high_state == -1.0 and low_state == -1.0
            zone_struct = 1.0 if both_up else (-1.0 if both_down else 0.0)
            if both_up and not zone_on:
                zone_on = True
                m_enter[j] = 1.0
            elif both_down and zone_on:
                zone_on = False
                m_exit[j] = 1.0
        m_last_high[j] = clean_float(last_high)
        m_prev_high[j] = clean_float(prev_high)
        m_last_low[j] = clean_float(last_low)
        m_prev_low[j] = clean_float(prev_low)
        m_on[j] = 1.0 if zone_on else 0.0
        m_struct[j] = zone_struct

    return {
        "on": m_on, "struct": m_struct,
        "enter": m_enter, "exit": m_exit,
        "hh": m_hh, "hl": m_hl, "lh": m_lh, "ll": m_ll,
        "last_high": m_last_high, "prev_high": m_prev_high,
        "last_low": m_last_low, "prev_low": m_prev_low,
    }


def _compute_zone_entry_mtf(
    candles: Any,
    resolution: str,
    length: int,
    reverse: bool = False,
    levels: Optional[Any] = None,
    extend_right: bool = True,
    extend_leg_to_live: bool = True,
    mode: str = "luxalgo",
    depth: int = 12,
    deviation: float = 20.0,
    backstep: int = 3,
    launch_touch_ticks: float = 1.0,
) -> Optional[Dict[str, Any]]:
    """✅ ZONE-ENTRY-MTF1 — المنطقة المسموحة للدخول على فريم مستقل، سببية كاملة.

    نفس أنماط compute_zone_exit_mtf المثبتة (ZONE-EXIT-TF1) بت-بت:
      1) شموع الفريم المستقل: أعلى من الشارت تُبنى من شموع القاعدة
         (_build_htf_bars) · أدق من الشارت تُؤخذ حقيقية من سياق الباك-تست
         (set_zone_exit_ltf_context — نفس السياق المسجل لمحرك الباك-تست).
      2) محرك الزقزاق الترندي على شموع الفريم المستقل → محاور مؤكدة.
      3) آلة المنطقة الكمية نفسها حرفياً على تلك المحاور (كل أعمدة الحالة).
      4) الإسقاط السببي على شموع القاعدة: الحالة تُقرأ من آخر شريط مستقل
         مُغلق فقط (الشريط النامي لا يُرى) · الأعلام/الأحداث لمرة واحدة عند
         أول شمعة قاعدة إغلاقها ≥ إغلاق شمعة الفريم المستقل التي أكدتها.

    يرجع None عند فشل دفاعي (السلوك التاريخي يسود — لا كسر أبداً).
    """
    try:
        t, o, h, l, c = _norm_candles_arrays(candles)
    except Exception:
        return None
    N = int(t.size)
    if N == 0:
        return None

    # خطوة شمعة القاعدة (متينة أمام فجوات البيانات — نفس عقد MTFEMA1)
    if N > 1:
        diffs = np.diff(t)
        pos = diffs[diffs > 0]
        base_step = int(pos.min()) if pos.size else 60_000
    else:
        base_step = 60_000

    res_info = _parse_resolution(resolution)

    # فريم أدق من الشارت: سياق بيانات حقيقية أو التقييد الدفاعي (نفس عقد
    # ZONE-EXIT-LTF1 — محرك الباك-تست يسجل كليهما في نفس السياق).
    htf_step = res_info.get("step_ms")
    clamped = False
    ltf_ctx: Optional[Any] = None
    if res_info["kind"] == "fixed" and htf_step is not None and htf_step < base_step:
        try:
            from app.services.indicators.overlays_zone_exit_mtf import _ltf_context_for
            ltf_ctx = _ltf_context_for(res_info["label"])
        except Exception:
            ltf_ctx = None
        if ltf_ctx is None:
            htf_step = base_step
            res_info = dict(res_info, step_ms=base_step)
            clamped = True

    # 1) شموع الفريم المستقل
    if ltf_ctx is not None:
        try:
            lt, lo, lh, llo, lc = _norm_candles_arrays(ltf_ctx)
        except Exception:
            return None
        M = int(lt.size)
        if M == 0:
            return None
        if M > 1:
            ld = np.diff(lt)
            lp = ld[ld > 0]
            ltf_step_real = int(lp.min()) if lp.size else int(htf_step)
        else:
            ltf_step_real = int(htf_step)
        starts = lt
        closes = lt + ltf_step_real
        b_o, b_h, b_l, b_c = lo, lh, llo, lc
    else:
        try:
            starts, closes, b_o, b_h, b_l, b_c = _build_htf_bars(t, o, h, l, c, res_info)
        except Exception:
            return None
        M = int(starts.size)
        if M == 0:
            return None

    # 2) محرك الزقزاق الترندي على شموع الفريم المستقل (المحاور فقط المطلوبة)
    mtf_candles = [
        {
            "time": int(starts[j]),
            "open": float(b_o[j]),
            "high": float(b_h[j]),
            "low": float(b_l[j]),
            "close": float(b_c[j]),
        }
        for j in range(M)
    ]
    try:
        trendy = zigzag_fib_e2e_trendy(
            mtf_candles,
            length=length,
            reverse=reverse,
            levels=levels,
            extend_right=extend_right,
            extend_leg_to_live=extend_leg_to_live,
            mode=mode,
            depth=depth,
            deviation=deviation,
            backstep=backstep,
            launch_touch_ticks=launch_touch_ticks,
        )
    except Exception:
        return None
    pivots_mtf: List[Dict[str, Any]] = trendy.get("pivots") or []

    # 3) آلة المنطقة على محاور الفريم المستقل (كل أعمدة الحالة)
    mach = _zone_entry_machine_on_pivots(pivots_mtf, M)

    # 4) الإسقاط السببي على شموع القاعدة:
    #    (أ) الحالة الاستمرائية من آخر شريط مستقل مُغلق (نفس محاذاة رصة EMA)
    jlast = np.searchsorted(closes, t + base_step, side="right") - 1
    p_on = [0.0] * N
    p_struct = [0.0] * N
    p_last_high: List[Any] = [None] * N
    p_prev_high: List[Any] = [None] * N
    p_last_low: List[Any] = [None] * N
    p_prev_low: List[Any] = [None] * N
    for i in range(N):
        jj = int(jlast[i])
        if jj >= 0:
            p_on[i] = float(mach["on"][jj])
            p_struct[i] = float(mach["struct"][jj])
            p_last_high[i] = mach["last_high"][jj]
            p_prev_high[i] = mach["prev_high"][jj]
            p_last_low[i] = mach["last_low"][jj]
            p_prev_low[i] = mach["prev_low"][jj]

    #    (ب) الأعلام/الأحداث لمرة واحدة: أول شمعة قاعدة إغلاقها ≥ إغلاق
    #        الشريط المستقل الذي وقع فيه الحدث (الشريط النامي لا يُرى).
    p_enter = [0.0] * N
    p_exit = [0.0] * N
    p_hh = [0.0] * N
    p_hl = [0.0] * N
    p_lh = [0.0] * N
    p_ll = [0.0] * N
    events: List[Dict[str, Any]] = []
    for j in range(M):
        fire = None
        if mach["enter"][j]:
            fire = "enter"
        elif mach["exit"][j]:
            fire = "exit"
        elif mach["hh"][j]:
            fire = "hh"
        elif mach["hl"][j]:
            fire = "hl"
        elif mach["lh"][j]:
            fire = "lh"
        elif mach["ll"][j]:
            fire = "ll"
        if fire is None:
            continue
        i0 = int(np.searchsorted(t, closes[j] - base_step, side="left"))
        if i0 >= N:
            # الحدث لم يُغلق بعد ضمن نافذة البيانات — لا يُرى (سببية كاملة)
            continue
        if fire == "enter":
            p_enter[i0] = 1.0
        elif fire == "exit":
            p_exit[i0] = 1.0
        elif fire == "hh":
            p_hh[i0] = 1.0
        elif fire == "hl":
            p_hl[i0] = 1.0
        elif fire == "lh":
            p_lh[i0] = 1.0
        else:
            p_ll[i0] = 1.0
        events.append({
            "kind": fire, "mtf_bar": int(j),
            "mtf_close_time": int(closes[j]),
            "base_bar": int(i0), "base_time": int(t[i0]),
        })

    return {
        "spec": ZONE_ENTRY_MTF_SPEC,
        "resolution": res_info["label"],
        "htf_kind": res_info["kind"],
        "length": int(length),
        "mtf_bars": M,
        "htf_step_ms": int(htf_step) if htf_step is not None else None,
        "base_step_ms": int(base_step),
        "resolution_clamped_to_chart_tf": clamped,
        "ltf_real_context": bool(ltf_ctx is not None),
        "zone_on": p_on,
        "zone_struct": p_struct,
        "zone_enter": p_enter,
        "zone_exit": p_exit,
        "zone_hh": p_hh,
        "zone_hl": p_hl,
        "zone_lh": p_lh,
        "zone_ll": p_ll,
        "zone_last_high": p_last_high,
        "zone_prev_high": p_prev_high,
        "zone_last_low": p_last_low,
        "zone_prev_low": p_prev_low,
        "events": events,
        "counts": {
            "zone_enters": int(sum(p_enter)),
            "zone_exits": int(sum(p_exit)),
            "hh": int(sum(p_hh)), "hl": int(sum(p_hl)),
            "lh": int(sum(p_lh)), "ll": int(sum(p_ll)),
        },
    }


# ---------------------------------------------------------------------------
# المحرك الرئيسي — ZLF-End-To-End-Trendy-Quantum (طبقة المنطقة فوق الترندية)
# ---------------------------------------------------------------------------
def zigzag_fib_e2e_trendy_quantum(
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
    launch_touch_ticks: float = 1.0,
    trend_periods: Any = None,
    trend_confirm: Any = "majority",
    trend_gate: Any = None,
    zone_gate: Any = None,
    zone_exit_resolution: Any = None,
    zone_exit_length: Any = None,
    # ✅ ZONE-ENTRY-MTF1 — فريم المنطقة المسموحة للدخول (HH+HL على أي فريم).
    #      None/فارغ/«none»/«base»/«chart» = فريم الشارت (السلوك التاريخي بت-بت).
    zone_resolution: Any = None,
    zone_length: Any = None,
) -> Dict[str, Any]:
    """ZLF-End-To-End-Trendy-Quantum — الترندية بحذافيرها + بوابة المنطقة الكمومية.

    المعاملات: نفس معاملات الترندية حرفياً (mode/length/depth/deviation/
    backstep/reverse/levels/extend_right/extend_leg_to_live/launch_touch_ticks/
    trend_periods/trend_confirm/trend_gate) + قالب المنطقة:
      zone_gate: أنواع الإشارات المبوّبة بالمنطقة — s1/s2/s3 (افتراضياً الثلاثة)
                 أو "none" لتعطيل بوابة الدخول (بيانات المنطقة تبقى محسوبة).
      zone_exit_resolution/zone_exit_length: ✅ ZONE-EXIT-TF1 — فريم هيكل
                 الخروج (CHoCH LL+LH) — None = فريم الشارت (السلوك التاريخي).
      zone_resolution/zone_length: ✅ ZONE-ENTRY-MTF1 — فريم المنطقة المسموحة
                 للدخول (HH+HL) — تُحسب آلة المنطقة على شموع الفريم المستقل
                 (زقزاق length=zone_length أو نفس length افتراضياً) وتُسقط
                 سببياً على شموع القاعدة (آخر شريط مستقل مُغلق فقط). النسخة
                 الأصلية على فريم الشارت تُحفظ بأعمدة zzfetq_zone_*_base.
                 None/فارغ/«none»/«base»/«chart» = فريم الشارت بت-بت بلا أي
                 تغيير (عقد الإضافة الصرفة — لا مساس بأي مسار قائم).

    المخرجات: سلاسل تحتوي عقدَي التمايز معاً — zzfetq_* الكمية (62 عموداً)
    + zzfet_* الترندية (47 عموداً) ممرَّرة بت-بت (إصلاح بيانات الرسم الكاملة).
    """
    # ------------------------------------------------------------------
    # 1) المحرك الترندي الأصلي — حرفياً بنفس المعاملات (المصدر الموحد)
    #    كل أعمدته (zzfet_*) تُمرَّر كما هي إلى المخرجات + تُستنسخ بمرايا zzfetq_*.
    # ------------------------------------------------------------------
    base = zigzag_fib_e2e_trendy(
        candles,
        length=length,
        reverse=reverse,
        levels=levels,
        extend_right=extend_right,
        extend_leg_to_live=extend_leg_to_live,
        mode=mode,
        depth=depth,
        deviation=deviation,
        backstep=backstep,
        launch_touch_ticks=launch_touch_ticks,
        trend_periods=trend_periods,
        trend_confirm=trend_confirm,
        trend_gate=trend_gate,
    )
    base_series: Dict[str, List[Optional[float]]] = base.get("series") or {}

    t, o, h, l, c = norm_candles(candles)
    N = len(c)
    zone_cells = _norm_zone_gate(zone_gate)

    # ------------------------------------------------------------------
    # 2) منطق المنطقة الكمومية — من محاور الزقزاق المؤكدة (سببية كاملة:
    #    كل محور يُقرأ عند شمعة تأكيده confirmed_at_bar — لا استشراف).
    # ------------------------------------------------------------------
    pivots: List[Dict[str, Any]] = base.get("pivots") or []

    z_last_high: List[Optional[float]] = [None] * N
    z_prev_high: List[Optional[float]] = [None] * N
    z_last_low: List[Optional[float]] = [None] * N
    z_prev_low: List[Optional[float]] = [None] * N
    z_hh: List[float] = [0.0] * N
    z_hl: List[float] = [0.0] * N
    z_lh: List[float] = [0.0] * N
    z_ll: List[float] = [0.0] * N
    z_on: List[float] = [0.0] * N
    z_struct: List[float] = [0.0] * N
    z_enter: List[float] = [0.0] * N
    z_exit: List[float] = [0.0] * N
    zone_signals: List[Dict[str, Any]] = []

    last_high: Optional[float] = None
    last_low: Optional[float] = None
    prev_high: Optional[float] = None   # آخر قمة قبل الأخيرة (سلف المقارنة)
    prev_low: Optional[float] = None    # آخر قاع قبل الأخيرة (سلف المقارنة)
    high_state: Optional[float] = None   # +1 صاعد / −1 هابط لآخر مقارنة قمة
    low_state: Optional[float] = None   # +1 صاعد / −1 هابط لآخر مقارنة قاع
    zone_on = False
    zone_struct = 0.0

    pi = 0
    for i in range(N):
        # معالجة كل محور تأكد عند هذه الشمعة (مرتبة بconfirmed_at_bar)
        while pi < len(pivots) and int(pivots[pi]["confirmed_at_bar"]) <= i:
            p = pivots[pi]
            pi += 1
            price = clean_float(p.get("price"))
            kind = str(p.get("kind") or "")
            if price is None:
                continue
            if kind in ("top", "high"):
                prev_high = last_high
                last_high = price
                if prev_high is not None:
                    up = price > prev_high
                    high_state = 1.0 if up else -1.0
                    if up:
                        z_hh[i] = 1.0
                    else:
                        z_lh[i] = 1.0
            else:
                prev_low = last_low
                last_low = price
                if prev_low is not None:
                    up = price > prev_low
                    low_state = 1.0 if up else -1.0
                    if up:
                        z_hl[i] = 1.0
                    else:
                        z_ll[i] = 1.0
            # البنية المجمعة + آلة المنطقة (عند شمعة المحور نفسها)
            both_up = high_state == 1.0 and low_state == 1.0
            both_down = high_state == -1.0 and low_state == -1.0
            zone_struct = 1.0 if both_up else (-1.0 if both_down else 0.0)
            if both_up and not zone_on:
                zone_on = True
                z_enter[i] = 1.0
                zone_signals.append({
                    "bar": i, "time": t[i] if i < len(t) else None,
                    "side": "zone", "signal": "ZLF-E2E-Trendy-Quantum Zone ENTER (HH+HL)",
                    "engine": ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME,
                    "last_high": clean_float(last_high),
                    "prev_high": clean_float(prev_high),
                    "last_low": clean_float(last_low),
                    "prev_low": clean_float(prev_low),
                    "zone_struct": zone_struct,
                })
            elif both_down and zone_on:
                zone_on = False
                z_exit[i] = 1.0
                zone_signals.append({
                    "bar": i, "time": t[i] if i < len(t) else None,
                    "side": "zone", "signal": "ZLF-E2E-Trendy-Quantum Zone EXIT (LL+LH)",
                    "engine": ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME,
                    "last_high": clean_float(last_high),
                    "prev_high": clean_float(prev_high),
                    "last_low": clean_float(last_low),
                    "prev_low": clean_float(prev_low),
                    "zone_struct": zone_struct,
                })
        # ختم قيم الحالة عند كل شمعة (استمرارية كاملة للأعمدة)
        z_last_high[i] = clean_float(last_high)
        z_prev_high[i] = clean_float(prev_high)
        z_last_low[i] = clean_float(last_low)
        z_prev_low[i] = clean_float(prev_low)
        z_on[i] = 1.0 if zone_on else 0.0
        z_struct[i] = zone_struct

    # ------------------------------------------------------------------
    # 2-ب) ✅ ZONE-ENTRY-MTF1 — فريم المنطقة المسموحة للدخول (HH+HL على أي
    #      فريم): آلة المنطقة نفسها تُحسب على شموع الفريم المستقل وتُسقط
    #      سببياً على شموع القاعدة، فتحل محل نسخة فريم الشارت في كل أعمدة
    #      المنطقة (البوابة الرباعية أدناه تقرأ الحالة المسقطة). النسخة
    #      الأصلية على فريم الشارت تُحفظ للأعمدة الشفافة zzfetq_zone_*_base.
    #      عند التعطيل (None — الافتراضي) لا يتغير أي عمود بت-بت إطلاقاً.
    # ------------------------------------------------------------------
    zone_entry_section: Dict[str, Any] = {
        "enabled": False,
        "spec": ZONE_ENTRY_MTF_SPEC,
        "rule": "المنطقة المسموحة للدخول (HH+HL) محسوبة على فريم الشارت نفسه "
                "(السلوك التاريخي) — zone_resolution غير مفعّل.",
    }
    zone_entry_base_mirror: Dict[str, List[Any]] = {}
    zr_raw = norm_zone_entry_resolution(zone_resolution)
    if zr_raw is not None:
        try:
            zl_int = int(zone_length) if zone_length is not None else int(length)
        except (TypeError, ValueError):
            zl_int = int(length)
        if zl_int < 2:
            zl_int = 2
        ze = _compute_zone_entry_mtf(
            candles,
            resolution=zr_raw,
            length=zl_int,
            reverse=reverse,
            levels=levels,
            extend_right=extend_right,
            extend_leg_to_live=extend_leg_to_live,
            mode=mode,
            depth=depth,
            deviation=deviation,
            backstep=backstep,
            launch_touch_ticks=launch_touch_ticks,
        )
        if ze is not None:
            # حفظ النسخة الأصلية على فريم الشارت (شفافية A/B والرسم)
            zone_entry_base_mirror = {
                "zzfetq_zone_on_base": list(z_on),
                "zzfetq_zone_struct_base": list(z_struct),
                "zzfetq_zone_enter_base": list(z_enter),
                "zzfetq_zone_exit_base": list(z_exit),
                "zzfetq_zone_hh_base": list(z_hh),
                "zzfetq_zone_hl_base": list(z_hl),
                "zzfetq_zone_lh_base": list(z_lh),
                "zzfetq_zone_ll_base": list(z_ll),
                "zzfetq_zone_last_high_base": list(z_last_high),
                "zzfetq_zone_prev_high_base": list(z_prev_high),
                "zzfetq_zone_last_low_base": list(z_last_low),
                "zzfetq_zone_prev_low_base": list(z_prev_low),
            }
            # ⬅ الحالة الفعالة تصبح نسخة الفريم المستقل المسقطة سببياً
            z_on = ze["zone_on"]
            z_struct = ze["zone_struct"]
            z_enter = ze["zone_enter"]
            z_exit = ze["zone_exit"]
            z_hh = ze["zone_hh"]
            z_hl = ze["zone_hl"]
            z_lh = ze["zone_lh"]
            z_ll = ze["zone_ll"]
            z_last_high = ze["zone_last_high"]
            z_prev_high = ze["zone_prev_high"]
            z_last_low = ze["zone_last_low"]
            z_prev_low = ze["zone_prev_low"]
            # أحداث المنطقة الفعالة تأتي من الفريم المستقل (مُسقطة سببياً)
            zone_signals = []
            for ev in ze["events"] or []:
                if ev.get("kind") not in ("enter", "exit"):
                    continue
                i0 = int(ev.get("base_bar") or 0)
                is_enter = ev.get("kind") == "enter"
                zone_signals.append({
                    "bar": i0,
                    "time": t[i0] if i0 < len(t) else None,
                    "side": "zone",
                    "signal": ("ZLF-E2E-Trendy-Quantum Zone ENTER (HH+HL) @ "
                               f"{ze.get('resolution')}")
                              if is_enter else
                              ("ZLF-E2E-Trendy-Quantum Zone EXIT (LL+LH) @ "
                               f"{ze.get('resolution')}"),
                    "engine": ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME,
                    "last_high": clean_float(z_last_high[i0]) if i0 < N else None,
                    "prev_high": clean_float(z_prev_high[i0]) if i0 < N else None,
                    "last_low": clean_float(z_last_low[i0]) if i0 < N else None,
                    "prev_low": clean_float(z_prev_low[i0]) if i0 < N else None,
                    "zone_struct": float(z_struct[i0]) if i0 < N else 0.0,
                    "resolution": ze.get("resolution"),
                    "mtf_close_time": int(ev.get("mtf_close_time") or 0),
                })
            zone_entry_section = {
                "enabled": True,
                "spec": ZONE_ENTRY_MTF_SPEC,
                "resolution": ze.get("resolution"),
                "htf_kind": ze.get("htf_kind"),
                "length": ze.get("length"),
                "mtf_bars": ze.get("mtf_bars"),
                "htf_step_ms": ze.get("htf_step_ms"),
                "base_step_ms": ze.get("base_step_ms"),
                "resolution_clamped_to_chart_tf": ze.get(
                    "resolution_clamped_to_chart_tf", False),
                "ltf_real_context": ze.get("ltf_real_context", False),
                "counts": ze.get("counts") or {},
                "events": ze.get("events") or [],
                "rule": "المنطقة المسموحة للدخول (HH+HL) محسوبة على فريم "
                        f"{ze.get('resolution')} (زقزاق length={ze.get('length')}) "
                        "ومسقطة سببياً على شموع القاعدة — الحالة تُقرأ من آخر "
                        "شريط مستقل مُغلق فقط (بلا أي استشراف). النسخة الأصلية "
                        "على فريم الشارت في أعمدة zzfetq_zone_*_base.",
            }
        else:
            zone_entry_section = {
                "enabled": False,
                "spec": ZONE_ENTRY_MTF_SPEC,
                "requested_resolution": zr_raw,
                "rule": "تعطّلت المنطقة المسموحة HTF دفاعياً — السلوك التاريخي "
                        "على فريم الشارت يسود بت-بت.",
            }

    # ------------------------------------------------------------------
    # 3) البوابة الرباعية على الدخول — فوق مخرجات الترندية مباشرة
    # ------------------------------------------------------------------
    def _base_col(name: str) -> List[Optional[float]]:
        return list(base_series.get(name) or [0.0] * N)

    cols_raw = {n: _base_col(f"zzfet_entry_raw_s{n}") for n in (1, 2, 3)}
    cols_trendy_final = {n: _base_col(f"zzfet_entry_s{n}") for n in (1, 2, 3)}
    cols_blocked = {n: _base_col(f"zzfet_entry_blocked_s{n}") for n in (1, 2, 3)}
    cols_signal = {n: _base_col(f"zzfet_signal_s{n}") for n in (1, 2, 3)}
    sig_any = _base_col("zzfet_signal_any")
    raw_all = _base_col("zzfet_entry_raw")

    q_entry = [0.0] * N
    q_entry_s = {n: [0.0] * N for n in (1, 2, 3)}
    q_zblocked = {n: [0.0] * N for n in (1, 2, 3)}
    n_final = 0
    n_zblocked = 0
    for i in range(N):
        for n in (1, 2, 3):
            gated = n in zone_cells
            trendy_final = float(cols_trendy_final[n][i] or 0.0)
            if gated:
                zone_allows_i = z_on[i] > 0.5
                if trendy_final and zone_allows_i:
                    q_entry_s[n][i] = 1.0
                    q_entry[i] = 1.0
                    n_final += 1
                elif trendy_final and not zone_allows_i:
                    q_zblocked[n][i] = 1.0
                    n_zblocked += 1
            else:
                if trendy_final:
                    q_entry_s[n][i] = 1.0
                    q_entry[i] = 1.0
                    n_final += 1

    # ------------------------------------------------------------------
    # 4) السلاسل — zzfetq_* الكمية (62) + zzfet_* الترندية (47) ممرَّرة
    # ------------------------------------------------------------------
    # (أ) المرايا الترندية zzfetq_* — نفس القيم بت-بت (المحرك نفسه حسبها)
    mirror_keys = [
        "zzfet_dir", "zzfet_p1", "zzfet_p2", "zzfet_i1", "zzfet_i2",
        "zzfet_anchor", "zzfet_range_index",
        "zzfet_liq_state", "zzfet_liq_ref_high", "zzfet_liq_ref_vol",
        "zzfet_liq_vol_ok",
        "zzfet_signal_s1", "zzfet_signal_s2", "zzfet_signal_s3",
        "zzfet_signal_any",
        "zzfet_entry_raw", "zzfet_entry_raw_s1", "zzfet_entry_raw_s2",
        "zzfet_entry_raw_s3",
        "zzfet_entry_blocked_s1", "zzfet_entry_blocked_s2",
        "zzfet_entry_blocked_s3",
        "zzfet_trend_ok", "zzfet_trend_bias",
        "zzfet_trend_votes_bull", "zzfet_trend_votes_bear",
    ]
    quantum_series: Dict[str, List[Optional[float]]] = {}
    for k in mirror_keys:
        if k in base_series:
            quantum_series["zzfetq_" + k[len("zzfet_"):]] = base_series[k]
    # مرايا الفيبو (level_*) وخطوط الترند (tr_p*) — ديناميكية حسب القالب
    for k in base_series:
        if k.startswith("zzfet_level_") or k.startswith("zzfet_tr_p"):
            quantum_series["zzfetq_" + k[len("zzfet_"):]] = base_series[k]

    # (ب) أعمدة البوابة الرباعية
    quantum_series["zzfetq_entry"] = q_entry
    for n in (1, 2, 3):
        quantum_series[f"zzfetq_entry_s{n}"] = q_entry_s[n]
        quantum_series[f"zzfetq_entry_raw_s{n}"] = cols_raw[n]
        quantum_series[f"zzfetq_entry_blocked_s{n}"] = cols_blocked[n]
        quantum_series[f"zzfetq_entry_zblocked_s{n}"] = q_zblocked[n]
        quantum_series[f"zzfetq_signal_s{n}"] = cols_signal[n]
    quantum_series["zzfetq_entry_raw"] = raw_all
    quantum_series["zzfetq_signal_any"] = sig_any

    # (ج) أعمدة المنطقة (12)
    quantum_series["zzfetq_zone_last_high"] = z_last_high
    quantum_series["zzfetq_zone_prev_high"] = z_prev_high
    quantum_series["zzfetq_zone_last_low"] = z_last_low
    quantum_series["zzfetq_zone_prev_low"] = z_prev_low
    quantum_series["zzfetq_zone_hh"] = z_hh
    quantum_series["zzfetq_zone_hl"] = z_hl
    quantum_series["zzfetq_zone_lh"] = z_lh
    quantum_series["zzfetq_zone_ll"] = z_ll
    quantum_series["zzfetq_zone_on"] = z_on
    quantum_series["zzfetq_zone_struct"] = z_struct
    quantum_series["zzfetq_zone_enter"] = z_enter
    quantum_series["zzfetq_zone_exit"] = z_exit
    # (ج-1-ب) ✅ ZONE-ENTRY-MTF1 — مرايا النسخة الأصلية على فريم الشارت
    #      (شفافية A/B والرسم) — تُضاف فقط عند تفعيل الفريم المستقل.
    if zone_entry_section.get("enabled"):
        quantum_series.update(zone_entry_base_mirror)

    # (ج-2) ✅ ZONE-EXIT-TF1 — فريم هيكل الخروج (CHoCH على أي فريم):
    #      حساب حدث إغلاق المنطقة (LL+LH) على فريم HTF مستقل وإسقاطه
    #      سببياً على شموع القاعدة. الدخول وبوابة المنطقة المسموحة
    #      (zone_enter/zone_on) يبقيان على فريم الشارت كما هما بت-بت.
    #      عند التعطيل (الافتراضي) لا يتغير أي عمود بت-بت.
    zone_exit_section: Dict[str, Any] = {
        "enabled": False,
        "spec": ZONE_EXIT_TF_SPEC,
        "rule": "هيكل الخروج (CHoCH: LL+LH) محسوب على فريم الشارت نفسه "
                "(السلوك التاريخي) — zone_exit_resolution غير مفعّل.",
    }
    zx_res_raw = norm_zone_exit_resolution(zone_exit_resolution)
    if zx_res_raw is not None:
        try:
            zx_len = int(zone_exit_length) if zone_exit_length is not None else int(length)
        except (TypeError, ValueError):
            zx_len = int(length)
        if zx_len < 2:
            zx_len = 2
        zx = compute_zone_exit_mtf(
            candles,
            resolution=zx_res_raw,
            length=zx_len,
            reverse=reverse,
            levels=levels,
            extend_right=extend_right,
            extend_leg_to_live=extend_leg_to_live,
            mode=mode,
            depth=depth,
            deviation=deviation,
            backstep=backstep,
            launch_touch_ticks=launch_touch_ticks,
        )
        if zx is not None:
            # النسخة الأصلية على فريم الشارت تُحفظ للشفافية (A/B والرسم)
            zx_base_original = list(z_exit)
            # ⬅ الباب الجديد: حدث الخروج محسوباً على HTF ومسقوطاً سببياً
            quantum_series["zzfetq_zone_exit"] = zx["zone_exit"]
            quantum_series["zzfetq_zone_exit_base"] = zx_base_original
            quantum_series["zzfetq_zone_exit_htf_enter"] = zx["zone_enter"]
            quantum_series["zzfetq_zone_exit_htf_on"] = zx["zone_on"]
            zx_meta = dict(zx["meta"])
            zone_exit_section = {
                "enabled": True,
                "spec": ZONE_EXIT_TF_SPEC,
                "resolution": zx_meta.get("resolution"),
                "length": zx_meta.get("length"),
                "htf_bars": zx_meta.get("htf_bars"),
                "htf_step_ms": zx_meta.get("htf_step_ms"),
                "base_step_ms": zx_meta.get("base_step_ms"),
                "resolution_clamped_to_chart_tf": zx_meta.get(
                    "resolution_clamped_to_chart_tf", False),
                "counts": zx_meta.get("counts") or {},
                "events": zx["events"],
                "rule": "هيكل الخروج (CHoCH: LL+LH) محسوب على فريم "
                        f"{zx_meta.get('resolution')} (زقزاق length={zx_meta.get('length')}) "
                        "ومسقوط سببياً على شموع القاعدة — بلا أي استشراف. الدخول "
                        "والمنطقة المسموحة يبقيان على فريم الشارت بلا أي تغيير.",
            }
        else:
            zone_exit_section = {
                "enabled": False,
                "spec": ZONE_EXIT_TF_SPEC,
                "requested_resolution": zx_res_raw,
                "rule": "تعطّل هيكل الخروج HTF دفاعياً — السلوك التاريخي يسود بت-بت.",
            }

    # (د) ✅ الإصلاح: تمرير أعمدة الترندية الأصلية zzfet_* كما هي (47 عموداً)
    #     — بيانات الرسم الكاملة (زقزاق/فيبو/خطوط ترند/سيولة/إشارات/ترند)
    passthrough = {k: v for k, v in base_series.items() if str(k).startswith("zzfet_")}
    full_series: Dict[str, List[Optional[float]]] = dict(passthrough)
    full_series.update(quantum_series)

    # ------------------------------------------------------------------
    # 5) سجل الإشارات — نفس عقد الترندية + شفافية المنطقة على كل حدث
    # ------------------------------------------------------------------
    signals: List[Dict[str, Any]] = []
    for sig in base.get("signals") or []:
        s = dict(sig)
        s["engine"] = ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME
        bar = int(s.get("bar") or 0)
        zone_state = z_on[bar] > 0.5 if bar < N else False
        if str(s.get("side")) == "buy":
            s["signal"] = str(s.get("signal") or "").replace(
                "ZLF-E2E-Trendy Entry", "ZLF-E2E-Trendy-Quantum Entry")
            gated = int(s.get("states", [0])[0] if s.get("states") else 0) in zone_cells
            if gated and not zone_state:
                # حالة الترندية النهائية التي حجبتها المنطقة — أعِد تصنيفها
                s["side"] = "zblocked"
                s["signal"] = s["signal"].replace(
                    "Entry", "ZBlocked (zone gate)")
                s["zone_gate_passed"] = False
            else:
                s["zone_gate_passed"] = True if gated else None
        elif str(s.get("side")) == "blocked":
            s["signal"] = str(s.get("signal") or "").replace(
                "ZLF-E2E-Trendy Blocked", "ZLF-E2E-Trendy-Quantum Blocked")
        s["zone_on"] = float(z_on[bar]) if bar < N else 0.0
        s["zone_struct"] = float(z_struct[bar]) if bar < N else 0.0
        signals.append(s)
    signals.extend(zone_signals)
    # ✅ ZONE-EXIT-TF1 — أحداث هيكل الخروج HTF في سجل الإشارات (side="zone_htf")
    if zone_exit_section.get("enabled"):
        for ev in zone_exit_section.get("events") or []:
            i0 = int(ev.get("base_bar") or 0)
            is_exit = ev.get("kind") == "exit"
            signals.append({
                "bar": i0,
                "time": t[i0] if i0 < len(t) else None,
                "side": "zone_htf",
                "signal": ("ZLF-E2E-Trendy-Quantum Zone EXIT (LL+LH) @ HTF "
                           f"{zone_exit_section.get('resolution')}")
                          if is_exit else
                          ("ZLF-E2E-Trendy-Quantum Zone ENTER (HH+HL) @ HTF "
                           f"{zone_exit_section.get('resolution')}"),
                "engine": ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME,
                "kind": ev.get("kind"),
                "htf_bar": int(ev.get("htf_bar") or 0),
                "htf_close_time": int(ev.get("htf_close_time") or 0),
                "resolution": zone_exit_section.get("resolution"),
            })
    signals.sort(key=lambda s: s.get("bar", 0))

    # ------------------------------------------------------------------
    # 6) الحالة الحية (نطاق + ترند + منطقة) — عقد الترندية + قسم zone
    # ------------------------------------------------------------------
    current: Optional[Dict[str, Any]] = None
    if base.get("current") is not None:
        current = dict(base["current"])
        current["zone"] = {
            "on": float(z_on[N - 1]) if N else 0.0,
            "struct": float(z_struct[N - 1]) if N else 0.0,
            "last_high": z_last_high[N - 1] if N else None,
            "prev_high": z_prev_high[N - 1] if N else None,
            "last_low": z_last_low[N - 1] if N else None,
            "prev_low": z_prev_low[N - 1] if N else None,
            "gate": [f"s{x}" for x in zone_cells],
        }

    params_echo = dict(base.get("params") or {})
    params_echo["zone_gate"] = [f"s{x}" for x in zone_cells]
    # ✅ ZONE-ENTRY-MTF1 — صدى فريم المنطقة المسموحة للدخول (None = الشارت)
    params_echo["zone_resolution"] = (
        zone_entry_section.get("resolution") if zone_entry_section.get("enabled") else None)
    try:
        params_echo["zone_length"] = (
            int(zone_entry_section.get("length")) if zone_entry_section.get("enabled") else None)
    except (TypeError, ValueError):
        params_echo["zone_length"] = None
    # ✅ ZONE-EXIT-TF1 — صدى فريم هيكل الخروج (None = فريم الشارت)
    params_echo["zone_exit_resolution"] = (
        zone_exit_section.get("resolution") if zone_exit_section.get("enabled") else None)
    try:
        params_echo["zone_exit_length"] = (
            int(zone_exit_section.get("length")) if zone_exit_section.get("enabled") else None)
    except (TypeError, ValueError):
        params_echo["zone_exit_length"] = None

    base_trend = dict(base.get("trend") or {})

    return {
        "name": "ZigZag Fib E2E Trendy Quantum (ZLF-End-To-End-Trendy-Quantum — "
                "Trend-gated + Zone-gated)",
        "engine": ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME,
        "spec": ZLF_E2E_TRENDY_QUANTUM_SPEC,
        "core": {"spec": ZIGZAG_FIB_CORE_SPEC, "version": ZIGZAG_FIB_CORE_VERSION},
        "volume_available": bool(base.get("volume_available")),
        "params": params_echo,
        "legs": base.get("legs") or [],
        "pivots": pivots,
        "window": dict(base.get("window") or {}),
        "ranges": base.get("ranges") or [],
        "current": current,
        "signals": signals,
        # ✅ الإصلاح: السلاسل تحمل عقدَي التمايز معاً — zzfetq_* (62 كمياً)
        # + zzfet_* (47 تمريراً ترندياً حرفياً) = 109 أعمدة لكل شمعة
        "series": full_series,
        "trend": base_trend,
        # ✅ ZONE-ENTRY-MTF1 — قسم فريم المنطقة المسموحة للدخول (HH+HL):
        "zone_entry": zone_entry_section,
        # ✅ ZONE-EXIT-TF1 — قسم فريم هيكل الخروج (CHoCH على أي فريم):
        "zone_exit": zone_exit_section,
        "zone": {
            "enabled": True,
            "engine": ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME,
            "spec": ZLF_E2E_TRENDY_QUANTUM_SPEC,
            "gate": [f"s{x}" for x in zone_cells],
            "gate_rule": "الدخول المبوّب لا يتحقق إلا داخل المنطقة المفتوحة: "
                         "زقزاق مؤكد HH (قمة أعلى من قمة) + HL (قاع أعلى من قاع) "
                         "يفتح المنطقة (zone_enter)؛ LL + LH يغلقها (zone_exit) "
                         "ويُخرج أي صفقة مفتوحة (next_open). zone_gate=none يعطل "
                         "بوابة الدخول مع بقاء بيانات المنطقة محسوبة ومُرجعة.",
            "counts": {
                "zone_enters": int(sum(z_enter)),
                "zone_exits": int(sum(z_exit)),
                "final_entries": int(sum(q_entry)),
                "zone_blocked": int(sum(q_zblocked[1])) + int(sum(q_zblocked[2]))
                                + int(sum(q_zblocked[3])),
                "hh": int(sum(z_hh)), "hl": int(sum(z_hl)),
                "lh": int(sum(z_lh)), "ll": int(sum(z_ll)),
            },
            "events": zone_signals,
        },
        "liquidity": dict(base.get("liquidity") or {}),
        "notes": "ZLF-End-To-End-Trendy-Quantum — «الاستراتيجية الترندية الكمومية»: "
                 "الترندية بحذافيرها (محرك واحد — لا استنساخ: أعمدتها zzfet_* "
                 "تُمرَّر كما هي بت-بت لرسم الزقزاق/الفيبو/خطوط الترند/السيولة) "
                 "+ بوابة المنطقة الكمومية HH+HL/LL+LH فوق إشارات الدخول مع "
                 "الشفافية الرباعية (raw/blocked_trend/zblocked_zone/final). "
                 "كل المخرجات الجديدة بأسماء عقد التمايز zzfetq_*/ind_zzfetq_*.",
    }


# ---------------------------------------------------------------------------
# ✅ التسجيل الذاتي كمؤشر منفصل — zigzag_fib_e2e_trendy_quantum
#    يُستورد مرة واحدة من app/services/indicators/__init__.py
# ---------------------------------------------------------------------------
def _register_quantum_indicator() -> None:
    try:
        from .base import BaseIndicator, IndicatorResult, IndicatorType
        from .registry import IndicatorRegistry
        import pandas as pd

        class ZigZagFibE2ETrendyQuantumIndicator(BaseIndicator):
            """ZLF-End-To-End-Trendy-Quantum — الترندية + بوابة المنطقة الكمومية."""

            @classmethod
            def get_required_columns(cls):
                return ["open", "high", "low", "close"]

            def calculate(self, data: pd.DataFrame) -> IndicatorResult:
                from .overlay_columns import config_to_overlay_params
                conv = config_to_overlay_params({
                    "name": "zigzag_fib_e2e_trendy_quantum",
                    "params": dict(self.params or {}),
                }) or {"zzfib_e2e_trendy_quantum": {}}
                params = conv.get("zzfib_e2e_trendy_quantum") or {}
                res = zigzag_fib_e2e_trendy_quantum(data, **params)
                values = res["series"].get("zzfetq_entry") or [None] * len(data)
                series = pd.Series(values, index=data.index, dtype=object)
                return IndicatorResult(
                    name=self.name,
                    values=series,
                    signals=None,
                    metadata={
                        "engine": ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME,
                        "overlay": "zzfib_e2e_trendy_quantum",
                        "primary_column": "ind_zzfetq_entry",
                        "available_columns": sorted(res["series"].keys()),
                    },
                )

        IndicatorRegistry.register(
            "zigzag_fib_e2e_trendy_quantum",
            display_name="ZLF-End-To-End-Trendy-Quantum — الاستراتيجية الترندية الكمومية",
            description="الترندية بحذافيرها (S1/S2/S3 + بوابة الترند 7/15/25) + بوابة "
                        "المنطقة الكمومية (HH+HL يفتح · LL+LH يغلق ويخرج next_open) مع "
                        "الشفافية الرباعية. تُرجع كل أعمدة الترندية zzfet_* (بيانات "
                        "الرسم: زقزاق/فيبو/خطوط ترند/سيولة) ممرَّرة بت-بت + أعمدة "
                        "الكمومية zzfetq_* (62). العمود الأساسي: ind_zzfetq_entry · "
                        "الخام ind_zzfetq_entry_raw · حجب الترند ind_zzfetq_entry_blocked_* · "
                        "حجب المنطقة ind_zzfetq_entry_zblocked_*.",
            category=IndicatorType.SUPPORT_RESISTANCE,
        )(ZigZagFibE2ETrendyQuantumIndicator)

        # مرادف قصير — نفس الفئة
        info = IndicatorRegistry._indicators.get("zigzag_fib_e2e_trendy_quantum")
        if info is not None:
            IndicatorRegistry._indicators.setdefault("zzfib_e2e_trendy_quantum", info)
    except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
        import logging
        logging.getLogger(__name__).exception(
            "ZLF-E2E-Trendy-Quantum indicator registration failed")


_register_quantum_indicator()
