from datetime import datetime
from typing import Literal


class SignalEvaluationResult:
    signal: Literal["buy", "sell", "hold", None]
    candle_time: datetime
    indicator_values: dict
    conditions_met: list[str]
