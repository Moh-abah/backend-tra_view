# =============================================================================
# 🟣 R76 — ZLF-E2E-Trendy-MACD — «الترندية الماكدية» (طبقة الموشرات فوق البطل)
# =============================================================================
# عقد الجيل الثالث (PRO73→PRO74→R76): نفس عقد الإنتاج الحي بت-بت مع إصلاحات
# الجولة 76 (B-1..B-8) ونواة PRO76-mtf-osc-core v2.0.0:
#   · indicator: zigzag_fib_e2e_trendy_macd · overlay: zzfib_e2e_trendy_macd
#   · سلاسل zzfetm_* (البنية zzfet_* للبطل + _osc_* للموشرات) → ind_zzfetm_*
#   · الدخول النهائي zzfetm_entry = إشارة البطل المبوّبة (بوابة الترند)
#     ∧ بوابة شجرة شروط الموشرات (osc_conditions) عند الشمعة نفسها.
#   · zzfetm_entry_iblocked{,_s1..s3} = الخام الممنوع ببوابة الموشرات.
#   · قسم osc كامل (instances/counts/crosses/view_times/warnings_v2).
#
# 🩸 علة SIGKILL (10000312-14) المحلولة هنا:
#   · osc_series="none" في مسار الباك-تست: البوابة تُحسب numpy على الدقة
#     الكاملة ولا تُخزَّن 256 سلسلة Python بطول 665K (كانت ≈5-7GB).
#   · التجميع الصاعد للثواني (B-1) + الصدق في base_tf (B-2).
# =============================================================================

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy
from app.services.indicators.mtf_oscillator_core import (
    build_osc_section,
    normalize_timeframe,
)

_LOG = logging.getLogger(__name__)

__all__ = [
    "zigzag_fib_e2e_trendy_macd",
    "ZLF_E2E_TRENDY_MACD_ENGINE_NAME",
    "ZLF_E2E_TRENDY_MACD_SPEC",
]

ZLF_E2E_TRENDY_MACD_ENGINE_NAME = "ZLF-End-To-End-Trendy-MACD"
ZLF_E2E_TRENDY_MACD_SPEC = "R76-trendy-macd"

_BASE_PARAMS = (
    "length", "reverse", "levels", "extend_right", "extend_leg_to_live",
    "mode", "depth", "deviation", "backstep", "launch_touch_ticks",
    "trend_periods", "trend_confirm", "trend_gate",
)


def zigzag_fib_e2e_trendy_macd(
    candles: Any,
    *,
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
    trend_periods=None,
    trend_confirm: str = "majority",
    trend_gate=None,
    osc_instances: Optional[Sequence[Any]] = None,
    osc_conditions: Optional[Dict[str, Any]] = None,
    osc_enabled: bool = True,
    osc_series: str = "full",
    osc_base_timeframe: Optional[str] = None,
    view_times: Optional[Sequence[Any]] = None,
    # ✅ R76 (B-2): مصدر شموع بالدقة الكاملة لمسار chart-data (بنية
    # {time_ms: [...], close: [...]} أو قائمة شموع/داتافريم) — عند تمريره
    # يُحسب قسم الموشرات عليه (الدقة الكاملة) بينما يعمل الرسم البنيوي
    # على شموع العرض — ثم تُؤخذ العينات عند view_times.
    osc_base: Optional[Any] = None,
    **_extra,
) -> Dict[str, Any]:
    """البطل الترندي حرفياً + طبقة الموشرات متعددة الفريمات (نواة R76).

    osc_enabled=False يعطّل طبقة الموشرات كلياً (يستخدمه مسار chart-data
    عندما يعيد بناء القسم من osc_base المخزّن بالدقة الكاملة — B-2).
    osc_series: full (الحي) · view (عينات عند view_times) · none (المحرك)."""
    base = zigzag_fib_e2e_trendy(
        candles,
        length=length, reverse=reverse, levels=levels,
        extend_right=extend_right, extend_leg_to_live=extend_leg_to_live,
        mode=mode, depth=depth, deviation=deviation, backstep=backstep,
        launch_touch_ticks=launch_touch_ticks,
        trend_periods=trend_periods, trend_confirm=trend_confirm,
        trend_gate=trend_gate,
    )

    # --- إعادة تسمية السلاسل zzfet_* → zzfetm_* (عقد الإنتاج حرفياً) ---
    b_series = base.get("series") or {}
    series: Dict[str, List[Optional[float]]] = {}
    for k, v in b_series.items():
        nk = ("zzfetm_" + k[len("zzfet_"):]) if k.startswith("zzfet_") else k
        series[nk] = v
    n = len(next(iter(series.values()), [])) or 0

    raw_entry = series.get("zzfetm_entry") or [None] * n
    osc_section: Dict[str, Any] = {"enabled": False}
    gate: Optional[List[bool]] = None

    if osc_enabled:
        # ✅ B-2: عند تمرير osc_base (مسار chart-data) يُحسب قسم الموشرات على
        # الدقة الكاملة ثم تُعاين القيم عند أعمدة العرض view_times — لا على
        # العرض المضغوط مباشرة (كان الجذر: base_tf 2040000ms على نافذة البطل).
        built = build_osc_section(
            (osc_base if osc_base is not None else candles),
            base_timeframe=osc_base_timeframe,
            osc_instances=osc_instances,
            osc_conditions=osc_conditions,
            view_times=view_times,
            prefix="zzfetm",
            entry_series=[bool(x) if x else False for x in raw_entry],
            entry_label="trend_entries",
            osc_series=osc_series,
        )
        osc_section = built["section"]
        # ✅ PRO76b-HF-A: اختيار البوابة بمقياس سلاسل المحرك (n) — بوابة
        # أعمدة العرض (gate_view: طولها = عدد أعمدة العرض كلها) عند وجودها،
        # وإلا بوابة شموع الدخل الأصلية (gate_orig)، وإلا بوابة القاعدة —
        # ثم درس الطول: أي بوابة بطول ≠ n تُسقط بتحذير صاخب والعرض يبقى
        # بلا بوابة (لا IndexError بعد اليوم — جذر 4d976421 عند L133).
        if osc_base is not None and built.get("gate_view") is not None:
            gate = built["gate_view"]
        elif built.get("gate_orig") is not None:
            gate = built["gate_orig"]
        else:
            gate = built["gate"]
        if gate is not None and len(gate) != n:
            _LOG.warning(
                "zzfetm gate len=%d != n=%d — gate dropped (ungated view, chart safe)",
                len(gate), n)
            try:
                osc_section.setdefault("warning_codes", []).append("gate_length_mismatch")
                osc_section.setdefault("warnings_v2", []).append({
                    "code": "gate_length_mismatch",
                    "message": "بوابة الموشرات بطول مخالف لسلاسل المحرك — الرسم بلا بوابة (آمن، لا انهيار)",
                    "instance": None,
                })
            except Exception:  # noqa: BLE001 — الشفافية لا تكسر المحرك
                pass
            gate = None
        for nm, arr in built["series"].items():
            series[nm] = arr

    # --- البوابة على الدخول + أعمدة الممنوع (بنفس الدقة الكاملة) ---
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
        series["zzfetm_entry"] = final
        series["zzfetm_entry_iblocked"] = iblock
        # الممنوع لكل إشارة مبوّبة على حدة (s1/s2/s3)
        for tag in ("s1", "s2", "s3"):
            key = f"zzfetm_entry_{tag}"
            if key in series:
                src = series[key]
                out: List[Optional[float]] = []
                for i in range(len(src)):
                    r = bool(src[i]) if i < len(src) else False
                    out.append(1.0 if (r and not gate[i]) else None)
                series[f"zzfetm_entry_iblocked_{tag}"] = out
    else:
        series.setdefault("zzfetm_entry_iblocked", [None] * n)
        for tag in ("s1", "s2", "s3"):
            series.setdefault(f"zzfetm_entry_iblocked_{tag}", [None] * n)
    series.setdefault("zzfetm_osc_gate", ([1.0 if g else None for g in gate]
                                          if gate is not None else [None] * n))

    out = dict(base)
    out["engine"] = ZLF_E2E_TRENDY_MACD_ENGINE_NAME
    out["spec"] = ZLF_E2E_TRENDY_MACD_SPEC
    out["base_engine"] = {
        "name": base.get("engine"),
        "spec": base.get("spec"),
        "note": "الترندية الماكدية = البطل الترندي بت-بت + بوابة الموشرات (PRO76)",
    }
    out["series"] = series
    out["osc"] = osc_section
    # ✅ B-8: النافذة = أعمدة التخزين الفعلي (مدخل المحرك نفسه)
    w = base.get("window") or {}
    out["window"] = {"bars": (len(view_times) if (view_times is not None and osc_section.get("view_sampled"))
                              else w.get("bars", n)),
                     "time_from": w.get("time_from"),
                     "time_to": w.get("time_to")}
    return out
