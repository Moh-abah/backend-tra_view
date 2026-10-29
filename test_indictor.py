import pandas as pd

import pytest

from app.services.indicators.calculator import IndicatorCalculator

def test_apply_indicators_basic():
    # إنشاء بيانات وهمية
    data = {
        "open": [100, 102, 101, 103, 105],
        "high": [101, 103, 102, 104, 106],
        "low": [99, 101, 100, 102, 104],
        "close": [100, 102, 101, 103, 105],
        "volume": [10, 15, 12, 13, 14]
    }
    df = pd.DataFrame(data)

    # تكوين المؤشرات
    indicators_config = [
        {
            "name": "rsi",
            "type": "momentum",
            "params": {
                "period": 14,
                "overbought": 70,
                "oversold": 30
            },
            "enabled": True,
            "timeframe": "1h"
        }
    ]

    service = IndicatorCalculator()  # إذا الدالة داخل class
    result = service.apply_indicators(df, indicators_config)

    assert isinstance(result, dict)
    assert "rsi" in result
