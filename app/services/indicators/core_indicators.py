# import pandas as pd
# import numpy as np
# from typing import Dict, Any, List
# from .base import BaseIndicator, IndicatorResult, IndicatorConfig, IndicatorType
# from .registry import IndicatorRegistry

# # ====================== مؤشرات الاتجاه ======================

# @IndicatorRegistry.register(
#     name="sma",
#     display_name="SMA",
#     description="المتوسط المتحرك البسيط",
#     category=IndicatorType.TREND
# )
# class SMAIndicator(BaseIndicator):
#     """المتوسط المتحرك البسيط"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {"period": 20}
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['close']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         period = self.params.get("period", 20)
#         values = data['close'].rolling(window=period).mean()
        
#         return IndicatorResult(
#             name=self.name,
#             values=values,
#             metadata={"period": period}
#         )



# @IndicatorRegistry.register(
#     name="sma_fast",
#     display_name="SMA Fast",
#     description="المتوسط المتحرك البسيط السريع",
#     category=IndicatorType.TREND
# )
# class SMAFastIndicator(BaseIndicator):
#     """SMA سريع (فترة قصيرة)"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {"period": 10}
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['close']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         period = self.params.get("period", 10)
#         values = data['close'].rolling(window=period).mean()
        
#         return IndicatorResult(
#             name=self.name,
#             values=values,
#             metadata={"period": period}
#         )

# @IndicatorRegistry.register(
#     name="sma_slow",
#     display_name="SMA Slow",
#     description="المتوسط المتحرك البسيط البطيء",
#     category=IndicatorType.TREND
# )
# class SMASlowIndicator(BaseIndicator):
#     """SMA بطيء (فترة طويلة)"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {"period": 20}
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['close']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         period = self.params.get("period", 20)
#         values = data['close'].rolling(window=period).mean()
        
#         return IndicatorResult(
#             name=self.name,
#             values=values,
#             metadata={"period": period}
#         )

# @IndicatorRegistry.register(
#     name="ema",
#     display_name="EMA",
#     description="المتوسط المتحرك الأسي",
#     category=IndicatorType.TREND
# )
# class EMAIndicator(BaseIndicator):
#     """المتوسط المتحرك الأسي"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {"period": 20}
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['close']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         period = self.params.get("period", 20)
#         values = data['close'].ewm(span=period, adjust=False).mean()
        
#         return IndicatorResult(
#             name=self.name,
#             values=values,
#             metadata={"period": period}
#         )

# @IndicatorRegistry.register(
#     name="wma",
#     display_name="WMA",
#     description="المتوسط المتحرك المرجح",
#     category=IndicatorType.TREND
# )
# class WMAIndicator(BaseIndicator):
#     """المتوسط المتحرك المرجح"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {"period": 20}
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['close']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         period = self.params.get("period", 20)
        
#         def wma(series):
#             weights = np.arange(1, period + 1)
#             return np.dot(series[-period:], weights) / weights.sum()
        
#         values = data['close'].rolling(window=period).apply(wma, raw=True)
        
#         return IndicatorResult(
#             name=self.name,
#             values=values,
#             metadata={"period": period}
#         )

# # ====================== مؤشرات الزخم ======================

# @IndicatorRegistry.register(
#     name="rsi",
#     display_name="RSI",
#     description="مؤشر القوة النسبية",
#     category=IndicatorType.MOMENTUM
# )
# class RSIIndicator(BaseIndicator):
#     """مؤشر القوة النسبية"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {
#             "period": 14,
#             "overbought": 70,
#             "oversold": 30
#         }
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['close']
    
#     def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
#         """حساب RSI"""
#         delta = prices.diff()
#         gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
#         loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
#         rs = gain / loss
#         rsi = 100 - (100 / (1 + rs))
        
#         return rsi
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         period = self.params.get("period", 14)
#         overbought = self.params.get("overbought", 70)
#         oversold = self.params.get("oversold", 30)
        
#         rsi_values = self._calculate_rsi(data['close'], period)
        
#         # توليد إشارات
#         signals = pd.Series(0, index=rsi_values.index)
#         signals[rsi_values > overbought] = -1  # بيع (مشترى زائد)
#         signals[rsi_values < oversold] = 1     # شراء (مباع زائد)
        
#         return IndicatorResult(
#             name=self.name,
#             values=rsi_values,
#             signals=signals,
#             metadata={
#                 "period": period,
#                 "overbought": overbought,
#                 "oversold": oversold
#             }
#         )

# @IndicatorRegistry.register(
#     name="macd",
#     display_name="MACD",
#     description="مؤشر التقارب والتباعد للمتوسطات المتحركة",
#     category=IndicatorType.MOMENTUM
# )
# class MACDIndicator(BaseIndicator):
#     """مؤشر MACD"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {
#             "fast": 12,
#             "slow": 26,
#             "signal": 9
#         }
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['close']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         fast_period = self.params.get("fast", 12)
#         slow_period = self.params.get("slow", 26)
#         signal_period = self.params.get("signal", 9)
        
#         # حساب المتوسطات المتحركة الأسية
#         ema_fast = data['close'].ewm(span=fast_period, adjust=False).mean()
#         ema_slow = data['close'].ewm(span=slow_period, adjust=False).mean()
        
#         # حساب MACD وخط الإشارة
#         macd_line = ema_fast - ema_slow
#         signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
#         histogram = macd_line - signal_line
        
#         # توليد إشارات
#         signals = pd.Series(0, index=macd_line.index)
#         cross_up = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
#         cross_down = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))
        
#         signals[cross_up] = 1    # إشارة شراء
#         signals[cross_down] = -1 # إشارة بيع
        
#         return IndicatorResult(
#             name=self.name,
#             values=macd_line,
#             signals=signals,
#             metadata={
#                 "macd_line": macd_line.tolist(),
#                 "signal_line": signal_line.tolist(),
#                 "histogram": histogram.tolist(),
#                 "fast": fast_period,
#                 "slow": slow_period,
#                 "signal": signal_period
#             }
#         )

# @IndicatorRegistry.register(
#     name="stochastic",
#     display_name="Stochastic",
#     description="المؤشر العشوائي",
#     category=IndicatorType.MOMENTUM
# )
# class StochasticIndicator(BaseIndicator):
#     """المؤشر العشوائي"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {
#             "k_period": 14,
#             "d_period": 3,
#             "smooth": 3,
#             "overbought": 80,
#             "oversold": 20
#         }
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['high', 'low', 'close']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         k_period = self.params.get("k_period", 14)
#         d_period = self.params.get("d_period", 3)
#         smooth = self.params.get("smooth", 3)
#         overbought = self.params.get("overbought", 80)
#         oversold = self.params.get("oversold", 20)
        
#         # حساب %K
#         low_min = data['low'].rolling(window=k_period).min()
#         high_max = data['high'].rolling(window=k_period).max()
        
#         k_line = 100 * ((data['close'] - low_min) / (high_max - low_min))
        
#         # تنعيم %K
#         k_smoothed = k_line.rolling(window=smooth).mean()
        
#         # حساب %D (متوسط %K)
#         d_line = k_smoothed.rolling(window=d_period).mean()
        
#         # توليد إشارات
#         signals = pd.Series(0, index=k_line.index)
#         signals[(k_smoothed < oversold) & (d_line < oversold)] = 1      # شراء
#         signals[(k_smoothed > overbought) & (d_line > overbought)] = -1 # بيع
        
#         return IndicatorResult(
#             name=self.name,
#             values=k_smoothed,
#             signals=signals,
#             metadata={
#                 "k_line": k_smoothed.tolist(),
#                 "d_line": d_line.tolist(),
#                 "k_period": k_period,
#                 "d_period": d_period,
#                 "smooth": smooth,
#                 "overbought": overbought,
#                 "oversold": oversold
#             }
#         )

# # ====================== مؤشرات التقلب ======================

# @IndicatorRegistry.register(
#     name="bb",
#     display_name="Bollinger Bands",
#     description="أشرطة بولينجر",
#     category=IndicatorType.VOLATILITY
# )
# class BollingerBandsIndicator(BaseIndicator):
#     """أشرطة بولينجر"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {
#             "period": 20,
#             "std": 2
#         }
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['close']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         period = self.params.get("period", 20)
#         std_dev = self.params.get("std", 2)
        
#         # حساب المتوسط المتحرك البسيط
#         sma = data['close'].rolling(window=period).mean()
        
#         # حساب الانحراف المعياري
#         rolling_std = data['close'].rolling(window=period).std()
        
#         # حساب النطاقات
#         upper_band = sma + (rolling_std * std_dev)
#         lower_band = sma - (rolling_std * std_dev)
        
#         # حساب عرض النطاق
#         band_width = (upper_band - lower_band) / sma
        
#         # توليد إشارات
#         signals = pd.Series(0, index=data.index)
#         signals[data['close'] < lower_band] = 1      # شراء (أسفل النطاق السفلي)
#         signals[data['close'] > upper_band] = -1     # بيع (فوق النطاق العلوي)
        
#         return IndicatorResult(
#             name=self.name,
#             values=sma,
#             signals=signals,
#             metadata={
#                 "sma": sma.tolist(),
#                 "upper_band": upper_band.tolist(),
#                 "lower_band": lower_band.tolist(),
#                 "band_width": band_width.tolist(),
#                 "period": period,
#                 "std": std_dev
#             }
#         )

# @IndicatorRegistry.register(
#     name="atr",
#     display_name="ATR",
#     description="مؤشر المدى الحقيقي المتوسط",
#     category=IndicatorType.VOLATILITY
# )
# class ATRIndicator(BaseIndicator):
#     """مؤشر المدى الحقيقي المتوسط"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {"period": 14}
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['high', 'low', 'close']
    
#     def _calculate_true_range(self, data: pd.DataFrame) -> pd.Series:
#         """حساب المدى الحقيقي"""
#         high_low = data['high'] - data['low']
#         high_close = abs(data['high'] - data['close'].shift(1))
#         low_close = abs(data['low'] - data['close'].shift(1))
        
#         true_range = pd.concat([high_low, high_close, low_close], axis=1)
#         return true_range.max(axis=1)
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         period = self.params.get("period", 14)
        
#         # حساب المدى الحقيقي
#         true_range = self._calculate_true_range(data)
        
#         # حساب ATR
#         atr_values = true_range.rolling(window=period).mean()
        
#         return IndicatorResult(
#             name=self.name,
#             values=atr_values,
#             metadata={"period": period}
#         )

# # ====================== مؤشرات الحجم ======================

# @IndicatorRegistry.register(
#     name="vwap",
#     display_name="VWAP",
#     description="متوسط السعر المرجح بالحجم",
#     category=IndicatorType.VOLUME
# )
# class VWAPIndicator(BaseIndicator):
#     """متوسط السعر المرجح بالحجم"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {"period": 20}
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['high', 'low', 'close', 'volume']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         period = self.params.get("period", 20)
        
#         # حساب السعر النموذجي
#         typical_price = (data['high'] + data['low'] + data['close']) / 3
        
#         # حساب VWAP
#         vwap = (typical_price * data['volume']).rolling(window=period).sum() / \
#                data['volume'].rolling(window=period).sum()
        
#         # إشارات عندما يكون السعر تحت/فوق VWAP
#         signals = pd.Series(0, index=data.index)
#         signals[data['close'] < vwap] = 1    # شراء (السعر تحت VWAP)
#         signals[data['close'] > vwap] = -1   # بيع (السعر فوق VWAP)
        
#         return IndicatorResult(
#             name=self.name,
#             values=vwap,
#             signals=signals,
#             metadata={"period": period}
#         )

# @IndicatorRegistry.register(
#     name="obv",
#     display_name="OBV",
#     description="مؤشر حجم الرصيد",
#     category=IndicatorType.VOLUME
# )
# class OBVIndicator(BaseIndicator):
#     """مؤشر حجم الرصيد"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {}
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['close', 'volume']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         # تحويل البيانات إلى مصفوفات numpy لتجنب مشكلة .iloc
#         close_prices = data['close'].values
#         volumes = data['volume'].values
        
#         obv = np.zeros(len(data))
        
#         # حساب OBV باستخدام المصفوفات
#         for i in range(1, len(data)):
#             if close_prices[i] > close_prices[i-1]:
#                 obv[i] = obv[i-1] + volumes[i]
#             elif close_prices[i] < close_prices[i-1]:
#                 obv[i] = obv[i-1] - volumes[i]
#             else:
#                 obv[i] = obv[i-1]
        
#         # تحويل إلى pandas Series
#         obv_series = pd.Series(obv, index=data.index)
        
#         # حساب اتجاه OBV
#         obv_sma = obv_series.rolling(window=20).mean()
#         signals = pd.Series(0, index=data.index)
#         signals[obv_series > obv_sma] = 1    # اتجاه صاعد
#         signals[obv_series < obv_sma] = -1   # اتجاه هابط
        
#         return IndicatorResult(
#             name=self.name,
#             values=obv_series,
#             signals=signals,
#             metadata={}
#         )

# # ====================== مؤشرات دعم ومقاومة ======================

# @IndicatorRegistry.register(
#     name="pivot_points",
#     display_name="Pivot Points",
#     description="نقاط المحورية",
#     category=IndicatorType.SUPPORT_RESISTANCE
# )
# class PivotPointsIndicator(BaseIndicator):
#     """نقاط المحورية"""
    
#     @classmethod
#     def get_default_params(cls) -> Dict[str, Any]:
#         return {"method": "standard"}  # standard, fibonacci, woodie
    
#     @classmethod
#     def get_required_columns(cls) -> List[str]:
#         return ['high', 'low', 'close']
    
#     def calculate(self, data: pd.DataFrame) -> IndicatorResult:
#         method = self.params.get("method", "standard")
        
#         # تحويل البيانات إلى مصفوفات numpy
#         high_prices = data['high'].values
#         low_prices = data['low'].values
#         close_prices = data['close'].values
        
#         # حساب نقاط المحورية لكل فترة
#         pivot_points = np.zeros(len(data))
#         resistance1 = np.zeros(len(data))
#         support1 = np.zeros(len(data))
        
#         for i in range(len(data)):
#             if i >= 1:
#                 prev_high = high_prices[i-1]
#                 prev_low = low_prices[i-1]
#                 prev_close = close_prices[i-1]
                
#                 # نقطة المحورية
#                 pivot = (prev_high + prev_low + prev_close) / 3
#                 pivot_points[i] = pivot
                
#                 # حساب الدعم والمقاومة
#                 if method == "standard":
#                     resistance1[i] = (2 * pivot) - prev_low
#                     support1[i] = (2 * pivot) - prev_high
#                 elif method == "fibonacci":
#                     resistance1[i] = pivot + 0.382 * (prev_high - prev_low)
#                     support1[i] = pivot - 0.382 * (prev_high - prev_low)
        
#         # تحويل إلى pandas Series
#         pivot_points_series = pd.Series(pivot_points, index=data.index)
#         resistance1_series = pd.Series(resistance1, index=data.index)
#         support1_series = pd.Series(support1, index=data.index)
        
#         # توليد إشارات بناءً على موقف السعر من نقاط المحورية
#         signals = pd.Series(0, index=data.index)
#         signals[close_prices < support1] = 1        # شراء عند الدعم
#         signals[close_prices > resistance1] = -1    # بيع عند المقاومة
        
#         return IndicatorResult(
#             name=self.name,
#             values=pivot_points_series,
#             signals=signals,
#             metadata={
#                 "pivot_points": pivot_points_series.tolist(),
#                 "resistance1": resistance1_series.tolist(),
#                 "support1": support1_series.tolist(),
#                 "method": method
#             }
#         )


