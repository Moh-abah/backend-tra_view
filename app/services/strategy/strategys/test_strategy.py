# app/services/strategy/strategys/test_strategy.py
from datetime import datetime
from app.services.indicators.base import IndicatorType

def get_sma_crossover_strategy():
    """إستراتيجية تقاطع SMA بسيطة للاختبار"""
    return {
        "name": "SMA Crossover Strategy",
        "version": "1.0.0",
        "description": "إستراتيجية اختبارية بسيطة - تقاطع SMA",
        "base_timeframe": "1h",  # مطابقة timeframe في الطلب
        "position_side": "long",
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
        
        "indicators": [
            {
                "name": "sma_fast",
                "type": IndicatorType.TREND.value,
                "params": {"period": 10},
                "enabled": True,
                "timeframe": "1h"
            },
            {
                "name": "sma_slow",
                "type": IndicatorType.TREND.value,
                "params": {"period": 20},
                "enabled": True,
                "timeframe": "1h"
            }
        ],
        
        "entry_rules": [
            {
                "name": "SMA Crossover Entry",
                "condition": {
                    "type": "indicator_crossover",
                    "operator": "cross_above",
                    "left_value": "indicator:sma_fast",
                    "right_value": "indicator:sma_slow"
                },
                "position_side": "long",
                "weight": 1.0,
                "enabled": True
            }
        ],
        
        "exit_rules": [
            {
                "name": "SMA Crossover Exit",
                "condition": {
                    "type": "indicator_crossover",
                    "operator": "cross_below",
                    "left_value": "indicator:sma_fast",
                    "right_value": "indicator:sma_slow"
                },
                "exit_type": "signal_exit",
                "enabled": True
            }
        ],
        
        "filter_rules": [],  # قائمة فارغة - لا يوجد فلاتر
        
        "risk_management": {
            "stop_loss_percentage": 5.0,
            "take_profit_percentage": 10.0,
            "max_position_size": 0.5
        }
    }