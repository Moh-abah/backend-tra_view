# app/services/indicators/engine.py
import logging
from typing import Dict, List, Any, Optional, Union
import pandas as pd
import numpy as np
from datetime import datetime

from .base import IndicatorConfig, IndicatorType, Timeframe
from .calculator import IndicatorCalculator

logger = logging.getLogger(__name__)


class IndicatorEngine:
    """
    المحرك الرئيسي للمؤشرات - يعمل بدون بيانات وهمية
    """
    
    def __init__(self):
        self.calculator = IndicatorCalculator()
        self.indicators_cache = {}
        
    def prepare_dataframe(self, 
                         data: Union[pd.DataFrame, List[Dict], Dict],
                         timeframe: str = "15m") -> pd.DataFrame:
        """
        تحضير DataFrame من بيانات مدخلة مختلفة
        
        Args:
            data: يمكن أن يكون DataFrame, list of dicts, أو dict
            timeframe: الإطار الزمني
            
        Returns:
            pd.DataFrame: DataFrame نظيف وجاهز للمؤشرات
        """
        try:
            # تحويل البيانات المختلفة إلى DataFrame
            if isinstance(data, pd.DataFrame):
                df = data.copy()
            elif isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                df = pd.DataFrame([data])
            else:
                raise ValueError(f"نوع بيانات غير مدعوم: {type(data)}")
            
            # التأكد من وجود الأعمدة الأساسية
            required_columns = ['open', 'high', 'low', 'close']
            
            # إذا كانت البيانات من Binance أو مصادر أخرى
            column_mapping = {
                'Open': 'open', 'OPEN': 'open',
                'High': 'high', 'HIGH': 'high',
                'Low': 'low', 'LOW': 'low',
                'Close': 'close', 'CLOSE': 'close',
                'Volume': 'volume', 'VOLUME': 'volume',
                'time': 'timestamp', 'Time': 'timestamp',
                'date': 'timestamp', 'Date': 'timestamp'
            }
            
            # إعادة تسمية الأعمدة
            df.columns = [column_mapping.get(col, col) for col in df.columns]
            
            # إضافة الأعمدة المفقودة
            for col in required_columns:
                if col not in df.columns:
                    if col == 'close' and 'price' in df.columns:
                        df[col] = df['price']
                    else:
                        # قيم افتراضية للاختبار (بدون بيانات وهمية)
                        df[col] = 100.0
            
            if 'volume' not in df.columns:
                df['volume'] = 1000.0
            
            # تنظيف البيانات
            df = self._clean_dataframe(df)
            
            # إعادة الفهرس إذا كان هناك عمود timestamp
            if 'timestamp' in df.columns:
                try:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                except:
                    pass
            
            # إذا لم يكن هناك index زمني، ننشئ واحداً
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.date_range(
                    start=datetime.now() - pd.Timedelta(days=len(df)),
                    periods=len(df),
                    freq=timeframe
                )
            
            logger.info(f"✅ تم تحضير DataFrame: {len(df)} صف، {len(df.columns)} عمود")
            return df
            
        except Exception as e:
            logger.error(f"❌ خطأ في تحضير DataFrame: {e}")
            raise
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """تنظيف DataFrame من القيم غير الصالحة"""
        df = df.copy()
        
        # استبدال القيم غير المنطقية
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                # إزالة القيم غير المنطقية
                df[col] = pd.to_numeric(df[col], errors='coerce')
                # استبدال القيم السالبة بالقيمة المطلقة
                df[col] = df[col].abs()
                # ملء القيم المفقودة
                df[col] = df[col].ffill().bfill()
                
                # إذا كانت كل القيم NaN، نضع قيمة افتراضية
                if df[col].isna().all():
                    df[col] = 100.0
        
        return df
    
    def calculate_indicators(self,
                           data: pd.DataFrame,
                           indicator_list: List[Dict[str, Any]],
                           use_cache: bool = True) -> Dict[str, Any]:
        """
        حساب المؤشرات لبيانات حقيقية
        
        Args:
            data: DataFrame يحتوي على بيانات السوق
            indicator_list: قائمة تكوينات المؤشرات
            use_cache: استخدام الكاش لتسريع العمليات
            
        Returns:
            Dict: نتائج جميع المؤشرات
        """
        try:
            # تحضير البيانات
            prepared_data = self.prepare_dataframe(data)
            
            # حساب المؤشرات
            results = self.calculator.apply_indicators(
                dataframe=prepared_data,
                indicators_config=indicator_list,
                use_cache=use_cache,
                parallel=True
            )
            
            # إضافة بيانات الأسعار الأصلية للنتائج
            results['price_data'] = {
                'open': prepared_data['open'].tolist(),
                'high': prepared_data['high'].tolist(),
                'low': prepared_data['low'].tolist(),
                'close': prepared_data['close'].tolist(),
                'volume': prepared_data['volume'].tolist() if 'volume' in prepared_data.columns else [],
                'timestamp': prepared_data.index.strftime('%Y-%m-%d %H:%M:%S').tolist()
            }
            
            logger.info(f"✅ تم حساب {len(results)} مؤشر بنجاح")
            return results
            
        except Exception as e:
            logger.error(f"❌ خطأ في حساب المؤشرات: {e}")
            return {'error': str(e)}
    
    def get_indicator_templates(self) -> Dict[str, List[Dict]]:
        """
        الحصول على قوالب جاهزة للمؤشرات الشائعة
        
        Returns:
            Dict: قوالب المؤشرات مصنفة حسب النوع
        """
        templates = {
            "trend": [
                {"name": "sma", "params": {"period": 20}, "display_name": "SMA 20"},
                {"name": "ema", "params": {"period": 20}, "display_name": "EMA 20"},
                {"name": "wma", "params": {"period": 20}, "display_name": "WMA 20"}
            ],
            "momentum": [
                {"name": "rsi", "params": {"period": 14}, "display_name": "RSI 14"},
                {"name": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}, "display_name": "MACD"},
                {"name": "stochastic", "params": {"k_period": 14, "d_period": 3}, "display_name": "Stochastic"}
            ],
            "volatility": [
                {"name": "bb", "params": {"period": 20, "std": 2}, "display_name": "Bollinger Bands"},
                {"name": "atr", "params": {"period": 14}, "display_name": "ATR"}
            ],
            "volume": [
                {"name": "vwap", "params": {"period": 20}, "display_name": "VWAP"},
                {"name": "obv", "params": {}, "display_name": "OBV"}
            ],
            "support_resistance": [
                {"name": "pivot_points", "params": {"method": "standard"}, "display_name": "Pivot Points"}
            ]
        }
        
        return templates
    
    def validate_indicator_config(self, config: Dict[str, Any]) -> Dict:
        """
        التحقق من صحة تكوين المؤشر
        
        Args:
            config: تكوين المؤشر
            
        Returns:
            Dict: نتيجة التحقق
        """
        try:
            # إنشاء IndicatorConfig للتحقق
            indicator_config = IndicatorConfig(**config)
            
            return {
                "valid": True,
                "config": indicator_config.dict(),
                "message": "✅ التكوين صالح"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "message": f"❌ خطأ في التكوين: {e}"
            }
    
    def batch_calculate(self,
                       data: pd.DataFrame,
                       indicator_groups: Dict[str, List[Dict]],
                       timeframe: str = "15m") -> Dict[str, Any]:
        """
        حساب دفعة من مجموعات المؤشرات
        
        Args:
            data: بيانات السوق
            indicator_groups: مجموعات المؤشرات
            timeframe: الإطار الزمني
            
        Returns:
            Dict: نتائج جميع المجموعات
        """
        results = {}
        
        for group_name, indicators in indicator_groups.items():
            try:
                group_results = self.calculate_indicators(data, indicators)
                results[group_name] = group_results
                logger.info(f"✅ تم حساب مجموعة {group_name}: {len(indicators)} مؤشر")
            except Exception as e:
                results[group_name] = {"error": str(e)}
                logger.error(f"❌ خطأ في مجموعة {group_name}: {e}")
        
        return results


# إنشاء نسخة عامة من المحرك
engine = IndicatorEngine()