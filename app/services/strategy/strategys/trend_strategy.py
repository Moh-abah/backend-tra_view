# app/services/strategy/strategys/trend_strategy.py
from datetime import datetime
from app.services.indicators.base import IndicatorType

def get_trend_strategy():
    """إستراتيجية تتبع الاتجاه"""
    return {
        "name": "Trend Following Strategy",
        "version": "1.0.0",
        "description": "استراتيجية تتبع الاتجاه باستخدام متوسطات متحركة متعددة ومؤشر ADX",
        "base_timeframe": "1d",
        "position_side": "long",
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
        
        "indicators": [
            {
                "name": "ema_20",
                "type": IndicatorType.TREND.value,
                "params": {"period": 20},
                "enabled": True
            },
            {
                "name": "ema_50",
                "type": IndicatorType.TREND.value,
                "params": {"period": 50},
                "enabled": True
            },
            {
                "name": "ema_200",
                "type": IndicatorType.TREND.value,
                "params": {"period": 200},
                "enabled": True
            },
            {
                "name": "adx",
                "type": IndicatorType.TREND.value,
                "params": {"period": 14},
                "enabled": True
            },
            {
                "name": "atr",
                "type": IndicatorType.VOLATILITY.value,
                "params": {"period": 14},
                "enabled": True
            }
        ],
        
        "entry_rules": [
            {
                "name": "Golden Cross Entry",
                "condition": {
                    "type": "logical_and",
                    "conditions": [
                        {
                            "type": "indicator_crossover",
                            "operator": "cross_above",
                            "left_value": "indicator:ema_20",
                            "right_value": "indicator:ema_50"
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:adx",
                            "right_value": 25
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "price.close",
                            "right_value": "indicator:ema_200"
                        }
                    ]
                },
                "position_side": "long",
                "weight": 0.8,
                "enabled": True
            },
            {
                "name": "Pullback Entry",
                "condition": {
                    "type": "logical_and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "price.close",
                            "right_value": "indicator:ema_50"
                        },
                        {
                            "type": "indicator_value",
                            "operator": "<",
                            "left_value": "price.close",
                            "right_value": "indicator:ema_20"
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:adx",
                            "right_value": 20
                        }
                    ]
                },
                "position_side": "long",
                "weight": 0.2,
                "enabled": True
            }
        ],
        
        "exit_rules": [
            {
                "name": "Death Cross Exit",
                "condition": {
                    "type": "indicator_crossover",
                    "operator": "cross_below",
                    "left_value": "indicator:ema_20",
                    "right_value": "indicator:ema_50"
                },
                "exit_type": "signal_exit",
                "enabled": True
            },
            {
                "name": "Trailing Stop ATR",
                "condition": {
                    "type": "price_crossover",
                    "operator": "cross_below",
                    "left_value": "price.close",
                    "right_value": 0.0  # سيتم تحديثه ديناميكياً
                },
                "exit_type": "trailing_stop",
                "value": 2.0,  # 2 x ATR
                "enabled": True
            }
        ],
        
        "filter_rules": [
            {
                "name": "Trend Strength Filter",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "indicator:adx",
                    "right_value": 20
                },
                "action": "allow",
                "enabled": True
            },
            {
                "name": "Volume Filter",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">",
                    "left_value": "price.volume",
                    "right_value": 1000000
                },
                "action": "allow",
                "enabled": True
            }
        ],
        
        "risk_management": {
            "stop_loss_percentage": 8.0,
            "take_profit_percentage": 20.0,
            "trailing_stop_percentage": 3.0,
            "max_position_size": 0.15,
            "max_daily_loss": 6.0,
            "max_concurrent_positions": 2
        },
        
        "require_confirmation": True,
        "confirmation_timeframe": "1w",
        "max_signals_per_week": 2
    }