from dataclasses import dataclass
import pandas as pd
from typing import Dict

@dataclass
class StrategyContext:
    symbol: str
    timeframe: str
    data: pd.DataFrame
    indicators: Dict[str, pd.Series]
