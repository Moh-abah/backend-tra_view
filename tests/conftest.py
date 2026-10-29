# tests/conftest.py
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

@pytest.fixture(scope="session")
def sample_ohlcv_data():
    """بيانات OHLCV نموذجية للاختبارات"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='H')
    np.random.seed(42)  # للحصول على نتائج متكررة
    
    prices = 100 + np.cumsum(np.random.randn(100) * 2)
    
    return pd.DataFrame({
        'open': prices + np.random.randn(100) * 0.5,
        'high': prices + np.abs(np.random.randn(100) * 1),
        'low': prices - np.abs(np.random.randn(100) * 1),
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)

@pytest.fixture
def mock_indicator_config():
    """تكوين مؤشر تجريبي"""
    from app.services.indicators.base import IndicatorConfig, IndicatorType, Timeframe
    
    return IndicatorConfig(
        name="test_indicator",
        type=IndicatorType.TREND,
        params={"period": 14},
        enabled=True,
        timeframe=Timeframe.MIN15
    )