# tests/unit/routers/test_strategies.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services.strategy import StrategyResult, TradeSignal
from app.services.indicators.base import IndicatorConfig, IndicatorType, Timeframe

# إنشاء TestClient
client = TestClient(app)

# بيانات تجريبية للاستراتيجية
MOCK_STRATEGY_CONFIG = {
    "name": "test_strategy",
    "version": "1.0.0",
    "description": "Test strategy for unit testing",
    "timeframe": "15m",
    "indicators": [
        {
            "name": "sma",
            "type": "trend",
            "params": {"period": 20},
            "enabled": True
        },
        {
            "name": "rsi",
            "type": "momentum",
            "params": {"period": 14, "overbought": 70, "oversold": 30},
            "enabled": True
        }
    ],
    "entry_rules": [
        {
            "name": "rsi_oversold",
            "condition": "rsi < 30 and close > sma_20",
            "action": "BUY",
            "strength": 1
        }
    ],
    "exit_rules": [
        {
            "name": "rsi_overbought",
            "condition": "rsi > 70",
            "action": "SELL",
            "strength": 1
        }
    ],
    "position_size": 1.0,
    "stop_loss": 2.0,
    "take_profit": 5.0
}

def create_mock_dataframe(rows=100):
    """إنشاء بيانات تجريبية"""
    dates = pd.date_range(start='2025-01-01', periods=rows, freq='min')
    
    # إنشاء بيانات سعر عشوائية
    np.random.seed(42)
    close_prices = 100 + np.cumsum(np.random.randn(rows)) * 0.5
    
    return pd.DataFrame({
        'open': close_prices - np.random.uniform(0.1, 0.5, rows),
        'high': close_prices + np.random.uniform(0.1, 0.5, rows),
        'low': close_prices - np.random.uniform(0.2, 0.8, rows),
        'close': close_prices,
        'volume': np.random.randint(100, 10000, rows)
    }, index=dates)

def create_mock_trade_signal(timestamp=None, action="BUY"):
    """إنشاء إشارة تجارية تجريبية"""
    if timestamp is None:
        timestamp = datetime.now()
    
    return TradeSignal(
        timestamp=timestamp,
        action=action,
        price=100.0,
        reason="Test signal",
        rule_name="test_rule",
        strength=1.0,
        metadata={"test": "data"}
    )

@pytest.fixture
def mock_db_session():
    """إنشاء جلسة قاعدة بيانات تجريبية"""
    return AsyncMock()

@pytest.fixture
def mock_data_service():
    """إنشاء خدمة بيانات تجريبية"""
    service = AsyncMock()
    
    # إعداد الـ mock لإرجاع بيانات تجريبية
    mock_df = create_mock_dataframe(50)
    service.get_historical.return_value = mock_df
    
    return service

@pytest.fixture
def mock_strategy_result():
    """إنشاء نتيجة استراتيجية تجريبية"""
    signals = [
        create_mock_trade_signal(datetime(2025, 1, 1, 10, 0), "BUY"),
        create_mock_trade_signal(datetime(2025, 1, 1, 12, 0), "SELL"),
    ]
    
    return StrategyResult(
        signals=signals,
        filtered_signals=signals,
        metrics={
            "total_trades": 2,
            "win_rate": 0.5,
            "profit_loss": 50.0,
            "max_drawdown": -10.0
        }
    )

@pytest.mark.asyncio
async def test_run_strategy_endpoint_success():
    """اختبار endpoint تشغيل الاستراتيجية بنجاح"""
    # Mock البيانات المطلوبة
    mock_df = create_mock_dataframe(30)
    mock_result = mock_strategy_result()
    
    with patch('app.routers.strategies.DataService') as MockDataService, \
         patch('app.routers.strategies.run_strategy') as mock_run_strategy:
        
        # إعداد الـ mocks
        mock_data_service = AsyncMock()
        mock_data_service.get_historical.return_value = mock_df
        MockDataService.return_value = mock_data_service
        
        mock_run_strategy.return_value = mock_result
        
        # إرسال الطلب
        response = client.post(
            "/strategies/run",
            params={
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "market": "crypto",
                "days": 7,
                "live_mode": False
            },
            json=MOCK_STRATEGY_CONFIG
        )
        
        # التحقق من النتيجة
        assert response.status_code == 200
        data = response.json()
        
        # التحقق من الهيكل الأساسي
        assert "signals" in data
        assert "filtered_signals" in data
        assert "metrics" in data
        assert "strategy_summary" in data
        
        # التحقق من عدد الإشارات
        assert len(data["signals"]) == 2
        assert len(data["filtered_signals"]) == 2
        
        # التحقق من القيم
        assert data["metrics"]["total_trades"] == 2
        assert data["strategy_summary"]["name"] == "test_strategy"

@pytest.mark.asyncio
async def test_run_strategy_endpoint_no_data():
    """اختبار endpoint عندما لا توجد بيانات"""
    with patch('app.routers.strategies.DataService') as MockDataService:
        # إعداد الـ mock لإرجاع dataframe فارغ
        mock_data_service = AsyncMock()
        mock_data_service.get_historical.return_value = pd.DataFrame()
        MockDataService.return_value = mock_data_service
        
        # إرسال الطلب
        response = client.post(
            "/strategies/run",
            params={
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "market": "crypto",
                "days": 7,
                "live_mode": False
            },
            json=MOCK_STRATEGY_CONFIG
        )
        
        # يجب أن يرجع 404
        assert response.status_code == 404
        assert "No data available" in response.json()["detail"]

@pytest.mark.asyncio
async def test_run_strategy_endpoint_invalid_config():
    """اختبار endpoint بتكوين استراتيجية غير صالح"""
    invalid_config = {"name": "invalid_strategy"}  # تكوين ناقص
    
    response = client.post(
        "/strategies/run",
        params={
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "market": "crypto",
            "days": 7,
            "live_mode": False
        },
        json=invalid_config
    )
    
    # يجب أن يرجع خطأ
    assert response.status_code in [400, 422, 500]  # حسب التحقق

@pytest.mark.asyncio
async def test_run_strategy_with_live_mode():
    """اختبار endpoint مع live mode"""
    mock_df = create_mock_dataframe(100)
    mock_result = mock_strategy_result()
    
    with patch('app.routers.strategies.DataService') as MockDataService, \
         patch('app.routers.strategies.run_strategy') as mock_run_strategy:
        
        mock_data_service = AsyncMock()
        mock_data_service.get_historical.return_value = mock_df
        MockDataService.return_value = mock_data_service
        
        mock_run_strategy.return_value = mock_result
        
        response = client.post(
            "/strategies/run",
            params={
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "market": "crypto",
                "days": 30,
                "live_mode": True  # تمكين live mode
            },
            json=MOCK_STRATEGY_CONFIG
        )
        
        assert response.status_code == 200
        # يمكن إضافة تحقق خاص بـ live mode إذا كان هناك سلوك مختلف

@pytest.mark.asyncio
async def test_run_strategy_endpoint_validation():
    """اختبار تحقق المعاملات"""
    # رمز غير صالح
    response = client.post(
        "/strategies/run",
        params={
            "symbol": "",  # رمز فارغ
            "timeframe": "15m",
            "market": "crypto",
            "days": 7,
            "live_mode": False
        },
        json=MOCK_STRATEGY_CONFIG
    )
    
    assert response.status_code == 422  # Unprocessable Entity
    
    # إطار زمني غير صالح
    response = client.post(
        "/strategies/run",
        params={
            "symbol": "BTCUSDT",
            "timeframe": "invalid_tf",  # إطار زمني غير صالح
            "market": "crypto",
            "days": 7,
            "live_mode": False
        },
        json=MOCK_STRATEGY_CONFIG
    )
    
    assert response.status_code == 422
    
    # عدد أيام غير صالح
    response = client.post(
        "/strategies/run",
        params={
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "market": "crypto",
            "days": 0,  # 0 أيام غير صالح
            "live_mode": False
        },
        json=MOCK_STRATEGY_CONFIG
    )
    
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_run_strategy_error_handling():
    """اختبار معالجة الأخطاء"""
    with patch('app.routers.strategies.DataService') as MockDataService:
        # إعداد الـ mock ليرفع استثناء
        mock_data_service = AsyncMock()
        mock_data_service.get_historical.side_effect = Exception("Database error")
        MockDataService.return_value = mock_data_service
        
        response = client.post(
            "/strategies/run",
            params={
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "market": "crypto",
                "days": 7,
                "live_mode": False
            },
            json=MOCK_STRATEGY_CONFIG
        )
        
        assert response.status_code == 500
        assert "Database error" in response.json()["detail"]

def test_run_strategy_logging():
    """اختبار تسجيل السجلات (اختياري)"""
    # يمكن اختبار أن السجلات يتم تسجيلها بشكل صحيح
    # هذا يتطلب إعداد إضافي للـ logging في الاختبارات
    pass

if __name__ == "__main__":
    pytest.main([__file__, "-v"])