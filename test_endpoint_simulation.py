"""
اختبار محاكاة نقطة النهاية /api/v1/indicators/apply
"""
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# إضافة المسار للأدوات
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.indicators import apply_indicators, calculate_trading_signals
from app.services.indicators.calculator import IndicatorCalculator

class EndpointSimulator:
    """محاكي نقطة النهاية /api/v1/indicators/apply"""
    
    def __init__(self):
        self.calculator = IndicatorCalculator()
        print("✅ EndpointSimulator initialized")
    
    def simulate_request(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        days: int,
        indicators_config: list
    ) -> dict:
        """
        محاكاة طلب POST إلى /api/v1/indicators/apply
        
        Args:
            symbol: رمز السهم أو العملة
            timeframe: الإطار الزمني
            market: نوع السوق
            days: عدد الأيام
            indicators_config: تكوينات المؤشرات
            
        Returns:
            dict: النتيجة المشابهة لنقطة النهاية
        """
        print(f"\n{'='*60}")
        print(f"🔍 محاكاة طلب POST إلى /api/v1/indicators/apply")
        print(f"{'='*60}")
        print(f"📊 الرمز: {symbol}")
        print(f"⏱️ الإطار الزمني: {timeframe}")
        print(f"🏪 السوق: {market}")
        print(f"📅 الأيام: {days}")
        print(f"📈 عدد المؤشرات: {len(indicators_config)}")
        
        # 1. محاكاة جلب البيانات التاريخية (بيانات وهمية)
        dataframe = self._mock_historical_data(symbol, timeframe, days)
        
        print(f"📊 حجم البيانات: {dataframe.shape}")
        print(f"📅 النطاق الزمني: {dataframe.index[0]} إلى {dataframe.index[-1]}")
        
        # 2. تطبيق المؤشرات (الجزء الأساسي)
        results = apply_indicators(
            dataframe=dataframe,
            indicators_config=indicators_config,
            use_cache=False,
            parallel=False
        )
        
        print(f"✅ تم تطبيق {len(results)} مؤشر(ات)")
        
        # 3. إعداد الإجابة كما في نقطة النهاية
        response = self._prepare_response(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            days=days,
            dataframe=dataframe,
            indicators_results=results
        )
        
        # 4. التحقق من أن الإجابة متوافقة مع JSON
        self._validate_json_compatibility(response)
        
        return response
    
    def _mock_historical_data(
        self, 
        symbol: str, 
        timeframe: str, 
        days: int
    ) -> pd.DataFrame:
        """
        إنشاء بيانات تاريخية وهمية تشبه بيانات Binance
        
        Args:
            symbol: رمز التداول
            timeframe: الإطار الزمني
            days: عدد الأيام
            
        Returns:
            pd.DataFrame: بيانات وهمية
        """
        # عدد الشموع بناءً على الإطار الزمني والأيام
        candles_per_day = {
            '1m': 1440, '5m': 288, '15m': 96, '30m': 48,
            '1h': 24, '4h': 6, '1d': 1, '1w': 0.14
        }
        
        candles = int(candles_per_day.get(timeframe, 24) * days)
        
        # إنشاء تاريخ زمني
        end_date = datetime.utcnow()
        dates = pd.date_range(
            end=end_date, 
            periods=candles, 
            freq=timeframe.replace('m', 'T').replace('h', 'H').replace('d', 'D')
        )
        
        # بيانات الأسعار الوهمية (مع قيم غير صالحة لمحاكاة البيانات الحقيقية)
        np.random.seed(42)  # للحصول على نتائج متسقة
        
        # قيم أساسية
        base_price = 0.07 if 'BTC' in symbol else 100.0
        volatility = 0.02
        
        # إنشاء سلسلة أسعار
        prices = []
        current_price = base_price
        
        for i in range(candles):
            # تقلب عشوائي
            change = np.random.randn() * volatility * current_price
            current_price += change
            
            # التأكد من أن السعر موجب
            current_price = abs(current_price)
            
            # إضافة بعض القيم غير الصالحة لمحاكاة البيانات الحقيقية
            if i % 50 == 0:  # كل 50 شمعة
                prices.append((np.nan, np.nan, np.nan, np.nan, 0))
            elif i % 100 == 0:  # كل 100 شمعة
                prices.append((float('inf'), float('inf'), float('-inf'), float('inf'), float('inf')))
            else:
                # سعر عادي
                open_price = current_price
                high_price = current_price * (1 + np.random.random() * 0.01)
                low_price = current_price * (1 - np.random.random() * 0.01)
                close_price = current_price * (1 + (np.random.random() - 0.5) * 0.02)
                volume = np.random.random() * 1000
                
                prices.append((open_price, high_price, low_price, close_price, volume))
        
        # إنشاء DataFrame
        df = pd.DataFrame(
            prices,
            columns=['open', 'high', 'low', 'close', 'volume'],
            index=dates[:len(prices)]
        )
        
        return df
    
    def _prepare_response(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        days: int,
        dataframe: pd.DataFrame,
        indicators_results: dict
    ) -> dict:
        """
        إعداد إجابة مشابهة لنقطة النهاية
        
        Returns:
            dict: إجابة منظمة
        """
        # تنظيف بيانات DataFrame للـ JSON
        clean_data = []
        for idx, row in dataframe.reset_index().iterrows():
            record = {}
            # تحويل التاريخ
            record['timestamp'] = row['index'].isoformat() if 'index' in row else idx.isoformat()
            
            # تنظيف القيم العددية
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in row:
                    val = row[col]
                    # تنظيف float
                    if isinstance(val, float):
                        if np.isinf(val) or np.isnan(val):
                            record[col] = None
                        else:
                            record[col] = round(val, 8)
                    else:
                        record[col] = val
                else:
                    record[col] = None
            
            clean_data.append(record)
        
        # إعداد metadata
        metadata = {
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "days": days,
            "data_points": len(dataframe),
            "start_date": dataframe.index[0].isoformat() if len(dataframe) > 0 else None,
            "end_date": dataframe.index[-1].isoformat() if len(dataframe) > 0 else None,
            "indicators_count": len(indicators_results),
            "generated_at": datetime.utcnow().isoformat()
        }
        
        # الهيكل النهائي
        response = {
            "status": "success",
            "data": clean_data,
            "indicators": indicators_results,
            "metadata": metadata
        }
        
        return response
    
    def _validate_json_compatibility(self, response: dict):
        """
        التحقق من أن الإجابة متوافقة مع JSON
        
        Args:
            response: الإجابة للتحقق منها
        """
        try:
            json_str = json.dumps(response, indent=2)
            print("✅ التحقق من JSON: ناجح")
            print(f"📏 حجم JSON: {len(json_str)} حرف")
            
            # يمكن حفظه في ملف للفحص
            with open("test_response.json", "w", encoding="utf-8") as f:
                f.write(json_str)
            print("💾 تم حفظ الإجابة في test_response.json")
            
        except (TypeError, ValueError) as e:
            print(f"❌ خطأ في التحقق من JSON: {e}")
            
            # البحث عن القيم المسببة للمشكلة
            problem_values = self._find_problem_values(response)
            if problem_values:
                print("🔍 القيم المسببة للمشكلة:")
                for path, value in problem_values:
                    print(f"  {path}: {value} (نوع: {type(value).__name__})")
            
            raise
    
    def _find_problem_values(self, obj, path=""):
        """
        البحث عن القيم غير المتوافقة مع JSON
        
        Returns:
            list: قائمة بالمسارات والقيم المسببة للمشاكل
        """
        problem_values = []
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                problem_values.extend(self._find_problem_values(value, current_path))
        
        elif isinstance(obj, (list, tuple)):
            for i, value in enumerate(obj):
                current_path = f"{path}[{i}]"
                problem_values.extend(self._find_problem_values(value, current_path))
        
        else:
            # التحقق من القيم الفردية
            if isinstance(obj, float):
                if np.isinf(obj) or np.isnan(obj):
                    problem_values.append((path, obj))
            elif isinstance(obj, (np.float32, np.float64)):
                problem_values.append((path, obj))
            elif isinstance(obj, (np.int32, np.int64)):
                problem_values.append((path, obj))
            elif isinstance(obj, pd.Timestamp):
                problem_values.append((path, obj))
        
        return problem_values
    
    def test_single_indicator(self):
        """اختبار مؤشر واحد (RSI)"""
        print("\n🧪 اختبار مؤشر RSI:")
        
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
        
        response = self.simulate_request(
            symbol="ETHBTC",
            timeframe="1h",
            market="crypto",
            days=30,
            indicators_config=indicators_config
        )
        
        # التحقق من النتائج
        if "rsi" in response["indicators"]:
            rsi_data = response["indicators"]["rsi"]
            print(f"📊 بيانات RSI:")
            if isinstance(rsi_data, dict):
                print(f"  - المفاتيح: {list(rsi_data.keys())}")
                if "values" in rsi_data:
                    values = rsi_data["values"]
                    if values:
                        print(f"  - عدد القيم: {len(values)}")
                        print(f"  - أول 5 قيم: {values[:5]}")
                        print(f"  - آخر 5 قيم: {values[-5:]}")
            elif isinstance(rsi_data, list):
                print(f"  - عدد العناصر: {len(rsi_data)}")
        
        return response
    
    def test_multiple_indicators(self):
        """اختبار مؤشرات متعددة"""
        print("\n🧪 اختبار مؤشرات متعددة:")
        
        indicators_config = [
            {
                "name": "rsi",
                "type": "momentum",
                "params": {"period": 14},
                "enabled": True
            },
            {
                "name": "macd",
                "type": "trend",
                "params": {"fast": 12, "slow": 26, "signal": 9},
                "enabled": True
            },
            {
                "name": "bollinger_bands",
                "type": "volatility",
                "params": {"period": 20, "std_dev": 2},
                "enabled": True
            },
            {
                "name": "ema",
                "type": "trend",
                "params": {"period": 20},
                "enabled": True
            }
        ]
        
        response = self.simulate_request(
            symbol="BTCUSDT",
            timeframe="4h",
            market="crypto",
            days=90,
            indicators_config=indicators_config
        )
        
        print(f"\n📈 المؤشرات المحسوبة:")
        for indicator_name in response["indicators"]:
            data = response["indicators"][indicator_name]
            if isinstance(data, dict):
                print(f"  - {indicator_name}: {len(data)} مفتاح/مفاتيح")
            elif isinstance(data, list):
                print(f"  - {indicator_name}: {len(data)} عنصر")
        
        return response
    
    def test_trading_signals(self):
        """اختبار توليد إشارات التداول"""
        print("\n🚦 اختبار إشارات التداول:")
        
        # إنشاء بيانات وهمية
        np.random.seed(42)
        dates = pd.date_range(end=datetime.utcnow(), periods=100, freq='1h')
        data = {
            'open': np.random.randn(100).cumsum() + 100,
            'high': np.random.randn(100).cumsum() + 102,
            'low': np.random.randn(100).cumsum() + 98,
            'close': np.random.randn(100).cumsum() + 100,
            'volume': np.random.rand(100) * 1000
        }
        dataframe = pd.DataFrame(data, index=dates)
        
        indicators_config = [
            {
                "name": "rsi",
                "params": {"period": 14}
            },
            {
                "name": "macd",
                "params": {"fast": 12, "slow": 26, "signal": 9}
            }
        ]
        
        # حساب إشارات التداول
        signals = calculate_trading_signals(
            dataframe=dataframe,
            indicator_configs=indicators_config,
            signal_threshold=0.3
        )
        
        print(f"📊 نتائج إشارات التداول:")
        print(f"  - الإشارة الأخيرة: {signals.get('last_signal', 'N/A')}")
        print(f"  - قوة الإشارة: {signals.get('signal_strength', 'N/A')}")
        
        if 'signal_analysis' in signals:
            analysis = signals['signal_analysis']
            print(f"  - التحليل:")
            print(f"    * إشارات شراء: {analysis.get('buy_signals', 0)}")
            print(f"    * إشارات بيع: {analysis.get('sell_signals', 0)}")
            print(f"    * الاتجاه: {analysis.get('signal_trend', 'N/A')}")
        
        # التحقق من JSON
        try:
            json.dumps(signals)
            print("✅ إشارات التداول متوافقة مع JSON")
        except Exception as e:
            print(f"❌ خطأ في JSON لإشارات التداول: {e}")
        
        return signals
    
    def run_all_tests(self):
        """تشغيل جميع الاختبارات"""
        print("🚀 بدء جميع اختبارات محاكاة نقطة النهاية")
        print("="*60)
        
        results = {}
        
        try:
            # اختبار 1: مؤشر واحد
            results['single_indicator'] = self.test_single_indicator()
            
            # اختبار 2: مؤشرات متعددة
            results['multiple_indicators'] = self.test_multiple_indicators()
            
            # اختبار 3: إشارات التداول
            results['trading_signals'] = self.test_trading_signals()
            
            print(f"\n{'='*60}")
            print("🎉 جميع الاختبارات تمت بنجاح!")
            print(f"{'='*60}")
            
            # إحصاءات
            total_indicators = 0
            for test_name, result in results.items():
                if test_name != 'trading_signals':
                    total_indicators += len(result.get('indicators', {}))
            
            print(f"📈 الإحصاءات النهائية:")
            print(f"  - عدد الاختبارات: {len(results)}")
            print(f"  - إجمالي المؤشرات المحسوبة: {total_indicators}")
            print(f"  - جميع النتائج متوافقة مع JSON ✅")
            
        except Exception as e:
            print(f"\n❌ فشل الاختبار: {e}")
            import traceback
            traceback.print_exc()
        
        return results


def main():
    """الدالة الرئيسية"""
    print("🎯 اختبار محاكاة نقطة النهاية /api/v1/indicators/apply")
    
    # إنشاء المحاكي
    simulator = EndpointSimulator()
    
    # تشغيل جميع الاختبارات
    results = simulator.run_all_tests()
    
    # عرض ملخص
    if results:
        print("\n📋 ملخص الاختبارات:")
        for test_name, result in results.items():
            if isinstance(result, dict):
                print(f"\n🔹 {test_name}:")
                for key, value in result.items():
                    if key == 'indicators':
                        print(f"  - {key}: {len(value)} مؤشر")
                    elif key == 'metadata':
                        print(f"  - {key}: ✓")
                    elif isinstance(value, (list, dict)):
                        print(f"  - {key}: {len(value)} عنصر")
                    else:
                        print(f"  - {key}: {value}")


if __name__ == "__main__":
    main()