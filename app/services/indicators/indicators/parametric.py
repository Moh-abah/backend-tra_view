"""Parametric & missing indicators registration.

✅ إصلاح: كانت استراتيجيات النظام المدمجة تشير إلى أسماء مؤشرات غير مسجلة
(ema_20 / ema_50 / ema_200 / sma_50 / adx) فترجع قيمها None بصمت وتفشل
الاستراتيجيات كلياً. هنا:
  1. تسجيل دواليّ ema_N / sma_N للفترات الشائعة (تقبل تجاوز period من params)
  2. تنفيذ ADX الحقيقي (Wilder) — كان مفقوداً رغم اعتماد استراتيجية Trend عليه
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from ..base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from ..registry import IndicatorRegistry
from .indicators import EMAIndicator, SMAIndicator, BollingerBandsIndicator


def _bind_period(cls, period: int):
    """ينشئ صنفاً فرعياً يحقن period الافتراضي عند غيابه في params."""

    class _Bound(cls):
        def __init__(self, config: IndicatorConfig):
            if not config.params or not config.params.get("period"):
                merged = dict(config.params or {})
                merged["period"] = period
                config = config.model_copy(update={"params": merged})
            super().__init__(config)

    _Bound.__name__ = f"{cls.__name__}_{period}"
    _Bound.__qualname__ = _Bound.__name__
    return _Bound


# --- EMA periods used by the builtin strategies -----------------------------
for _p in (20, 50, 100, 200):
    IndicatorRegistry.register(
        name=f"ema_{_p}",
        display_name=f"EMA {_p}",
        description=f"المتوسط المتحرك الأسي بفترة {_p}",
        category=IndicatorType.TREND,
    )(_bind_period(EMAIndicator, _p))

# --- SMA periods used by the builtin strategies -----------------------------
for _p in (50, 100, 200):
    IndicatorRegistry.register(
        name=f"sma_{_p}",
        display_name=f"SMA {_p}",
        description=f"المتوسط المتحرك البسيط بفترة {_p}",
        category=IndicatorType.TREND,
    )(_bind_period(SMAIndicator, _p))


@IndicatorRegistry.register(
    name="adx",
    display_name="ADX",
    description="مؤشر متوسط الحركة الاتجاهي (Wilder) مع DI+/DI- في metadata",
    category=IndicatorType.TREND,
)
class ADXIndicator(BaseIndicator):
    """ADX — متوسط الحركة الاتجاهي بتنعيم Wilder المعياري."""

    @classmethod
    def get_default_params(cls) -> Dict[str, Any]:
        return {"period": 14}

    @classmethod
    def get_required_columns(cls) -> List[str]:
        return ["high", "low", "close"]

    def calculate(self, data: pd.DataFrame) -> IndicatorResult:
        period = int(self.params.get("period", 14))

        up_move = data["high"].diff()
        down_move = -data["low"].diff()
        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
            index=data.index,
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
            index=data.index,
        )

        prev_close = data["close"].shift(1)
        tr = pd.concat(
            [
                data["high"] - data["low"],
                (data["high"] - prev_close).abs(),
                (data["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        alpha = 1.0 / period  # تنعيم Wilder
        atr = tr.ewm(alpha=alpha, adjust=False).mean()
        with np.errstate(divide="ignore", invalid="ignore"):
            plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False).mean() / atr
            minus_di = 100 * minus_dm.ewm(alpha=alpha, adjust=False).mean() / atr
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = dx.ewm(alpha=alpha, adjust=False).mean()

        return IndicatorResult(
            name=self.name,
            values=adx,
            signals=None,
            metadata={
                "period": period,
                "plus_di": plus_di.tolist(),
                "minus_di": minus_di.tolist(),
                "smoothing": "wilder_rma",
            },
        )


# --- Standalone Bollinger bands (lower/upper) --------------------------------
# تسمح للاستراتيجيات بمقارنة السعر بالنطاق مباشرة عبر
# price:close مقابل indicator:bollinger_lower / bollinger_upper
class _BollingerBandBase(BollingerBandsIndicator):
    def __init__(self, config: IndicatorConfig):
        super().__init__(config)

    def calculate(self, data: pd.DataFrame) -> IndicatorResult:
        period = int(self.params.get("period", 20))
        std_dev = float(self.params.get("std", 2.0))
        sma = data["close"].rolling(window=period).mean()
        sd = data["close"].rolling(window=period).std(ddof=0)
        if self.name == "bollinger_lower":
            values = sma - std_dev * sd
        else:
            values = sma + std_dev * sd
        return IndicatorResult(
            name=self.name,
            values=values,
            signals=None,
            metadata={"period": period, "std": std_dev, "band": self.name.split("_")[1]},
        )


for _band in ("bollinger_lower", "bollinger_upper"):
    IndicatorRegistry.register(
        name=_band,
        display_name=f"Bollinger {_band.split('_')[1].title()}",
        description=f"النطاق {_band.split('_')[1]} لبولينجر كمؤشر مستقل قابل للمقارنة مع السعر",
        category=IndicatorType.VOLATILITY,
    )(_BollingerBandBase)
