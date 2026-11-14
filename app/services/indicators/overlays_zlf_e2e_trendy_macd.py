# =============================================================================
# ✅ PRO73-R2 — ZLF-End-To-End-Trendy-MACDized — «الترندية الماكدية»
# =============================================================================
# أمر صاحب القرار (2026-11-13): «سوي استراتيجية مستنبطة من الترندية البطل
#   والملتهبة… وادمج عليها الموشرات (RSI/MACD/Momentum نسخ متعددة فريمات
#   متعددة)… وسمّ إصداراً "ترنديه ماكديه"… تكون فيها كل البيانات — المحرك
#   عباره عن الترندية ولكن مع الدمج والبيانات المرجعة كاملة مع الجديدة…
#   والشروط قابلة للتركيب (مثلاً S1 AND مع انطباق كل شروط الماكد والمومنتم
#   والآر إس آي)… وكل الإعدادات مضبوطة وقابلة للتعديل».
#
# هذا الملف = محرك معزول جديد كلياً فوق «الترندية» (لا يمسّها إطلاقاً):
#   1) يُشغّل محرك الترندية zigzag_fib_e2e_trendy حرفياً بمعاملاته كاملة
#      (الترندية تبقى كما هي بت-بت — S1/S2/S3 + بوابة الترند القالبية).
#   2) يحسب طبقة الدمج المشتركة (macdized_layer): أي عدد نسخ RSI/MACD/
#      Momentum، كل نسخة بفريمها الخاص من الـ14 (1s…1M) ومعاملاتها الخاصة —
#      كلها قالبية من التكوين بلا أرقام داخل الكود.
#   3) يطبّق بوابة الشروط القابلة للتركيب (osc_conditions — شجرة and/or/not
#      بأي عمق) لحظة كل إشارة: الدخول النهائي = إشارة الترندية المبوّبة
#      ∧ انطباق كل شروط الموشرات عند شمعة الإشارة نفسها (سببية كاملة).
#
# الشفافية الرباعية (امتداد ثلاثية الترندية):
#   zzfetm_entry_raw_s{n}     = الخام (قبل بوابة الترند — كما في الترندية)
#   zzfetm_entry_blocked_s{n} = خام منعها الترند (كما في الترندية)
#   zzfetm_entry_iblocked_s{n}= عبرت بوابة الترند لكن شروط الموشرات منعتها (جديد)
#   zzfetm_entry_s{n}         = النهائي (ترند ∧ موشرات)
#
# عقد التمايز (صفر تداخل مع zzf_*/zzfe_*/zzfet_*/zzfb_*/trf_*):
#   سلاسل zzfetm_* → أعمدة ind_zzfetm_* · إشارات "ZLF-E2E-Trendy-MACD ..."
#   indicator: zigzag_fib_e2e_trendy_macd · base: zzfib_e2e_trendy_macd
#   الحمولة كاملة: كل ما تعيده الترندية (نطاقات/أرجل/محاور/ترند/سيولة/
#   current/levels) + قسم الموشرات الجديد + سلاسلها على نفس الشموع.
#
# إيقاف البوابة (osc_instances فارغة أو osc_conditions غائبة) = تمرير كامل
#   → تطابق بت-بت مع الترندية (مفتاح A/B للتحقق — مثبت بالاختبارات).
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.services.indicators.overlays_zlf_e2e_trendy import (
    zigzag_fib_e2e_trendy,
    ZLF_E2E_TRENDY_ENGINE_NAME,
    ZLF_E2E_TRENDY_SPEC,
)
from app.services.indicators.mtf_oscillator_core import (
    MTF_OSC_CORE_SPEC,
    MTF_OSC_CORE_VERSION,
    OSC_KIND_FIELDS,
    macdized_layer,
)

__all__ = [
    "zigzag_fib_e2e_trendy_macd",
    "ZLF_E2E_TRENDY_MACD_ENGINE_NAME",
    "ZLF_E2E_TRENDY_MACD_SPEC",
]

# ---------------------------------------------------------------------------
# هوية المحرك المنفصل (عقد تمايز خامس — أسماء جديدة كلياً عن كل المحركات)
# ---------------------------------------------------------------------------
ZLF_E2E_TRENDY_MACD_ENGINE_NAME = "ZLF-E2E-Trendy-MACD"
ZLF_E2E_TRENDY_MACD_SPEC = "PRO73-trendy-macd"

ZLF_E2E_TRENDY_MACD_SIGNALS: List[int] = [1, 2, 3]  # s1/s2/s3 (وراثة الترندية)


def _mirror_series(base_series: Dict[str, Any], src_prefix: str, dst_prefix: str) -> Dict[str, List[Optional[float]]]:
    """سلاسل المحرك الأصل {src}_X → مرآة {dst}_X (نفس القيم بت-بت)."""
    out: Dict[str, List[Optional[float]]] = {}
    for key, vals in (base_series or {}).items():
        k = str(key)
        if not k.startswith(src_prefix):
            continue
        out[dst_prefix + k[len(src_prefix):]] = vals if vals is not None else []
    return out


def zigzag_fib_e2e_trendy_macd(
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
    osc_instances: Any = None,
    osc_conditions: Any = None,
) -> Dict[str, Any]:
    """«الترندية الماكدية» — الترندية بت-بت + مصفوفة الموشرات + بوابة الشروط القابلة للتركيب.

    المعاملات: نفس معاملات الترندية حرفياً (تُمرَّر إليها كما هي) +
      osc_instances:  قائمة نسخ الموشرات [{kind, id, timeframe, ...params}] —
                      RSI/MACD/Momentum بأي عدد نسخ و14 فريماً (قالبية كاملة).
      osc_conditions: شجرة الشروط القابلة للتركيب (and/or/not بأي عمق) —
                      الغائبة/الفارغة = تمرير كامل (هوية الترندية).
    """
    # ------------------------------------------------------------------
    # 1) الترندية كما هي — بمعاملاتها كاملة (لا أي مساس بها)
    # ------------------------------------------------------------------
    trendy = zigzag_fib_e2e_trendy(
        candles,
        length=length, reverse=reverse, levels=levels,
        extend_right=extend_right, extend_leg_to_live=extend_leg_to_live,
        mode=mode, depth=depth, deviation=deviation, backstep=backstep,
        launch_touch_ticks=launch_touch_ticks,
        trend_periods=trend_periods, trend_confirm=trend_confirm,
        trend_gate=trend_gate,
    )
    layer = macdized_layer(candles, osc_instances, osc_conditions)
    N = layer["N"]
    gate = layer["gate"]
    t_series = trendy.get("series") or {}

    # ------------------------------------------------------------------
    # 2) الطبقات الأربعة للدخول — خام/ترند-ممنوع/موشرات-ممنوع/نهائي
    # ------------------------------------------------------------------
    def _col(name: str) -> List[float]:
        v = t_series.get(name) or []
        out = [float(x) if x is not None else 0.0 for x in v]
        if len(out) < N:
            out = out + [0.0] * (N - len(out))
        return out[:N]

    e_final: List[float] = [0.0] * N
    e_iblocked: List[float] = [0.0] * N
    per_final: Dict[int, List[float]] = {n: [0.0] * N for n in ZLF_E2E_TRENDY_MACD_SIGNALS}
    per_iblocked: Dict[int, List[float]] = {n: [0.0] * N for n in ZLF_E2E_TRENDY_MACD_SIGNALS}
    n_trend_entries = 0
    n_final_entries = 0
    n_iblocked = 0

    for n in ZLF_E2E_TRENDY_MACD_SIGNALS:
        raw_col = _col(f"zzfet_entry_s{n}")  # دخول الترندية (بعد بوابة الترند)
        for i in range(N):
            if raw_col[i] >= 0.5:
                n_trend_entries += 1
                if gate[i]:
                    per_final[n][i] = 1.0
                    e_final[i] = 1.0
                    n_final_entries += 1
                else:
                    per_iblocked[n][i] = 1.0
                    e_iblocked[i] = 1.0
                    n_iblocked += 1

    # ------------------------------------------------------------------
    # 3) الإشارات — كل إشارات الترندية + تحويل الدخول عبر بوابة الموشرات
    # ------------------------------------------------------------------
    signals: List[Dict[str, Any]] = []
    for sig in (trendy.get("signals") or []):
        s2 = dict(sig)
        s2["engine"] = ZLF_E2E_TRENDY_MACD_ENGINE_NAME
        side = str(sig.get("side") or "")
        if side == "buy":
            bar = int(sig.get("bar") or 0)
            g = bool(gate[bar]) if 0 <= bar < N else False
            states = sig.get("states") or []
            n_kind = int(states[0]) if states else 0
            if g:
                s2["signal"] = f"ZLF-E2E-Trendy-MACD Entry S{n_kind}"
                s2["osc_gate"] = True
                s2["trend_gate_passed"] = True
            else:
                s2["side"] = "osc_blocked"
                s2["signal"] = f"ZLF-E2E-Trendy-MACD EntryBlocked S{n_kind} (osc conditions)"
                s2["osc_gate"] = False
                s2["trend_gate_passed"] = True
        else:
            s2["signal"] = str(sig.get("signal") or "").replace(
                "ZLF-E2E-Trendy", "ZLF-E2E-Trendy-MACD", 1)
        signals.append(s2)
    signals.sort(key=lambda s: s.get("bar", 0))

    # ------------------------------------------------------------------
    # 4) السلاسل — مرآة الترندية الكاملة (zzfetm_*) + الموشرات + البوابة
    # ------------------------------------------------------------------
    merged_series: Dict[str, List[Any]] = _mirror_series(t_series, "zzfet_", "zzfetm_")
    # الطبقات النهائية تحل محل مرآة zzfet_entry_* الأصلية
    merged_series["zzfetm_entry"] = e_final
    merged_series["zzfetm_entry_iblocked"] = e_iblocked
    for n in ZLF_E2E_TRENDY_MACD_SIGNALS:
        merged_series[f"zzfetm_entry_s{n}"] = per_final[n]
        merged_series[f"zzfetm_entry_iblocked_s{n}"] = per_iblocked[n]
        # raw/blocked ترث من المرآة (zzfetm_entry_raw_s{n} / zzfetm_entry_blocked_s{n})
    merged_series["zzfetm_osc_gate"] = layer["gate_list"]
    # سلاسل الموشرات — zzfetm_osc_<id>_<field>
    for iid, fields in (layer["osc_json"] or {}).items():
        for f, vals in fields.items():
            merged_series[f"zzfetm_osc_{iid}_{f}"] = vals if vals is not None else []

    # ------------------------------------------------------------------
    # 5) الحمولة الكاملة — كل بيانات الترندية المرجعة + قسم الموشرات الجديد
    # ------------------------------------------------------------------
    osc = layer["osc"]
    out: Dict[str, Any] = dict(trendy)  # legs/pivots/ranges/current/trend/liquidity...
    out.update({
        "name": "ZigZag Fib E2E Trendy-MACDized (ZLF-End-To-End-Trendy-MACD — الترندية الماكدية · S1/S2/S3 + بوابة الموشرات)",
        "engine": ZLF_E2E_TRENDY_MACD_ENGINE_NAME,
        "spec": ZLF_E2E_TRENDY_MACD_SPEC,
        "base_engine": {
            "name": ZLF_E2E_TRENDY_ENGINE_NAME,
            "spec": ZLF_E2E_TRENDY_SPEC,
            "note": "الترندية تعمل كما هي بت-بت — هذا المحرك فوقها فقط (دمج + بوابة موشرات)",
        },
        "params": dict(trendy.get("params") or {}),
        "signals": signals,
        "series": merged_series,
        "osc": {
            "enabled": True,
            "engine": MTF_OSC_CORE_SPEC,
            "version": MTF_OSC_CORE_VERSION,
            "base_tf": osc.get("base_tf"),
            "bars": osc.get("bars"),
            "instances": osc.get("instances") or [],
            "conditions": layer["tree"],
            "warnings": layer["warnings"],
            "fields_per_kind": {k: list(v) for k, v in OSC_KIND_FIELDS.items()},
            "rule": "الدخول النهائي = إشارة الترندية المبوّبة (بوابة الترند) ∧ انطباق شجرة شروط "
                    "الموشرات القابلة للتركيب (and/or/not بأي عمق) عند شمعة الإشارة نفسها — "
                    "المرجع: osc:<id>.<field> أو price:<عمود> أو رقم · المعاملات: > >= < <= == != "
                    "cross_above cross_below · فترات إحماء الموشرات تحجب (NaN → False) — سببية كاملة",
            "counts": {
                "trend_entries": n_trend_entries,
                "final_entries": n_final_entries,
                "osc_blocked_entries": n_iblocked,
            },
            "gate_open": layer["tree"] is None,
        },
        "notes": "ZLF-End-To-End-Trendy-MACD — «الترندية الماكدية» (PRO73): الترندية بت-بت "
                 "(S1/S2/S3 + بوابة الترند القالبية) + مصفوفة موشرات متعددة النسخ والفريمات "
                 "(RSI/MACD/Momentum × 14 فريماً — نواة mtf_oscillator_core) + بوابة شروط قابلة "
                 "للتركيب فوق إشارات الدخول. كل الأسماء بعقد تمايز جديد (zzfetm_*/ind_zzfetm_*) "
                 "— صفر تداخل مع zzf_*/zzfe_*/zzfet_*/zzfb_*/trf_*. الشفافية الرباعية: "
                 "entry_raw (خام) / entry_blocked (منعها الترند) / entry_iblocked (منعتها "
                 "الموشرات) / entry (النهائي). إيقاف البوابة = هوية الترندية بت-بت.",
    })
    return out


# ---------------------------------------------------------------------------
# ✅ التسجيل الذاتي كمؤشر منفصل — zigzag_fib_e2e_trendy_macd
# ---------------------------------------------------------------------------
def _register_trendy_macd_indicator() -> None:
    try:
        from .base import BaseIndicator, IndicatorResult, IndicatorType
        from .registry import IndicatorRegistry
        import pandas as pd

        class ZigZagFibE2ETrendyMACDIndicator(BaseIndicator):
            """«الترندية الماكدية» — الترندية + موشرات متعددة النسخ/الفريمات + بوابة شروط قابلة للتركيب."""

            @classmethod
            def get_required_columns(cls):
                return ["open", "high", "low", "close"]

            def calculate(self, data: pd.DataFrame) -> IndicatorResult:
                from .overlay_columns import config_to_overlay_params
                conv = config_to_overlay_params({
                    "name": "zigzag_fib_e2e_trendy_macd",
                    "params": dict(self.params or {}),
                }) or {"zzfib_e2e_trendy_macd": {}}
                params = conv.get("zzfib_e2e_trendy_macd") or {}
                res = zigzag_fib_e2e_trendy_macd(data, **params)
                values = res["series"].get("zzfetm_entry") or [None] * len(data)
                series = pd.Series(values, index=data.index, dtype=object)
                return IndicatorResult(
                    name=self.name,
                    values=series,
                    signals=None,
                    metadata={
                        "engine": ZLF_E2E_TRENDY_MACD_ENGINE_NAME,
                        "overlay": "zzfib_e2e_trendy_macd",
                        "primary_column": "ind_zzfetm_entry",
                        "available_columns": sorted(res["series"].keys()),
                    },
                )

        IndicatorRegistry.register(
            "zigzag_fib_e2e_trendy_macd",
            display_name="ZLF-E2E-Trendy-MACD — الترندية الماكدية (S1/S2/S3 + موشرات متعددة النسخ/الفريمات)",
            description="المحرك (PRO73): الترندية بت-بت (S1/S2/S3 + بوابة الترند القالبية "
                        "فترات [7,15,25] majority) + مصفوفة موشرات RSI/MACD/Momentum بأي عدد "
                        "نسخ، كل نسخة بفريمها الخاص من الـ14 (1s·5s·30s·1m·5m·15m·1h·4h·1d·2d·3d·"
                        "1w·2w·1M) ومعاملاتها الخاصة (period/ma_length · fast/slow/signal · "
                        "length) — كلها قالبية من التكوين. بوابة شروط قابلة للتركيب "
                        "(and/or/not بأي عمق؛ المرجع osc:<id>.<field> أو price:<عمود> أو رقم؛ "
                        "المعاملات > >= < <= == != cross_above cross_below) تُطبَّق لحظة كل إشارة. "
                        "العمود الأساسي: ind_zzfetm_entry · الممنوع بالموشرات ind_zzfetm_entry_iblocked_s1|s2|s3 "
                        "· سلاسل الموشرات ind_zzfetm_osc_<id>_<field>.",
            category=IndicatorType.SUPPORT_RESISTANCE,
        )(ZigZagFibE2ETrendyMACDIndicator)

        info = IndicatorRegistry._indicators.get("zigzag_fib_e2e_trendy_macd")
        if info is not None:
            IndicatorRegistry._indicators.setdefault("zzfib_e2e_trendy_macd", info)
    except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
        import logging
        logging.getLogger(__name__).exception("ZLF-E2E-Trendy-MACD indicator registration failed")


_register_trendy_macd_indicator()
