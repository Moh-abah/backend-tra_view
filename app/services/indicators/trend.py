# app/services/indicators/trend.py
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from .base import BaseIndicator, IndicatorResult, IndicatorConfig, IndicatorType

class SMAIndicator(BaseIndicator):
    """المتوسط المتحرك البسيط"""
    
    @classmethod
    def get_required_columns(cls):
        return ['close']
    
    @classmethod
    def get_default_params(cls):
        return {'period': 20}
    
    def calculate(self, data: pd.DataFrame) -> IndicatorResult:
        """حساب المتوسط المتحرك البسيط"""
        self.validate_data(data)
        period = self.params.get('period', 20)
        
        # حساب SMA
        values = data['close'].rolling(window=period, min_periods=1).mean()
        
        # توليد إشارات (عندما يعبر السعر فوق/تحت SMA)
        signals = pd.Series(0, index=data.index)
        if len(data) > period:
            # إشارة شراء عندما يعبر السعر فوق SMA
            signals[(data['close'] > values) & (data['close'].shift(1) <= values.shift(1))] = 1
            # إشارة بيع عندما يعبر السعر تحت SMA
            signals[(data['close'] < values) & (data['close'].shift(1) >= values.shift(1))] = -1
        
        return IndicatorResult(
            name=self.name,
            values=values,
            signals=signals,
            metadata={
                'period': period,
                'type': 'simple_moving_average'
            }
        )


class EMAIndicator(BaseIndicator):
    """المتوسط المتحرك الأسي"""
    
    @classmethod
    def get_required_columns(cls):
        return ['close']
    
    @classmethod
    def get_default_params(cls):
        return {'period': 20}
    
    def calculate(self, data: pd.DataFrame) -> IndicatorResult:
        """حساب المتوسط المتحرك الأسي"""
        self.validate_data(data)
        period = self.params.get('period', 20)
        
        # حساب EMA
        values = data['close'].ewm(span=period, adjust=False).mean()
        
        # توليد إشارات مشابهة لـ SMA
        signals = pd.Series(0, index=data.index)
        if len(data) > period:
            signals[(data['close'] > values) & (data['close'].shift(1) <= values.shift(1))] = 1
            signals[(data['close'] < values) & (data['close'].shift(1) >= values.shift(1))] = -1
        
        return IndicatorResult(
            name=self.name,
            values=values,
            signals=signals,
            metadata={
                'period': period,
                'type': 'exponential_moving_average'
            }
        )