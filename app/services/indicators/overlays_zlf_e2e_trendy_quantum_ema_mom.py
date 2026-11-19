# =============================================================================
# QMOM1 — ZLF-End-To-End-Trendy-Quantum-EMA-Mom «كموميه الزخم الاولى»
# =============================================================================
# أمر صاحب القرار (2026-11-18): «سنقوم باضافه بوابه جديده للشروط وتكون مرنه
#   وقابله للتعديل والاضافه ع اي استراتيجيه ... ونسوي من
#   ZLF-End-To-End-Trendy-Quantum-EMA نسخه باسم: كموميه الزخم الاولى».
#
# هذا الملف = طبقة بوابة الشروط المرنة فوق الكمومية المتوسطة المتحركة
# الأسية (QUANTUMEMA1) — بلا أي مساس بأي محرك قائم (إضافة تسجيل فقط):
#   · indicator: zigzag_fib_e2e_trendy_quantum_ema_mom
#     overlay: zzfib_e2e_trendy_quantum_ema_mom
#   · عقد التمايز العاشر: zzfetqem_X → ind_zzfetqem_X — مرآة كاملة
#     للكمومية-EMA + ✅ R78 (عقد الإضافة الصرفة): عائلة zzfetqe_* الأصلية
#     تبقى أيضاً بأسمائها القديمة (رسم الفرونت القائم — خطوط EMA الستة
#     ind_zzfetqe_ema_* والمنطقة والرصة بت-بت كما كان البطل يرجعها) مع
#     تمرير عقدَي الكمية zzfetq_* والترندية zzfet_* كما هما بت-بت، وعمودان
#     مجمّعان: ind_zigzag_fib_e2e_trendy_quantum_ema (خام 0/1 — قيم البطل)
#     و ind_zigzag_fib_e2e_trendy_quantum_ema_mom (نهائي 0/1 بعد البوابة).
#   · الدخول النهائي zzfetqem_entry / zzfetqem_entry_s{1,2,3} = نهائي
#     الكمومية-EMA (ترند + منطقة + رصة) ∧ بوابة شجرة شروط الموشرات
#     (osc_conditions) عند الشمعة نفسها — بلا أي نظر مستقبلية.
#   · zzfetqem_entry_iblocked{,_s1..s3} = الخام الممنوع ببوابة الزخم.
#   · قسم osc كامل (instances/counts/crosses/view_times/warnings_v2)
#     + سلاسل كل نسخة zzfetqem_osc_<id>_<field> (macd: line/signal/hist ·
#     rsi: value/ma/bb_upper/bb_lower · mom: line/pct) → أعمدة
#     ind_zzfetqem_osc_* قابلة للاستخدام مباشرة في شروط JSON
#     بصيغة indicator:zigzag_fib_e2e_trendy_quantum_ema_mom:zzfetqem_osc_...
#
# البنية (طبقة سياسات رقيقة فوق المحرك الكمي-الأسّي — لا استنساخ):
#   1) يُحسب المحرك zigzag_fib_e2e_trendy_quantum_ema حرفياً (نفس
#      المعاملات) → ✅ R78: أعمدته zzfetqe_* تبقى كما هي + تُضاف مراياها
#      zzfetqem_* بت-بت (نفس كائن القائمة تحت الاسمين — عقد الإضافة
#      الصرفة)، وعقدا zzfetq_*/zzfet_* يمران كما هما.
#   2) نواة الموشرات متعددة الفريمات PRO76-mtf-osc-core v2.0.0 تحسب
#      النسخ المطلوبة (osc_instances — أي عدد، macd/rsi/mom، أي فريم من
#      1s حتى 1mo) على شموع القاعدة بتجميع صاعد + إسقاط سببي
#      (آخر شريط أعلى مكتمل فقط — بلا استشراف)، ثم تُقيَّم شجرة الشروط
#      osc_conditions (and/or/not بأي عمق) عند كل شمعة مغلقة.
#   3) البوابة تُطبَّق على إشارات الدخول النهائية (s1/s2/s3) بشفافية
#      رباعية: entry_raw (الكمومية) · eblocked (الرصة) · iblocked (الزخم)
#      · entry (النهائي بعد كل البوابات).
#
# وضع الهوية (بلا قالب): عند غياب osc_instances و osc_conditions معاً
# يبقى المحرك مرآة بت-بت للكمومية-EMA (البوابة مفتوحة دائماً) — لا حساب
# موشرات إطلاقاً (حماية أداء مسار «كل الأنواع» الافتراضي للوحات الحي).
#
# الأداء: البوابة والعدادات تُحسب numpy على الدقة الكاملة؛ سلاسل النسخ
# تُخزَّن فقط للنسخ المحسوبة (المستخدمة في الشروط أو المعروضة) — نفس
# عقد الذاكرة المحكمة لنواة R76.
# =============================================================================

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (
    zigzag_fib_e2e_trendy_quantum_ema,
)
from app.services.indicators.mtf_oscillator_core import (
    build_osc_section,
    normalize_timeframe,
)

_LOG = logging.getLogger(__name__)

__all__ = [
    "zigzag_fib_e2e_trendy_quantum_ema_mom",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_MOM_ENGINE_NAME",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_MOM_SPEC",
]

ZLF_E2E_TRENDY_QUANTUM_EMA_MOM_ENGINE_NAME = (
    "ZLF-End-To-End-Trendy-Quantum-EMA-Mom")
ZLF_E2E_TRENDY_QUANTUM_EMA_MOM_SPEC = "QMOM1-quantum-momentum"
QMOM1_STRATEGY_AR_NAME = "كموميه الزخم الاولى"


def zigzag_fib_e2e_trendy_quantum_ema_mom(
    candles: Any,
    *,
    # ---- معاملات الكمومية-EMA (تمرير حرفي للمحرك الأساسي) ----
    length: int = 100,
    reverse: bool = False,
    levels=None,
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
    ema_lengths: Any = None,
    ema_resolution: Any = None,
    ema_source: str = "close",
    ema_offset: int = 0,
    ema_gate: Any = None,
    zone_exit_resolution: Any = None,
    zone_exit_length: Any = None,
    # ✅ EMAGATE-UNIFIED — تمرير حرفي لنواة الرصة الموحدة (الشروط السبعة)
    ema_stack_mode: Any = None,
    ema_stack_base: Any = None,
    # ---- قالب بوابة الشروط المرنة (نواة PRO76) ----
    osc_instances: Optional[Sequence[Any]] = None,
    osc_conditions: Optional[Dict[str, Any]] = None,
    osc_enabled: bool = True,
    osc_series: str = "full",
    osc_base_timeframe: Optional[str] = None,
    view_times: Optional[Sequence[Any]] = None,
    osc_base: Optional[Any] = None,
    **_extra,
) -> Dict[str, Any]:
    """«كموميه الزخم الاولى» — الكمومية-EMA بحذافيرها + بوابة الشروط المرنة.

    المعاملات: نفس معاملات الكمومية المتوسطة المتحركة الأسية حرفياً
    (length/mode/depth/deviation/backstep/reverse/levels/extend_right/
    extend_leg_to_live/launch_touch_ticks/trend_periods/trend_confirm/
    trend_gate/zone_gate/ema_lengths/ema_resolution/ema_source/ema_offset/
    ema_gate/zone_exit_resolution/zone_exit_length + ✅ EMAGATE-UNIFIED:
    ema_stack_mode/ema_stack_base — تمرير حرفي للمحرك الأساسي؛ البوابة
    واحدة مركزية هناك) + قالب الموشرات:

      osc_instances : نسخ الموشرات — [{kind: macd|rsi|mom, id, timeframe,
                     fast/slow/signal | period/ma_length/bb_std | length,
                     enabled, doc}] بأي عدد وأي فريم (1s..1mo). None مع
                     وجود شروط ⇒ مكتبة المستند الكاملة (67 نسخة) كما في
                     عائلة الماكدية.
      osc_conditions: شجرة الشروط القابلة للتركيب — {logic: and|or|not,
                     conditions: [...]} بأي عمق؛ الورقة {left, op, right,
                     skip_unavailable, enabled} حيث left/right مرجع
                     "osc:<id>.<field>" أو "price:<col>" أو رقم، وop من
                     > >= < <= == !=. enabled:false = تعطيل الورقة/الفرع
                     (محايد — كأنه غير موجود).
      osc_series    : full (سلاسل كاملة) · view (عينات عند view_times)
                     · none (المحرك — بوابات وعدادات فقط).

    المخرجات: سلاسل zzfetqem_* (مرآة الكمومية-EMA بعد البوابة + سلاسل
    الموشرات zzfetqem_osc_<id>_<field> + الشفافية iblocked + osc_gate)
    + تمرير zzfetq_*/zzfet_* بت-بت + قسم osc كامل.
    """

    # ------------------------------------------------------------------
    # 1) المحرك الأساسي — الكمومية-EMA حرفياً بنفس المعاملات (المصدر
    #    الموحد لكل بيانات zzfetqe_* + zzfetq_* + zzfet_*)
    # ------------------------------------------------------------------
    base = zigzag_fib_e2e_trendy_quantum_ema(
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
        zone_gate=zone_gate,
        ema_lengths=ema_lengths,
        ema_resolution=ema_resolution,
        ema_source=ema_source,
        ema_offset=ema_offset,
        ema_gate=ema_gate,
        zone_exit_resolution=zone_exit_resolution,
        zone_exit_length=zone_exit_length,
        # ✅ EMAGATE-UNIFIED — البوابة المركزية الموحدة تُطبّق هنا أيضاً
        # (كموميه الزخم الاولى فيها البوابة — لا مسار جانبي إطلاقاً).
        ema_stack_mode=ema_stack_mode,
        ema_stack_base=ema_stack_base,
    )

    # --- ✅ R78 (عقد الإضافة الصرفة — «الدمج فقط إضافة») ---
    # سلاسل الكمومية-EMA zzfetqe_* تبقى كما هي بأسمائها الأصلية (عقد
    # الرسم القائم مع الفرونت: خطوط EMA الستة ind_zzfetqe_ema_* · المنطقة ·
    # الرصة · الزقزاق/الفيبو — نفس ما كان البطل #10000604 يرجعه بت-بت)
    # + تُضاف المرآة zzfetqem_* فوقها — نفس كائن القائمة في الذاكرة تحت
    # الاسمين (تطابق بت-بت بالبناء، صفر نسخ إضافي).
    # عقدا الكمية zzfetq_* والترندية zzfet_* يمران كما هما (بيانات الرسم
    # الكاملة بت-بت من المحرك الواحد نفسه — نفس سلوك الكمومية-EMA).
    b_series: Dict[str, Any] = base.get("series") or {}
    series: Dict[str, Any] = {}
    for k, v in b_series.items():
        ks = str(k)
        if ks.startswith("zzfetqe_"):
            series[ks] = v                                   # الأساس كما هو
            series["zzfetqem_" + ks[len("zzfetqe_"):]] = v    # المرآة الجديدة
        else:
            series[ks] = v
    n = len(next(iter(series.values()), [])) or 0

    raw_entry = series.get("zzfetqem_entry") or [None] * n
    osc_section: Dict[str, Any] = {
        "enabled": False,
        "spec": "QMOM1 — وضع الهوية: بلا osc_instances و بلا osc_conditions "
                "(مرآة الكمومية-EMA بت-بت — البوابة مفتوحة دائماً)",
    }
    gate: Optional[List[bool]] = None
    has_template = (osc_instances is not None) or (osc_conditions is not None)

    if osc_enabled and has_template:
        # مسار البناء: نواة R76 تحسب النسخ على شموع القاعدة (أو osc_base
        # بالدقة الكاملة لمسار chart-data عند تمريره) وتُقيّم شجرة الشروط.
        built = build_osc_section(
            (osc_base if osc_base is not None else candles),
            base_timeframe=osc_base_timeframe,
            osc_instances=osc_instances,
            osc_conditions=osc_conditions,
            view_times=view_times,
            prefix="zzfetqem",
            entry_series=[bool(x) if x else False for x in raw_entry],
            entry_label="quantum_ema_entries",
            osc_series=osc_series,
        )
        osc_section = built["section"]
        # اختيار البوابة بمقياس سلاسل المحرك (n) — نفس درس الطول PRO76b:
        # أي بوابة بطول != n تُسقط بتحذير صاخب وتبقى الإشارات بلا بوابة
        # (لا IndexError — الرسم آمن دائماً).
        if osc_base is not None and built.get("gate_view") is not None:
            gate = built["gate_view"]
        elif built.get("gate_orig") is not None:
            gate = built["gate_orig"]
        else:
            gate = built["gate"]
        if gate is not None and len(gate) != n:
            _LOG.warning(
                "zzfetqem osc gate len=%d != n=%d — gate dropped (ungated, safe)",
                len(gate), n)
            try:
                osc_section.setdefault("warning_codes", []).append("gate_length_mismatch")
                osc_section.setdefault("warnings_v2", []).append({
                    "code": "gate_length_mismatch",
                    "message": "بوابة الزخم بطول مخالف لسلاسل المحرك — الإشارات بلا بوابة (آمن، لا انهيار)",
                    "instance": None,
                })
            except Exception:  # noqa: BLE001 — الشفافية لا تكسر المحرك
                pass
            gate = None
        for nm, arr in built["series"].items():
            series[nm] = arr

    # ------------------------------------------------------------------
    # 2) البوابة على الدخول + أعمدة الممنوع (بنفس الدقة الكاملة)
    # ------------------------------------------------------------------
    # ✅ R77 (علة #10000616 — النصف الثاني من «النتيجة لم تتغير»):
    # كانت البوابة تُطبَّق على zzfetqem_entry (المجمّع) فقط وتترك إشارات
    # s1/s2/s3 خاماً — وقواعد دخول الاستراتيجية تشير إلى zzfetqem_entry_s{1,2,3}
    # (عقد FRONTEND-AGENT-BRIEF-QMOM1 §1ب: «الدخول النهائي zzfetqem_entry_s{1,2,3}
    # = نهائي الكمومية-EMA ∧ قيمة الشجرة») ⇒ البوابة لم تمنع شيئاً فعلياً
    # والصفقات خرجت = الأساس بت-بت (46 كما هي). الآن كل إشارة على حدة
    # تُبوّب فعلياً + شفافية iblocked_{tag} (ما قتلته البوابة وأين).
    if gate is not None:
        final: List[Optional[float]] = []
        iblock: List[Optional[float]] = []
        for i in range(n):
            r = bool(raw_entry[i]) if i < len(raw_entry) else False
            if r:
                if gate[i]:
                    final.append(raw_entry[i])
                    iblock.append(None)
                else:
                    final.append(None)
                    iblock.append(1.0)
            else:
                final.append(None)
                iblock.append(None)
        series["zzfetqem_entry"] = final
        series["zzfetqem_entry_iblocked"] = iblock
        # البوابة الفعلية + الممنوع لكل إشارة على حدة (s1/s2/s3)
        for tag in ("s1", "s2", "s3"):
            key = f"zzfetqem_entry_{tag}"
            if key in series:
                src = series[key]
                gated: List[Optional[float]] = []
                out: List[Optional[float]] = []
                for i in range(len(src)):
                    r = bool(src[i]) if i < len(src) else False
                    g = bool(gate[i]) if i < len(gate) else False
                    if r:
                        gated.append(src[i] if g else None)  # ✅ R77 — بوابة فعّالة
                        out.append(None if g else 1.0)        # شفافية الممنوع
                    else:
                        gated.append(None)
                        out.append(None)
                series[key] = gated
                series[f"zzfetqem_entry_iblocked_{tag}"] = out
    else:
        series.setdefault("zzfetqem_entry_iblocked", [None] * n)
        for tag in ("s1", "s2", "s3"):
            series.setdefault(f"zzfetqem_entry_iblocked_{tag}", [None] * n)
    series.setdefault(
        "zzfetqem_osc_gate",
        ([1.0 if g else None for g in gate] if gate is not None else [None] * n))

    # ------------------------------------------------------------------
    # 2ب) ✅ R78 — العمودان المجمّعان (عقد القيم الكلاسيكي «نفس الكمومية»):
    # البطل #10000604 كان يرجع ind_zigzag_fib_e2e_trendy_quantum_ema
    # (0/1 عند كل شمعة — 1.0 عند شمعة الإشارة) من مسار قيم المؤشر الكلاسيكي،
    # والمحرك الجديد لم يرجع أي مكافئ. الآن يُرجع الاثنين معاً:
    #   · zigzag_fib_e2e_trendy_quantum_ema     = خام الكمومية-EMA 0/1
    #     (نفس قيم البطل بت-بت — مرآة zzfetqe_entry)
    #   · zigzag_fib_e2e_trendy_quantum_ema_mom = نهائي بعد بوابة الزخم 0/1
    #     (مرآة zzfetqem_entry المبوّبة)
    # (تصبح عمودي ind_zigzag_* عبر _zzfetqem_columns — عقد R78).
    # ------------------------------------------------------------------
    _agg_raw: List[float] = []
    for i in range(n):
        _rv = series.get("zzfetqe_entry")
        _v = _rv[i] if (_rv is not None and i < len(_rv)) else None
        _agg_raw.append(1.0 if _v else 0.0)
    series["zigzag_fib_e2e_trendy_quantum_ema"] = _agg_raw
    _agg_final: List[float] = []
    _fv = series.get("zzfetqem_entry") or []
    for i in range(n):
        _v = _fv[i] if i < len(_fv) else None
        _agg_final.append(1.0 if _v else 0.0)
    series["zigzag_fib_e2e_trendy_quantum_ema_mom"] = _agg_final

    # ------------------------------------------------------------------
    # 3) المخرجات — المحرك الأساسي بت-بت + السلاسل بعد البوابة + قسم osc
    # ------------------------------------------------------------------
    out = dict(base)
    out["name"] = (
        "ZigZag Fib E2E Trendy Quantum EMA Mom (ZLF-End-To-End-Trendy-Quantum-"
        "EMA-Mom — «كموميه الزخم الاولى»: Trend+Zone+EMA-stack gated + "
        "Flexible Oscillator-Conditions Gate)")
    out["engine"] = ZLF_E2E_TRENDY_QUANTUM_EMA_MOM_ENGINE_NAME
    out["spec"] = ZLF_E2E_TRENDY_QUANTUM_EMA_MOM_SPEC
    out["base_engine"] = {
        "name": base.get("engine"),
        "spec": base.get("spec"),
        "note": "كموميه الزخم الاولى = الكمومية-EMA بت-بت + بوابة الشروط "
                "المرنة للموشرات متعددة الفريمات (QMOM1)",
    }
    out["strategy_ar_name"] = QMOM1_STRATEGY_AR_NAME
    out["series"] = series
    out["osc"] = osc_section
    # النافذة = أعمدة التخزين الفعلي (مدخل المحرك نفسه)
    w = base.get("window") or {}
    out["window"] = {
        "bars": (len(view_times) if (view_times is not None
                                     and osc_section.get("view_sampled"))
                 else w.get("bars", n)),
        "time_from": w.get("time_from"),
        "time_to": w.get("time_to"),
    }
    return out


# ---------------------------------------------------------------------------
# التسجيل الذاتي كمؤشر منفصل — zigzag_fib_e2e_trendy_quantum_ema_mom
# يُستورد مرة واحدة من app/services/indicators/__init__.py
# ---------------------------------------------------------------------------
def _register_quantum_momentum_indicator() -> None:
    try:
        from .base import BaseIndicator, IndicatorResult, IndicatorType
        from .registry import IndicatorRegistry
        import pandas as pd

        class ZigZagFibE2ETrendyQuantumEmaMomIndicator(BaseIndicator):
            """«كموميه الزخم الاولى» — الكمومية-EMA + بوابة الشروط المرنة."""

            @classmethod
            def get_required_columns(cls):
                return ["open", "high", "low", "close"]

            @classmethod
            def get_default_params(cls):
                # ✅ EMAGATE-UNIFIED — لوحة إعدادات الواجهة (endpoint /params):
                # كل مفاتيح بوابة الرصة الهرمية + قالب الموشرات ظاهرة هنا —
                # ملاحظة صاحب القرار: الديفولت length=100 (لا 226) + الرصة
                # الكاملة الستة مع EMA21 الجديدة «كامله مع الجديده».
                return {
                    "length": 100, "mode": "luxalgo",
                    "trend_periods": [7, 15, 25], "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3"],
                    "zone_gate": ["s1", "s2", "s3"],
                    "ema_lengths": [21, 50, 100, 200, 350, 500],
                    "ema_resolution": "60", "ema_source": "close",
                    "ema_offset": 0, "ema_gate": ["s1", "s2", "s3"],
                    "ema_stack_mode": "hierarchical", "ema_stack_base": 21,
                    "zone_exit_resolution": "5", "zone_exit_length": 100,
                }

            def calculate(self, data: pd.DataFrame) -> IndicatorResult:
                from .overlay_columns import config_to_overlay_params
                conv = config_to_overlay_params({
                    "name": "zigzag_fib_e2e_trendy_quantum_ema_mom",
                    "params": dict(self.params or {}),
                }) or {"zzfib_e2e_trendy_quantum_ema_mom": {}}
                params = conv.get("zzfib_e2e_trendy_quantum_ema_mom") or {}
                res = zigzag_fib_e2e_trendy_quantum_ema_mom(data, **params)
                values = res["series"].get("zzfetqem_entry") or [None] * len(data)
                series = pd.Series(values, index=data.index, dtype=object)
                return IndicatorResult(
                    name=self.name,
                    values=series,
                    signals=None,
                    metadata={
                        "engine": ZLF_E2E_TRENDY_QUANTUM_EMA_MOM_ENGINE_NAME,
                        "overlay": "zzfib_e2e_trendy_quantum_ema_mom",
                        "primary_column": "ind_zzfetqem_entry",
                        "available_columns": sorted(res["series"].keys()),
                    },
                )

        IndicatorRegistry.register(
            "zigzag_fib_e2e_trendy_quantum_ema_mom",
            display_name="ZLF-End-To-End-Trendy-Quantum-EMA-Mom — كموميه الزخم الاولى",
            description="الكمومية-EMA بحذافيرها (S1/S2/S3 + بوابة الترند 7/15/25 "
                        "+ بوابة المنطقة الكمومية + رصة EMA الستة) + بوابة "
                        "الشروط المرنة للموشرات متعددة الفريمات (macd/rsi/mom "
                        "على أي فريم 1s..1mo — شجرة and/or/not قابلة للتركيب "
                        "بأي عمق، مع enabled:false لتعطيل أي ورقة/فرع). "
                        "العمود الأساسي: ind_zzfetqem_entry · الممنوع بالزخم "
                        "ind_zzfetqem_entry_iblocked_* · بوابة الزخم "
                        "ind_zzfetqem_osc_gate · سلاسل كل نسخة "
                        "ind_zzfetqem_osc_<id>_<field> قابلة للشروط مباشرة.",
            category=IndicatorType.SUPPORT_RESISTANCE,
        )(ZigZagFibE2ETrendyQuantumEmaMomIndicator)

        # مرادف قصير — نفس الفئة (نمط العائلة)
        info = IndicatorRegistry._indicators.get(
            "zigzag_fib_e2e_trendy_quantum_ema_mom")
        if info is not None:
            IndicatorRegistry._indicators.setdefault(
                "zzfib_e2e_trendy_quantum_ema_mom", info)
    except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
        logging.getLogger(__name__).exception(
            "ZLF-E2E-Trendy-Quantum-EMA-Mom indicator registration failed")


_register_quantum_momentum_indicator()
