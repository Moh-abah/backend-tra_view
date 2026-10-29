# app/market/indicator_scheduler.py
from typing import Dict, List
from app.markets.candle_store import CandleStore
from app.markets.models import Candle
from app.services.indicators import apply_indicators

class IndicatorScheduler:
    def __init__(self, store: CandleStore):
        self.store = store
        self.active_indicators: Dict[str, List[dict]] = {}
        self.results_cache: Dict[str, Dict] = {}
        self.on_update = None  # callback

    def register_indicators(
        self,
        symbol: str,
        timeframe: str,
        indicators: List[dict]
    ):
        key = f"{symbol}:{timeframe}"
        self.active_indicators[key] = indicators


    def set_on_update(self, callback):
        self.on_update = callback



    def on_candle_close(self, candle: Candle):
        key = f"{candle.symbol}:{candle.timeframe}"

        # حفظ الشمعة
        self.store.add(candle)

        # لا مؤشرات؟ نخرج
        if key not in self.active_indicators:
            return

        df = self.store.to_dataframe(candle.symbol, candle.timeframe)
        if df.empty:
            return

        indicators_config = self.active_indicators[key]

        results = apply_indicators(
            dataframe=df,
            indicators_config=indicators_config,
            use_cache=False,
            parallel=True
        )

        self.results_cache[key] = {
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "last_candle": candle.to_dict(),
            "indicators": results
        }

        if self.on_update:
            self.on_update(candle.symbol, candle.timeframe)        
