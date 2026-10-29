import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union
import logging
from dataclasses import dataclass
from abc import ABC, abstractmethod
from ..strategy.schemas import IndicatorConfig, IndicatorType

logger = logging.getLogger(__name__)

@dataclass
class IndicatorOutput:
    """مخرجات المؤشر الموحدة"""
    name: str
    series: pd.Series
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class BaseIndicatorCalculator(ABC):
    """آلة حاسبة أساسية للمؤشرات"""
    
    @abstractmethod
    def calculate(self, data: pd.DataFrame, config: IndicatorConfig) -> IndicatorOutput:
        pass
    
    @abstractmethod
    def can_calculate(self, config: IndicatorConfig) -> bool:
        pass

class SMACalculator(BaseIndicatorCalculator):
    """حاسبة SMA"""
    
    def can_calculate(self, config: IndicatorConfig) -> bool:
        return config.type == IndicatorType.TREND and "sma" in config.name.lower()
    
    def calculate(self, data: pd.DataFrame, config: IndicatorConfig) -> IndicatorOutput:
        period = config.params.get('period', 10)
        
        if 'close' not in data.columns:
            raise ValueError("عمود 'close' غير موجود في البيانات")
        
        close_series = data['close']
        sma_values = close_series.rolling(window=period, min_periods=1).mean()
        
        return IndicatorOutput(
            name=config.name,
            series=sma_values,
            metadata={'period': period, 'type': 'sma'}
        )

class EMACalculator(BaseIndicatorCalculator):
    """حاسبة EMA"""
    
    def can_calculate(self, config: IndicatorConfig) -> bool:
        return config.type == IndicatorType.TREND and "ema" in config.name.lower()
    
    def calculate(self, data: pd.DataFrame, config: IndicatorConfig) -> IndicatorOutput:
        period = config.params.get('period', 10)
        
        if 'close' not in data.columns:
            raise ValueError("عمود 'close' غير موجود في البيانات")
        
        close_series = data['close']
        ema_values = close_series.ewm(span=period, adjust=False).mean()
        
        return IndicatorOutput(
            name=config.name,
            series=ema_values,
            metadata={'period': period, 'type': 'ema'}
        )

class RSICalculator(BaseIndicatorCalculator):
    """حاسبة RSI"""
    
    def can_calculate(self, config: IndicatorConfig) -> bool:
        return config.type == IndicatorType.MOMENTUM and "rsi" in config.name.lower()
    
    def calculate(self, data: pd.DataFrame, config: IndicatorConfig) -> IndicatorOutput:
        period = config.params.get('period', 14)
        
        if 'close' not in data.columns:
            raise ValueError("عمود 'close' غير موجود في البيانات")
        
        close_series = data['close']
        delta = close_series.diff()
        
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi_values = 100 - (100 / (1 + rs))
        
        return IndicatorOutput(
            name=config.name,
            series=rsi_values,
            metadata={'period': period, 'type': 'rsi'}
        )

class ReliableIndicatorCalculator:
    """آلة حاسبة موثوقة للمؤشرات"""
    
    def __init__(self):
        self.calculators = [
            SMACalculator(),
            EMACalculator(),
            RSICalculator(),
        ]
        self._cache: Dict[str, pd.Series] = {}
        
    def calculate_indicator(
        self, 
        data: pd.DataFrame, 
        config: IndicatorConfig,
        use_cache: bool = True
    ) -> pd.Series:
        """حساب مؤشر واحد"""
        
        # إنشاء مفتاح كاش فريد
        cache_key = self._create_cache_key(data, config)
        
        if use_cache and cache_key in self._cache:
            logger.debug(f"📦 استخدام مؤشر '{config.name}' من الكاش")
            return self._cache[cache_key].copy()
        
        # البحث عن الحاسبة المناسبة
        calculator = None
        for calc in self.calculators:
            if calc.can_calculate(config):
                calculator = calc
                break
        
        if not calculator:
            logger.warning(f"⚠️ لا توجد حاسبة مناسبة للمؤشر '{config.name}'، سيتم استخدام الحاسبة الافتراضية")
            series = self._calculate_fallback(data, config)
        else:
            try:
                output = calculator.calculate(data, config)
                series = output.series
            except Exception as e:
                logger.error(f"❌ خطأ في حساب المؤشر '{config.name}': {e}")
                series = self._calculate_fallback(data, config)
        
        # المحاذاة مع البيانات
        if len(series) != len(data):
            series = self._align_series(series, data)
        
        # التخزين في الكاش
        if use_cache:
            self._cache[cache_key] = series.copy()
        
        return series
    
    def calculate_all(
        self, 
        data: pd.DataFrame, 
        configs: List[IndicatorConfig],
        use_cache: bool = True
    ) -> Dict[str, pd.Series]:
        """حساب جميع المؤشرات"""
        
        results = {}
        
        for config in configs:
            if not config.enabled:
                continue
                
            logger.info(f"🔧 حساب مؤشر '{config.name}'...")
            series = self.calculate_indicator(data, config, use_cache)
            results[config.name] = series
            
            # تسجيل الإحصائيات
            non_nan_count = series.notna().sum()
            logger.info(f"   ✅ تم الحساب، الطول: {len(series)}، قيم غير NaN: {non_nan_count}")
        
        return results
    
    def _create_cache_key(self, data: pd.DataFrame, config: IndicatorConfig) -> str:
        """إنشاء مفتاح فريد للكاش"""
        import hashlib
        import json
        
        data_hash = hashlib.md5(
            str(data.index[-1] if len(data) > 0 else '').encode() + 
            str(data.shape).encode()
        ).hexdigest()[:8]
        
        config_str = f"{config.name}_{config.type}_{json.dumps(config.params, sort_keys=True)}"
        
        return f"{data_hash}_{config_str}"
    
    def _calculate_fallback(self, data: pd.DataFrame, config: IndicatorConfig) -> pd.Series:
        """حساب افتراضي للمؤشرات غير المدعومة"""
        logger.warning(f"🔄 استخدام الحساب الافتراضي للمؤشر '{config.name}'")
        
        # إنشاء سلسلة بنفس طول البيانات
        series = pd.Series([np.nan] * len(data), index=data.index)
        
        # محاولة حساب SMA إذا كان هناك فترة
        period = config.params.get('period', 10)
        if 'close' in data.columns and len(data) >= period:
            try:
                close_series = data['close']
                sma_values = close_series.rolling(window=period, min_periods=1).mean()
                series = sma_values
            except:
                pass
        
        return series
    
    def _align_series(self, series: pd.Series, data: pd.DataFrame) -> pd.Series:
        """محاذاة السلسلة مع البيانات"""
        if len(series) == len(data):
            return series
        
        if len(series) > len(data):
            return series.iloc[:len(data)]
        else:
            # إضافة قيم NaN في البداية
            padding = pd.Series([np.nan] * (len(data) - len(series)))
            return pd.concat([padding, series], ignore_index=False)
    
    def clear_cache(self):
        """مسح الكاش"""
        self._cache.clear()
        logger.info("🗑️ تم مسح كاش المؤشرات")