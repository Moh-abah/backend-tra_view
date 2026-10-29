# tests/unit/test_trend_indicators.py
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.indicators.base import IndicatorConfig, IndicatorType, Timeframe
from app.services.indicators.trend import SMAIndicator, EMAIndicator

def create_sample_data(n=100):
    """إنشاء بيانات عينة للسعر"""
    # استخدام 'h' بدلاً من 'H' (حرف صغير)
    dates = pd.date_range(start='2025-01-01', periods=n, freq='h')
    
    # إنشاء سعر مع بعض الاتجاه والضوضاء
    trend = np.linspace(100, 150, n)
    noise = np.random.normal(0, 5, n)
    prices = trend + noise
    
    return pd.DataFrame({
        'open': prices - np.random.uniform(0.5, 2, n),
        'high': prices + np.random.uniform(0.5, 2, n),
        'low': prices - np.random.uniform(1, 3, n),
        'close': prices,
        'volume': np.random.randint(1000, 10000, n)
    }, index=dates)



def test_sma_indicator_basic():
    """اختبار SMA الأساسي"""
    data = create_sample_data(50)
    config = IndicatorConfig(
        name='sma',
        type=IndicatorType.TREND,
        params={'period': 10},
        timeframe=Timeframe.HOUR1
    )
    
    sma = SMAIndicator(config)
    result = sma.calculate(data)
    
    # التحقق من الشكل الأساسي
    assert result.name == 'sma'
    assert len(result.values) == len(data)
    assert result.values.index.equals(data.index)
    assert 'period' in result.metadata
    assert result.metadata['period'] == 10
    
    # مع min_periods=1، القيم الأولى لن تكون NaN
    # لذا نتوقع أن تكون جميع القيم محسوبة
    assert not pd.isna(result.values.iloc[0])  # هذا هو التعديل
    assert not pd.isna(result.values.iloc[8])
    
    # التحقق من أن القيم بعد الفترة ليست NaN
    assert not pd.isna(result.values.iloc[9])
    assert not pd.isna(result.values.iloc[49])
    
    # التحقق من أن SMA هو متوسط الفترة
    expected_sma = data['close'].rolling(window=10, min_periods=1).mean()
    pd.testing.assert_series_equal(result.values, expected_sma, check_dtype=False)


def test_sma_signals():
    """اختبار إشارات SMA"""
    # إنشاء بيانات بسيطة لتتبع الإشارات
    dates = pd.date_range('2025-01-01', periods=10, freq='D')
    data = pd.DataFrame({
        'open': [100, 102, 101, 103, 105, 107, 106, 108, 110, 109],
        'high': [102, 104, 103, 105, 107, 109, 108, 110, 112, 111],
        'low': [98, 100, 99, 101, 103, 105, 104, 106, 108, 107],
        'close': [101, 103, 102, 104, 106, 108, 107, 109, 111, 110],
        'volume': [1000] * 10
    }, index=dates)
    
    config = IndicatorConfig(
        name='sma',
        type=IndicatorType.TREND,
        params={'period': 3},
        timeframe=Timeframe.DAY1
    )
    
    sma = SMAIndicator(config)
    result = sma.calculate(data)
    
    # التحقق من وجود إشارات
    assert result.signals is not None
    assert len(result.signals) == len(data)
    
    # يمكنك إضافة المزيد من الاختبارات المحددة للإشارات

def test_ema_indicator():
    """اختبار EMA"""
    data = create_sample_data(50)
    config = IndicatorConfig(
        name='ema',
        type=IndicatorType.TREND,
        params={'period': 10},
        timeframe=Timeframe.HOUR1
    )
    
    ema = EMAIndicator(config)
    result = ema.calculate(data)
    
    # التحقق من الشكل الأساسي
    assert result.name == 'ema'
    assert len(result.values) == len(data)
    assert 'period' in result.metadata
    
    # التحقق من أن EMA مختلف عن SMA
    sma_config = IndicatorConfig(
        name='sma',
        type=IndicatorType.TREND,
        params={'period': 10},
        timeframe=Timeframe.HOUR1
    )
    sma = SMAIndicator(sma_config)
    sma_result = sma.calculate(data)
    
    # EMA يجب أن يكون مختلفاً عن SMA
    assert not result.values.equals(sma_result.values)
    
    # EMA يجب أن يتفاعل بشكل أسرع مع التغيرات
    # (يمكن إضافة اختبارات أكثر تعقيداً هنا)
def test_indicator_serialization():
    """اختبار تسلسل/تفريغ النتائج"""
    data = create_sample_data(20)
    config = IndicatorConfig(
        name='sma',
        type=IndicatorType.TREND,
        params={'period': 5},
        timeframe=Timeframe.HOUR1
    )
    
    sma = SMAIndicator(config)
    result = sma.calculate(data)
    
    # التحويل إلى dict والعودة
    result_dict = result.to_dict()
    result_from_dict = result.from_dict(result_dict)
    
    # التحقق من المساواة (تجاهل الاسم)
    pd.testing.assert_series_equal(
        result.values,
        result_from_dict.values,
        check_dtype=False,
        check_names=False  # تجاهل اسم السلسلة
    )
    
    # التحقق من بقية الخصائص
    assert result.name == result_from_dict.name
    assert result.metadata == result_from_dict.metadata
    
    # التحقق من الإشارات إذا كانت موجودة
    if result.signals is not None:
        pd.testing.assert_series_equal(
            result.signals,
            result_from_dict.signals,
            check_dtype=False,
            check_names=False
        )
    
    # التحويل إلى JSON والعودة
    json_str = result.to_json()
    result_from_json = result.from_json(json_str)
    
    pd.testing.assert_series_equal(
        result.values,
        result_from_json.values,
        check_dtype=False,
        check_names=False
    )


def test_invalid_period():
    """اختبار فترة غير صالحة"""
    data = create_sample_data(10)
    
    # فترة صغيرة جداً
    config = IndicatorConfig(
        name='sma',
        type=IndicatorType.TREND,
        params={'period': 0},  # غير صالح
        timeframe=Timeframe.HOUR1
    )
    
    with pytest.raises(ValueError):
        sma = SMAIndicator(config)
        sma.calculate(data)

def test_ema_with_different_periods():
    """اختبار EMA بفترات مختلفة"""
    data = create_sample_data(100)
    
    periods = [5, 10, 20, 50]
    results = []
    
    for period in periods:
        config = IndicatorConfig(
            name=f'ema_{period}',
            type=IndicatorType.TREND,
            params={'period': period},
            timeframe=Timeframe.HOUR1
        )
        
        ema = EMAIndicator(config)
        result = ema.calculate(data)
        results.append(result)
        
        # التحقق من أن EMA أصغر فترة يكون أكثر تقلباً
        if period > 5:
            # حساب التقلب (الانحراف المعياري للتغيرات)
            volatility_short = results[0].values.diff().std()
            volatility_long = result.values.diff().std()
            
            # EMA طويل الأجل يجب أن يكون أقل تقلباً
            assert volatility_long < volatility_short

if __name__ == '__main__':
    pytest.main([__file__, '-v'])