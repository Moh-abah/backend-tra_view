# tests/unit/services/test_strategy_service.py
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from app.services.strategy import (
    run_strategy,
    validate_strategy_config,
    StrategyResult,
    TradeSignal
)
from app.services.indicators.base import IndicatorConfig

def test_validate_strategy_config_valid():
    """اختبار تحقق صحة تكوين الاستراتيجية"""
    valid_config = {
        "name": "test_strategy",
        "version": "1.0.0",
        "timeframe": "15m",
        "indicators": [
            {
                "name": "sma",
                "type": "trend",
                "params": {"period": 20},
                "enabled": True
            }
        ],
        "entry_rules": [],
        "exit_rules": []
    }
    
    # يجب ألا يرفع استثناء
    result = validate_strategy_config(valid_config)
    assert result is True

def test_validate_strategy_config_invalid():
    """اختبار تحقق تكوين استراتيجية غير صالح"""
    # تكوين بدون اسم
    invalid_config = {
        "version": "1.0.0",
        "timeframe": "15m"
    }
    
    with pytest.raises(ValueError) as exc_info:
        validate_strategy_config(invalid_config)
    assert "name" in str(exc_info.value).lower()

def test_validate_strategy_config_with_invalid_indicators():
    """اختبار تحقق تكوين بمؤشرات غير صالحة"""
    config_with_invalid_indicator = {
        "name": "test",
        "version": "1.0.0",
        "timeframe": "15m",
        "indicators": [
            {
                "name": "invalid_indicator",  # مؤشر غير موجود
                "type": "trend",
                "params": {},
                "enabled": True
            }
        ],
        "entry_rules": [],
        "exit_rules": []
    }
    
    with pytest.raises(ValueError) as exc_info:
        validate_strategy_config(config_with_invalid_indicator)
    assert "indicator" in str(exc_info.value).lower()

def create_test_data():
    """إنشاء بيانات اختبار"""
    dates = pd.date_range('2025-01-01', periods=20, freq='h')
    
    return pd.DataFrame({
        'open': np.random.uniform(90, 110, 20),
        'high': np.random.uniform(95, 115, 20),
        'low': np.random.uniform(85, 105, 20),
        'close': np.random.uniform(90, 110, 20),
        'volume': np.random.randint(1000, 10000, 20)
    }, index=dates)

@pytest.mark.asyncio
async def test_run_strategy_basic():
    """اختبار أساسي لتشغيل الاستراتيجية"""
    data = create_test_data()
    
    simple_config = {
        "name": "simple_test",
        "version": "1.0.0",
        "timeframe": "1h",
        "indicators": [
            {
                "name": "sma",
                "type": "trend",
                "params": {"period": 5},
                "enabled": True
            }
        ],
        "entry_rules": [
            {
                "name": "buy_rule",
                "condition": "close > sma",  # شراء عندما يعبر السعر فوق SMA
                "action": "BUY",
                "strength": 1.0
            }
        ],
        "exit_rules": [
            {
                "name": "sell_rule",
                "condition": "close < sma",  # بيع عندما يعبر السعر تحت SMA
                "action": "SELL",
                "strength": 1.0
            }
        ],
        "position_size": 1.0,
        "stop_loss": 2.0,
        "take_profit": 5.0
    }
    
    # Mock مؤشر SMA
    with patch('app.services.strategy.IndicatorFactory.create_indicator') as mock_factory:
        mock_indicator = Mock()
        
        # إعداد mock لإرجاع قيم SMA تجريبية
        sma_values = data['close'].rolling(window=5).mean()
        mock_indicator.calculate.return_value.values = sma_values
        mock_indicator.name = "sma"
        
        mock_factory.return_value = mock_indicator
        
        # تشغيل الاستراتيجية
        result = await run_strategy(data, simple_config, live_mode=False)
        
        # التحقق من النتائج
        assert isinstance(result, StrategyResult)
        assert hasattr(result, 'signals')
        assert hasattr(result, 'filtered_signals')
        assert hasattr(result, 'metrics')
        
        # يجب أن تحتوي على إشارات (حسب البيانات)
        # في هذه الحالة قد تكون هناك إشارات أو لا، حسب البيانات العشوائية

@pytest.mark.asyncio
async def test_run_strategy_live_mode():
    """اختبار وضع التشغيل المباشر"""
    data = create_test_data()
    
    config = {
        "name": "live_test",
        "version": "1.0.0",
        "timeframe": "1h",
        "indicators": [],
        "entry_rules": [],
        "exit_rules": [],
        "position_size": 1.0
    }
    
    # في وضع live، قد يكون هناك سلوك مختلف (مثل عدم استخدام كل البيانات)
    result = await run_strategy(data, config, live_mode=True)
    
    assert isinstance(result, StrategyResult)
    # يمكن إضافة تحقق إضافي لوضع live

@pytest.mark.asyncio
async def test_run_strategy_no_indicators():
    """اختبار استراتيجية بدون مؤشرات"""
    data = create_test_data()
    
    config = {
        "name": "no_indicator_strategy",
        "version": "1.0.0",
        "timeframe": "1h",
        "indicators": [],
        "entry_rules": [
            {
                "name": "always_buy",
                "condition": "True",  # دائماً تشتري
                "action": "BUY",
                "strength": 1.0
            }
        ],
        "exit_rules": [],
        "position_size": 1.0
    }
    
    result = await run_strategy(data, config, live_mode=False)
    
    # يجب أن تحتوي على إشارات شراء على كل صف
    assert len(result.signals) > 0
    assert all(s.action == "BUY" for s in result.signals)

def test_trade_signal_creation():
    """اختبار إنشاء إشارة تجارية"""
    timestamp = datetime.now()
    signal = TradeSignal(
        timestamp=timestamp,
        action="BUY",
        price=100.50,
        reason="RSI oversold",
        rule_name="rsi_buy_rule",
        strength=0.8,
        metadata={"rsi_value": 25.5}
    )
    
    assert signal.timestamp == timestamp
    assert signal.action == "BUY"
    assert signal.price == 100.50
    assert signal.reason == "RSI oversold"
    assert signal.rule_name == "rsi_buy_rule"
    assert signal.strength == 0.8
    assert signal.metadata["rsi_value"] == 25.5

def test_trade_signal_to_dict():
    """اختبار تحويل إشارة تجارية إلى قاموس"""
    timestamp = datetime(2025, 1, 1, 10, 30, 0)
    signal = TradeSignal(
        timestamp=timestamp,
        action="SELL",
        price=99.75,
        reason="Take profit",
        rule_name="tp_rule",
        strength=1.0,
        metadata={"profit_percent": 5.0}
    )
    
    signal_dict = {
        "timestamp": timestamp.isoformat(),
        "action": "SELL",
        "price": 99.75,
        "reason": "Take profit",
        "rule_name": "tp_rule",
        "strength": 1.0,
        "metadata": {"profit_percent": 5.0}
    }
    
    # يجب أن يكون هناك طريقة لتحويل Signal إلى dict
    # أو يمكن اختبار أن الـ router يحولها بشكل صحيح

@pytest.mark.asyncio
async def test_run_strategy_with_filtered_signals():
    """اختبار الاستراتيجية مع تصفية الإشارات"""
    data = create_test_data()
    
    config = {
        "name": "filter_test",
        "version": "1.0.0",
        "timeframe": "1h",
        "indicators": [],
        "entry_rules": [
            {
                "name": "buy_even",
                "condition": "index % 2 == 0",  # شراء في الصفوف الزوجية
                "action": "BUY",
                "strength": 1.0
            },
            {
                "name": "buy_odd",
                "condition": "index % 2 == 1",  # شراء في الصفوف الفردية
                "action": "BUY",
                "strength": 0.5  # قوة أقل
            }
        ],
        "exit_rules": [],
        "position_size": 1.0,
        "signal_filtering": {
            "min_strength": 0.6,  # تجاهل الإشارات ذات القوة < 0.6
            "max_signals_per_day": 5
        }
    }
    
    result = await run_strategy(data, config, live_mode=False)
    
    # يجب أن تحتوي filtered_signals على إشارات أقل من signals
    # لأن الإشارات ذات القوة 0.5 يجب أن تُفلتر
    assert len(result.filtered_signals) <= len(result.signals)
    # جميع الإشارات المفلترة يجب أن تكون قوتها >= 0.6
    assert all(s.strength >= 0.6 for s in result.filtered_signals)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])