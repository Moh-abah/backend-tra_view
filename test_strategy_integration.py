import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import asyncio
import logging
from typing import Dict, Any
import sys
import os

# إضافة المسار إلى sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.strategy.core import StrategyEngine
from app.services.strategy.schemas import (
    StrategyConfig, EntryRule, ExitRule, Condition, 
    PositionSide, RiskManagementConfig, IndicatorConfig
)
from app.services.strategy.conditions import ConditionEvaluator

# تكوين logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_data(
    symbol: str = "ETHUSDT", 
    timeframe: str = "1m",
    days: int = 100
) -> pd.DataFrame:
    """
    إنشاء بيانات اختبارية واقعية
    """
    logger.info(f"إنشاء بيانات اختبارية: {symbol}, {timeframe}, {days} يوم")
    
    # إنشاء تواريخ
    end_date = datetime.now()
    if timeframe == "1m":
        periods = days * 24 * 60  # 100 يوم × 24 ساعة × 60 دقيقة
        start_date = end_date - timedelta(days=days)
        dates = pd.date_range(start=start_date, end=end_date, freq='1min')
    elif timeframe == "1d":
        periods = days
        start_date = end_date - timedelta(days=days)
        dates = pd.date_range(start=start_date, end=end_date, freq='1D')
    else:
        periods = days * 24  # افتراضي 1 ساعة
        start_date = end_date - timedelta(days=days)
        dates = pd.date_range(start=start_date, end=end_date, freq='1H')
    
    # إنشاء بيانات واقعية مع بعض الاتجاه والتقلب
    np.random.seed(42)
    base_price = 3500  # سعر ETH تقريبي
    
    # إنشاء اتجاه مع تقلبات
    trend = np.linspace(0, 0.2, periods)  # اتجاه صعودي 20%
    noise = np.random.normal(0, 0.01, periods)  # ضوضاء يومية
    
    # إنشاء أسعار
    returns = trend + noise
    prices = base_price * np.exp(np.cumsum(returns))
    
    # إنشاء OHLCV
    open_prices = prices * (1 + np.random.normal(0, 0.005, periods))
    high_prices = open_prices * (1 + np.abs(np.random.normal(0, 0.01, periods)))
    low_prices = open_prices * (1 - np.abs(np.random.normal(0, 0.01, periods)))
    close_prices = prices
    volume = np.random.randint(1000, 10000, periods)
    
    # إنشاء DataFrame
    data = pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volume
    }, index=dates[:periods])
    
    logger.info(f"تم إنشاء بيانات: شكل {data.shape}")
    logger.info(f"النطاق الزمني: {data.index[0]} إلى {data.index[-1]}")
    
    return data

def create_test_strategy() -> Dict[str, Any]:
    """
    إنشاء إستراتيجية اختبارية
    """
    return {
        "name": "SMA Quick Test",
        "version": "1.0.0",
        "description": "استراتيجية اختبارية سريعة لتوليد إشارات",
        "base_timeframe": "1m",
        "position_side": "long",
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
        "indicators": [
            {
                "name": "sma_fast",
                "type": "trend",
                "params": {"period": 5},  # فترة قصيرة لضمان وجود تقاطعات
                "enabled": True,
                "timeframe": "1m"
            },
            {
                "name": "sma_slow",
                "type": "trend",
                "params": {"period": 10},
                "enabled": True,
                "timeframe": "1m"
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
        "filter_rules": [],
        "risk_management": {
            "stop_loss_percentage": 5.0,
            "take_profit_percentage": 10.0,
            "max_position_size": 0.5
        }
    }

def test_data_structure():
    """اختبار هيكل البيانات"""
    logger.info("=" * 60)
    logger.info("اختبار هيكل البيانات")
    logger.info("=" * 60)
    
    data = create_test_data()
    
    # التحقق من الأعمدة
    required_columns = ['open', 'high', 'low', 'close', 'volume']
    missing_columns = [col for col in required_columns if col not in data.columns]
    
    if missing_columns:
        logger.error(f"❌ أعمدة مفقودة: {missing_columns}")
    else:
        logger.info("✅ جميع الأعمدة موجودة")
    
    # التحقق من الفهرس
    logger.info(f"نوع الفهرس: {type(data.index)}")
    logger.info(f"طول البيانات: {len(data)}")
    logger.info(f"عينة من البيانات:\n{data.head(3)}")
    
    return data

def test_indicators_calculation():
    """اختبار حساب المؤشرات"""
    logger.info("\n" + "=" * 60)
    logger.info("اختبار حساب المؤشرات")
    logger.info("=" * 60)
    
    data = create_test_data(days=10)  # بيانات أقل للاختبار
    
    # استيراد دالة حساب المؤشرات
    from app.services.indicators import apply_indicators
    
    strategy_config = create_test_strategy()
    indicators_config = strategy_config["indicators"]
    
    logger.info(f"عدد المؤشرات: {len(indicators_config)}")
    
    try:
        # حساب المؤشرات
        indicators = apply_indicators(
            dataframe=data,
            indicators_config=indicators_config,
            use_cache=False
        )
        
        logger.info(f"✅ تم حساب المؤشرات بنجاح")
        logger.info(f"عدد المؤشرات المحسوبة: {len(indicators)}")
        
        # عرض عينة من كل مؤشر
        for name, values in indicators.items():
            logger.info(f"\nالمؤشر: {name}")
            if isinstance(values, pd.Series):
                logger.info(f"  النوع: Series")
                logger.info(f"  الطول: {len(values)}")
                logger.info(f"  القيم غير NaN: {values.notna().sum()}")
                logger.info(f"  أول 5 قيم: {values.head(5).tolist()}")
            elif isinstance(values, np.ndarray):
                logger.info(f"  النوع: ndarray")
                logger.info(f"  الشكل: {values.shape}")
                logger.info(f"  أول 5 قيم: {values[:5]}")
            else:
                logger.info(f"  النوع: {type(values)}")
                
    except Exception as e:
        logger.error(f"❌ خطأ في حساب المؤشرات: {e}")
        import traceback
        logger.error(traceback.format_exc())

def test_condition_evaluator():
    """اختبار تقييم الشروط"""
    logger.info("\n" + "=" * 60)
    logger.info("اختبار تقييم الشروط")
    logger.info("=" * 60)
    
    # إنشاء بيانات بسيطة للاختبار
    dates = pd.date_range(end=datetime.now(), periods=20, freq='1min')
    data = pd.DataFrame({
        'open': [100] * 20,
        'high': [102] * 20,
        'low': [98] * 20,
        'close': list(range(95, 115)),  # سعر يرتفع تدريجياً
        'volume': [1000] * 20
    }, index=dates)
    
    # حساب SMA يدوياً للاختبار
    sma_fast = data['close'].rolling(window=5).mean()
    sma_slow = data['close'].rolling(window=10).mean()
    
    logger.info(f"السعر الأخير: {data['close'].iloc[-1]}")
    logger.info(f"SMA السريع (5): {sma_fast.dropna().tail().tolist()}")
    logger.info(f"SMA البطيء (10): {sma_slow.dropna().tail().tolist()}")
    
    # إنشاء مؤشرات
    indicators = {
        'sma_fast': sma_fast,
        'sma_slow': sma_slow
    }
    
    # اختبار ConditionEvaluator
    evaluator = ConditionEvaluator()
    evaluator.set_indicators_data(indicators)
    
    # إنشاء شرط تقاطع
    condition = Condition(
        type="indicator_crossover",
        operator="cross_above",
        left_value="indicator:sma_fast",
        right_value="indicator:sma_slow"
    )
    
    # اختبار التقييم عند نقاط مختلفة
    test_points = [10, 11, 12, 13, 14, 15]  # بعد أن تمتلىء النوافذ
    
    for idx in test_points:
        try:
            result = evaluator.evaluate(condition, data, indicators, idx)
            logger.info(f"  الفهرس {idx}: {result}")
            logger.info(f"    sma_fast[{idx}] = {sma_fast.iloc[idx]}")
            logger.info(f"    sma_slow[{idx}] = {sma_slow.iloc[idx]}")
            logger.info(f"    سعر[{idx}] = {data['close'].iloc[idx]}")
        except Exception as e:
            logger.error(f"  الفهرس {idx}: خطأ - {e}")

async def test_strategy_engine_full():
    """اختبار كامل لمحرك الإستراتيجية"""
    logger.info("\n" + "=" * 60)
    logger.info("اختبار كامل لمحرك الإستراتيجية")
    logger.info("=" * 60)
    
    # 1. إنشاء البيانات
    data = create_test_data(days=30)  # 30 يوم للاختبار
    
    # 2. إنشاء تكوين الإستراتيجية
    strategy_dict = create_test_strategy()
    
    logger.info(f"اسم الإستراتيجية: {strategy_dict['name']}")
    logger.info(f"قواعد الدخول: {len(strategy_dict['entry_rules'])}")
    logger.info(f"قواعد الخروج: {len(strategy_dict['exit_rules'])}")
    
    # 3. تحميل الإستراتيجية
    from app.services.strategy.loader import StrategyLoader
    loader = StrategyLoader()
    
    try:
        config = StrategyConfig(**strategy_dict)
        logger.info("✅ تم إنشاء StrategyConfig بنجاح")
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء StrategyConfig: {e}")
        return
    
    # 4. إنشاء محرك الإستراتيجية
    engine = StrategyEngine(config)
    logger.info("✅ تم إنشاء محرك الإستراتيجية")
    
    # 5. تشغيل الإستراتيجية مع تفصيل خطوة بخطوة
    logger.info("\n🚀 بدء تشغيل الإستراتيجية...")
    
    try:
        result = await engine.run_strategy(data, live_mode=False, use_cache=False)
        
        logger.info(f"✅ تم تشغيل الإستراتيجية")
        logger.info(f"عدد الإشارات: {len(result.signals)}")
        logger.info(f"عدد الإشارات المفلترة: {len(result.filtered_signals)}")
        logger.info(f"المقاييس: {result.metrics}")
        
        # عرض تفاصيل الإشارات
        if result.signals:
            logger.info("\n📊 الإشارات المولدة:")
            for i, signal in enumerate(result.signals[:10]):  # عرض أول 10 إشارات
                logger.info(f"  [{i+1}] {signal.timestamp}: {signal.action} بسعر {signal.price}")
                logger.info(f"      السبب: {signal.reason}")
                logger.info(f"      القاعدة: {signal.rule_name}")
                logger.info(f"      القوة: {signal.strength}")
        else:
            logger.warning("⚠️ لم يتم توليد أي إشارات!")
            
            # فحص البيانات والمؤشرات بالتفصيل
            logger.info("\n🔍 فحص تفصيلي للبيانات:")
            
            # حساب SMA يدوياً للتحقق
            close_prices = data['close']
            sma_fast = close_prices.rolling(window=5).mean()
            sma_slow = close_prices.rolling(window=10).mean()
            
            # البحث عن تقاطعات
            crossover_above = (sma_fast.shift(1) < sma_slow.shift(1)) & (sma_fast > sma_slow)
            crossover_below = (sma_fast.shift(1) > sma_slow.shift(1)) & (sma_fast < sma_slow)
            
            logger.info(f"عدد نقاط البيانات: {len(data)}")
            logger.info(f"نقاط SMA السريع غير NaN: {sma_fast.notna().sum()}")
            logger.info(f"نقاط SMA البطيء غير NaN: {sma_slow.notna().sum()}")
            logger.info(f"عدد التقاطعات فوق: {crossover_above.sum()}")
            logger.info(f"عدد التقاطعات تحت: {crossover_below.sum()}")
            
            if crossover_above.any():
                crossover_indices = np.where(crossover_above)[0]
                logger.info("أمثلة على تقاطعات فوق:")
                for idx in crossover_indices[:5]:
                    logger.info(f"  الفهرس {idx}:")
                    logger.info(f"    الوقت: {data.index[idx]}")
                    logger.info(f"    السعر: {close_prices.iloc[idx]}")
                    logger.info(f"    SMA السريع: {sma_fast.iloc[idx]}")
                    logger.info(f"    SMA البطيء: {sma_slow.iloc[idx]}")
                    
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل الإستراتيجية: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def test_simple_crossover():
    """اختبار بسيط للتقاطع"""
    logger.info("\n" + "=" * 60)
    logger.info("اختبار بسيط للتقاطع")
    logger.info("=" * 60)
    
    # إنشاء بيانات بسيطة جداً مع تقاطع واضح
    dates = pd.date_range(end=datetime.now(), periods=15, freq='1min')
    
    # إنشاء بيانات حيث SMA السريع يتقاطع فوق SMA البطيء عند الفهرس 10
    close_prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 115, 116, 117, 118, 119]
    
    data = pd.DataFrame({
        'open': close_prices,
        'high': [p * 1.01 for p in close_prices],
        'low': [p * 0.99 for p in close_prices],
        'close': close_prices,
        'volume': [1000] * 15
    }, index=dates)
    
    # حساب SMA يدوياً
    sma_fast = data['close'].rolling(window=5).mean()
    sma_slow = data['close'].rolling(window=10).mean()
    
    logger.info("بيانات الاختبار:")
    logger.info(f"السعر: {close_prices}")
    logger.info(f"SMA السريع (5): {sma_fast.tolist()}")
    logger.info(f"SMA البطيء (10): {sma_slow.tolist()}")
    
    # التحقق من التقاطع
    for i in range(10, 15):
        logger.info(f"\nالنقطة {i}:")
        logger.info(f"  sma_fast[{i}] = {sma_fast.iloc[i]}")
        logger.info(f"  sma_slow[{i}] = {sma_slow.iloc[i]}")
        logger.info(f"  sma_fast > sma_slow? {sma_fast.iloc[i] > sma_slow.iloc[i]}")
        
        if i > 0:
            logger.info(f"  التقاطع فوق؟ {(sma_fast.iloc[i-1] < sma_slow.iloc[i-1]) and (sma_fast.iloc[i] > sma_slow.iloc[i])}")
    
    # الآن اختبر مع الإستراتيجية
    strategy_dict = {
        "name": "Simple Test",
        "version": "1.0",
        "description": "Test",
        "base_timeframe": "1m",
        "position_side": "long",
        "initial_capital": 10000,
        "commission_rate": 0.001,
        "indicators": [
            {
                "name": "sma_fast",
                "type": "trend",
                "params": {"period": 5},
                "enabled": True,
                "timeframe": "1m"
            },
            {
                "name": "sma_slow",
                "type": "trend",
                "params": {"period": 10},
                "enabled": True,
                "timeframe": "1m"
            }
        ],
        "entry_rules": [
            {
                "name": "Entry",
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
        "exit_rules": [],
        "filter_rules": [],
        "risk_management": {
            "stop_loss_percentage": 5.0,
            "take_profit_percentage": 10.0,
            "max_position_size": 0.5
        }
    }
    
    config = StrategyConfig(**strategy_dict)
    engine = StrategyEngine(config)
    
    result = await engine.run_strategy(data, live_mode=False, use_cache=False)
    
    logger.info(f"\nنتائج الإستراتيجية:")
    logger.info(f"عدد الإشارات: {len(result.signals)}")
    
    if result.signals:
        for signal in result.signals:
            logger.info(f"  إشارة: {signal.action} عند {signal.timestamp} بسعر {signal.price}")
    else:
        logger.error("❌ لم يتم توليد إشارات على الرغم من وجود تقاطع واضح!")

def main():
    """الدالة الرئيسية"""
    logger.info("بدء اختبارات التكامل للإستراتيجية")
    logger.info("=" * 60)
    
    # تشغيل الاختبارات
    data = test_data_structure()
    
    test_indicators_calculation()
    
    test_condition_evaluator()
    
    # تشغيل الاختبارات غير المتزامنة
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    loop.run_until_complete(test_strategy_engine_full())
    
    loop.run_until_complete(test_simple_crossover())
    
    logger.info("\n" + "=" * 60)
    logger.info("اكتملت جميع الاختبارات")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()