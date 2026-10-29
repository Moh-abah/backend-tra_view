# app/core/indicators/processor.py
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class Candle:
    """تمثيل موحد للشمعة"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool = True  # هل الشمعة مغلقة؟

class IndicatorProcessor:
    """معالج المؤشرات مع التخزين المؤقت والحساب المتوازي"""
    
    def __init__(self, max_workers: int = 4, cache_ttl: int = 300):
        self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self._cache = {}
        self._cache_ttl = cache_ttl
        self._last_cleanup = datetime.utcnow()
        
    async def calculate_indicators(
        self,
        candles: List[Candle],
        indicators_config: List[Dict[str, Any]],
        only_on_close: bool = True
    ) -> Dict[str, Any]:
        """
        حساب المؤشرات مع دعم الحساب عند الإغلاق فقط
        """
        # إذا كانت only_on_close=True ولم تغلق الشمعة الأخيرة، نرجع القيم السابقة
        if only_on_close and candles and not candles[-1].closed:
            return await self._get_cached_indicators(candles[:-1], indicators_config)
        
        # إنشاء DataFrame
        df = await self._create_dataframe(candles)
        
        if df.empty or len(df) < 5:  # الحد الأدنى للبيانات
            return {}
        
        # تجميع المؤشرات حسب النوع للحساب المتوازي
        indicator_groups = self._group_indicators(indicators_config)
        
        # حساب متوازي
        tasks = []
        for group_name, group_configs in indicator_groups.items():
            task = asyncio.create_task(
                self._calculate_indicator_group(df, group_configs)
            )
            tasks.append(task)
        
        # انتظار النتائج
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # دمج النتائج
        merged_results = {}
        for result in results:
            if isinstance(result, dict):
                merged_results.update(result)
        
        # التخزين المؤقت
        await self._cache_results(candles, indicators_config, merged_results)
        
        return merged_results
    
    async def _calculate_indicator_group(
        self,
        df: pd.DataFrame,
        configs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """حساب مجموعة مؤشرات في thread منفصل"""
        loop = asyncio.get_event_loop()
        
        try:
            # تشغيل في thread منفصل لتجنب حظر event loop
            result = await loop.run_in_executor(
                self._thread_pool,
                self._calculate_sync,
                df.copy(),  # نسخة لتجنب مشاكل التزامن
                configs
            )
            return result
        except Exception as e:
            logger.error(f"Error calculating indicator group: {e}")
            return {}
    
    def _calculate_sync(self, df: pd.DataFrame, configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """الحساب المتزامن (يتم في thread منفصل)"""
        results = {}
        
        for config in configs:
            try:
                indicator_name = config.get("name", "")
                indicator_type = config.get("type", "")
                
                # حساب المؤشر حسب النوع
                if indicator_name == "rsi":
                    result = self._calculate_rsi(df, config.get("params", {}))
                elif indicator_name == "ema":
                    result = self._calculate_ema(df, config.get("params", {}))
                elif indicator_name == "macd":
                    result = self._calculate_macd(df, config.get("params", {}))
                elif indicator_name == "bb":
                    result = self._calculate_bollinger_bands(df, config.get("params", {}))
                else:
                    continue
                
                # تنظيف القيم NaN/Inf
                result = self._clean_indicator_values(result)
                
                results[f"{indicator_name}_{indicator_type}"] = {
                    "name": indicator_name,
                    "type": indicator_type,
                    "values": result.tolist() if hasattr(result, 'tolist') else result,
                    "last_value": float(result.iloc[-1]) if hasattr(result, 'iloc') else result[-1],
                    "metadata": {
                        "period": config.get("params", {}).get("period", 14),
                        "calculated_at": datetime.utcnow().isoformat(),
                        "valid_values": np.sum(~np.isnan(result)) if hasattr(result, '__len__') else 1
                    }
                }
                
            except Exception as e:
                logger.error(f"Error calculating {config.get('name')}: {e}")
                continue
        
        return results
    
    def _calculate_rsi(self, df: pd.DataFrame, params: Dict) -> pd.Series:
        """حساب RSI بدون استخدام مكتبات خارجية"""
        period = params.get("period", 14)
        
        if len(df) < period + 1:
            return pd.Series([np.nan] * len(df))
        
        close_prices = df['close']
        delta = close_prices.diff()
        
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _clean_indicator_values(self, series: pd.Series) -> pd.Series:
        """تنظيف قيم المؤشر من NaN و Inf"""
        if series is None or len(series) == 0:
            return pd.Series()
        
        # استبدال Inf بـ NaN
        series = series.replace([np.inf, -np.inf], np.nan)
        
        # ملء NaN باستخدام interpolation
        if series.isna().any():
            series = series.interpolate(method='linear', limit_direction='both')
        
        return series
    
    def _generate_cache_key(self, candles: List[Candle], configs: List[Dict]) -> str:
        """إنشاء مفتاح تخزين مؤقت فريد"""
        data_str = f"{len(candles)}_{candles[-1].timestamp if candles else ''}"
        config_str = json.dumps(configs, sort_keys=True)
        
        return hashlib.md5(f"{data_str}_{config_str}".encode()).hexdigest()