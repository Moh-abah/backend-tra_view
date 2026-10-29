# app/services/strategy/strategys/mean_reversion_strategy.py
from datetime import datetime
from app.services.indicators.base import IndicatorType

def get_mean_reversion_strategy():
    """إستراتيجية الارتداد المتوسط"""
    return {
        "name": "Mean Reversion Strategy",
        "version": "1.0.0",
        "description": "استراتيجية الارتداد المتوسط باستخدام بولينجر باندز ومؤشرات الزخم",
        "base_timeframe": "4h",
        "position_side": "both",
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
        
        "indicators": [
            {
                "name": "bollinger_bands",
                "type": IndicatorType.VOLATILITY.value,
                "params": {"period": 20, "std_dev": 2},
                "enabled": True
            },
            {
                "name": "rsi",
                "type": IndicatorType.MOMENTUM.value,
                "params": {"period": 14},
                "enabled": True
            },
            {
                "name": "stochastic",
                "type": IndicatorType.MOMENTUM.value,
                "params": {"k_period": 14, "d_period": 3},
                "enabled": True
            },
            {
                "name": "sma_50",
                "type": IndicatorType.TREND.value,
                "params": {"period": 50},
                "enabled": True
            }
        ],
        
        "entry_rules": [
            {
                "name": "Bollinger Bounce Long",
                "condition": {
                    "type": "logical_and",
                    "conditions": [
                        {
                            "type": "price_crossover",
                            "operator": "cross_below",
                            "left_value": "price.close",
                            "right_value": "indicator:bollinger_bands.lower"
                        },
                        {
                            "type": "indicator_value",
                            "operator": "<",
                            "left_value": "indicator:rsi",
                            "right_value": 30
                        },
                        {
                            "type": "indicator_value",
                            "operator": "<",
                            "left_value": "indicator:stochastic.k",
                            "right_value": 20
                        }
                    ]
                },
                "position_side": "long",
                "weight": 0.6,
                "enabled": True
            },
            {
                "name": "Bollinger Bounce Short",
                "condition": {
                    "type": "logical_and",
                    "conditions": [
                        {
                            "type": "price_crossover",
                            "operator": "cross_above",
                            "left_value": "price.close",
                            "right_value": "indicator:bollinger_bands.upper"
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:rsi",
                            "right_value": 70
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:stochastic.k",
                            "right_value": 80
                        }
                    ]
                },
                "position_side": "short",
                "weight": 0.4,
                "enabled": True
            }
        ],
        
        "exit_rules": [
            {
                "name": "Middle Band Exit",
                "condition": {
                    "type": "price_crossover",
                    "operator": "cross_above",
                    "left_value": "price.close",
                    "right_value": "indicator:bollinger_bands.middle"
                },
                "exit_type": "signal_exit",
                "enabled": True
            },
            {
                "name": "Profit Target",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">=",
                    "left_value": "indicator:rsi",
                    "right_value": 60
                },
                "exit_type": "take_profit",
                "value": 3.0,
                "enabled": True
            }
        ],
        
        "filter_rules": [
            {
                "name": "Trend Filter",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "price.close",
                    "right_value": "indicator:sma_50"
                },
                "action": "allow",
                "enabled": True
            },
            {
                "name": "Volatility Filter",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:bollinger_bands.width",
                    "right_value": 0.05  # عرض النطاق 5% على الأقل
                },
                "action": "allow",
                "enabled": True
            }
        ],
        
        "risk_management": {
            "stop_loss_percentage": 2.0,
            "take_profit_percentage": 3.0,
            "trailing_stop_percentage": 1.0,
            "max_position_size": 0.1,
            "max_daily_loss": 4.0,
            "max_concurrent_positions": 3
        },
        
        "require_confirmation": False,
        "max_signals_per_day": 3
    }