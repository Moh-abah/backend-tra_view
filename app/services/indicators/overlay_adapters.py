# =============================================================================
# ✅ الجولة 11 (v2) — تسجيل مؤشرات البنية في سجل المؤشرات الكلاسيكي
# =============================================================================
# يُستورد مرة واحدة من app/services/indicators/__init__.py — يسجّل الأسماء
# الثلاثة (بصيغتيها القصيرة والكاملة) في IndicatorRegistry كي:
#   - تظهر في GET /api/v1/indicators/available
#   - يقبلها IndicatorConfig مع type="support_resistance"
#   - يجتازها فحص validate (is_known_indicator_name)
#
# المسار الحسابي الفعلي داخل محرك الاستراتيجيات يمر عبر جسر calculator.py
# وأعمدة overlay_columns.py (أدق وأغنى) — هذه المحوّلات تعطي السلسلة
# الأساسية التعاقدية لأي مسار عام آخر (حاسبة المؤشرات العامة مثلًا).
# =============================================================================

from typing import Any, Dict

import pandas as pd

from .base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from .registry import IndicatorRegistry
from .overlay_columns import columns_from_overlays_result
from .overlays import compute_overlays

__all__ = [
    "ZigZagChannelsIndicator",
    "AutoFibRetracementIndicator",
    "AutoTrendlineIndicator",
    "register_overlay_indicators",
]


class _OverlayIndicatorBase(BaseIndicator):
    """أساس مشترك: يحسب عبر compute_overlays ويعيد العمود التعاقدي الأساسي."""

    BASE: str = ""
    PRIMARY_COLUMN: str = ""

    @classmethod
    def get_required_columns(cls):
        return ["open", "high", "low", "close"]

    def _kw_from_params(self) -> Dict[str, Any]:
        p = dict(self.params or {})
        out: Dict[str, Any] = {}

        def _num(aliases, cast=float):
            for k in aliases:
                if k in p:
                    try:
                        return cast(p[k])
                    except (TypeError, ValueError):
                        continue
            return None

        if self.BASE == "zigzag":
            v = _num(("length",), int)
            if v is not None:
                out["length"] = max(2, v)
        elif self.BASE == "fib":
            v = _num(("depth",), int)
            if v is not None:
                out["depth"] = max(1, v)
            v = _num(("dev_threshold", "dev", "deviation", "deviation_threshold"))
            if v is not None:
                out["dev_threshold"] = v
            v = _num(("retracement", "ret", "target_ratio"))
            if v is not None:
                out["retracement"] = v
            lv = p.get("level_ratios", p.get("levels"))
            if isinstance(lv, (list, tuple)) and lv:
                try:
                    out["level_ratios"] = [float(x) for x in lv]
                except (TypeError, ValueError):
                    pass
            for k in ("reverse", "extend_left", "extend_right"):
                if k in p:
                    out[k] = bool(p[k])
        else:
            v = _num(("period", "n", "fractal_period"), int)
            if v is not None:
                out["period"] = max(2, v)
            v = _num(("max_pairs", "pairs", "max_tl"), int)
            if v is not None:
                out["max_pairs"] = max(1, v)
            if "extend" in p:
                out["extend"] = str(p["extend"])
        return out

    def calculate(self, data: pd.DataFrame) -> IndicatorResult:
        res = compute_overlays(data, types=[self.BASE], params={self.BASE: self._kw_from_params()})
        cols = columns_from_overlays_result(res)
        values = cols.get(self.PRIMARY_COLUMN) or [None] * len(data)
        series = pd.Series(values, index=data.index, dtype=object)
        return IndicatorResult(
            name=self.name,
            values=series,
            signals=None,
            metadata={
                "overlay": self.BASE,
                "primary_column": self.PRIMARY_COLUMN,
                "available_columns": cols and sorted(cols.keys()),
                "engine": "overlays_v2 (الجولة 11)",
            },
        )


@IndicatorRegistry.register(
    "zigzag_channels",
    display_name="Zig Zag Channels [LuxAlgo]",
    description="قنوات الزيجزاج: قمم/قيعان مؤكدة + خطوط انحراف متوازية. العمود الأساسي: ind_zz_pivot (+1 قمة مؤكدة / -1 قاع مؤكد). © LuxAlgo — CC BY-NC-SA 4.0",
    category=IndicatorType.SUPPORT_RESISTANCE,
)
class ZigZagChannelsIndicator(_OverlayIndicatorBase):
    BASE = "zigzag"
    PRIMARY_COLUMN = "ind_zz_pivot"

    @classmethod
    def get_default_params(cls):
        return {"length": 100, "extend": True, "show_ext": True, "show_labels": True}


@IndicatorRegistry.register(
    "auto_fib_retracement",
    display_name="Auto Fib Retracement Alerts",
    description="فيبوناتشي تلقائي بأرجل متعاقبة وإشارات ارتداد. العمود الأساسي: ind_fib_signal (+1 Buy Retrace / -1 Sell Retrace). © LucemAnb — MPL-2.0",
    category=IndicatorType.SUPPORT_RESISTANCE,
)
class AutoFibRetracementIndicator(_OverlayIndicatorBase):
    BASE = "fib"
    PRIMARY_COLUMN = "ind_fib_signal"

    @classmethod
    def get_default_params(cls):
        return {"depth": 10, "dev_threshold": 5.0, "retracement": 0.618, "extend_left": False, "extend_right": True}


@IndicatorRegistry.register(
    "auto_trendline",
    display_name="Auto Trendline [DojiEmoji]",
    description="خطوط اتجاه تلقائية من الفراكتالات مع كشف التقاطعات. العمود الأساسي: ind_atl_signal (+1 قطع العلوي لأعلى / -1 كسر السفلي لأسفل). © DojiEmoji — MPL-2.0",
    category=IndicatorType.SUPPORT_RESISTANCE,
)
class AutoTrendlineIndicator(_OverlayIndicatorBase):
    BASE = "trendline"
    PRIMARY_COLUMN = "ind_atl_signal"

    @classmethod
    def get_default_params(cls):
        return {"period": 10, "max_pairs": 1, "extend": "right"}


# أسماء قصيرة مرادفة (zigzag / fib / trendline) — نفس الفئات بالضبط
def register_overlay_indicators() -> None:
    """يسجّل المرادفات القصيرة على نفس الفئات (استدعاء واحد عند الإقلاع)."""
    for short, full in (
        ("zigzag", "zigzag_channels"),
        ("fib", "auto_fib_retracement"),
        ("trendline", "auto_trendline"),
    ):
        info = IndicatorRegistry._indicators.get(full)
        if info is None:
            continue
        IndicatorRegistry._indicators.setdefault(short, info)


register_overlay_indicators()
