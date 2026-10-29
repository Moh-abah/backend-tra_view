# # app/services/indicators/indicators.py
# import numpy as np
# import pandas as pd
# from typing import Dict, Any, List
# from .base import BaseIndicator, IndicatorResult, IndicatorConfig
# from .registry import IndicatorRegistry

# # SMA
# @IndicatorRegistry.register(name="sma", display_name="SMA", description="Simple MA")
# class SMAIndicator(BaseIndicator):
#     @classmethod
#     def get_default_params(cls): return {"period": 20}
#     @classmethod
#     def get_required_columns(cls): return ["close"]
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         p = int(self.params.get("period", 20))
#         s = data["close"].rolling(window=p, min_periods=1).mean()
#         s.name = f"sma_{p}"
#         return IndicatorResult(name=self.name, series={"sma": s}, metadata={"period": p})

# # EMA
# @IndicatorRegistry.register(name="ema", display_name="EMA", description="Exponential MA")
# class EMAIndicator(BaseIndicator):
#     @classmethod
#     def get_default_params(cls): return {"period": 20}
#     @classmethod
#     def get_required_columns(cls): return ["close"]
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         p = int(self.params.get("period", 20))
#         s = data["close"].ewm(span=p, adjust=False).mean()
#         s.name = f"ema_{p}"
#         return IndicatorResult(name=self.name, series={"ema": s}, metadata={"period": p})

# # RSI (Wilder smoothing)
# @IndicatorRegistry.register(name="rsi", display_name="RSI", description="Relative Strength Index")
# class RSIIndicator(BaseIndicator):
#     @classmethod
#     def get_default_params(cls): return {"period": 14, "overbought": 70, "oversold": 30}
#     @classmethod
#     def get_required_columns(cls): return ["close"]

#     def _wilder(self, s: pd.Series, period: int) -> pd.Series:
#         return s.ewm(alpha=1.0/period, adjust=False).mean()

#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         p = int(self.params.get("period", 14))
#         ob = float(self.params.get("overbought", 70))
#         os = float(self.params.get("oversold", 30))

#         close = data["close"]
#         delta = close.diff()
#         gain = delta.clip(lower=0).fillna(0)
#         loss = -delta.clip(upper=0).fillna(0)

#         avg_gain = self._wilder(gain, p)
#         avg_loss = self._wilder(loss, p)

#         with np.errstate(divide='ignore', invalid='ignore'):
#             rs = avg_gain / avg_loss
#             rsi = 100 - (100 / (1 + rs))

#         # edge-cases
#         rsi[(avg_loss == 0) & (avg_gain > 0)] = 100
#         rsi[(avg_gain == 0) & (avg_loss > 0)] = 0
#         rsi[(avg_gain == 0) & (avg_loss == 0)] = 50

#         rsi = rsi.reindex(close.index).fillna(50)
#         rsi.name = f"rsi_{p}"

#         return IndicatorResult(name=self.name, series={"rsi": rsi}, levels={"overbought": ob, "oversold": os}, metadata={"period": p})

# # MACD
# @IndicatorRegistry.register(name="macd", display_name="MACD", description="MACD")
# class MACDIndicator(BaseIndicator):
#     @classmethod
#     def get_default_params(cls): return {"fast": 12, "slow": 26, "signal": 9}
#     @classmethod
#     def get_required_columns(cls): return ["close"]
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         fast = int(self.params.get("fast", 12)); slow = int(self.params.get("slow", 26)); sig = int(self.params.get("signal", 9))
#         ema_fast = data["close"].ewm(span=fast, adjust=False).mean()
#         ema_slow = data["close"].ewm(span=slow, adjust=False).mean()
#         macd = ema_fast - ema_slow
#         signal = macd.ewm(span=sig, adjust=False).mean()
#         hist = macd - signal
#         macd.name="macd"; signal.name="macd_signal"; hist.name="macd_hist"
#         return IndicatorResult(name=self.name, series={"macd": macd, "signal": signal, "hist": hist}, metadata={"fast": fast,"slow": slow,"signal": sig})

# # Bollinger
# @IndicatorRegistry.register(name="bb", display_name="Bollinger", description="Bollinger Bands")
# class BollingerIndicator(BaseIndicator):
#     @classmethod
#     def get_default_params(cls): return {"period":20,"std":2}
#     @classmethod
#     def get_required_columns(cls): return ["close"]
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         p = int(self.params.get("period",20)); sd = float(self.params.get("std",2))
#         mid = data["close"].rolling(p, min_periods=1).mean()
#         rstd = data["close"].rolling(p, min_periods=1).std().fillna(0)
#         up = mid + (rstd * sd); low = mid - (rstd * sd)
#         mid.name="bb_mid"; up.name="bb_up"; low.name="bb_low"
#         return IndicatorResult(name=self.name, series={"mid": mid, "upper": up, "lower": low}, metadata={"period":p,"std":sd})

# # ATR
# @IndicatorRegistry.register(name="atr", display_name="ATR", description="Average True Range")
# class ATRIndicator(BaseIndicator):
#     @classmethod
#     def get_default_params(cls): return {"period":14}
#     @classmethod
#     def get_required_columns(cls): return ["high","low","close"]
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         p = int(self.params.get("period",14))
#         high_low = data["high"] - data["low"]
#         high_close = (data["high"] - data["close"].shift(1)).abs()
#         low_close = (data["low"] - data["close"].shift(1)).abs()
#         tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
#         atr = tr.rolling(window=p, min_periods=1).mean()
#         atr.name="atr"
#         return IndicatorResult(name=self.name, series={"atr": atr}, metadata={"period": p})

# # VWAP
# @IndicatorRegistry.register(name="vwap", display_name="VWAP", description="Volume Weighted Average Price")
# class VWAPIndicator(BaseIndicator):
#     @classmethod
#     def get_default_params(cls): return {"period":20}
#     @classmethod
#     def get_required_columns(cls): return ["high","low","close","volume"]
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         p = int(self.params.get("period",20))
#         tp = (data["high"] + data["low"] + data["close"]) / 3.0
#         tpv = tp * data["volume"]
#         tpv_sum = tpv.rolling(window=p, min_periods=1).sum()
#         vol_sum = data["volume"].rolling(window=p, min_periods=1).sum().replace(0, np.nan)
#         vwap = tpv_sum / vol_sum
#         vwap.name="vwap"
#         return IndicatorResult(name=self.name, series={"vwap": vwap}, metadata={"period": p})

# # OBV
# @IndicatorRegistry.register(name="obv", display_name="OBV", description="On-Balance Volume")
# class OBVIndicator(BaseIndicator):
#     @classmethod
#     def get_default_params(cls): return {}
#     @classmethod
#     def get_required_columns(cls): return ["close","volume"]
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         close = data["close"].values; vol = data["volume"].values
#         obv = np.zeros(len(data), dtype=float)
#         for i in range(1, len(data)):
#             if close[i] > close[i-1]: obv[i] = obv[i-1] + vol[i]
#             elif close[i] < close[i-1]: obv[i] = obv[i-1] - vol[i]
#             else: obv[i] = obv[i-1]
#         s = pd.Series(obv, index=data.index); s.name="obv"
#         return IndicatorResult(name=self.name, series={"obv": s}, metadata={})

# # Pivot Points
# @IndicatorRegistry.register(name="pivot_points", display_name="Pivot Points", description="Pivot Points (support/resistance)")
# class PivotIndicator(BaseIndicator):
#     @classmethod
#     def get_default_params(cls): return {"method":"standard"}
#     @classmethod
#     def get_required_columns(cls): return ["high","low","close"]
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         method = str(self.params.get("method","standard"))
#         highs = data["high"].values; lows = data["low"].values; closes = data["close"].values
#         n = len(data)
#         pivot = np.zeros(n); r1 = np.zeros(n); s1 = np.zeros(n)
#         for i in range(1, n):
#             prev_h = highs[i-1]; prev_l = lows[i-1]; prev_c = closes[i-1]
#             p = (prev_h + prev_l + prev_c) / 3.0
#             pivot[i] = p
#             if method == "standard":
#                 r1[i] = (2*p) - prev_l; s1[i] = (2*p) - prev_h
#             else:
#                 r1[i] = p + 0.382*(prev_h - prev_l); s1[i] = p - 0.382*(prev_h - prev_l)
#         ps = pd.Series(pivot, index=data.index); r1s = pd.Series(r1, index=data.index); s1s = pd.Series(s1, index=data.index)
#         ps.name="pivot"; r1s.name="resistance1"; s1s.name="support1"
#         return IndicatorResult(name=self.name, series={"pivot": ps, "resistance1": r1s, "support1": s1s}, metadata={"method": method})
