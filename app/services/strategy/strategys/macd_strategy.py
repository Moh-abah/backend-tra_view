# app/services/strategy/strategys/macd_strategy.py
from datetime import datetime
from app.services.indicators.base import IndicatorType

def get_macd_strategy():
    """إستراتيجية MACD متقدمة"""
    return {
        "name": "MACD Trend Strategy",
        "version": "1.0.0",
        "description": "استراتيجية تعتمد على تقاطع مؤشر MACD مع تأكيد من RSI",
        "base_timeframe": "4h",
        "position_side": "both",
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
        
        "indicators": [
            {
                "name": "macd",
                "type": IndicatorType.MOMENTUM.value,
                "params": {"fast": 12, "slow": 26, "signal": 9},
                "enabled": True
            },
            {
                "name": "rsi",
                "type": IndicatorType.MOMENTUM.value,
                "params": {"period": 14},
                "enabled": True
            },
            {
                "name": "ema_20",
                "type": IndicatorType.TREND.value,
                "params": {"period": 20},
                "enabled": True
            }
        ],
        
        "entry_rules": [
            {
                "name": "MACD Bullish Crossover Long",
                "condition": {
                    "type": "logical_and",
                    "conditions": [
                        {
                            "type": "indicator_crossover",
                            "operator": "cross_above",
                            "left_value": "indicator:macd",
                            "right_value": "indicator:macd.signal"
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "price.close",
                            "right_value": "indicator:ema_20"
                        },
                        {
                            "type": "indicator_value",
                            "operator": ">",
                            "left_value": "indicator:rsi",
                            "right_value": 50
                        }
                    ]
                },
                "position_side": "long",
                "weight": 0.6,
                "enabled": True
            },
            {
                "name": "MACD Bearish Crossover Short",
                "condition": {
                    "type": "logical_and",
                    "conditions": [
                        {
                            "type": "indicator_crossover",
                            "operator": "cross_below",
                            "left_value": "indicator:macd",
                            "right_value": "indicator:macd.signal"
                        },
                        {
                            "type": "indicator_value",
                            "operator": "<",
                            "left_value": "price.close",
                            "right_value": "indicator:ema_20"
                        },
                        {
                            "type": "indicator_value",
                            "operator": "<",
                            "left_value": "indicator:rsi",
                            "right_value": 50
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
                "name": "MACD Reverse Signal",
                "condition": {
                    "type": "logical_or",
                    "conditions": [
                        {
                            "type": "indicator_crossover",
                            "operator": "cross_below",
                            "left_value": "indicator:macd",
                            "right_value": "indicator:macd.signal"
                        },
                        {
                            "type": "indicator_crossover",
                            "operator": "cross_above",
                            "left_value": "indicator:macd",
                            "right_value": "indicator:macd.signal"
                        }
                    ]
                },
                "exit_type": "signal_exit",
                "enabled": True
            }
        ],
        
        "risk_management": {
            "stop_loss_percentage": 3.0,
            "take_profit_percentage": 6.0,
            "trailing_stop_percentage": 1.5,
            "max_position_size": 0.15,
            "max_daily_loss": 4.0,
            "max_concurrent_positions": 3
        },
        
        "require_confirmation": True,
        "confirmation_timeframe": "1d",
        "max_signals_per_day": 2
    }