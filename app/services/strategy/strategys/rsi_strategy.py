# app/services/strategy/strategys/rsi_strategy.py
from datetime import datetime
from app.services.indicators.base import IndicatorType

def get_rsi_strategy():
    """إستراتيجية RSI بسيطة"""
    return {
        "name": "RSI Basic Strategy",
        "version": "1.0.0",
        "description": "استراتيجية تعتمد على مؤشر RSI للدخول والخروج",
        "base_timeframe": "1h",
        "position_side": "long",
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
        
        "indicators": [
            {
                "name": "rsi",
                "type": IndicatorType.MOMENTUM.value,
                "params": {"period": 14, "overbought": 70, "oversold": 30},
                "enabled": True,
                "timeframe": "1h"
            }
        ],
        
        "entry_rules": [
            {
                "name": "RSI Oversold Entry",
                "condition": {
                    "type": "indicator_value",
                    "operator": "<=",
                    "left_value": "indicator:rsi",
                    "right_value": 30
                },
                "position_side": "long",
                "weight": 0.7,
                "enabled": True
            },
            {
                "name": "RSI Bullish Divergence",
                "condition": {
                    "type": "logical_and",
                    "conditions": [
                        {
                            "type": "indicator_value",
                            "operator": "<",
                            "left_value": "indicator:rsi",
                            "right_value": 40
                        },
                        {
                            "type": "price_crossover",
                            "operator": "cross_above",
                            "left_value": "price.close",
                            "right_value": "indicator:sma_20"
                        }
                    ]
                },
                "position_side": "long",
                "weight": 0.3,
                "enabled": True
            }
        ],
        
        "exit_rules": [
            {
                "name": "RSI Overbought Exit",
                "condition": {
                    "type": "indicator_value",
                    "operator": ">=",
                    "left_value": "indicator:rsi",
                    "right_value": 70
                },
                "exit_type": "signal_exit",
                "enabled": True
            },
            {
                "name": "Stop Loss",
                "condition": {
                    "type": "price_crossover",
                    "operator": "cross_below",
                    "left_value": "price.close",
                    "right_value": 0.95  # 5% stop loss
                },
                "exit_type": "stop_loss",
                "value": 5.0,
                "enabled": True
            }
        ],
        
        "filter_rules": [
            {
                "name": "Volume Filter",
                "condition": {
                    "type": "volume_condition",
                    "operator": ">",
                    "left_value": "price.volume",
                    "right_value": 1000000  # حجم أدنى 1M
                },
                "action": "allow",
                "enabled": True
            }
        ],
        
        "risk_management": {
            "stop_loss_percentage": 5.0,
            "take_profit_percentage": 10.0,
            "trailing_stop_percentage": 2.0,
            "max_position_size": 0.2,
            "max_daily_loss": 5.0,
            "max_concurrent_positions": 2
        }
    }