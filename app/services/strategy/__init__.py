# app\services\strategy\__init__.py
from typing import Dict, List, Any, Optional
import pandas as pd
from .schemas import StrategyConfig
from .core import StrategyEngine, StrategyResult, TradeSignal
from .loader import StrategyLoader
from .conditions import ConditionEvaluator

# إنشاء كائنات عامة
_strategy_loader = StrategyLoader()

async def run_strategy(
    data: pd.DataFrame,
    strategy_config: Dict[str, Any],
    live_mode: bool = False,
    use_cache: bool = True
) -> StrategyResult:
    """
    الوظيفة المركزية لتشغيل إستراتيجية على البيانات (دالة async)

    Args:
        data: DataFrame يحتوي على بيانات السوق
        strategy_config: تكوين الإستراتيجية (قاموس)
        live_mode: وضع التشغيل الحي (للبيانات المستمرة)
        use_cache: استخدام الكاش (افتراضي: True)

    Returns:
        StrategyResult: نتيجة تشغيل الإستراتيجية

    Example:
        >>> strategy_config = {
        ...     "name": "RSI Strategy",
        ...     "indicators": [{"name": "rsi", "params": {"period": 14}}],
        ...     "entry_rules": [...],
        ...     "exit_rules": [...]
        ... }
        >>> result = await run_strategy(data, strategy_config)
    """
    # تحميل الإستراتيجية (يؤكد صحة التكوين عبر StrategyConfig)
    engine = _strategy_loader.load_strategy_from_dict(strategy_config)

    # تشغيل الإستراتيجية (coroutine يجب انتظاره)
    result = await engine.run_strategy(data, live_mode, use_cache)

    return result

def validate_strategy_config(strategy_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    التحقق من صحة تكوين الإستراتيجية
    
    Args:
        strategy_config: تكوين الإستراتيجية
        
    Returns:
        Dict: نتيجة التحقق
    """
    try:
        config = StrategyConfig(**strategy_config)
        
        return {
            "valid": True,
            "config": config.dict(),
            "errors": []
        }
    except Exception as e:
        return {
            "valid": False,
            "config": None,
            "errors": [str(e)]
        }

def save_strategy(
    strategy_config: Dict[str, Any],
    file_name: Optional[str] = None
) -> str:
    """
    حفظ إستراتيجية إلى ملف
    
    Args:
        strategy_config: تكوين الإستراتيجية
        file_name: اسم الملف (اختياري)
        
    Returns:
        str: مسار الملف المحفوظ
    """
    config = StrategyConfig(**strategy_config)
    file_path = _strategy_loader.save_strategy_to_file(config, file_name)
    
    return str(file_path)

def load_strategy_from_file(file_path: str) -> StrategyEngine:
    """
    تحميل إستراتيجية من ملف
    
    Args:
        file_path: مسار الملف
        
    Returns:
        StrategyEngine: محرك الإستراتيجية المحملة
    """
    return _strategy_loader.load_strategy_from_file(file_path)

def update_strategy(
    strategy_name: str,
    updates: Dict[str, Any]
) -> Optional[StrategyEngine]:
    """
    تحديث إستراتيجية محملة
    
    Args:
        strategy_name: اسم الإستراتيجية
        updates: التحديثات المطلوبة
        
    Returns:
        StrategyEngine: محرك الإستراتيجية المحدثة
    """
    return _strategy_loader.update_strategy(strategy_name, updates)

def get_strategy_loader() -> StrategyLoader:
    """الوصول المباشر للمحمّل (للمسح من القرص عبر /list و/s-reload)."""
    return _strategy_loader

def get_loaded_strategies() -> List[Dict[str, Any]]:
    """
    الحصول على قائمة بالإستراتيجيات المحملة
    
    Returns:
        List[Dict]: قائمة بالإستراتيجيات
    """
    return _strategy_loader.list_loaded_strategies()

def reload_strategy(strategy_name: str) -> Optional[StrategyEngine]:
    """
    إعادة تحميل إستراتيجية من الملف
    
    Args:
        strategy_name: اسم الإستراتيجية
        
    Returns:
        StrategyEngine: محرك الإستراتيجية المُعاد تحميله
    """
    return _strategy_loader.reload_strategy(strategy_name)

# تصدير الكلاسات الرئيسية
__all__ = [
    "StrategyConfig",
    "StrategyEngine",
    "StrategyResult",
    "TradeSignal",
    "StrategyLoader",
    "ConditionEvaluator",
    "run_strategy",
    "validate_strategy_config",
    "save_strategy",
    "load_strategy_from_file",
    "update_strategy",
    "get_loaded_strategies",
    "reload_strategy"
]
