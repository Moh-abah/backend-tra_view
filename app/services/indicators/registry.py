

# app\services\indicators\registry.py

from typing import Dict, Type, List, Optional, Any
from dataclasses import dataclass
import inspect
import logging
import pandas as pd
from .base import BaseIndicator, IndicatorConfig, IndicatorType, IndicatorResult

logger = logging.getLogger(__name__)

@dataclass
class IndicatorInfo:
    """معلومات المؤشر المسجل"""
    name: str
    display_name: str
    description: str
    indicator_class: Type[BaseIndicator]
    category: IndicatorType
    default_params: Dict[str, Any]
    required_columns: List[str]

class IndicatorRegistry:
    """سجل مركزي لتسجيل وإدارة المؤشرات"""
    
    _instance = None
    _indicators: Dict[str, IndicatorInfo] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._calculated_indicators: Dict[str, pd.Series] = {} # type: ignore
        return cls._instance
    
    @classmethod
    def register(
        cls,
        name: str,
        display_name: Optional[str] = None,
        description: str = "",
        category: IndicatorType = IndicatorType.CUSTOM
    ):
        """ديكوراتور لتسجيل مؤشر جديد"""
        def decorator(indicator_class: Type[BaseIndicator]):
            # التحقق من أن الفئة ترث من BaseIndicator
            if not inspect.isclass(indicator_class) or not issubclass(indicator_class, BaseIndicator):
                raise TypeError(f"Indicator must be a subclass of BaseIndicator")
            
            # جمع المعلومات
            info = IndicatorInfo(
                name=name.lower(),
                display_name=display_name or name.upper(),
                description=description,
                indicator_class=indicator_class,
                category=category,
                default_params=indicator_class.get_default_params(),
                required_columns=indicator_class.get_required_columns()
            )
            
            # التسجيل
            cls._indicators[name.lower()] = info
            return indicator_class
        
        return decorator
    
    def calculate_all_indicators(
        self,
        data: pd.DataFrame,
        indicator_configs: List[IndicatorConfig]
    ) -> Dict[str, pd.Series]:
        """
        حساب جميع المؤشرات المطلوبة
        
        Args:
            data: بيانات السوق
            indicator_configs: قائمة بتكوينات المؤشرات
            
        Returns:
            Dict[str, pd.Series]: قاموس بقيم المؤشرات المحسوبة
        """
        calculated = {}
        
        for config in indicator_configs:
            if not config.enabled:
                continue
            
            try:
                # حساب المؤشر
                values = self.calculate_indicator(data, config)
                
                # تخزين النتيجة
                calculated[config.name] = values
                
                logger.info(f"Calculated indicator: {config.name}, length: {len(values)}")
                
            except Exception as e:
                logger.error(f"Error calculating indicator {config.name}: {e}")
                # إرجاع سلسلة فارغة في حالة الخطأ
                calculated[config.name] = pd.Series([], dtype=float)
                continue
        
        # تخزين في الكاش
        self._calculated_indicators = calculated
        return calculated
    
    def calculate_indicator(
        self,
        data: pd.DataFrame,
        config: IndicatorConfig
    ) -> pd.Series:
        """
        حساب مؤشر محدد
        
        Args:
            data: بيانات السوق
            config: تكوين المؤشر
            
        Returns:
            pd.Series: قيم المؤشر المحسوبة
        """
        indicator_class = self.get_indicator(config.name)
        if not indicator_class:
            raise ValueError(f"Indicator '{config.name}' not found in registry")
        
        # إنشاء كائن المؤشر
        indicator = indicator_class(config)
        
        # حساب المؤشر
        result: IndicatorResult = indicator.calculate(data)
        
        # التحقق من النتيجة
        if not isinstance(result.values, pd.Series):
            raise TypeError(f"Indicator '{config.name}' did not return a pandas Series. Got: {type(result.values)}")
        
        # التحقق من طول السلسلة
        if len(result.values) != len(data):
            logger.warning(f"Indicator '{config.name}' returned series with length {len(result.values)}, expected {len(data)}")
        
        return result.values
    
    @classmethod
    def get_indicator(cls, name: str) -> Optional[Type[BaseIndicator]]:
        """الحصول على فئة المؤشر حسب الاسم"""
        info = cls._indicators.get(name.lower())
        return info.indicator_class if info else None
    
    @classmethod
    def get_indicator_info(cls, name: str) -> Optional[IndicatorInfo]:
        """الحصول على معلومات المؤشر"""
        return cls._indicators.get(name.lower())
    
    @classmethod
    def list_indicators(
        cls, 
        category: Optional[IndicatorType] = None
    ) -> List[Dict[str, Any]]:
        """سرد جميع المؤشرات المسجلة"""
        result = []
        
        for name, info in cls._indicators.items():
            if category and info.category != category:
                continue
            
            result.append({
                "name": name,
                "display_name": info.display_name,
                "description": info.description,
                "category": info.category.value,
                "default_params": info.default_params,
                "required_columns": info.required_columns
            })
        
        return result
    
    @classmethod
    def create_indicator(cls, config: IndicatorConfig) -> BaseIndicator:
        """إنشاء كائن مؤشر من التكوين"""
        indicator_class = cls.get_indicator(config.name)
        if not indicator_class:
            raise ValueError(f"Indicator '{config.name}' not found in registry")
        
        return indicator_class(config)
    
    def get_calculated_indicator(self, name: str) -> Optional[pd.Series]:
        """الحصول على مؤشر محسوب من الكاش"""
        return self._calculated_indicators.get(name)

class IndicatorFactory:
    """مصنع لإنشاء وإدارة المؤشرات"""
    
    @staticmethod
    def create_indicator(config: IndicatorConfig) -> BaseIndicator:
        """إنشاء مؤشر من التكوين"""
        registry = IndicatorRegistry()
        return registry.create_indicator(config)
    
    @staticmethod
    def calculate_indicators(
        data: pd.DataFrame,
        indicator_configs: List[IndicatorConfig]
    ) -> Dict[str, pd.Series]:
        """حساب مجموعة من المؤشرات"""
        registry = IndicatorRegistry()
        return registry.calculate_all_indicators(data, indicator_configs)
    
    @staticmethod
    def list_available_indicators(category: Optional[IndicatorType] = None) -> List[Dict[str, Any]]:
        """عرض المؤشرات المتاحة"""
        return IndicatorRegistry.list_indicators(category)