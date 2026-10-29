# trading_backend\app\services\indicators\calculator.py
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
import asyncio
import threading
import time
from collections import OrderedDict
from .base import IndicatorConfig, IndicatorResult
from .registry import IndicatorRegistry
from concurrent.futures import ThreadPoolExecutor

class IndicatorCalculator:
    """محرك حساب المؤشرات فقط - لا يعتمد على أي خدمات خارجية"""

    # ---- Cache bounds (bugfix: cache used to be an unbounded dict keyed by
    # DataFrame hash -> memory leak on long-running processes) ----
    _max_size: int = 256        # LRU eviction bound (max cached entries)
    _cache_ttl: float = 300.0   # seconds; entries older than this are purged

    def __init__(self):
        self.registry = IndicatorRegistry()
        # Ordered map: cache_key -> (monotonic_ts, value). OrderedDict gives us
        # O(1) move_to_end / popitem for LRU semantics while staying dict-compatible.
        self.cache = OrderedDict()
        # Guard against concurrent mutation from the ThreadPoolExecutor path.
        self._cache_lock = threading.Lock()

    # ==================== Cache helpers (LRU + TTL) ====================

    def _cache_get(self, cache_key: str):
        """Return cached value if present and fresh (moves key to MRU end)."""
        now = time.monotonic()
        with self._cache_lock:
            entry = self.cache.get(cache_key)
            if entry is None:
                return None
            ts, value = entry
            if now - ts > self._cache_ttl:
                # Expired entry: purge it and report a miss.
                del self.cache[cache_key]
                return None
            self.cache.move_to_end(cache_key)  # mark as recently used
            return value

    def _cache_set(self, cache_key: str, value) -> None:
        """Insert/update a cache entry, purging expired + LRU-overflow entries."""
        now = time.monotonic()
        with self._cache_lock:
            self.cache[cache_key] = (now, value)
            self.cache.move_to_end(cache_key)
            self._evict_cache_locked(now)

    def _evict_cache_locked(self, now: float) -> None:
        """Must be called while holding self._cache_lock."""
        # 1) Purge expired entries (oldest first — OrderedDict keeps insertion
        #    / access order, so the front is the least-recently-used).
        while self.cache:
            oldest_ts, _ = next(iter(self.cache.values()))
            if now - oldest_ts <= self._cache_ttl:
                break
            self.cache.popitem(last=False)
        # 2) Enforce the hard size bound by dropping least-recently-used entries.
        while len(self.cache) > self._max_size:
            self.cache.popitem(last=False)

    def clear_cache(self) -> None:
        """Explicit cache wipe (useful for tests / forced refresh)."""
        with self._cache_lock:
            self.cache.clear()

    def _calculate_single_indicator(self, dataframe, config, use_cache):
        import pandas as pd
        import numpy as np

        if callable(dataframe):
            raise ValueError(f"Expected a DataFrame, got callable: {dataframe}")

        if not isinstance(dataframe, pd.DataFrame):
            raise ValueError(f"Expected a DataFrame, got {type(dataframe)}")

        name = config.get('name', 'unknown')
        cache_key = self._generate_cache_key(dataframe, config)

        if use_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return name, cached

        try:
            indicator_config = IndicatorConfig(**config)
            indicator = self.registry.create_indicator(indicator_config)
            result = indicator.calculate(dataframe)
            result_dict = result.to_dict()
            if use_cache:
                self._cache_set(cache_key, result_dict)
            return name, result_dict
        except Exception as e:
            # ⚠️ لا نبتلع الخطأ بصمت — كان هذا يخفي أعطالاً حقيقية (مثل فشل
            # IndicatorConfig) وجعل كل قيم المؤشرات ترجع NaN دون أي تتبع
            import logging as _logging

            _logging.getLogger(__name__).exception(
                "Indicator '%s' failed to calculate: %s", name, e
            )
            return name, {
                "name": name,
                "values": {"data": [np.nan] * len(dataframe), "index": list(dataframe.index), "dtype": "float64"},
                "signals": None,
                "metadata": {"error": str(e)},
            }


    # def apply_indicators(
    #     self,
    #     dataframe: pd.DataFrame,
    #     indicators_config: List[Dict[str, Any]],  # استخدام Dict مباشرة
    #     use_cache: bool = True,
    #     parallel: bool = False  # ✅ إضافة خيار parallel
    # ) -> Dict[str, Dict[str, Any]]:

    #     results = {}

   
    #     if parallel:
    #         with ThreadPoolExecutor() as executor:
    #             futures = [
    #                 executor.submit(self._calculate_single_indicator, dataframe, cfg, use_cache)
    #                 for cfg in indicators_config if cfg.get('enabled', True)
    #             ]
    #             for future in futures:
    #                 name, res = future.result()
    #                 # تنظيف النتيجة
    #                 results[name] = self._clean_indicator_result(res)
    #     else:
    #         # التشغيل المتسلسل
            
    #         for cfg in indicators_config:
    #             if not cfg.get('enabled', True):
    #                 continue
    #             name, res = self._calculate_single_indicator(dataframe, cfg, use_cache)
    #             # تنظيف النتيجة
    #             results[name] = self._clean_indicator_result(res)

    #     return results  # ✅ إرجاع results هنا


    def apply_indicators(
        self,
        dataframe: pd.DataFrame,
        indicators_config: List[Dict[str, Any]],  # استخدام Dict مباشرة
        use_cache: bool = True,
        parallel: bool = False  # ✅ إضافة خيار parallel
    ) -> Dict[str, Dict[str, Any]]:

        results = {}

        has_ids = any(cfg.get('id') for cfg in indicators_config)



        if parallel:
            # ✅ تعديل الـ Parallel ليدعم IDs
            with ThreadPoolExecutor() as executor:
                futures = []
                
                # نقوم بتخزين الـ config مع الـ future لاسترجاعته لاحقاً
                for cfg in indicators_config:
                    if cfg.get('enabled', True):
                        future = executor.submit(self._calculate_single_indicator, dataframe, cfg, use_cache)
                        futures.append((future, cfg)) # <--- تخزين الـ Config مع الـ Future

                for future, original_cfg in futures:
                    # نستقبل النتيجة
                    name, res = future.result()
                    
                    # ✅ تحديد المفتاح باستخدام الـ original_cfg (وليس المتغير name)
                    if original_cfg.get('id'):
                        unique_key = original_cfg.get('id')
                       
                    elif original_cfg.get('label'):
                        unique_key = original_cfg.get('label')
                    else:
                        unique_key = name
                

                    results[unique_key] = self._clean_indicator_result(res)


        # if parallel:
        #     with ThreadPoolExecutor() as executor:
        #         futures = [
        #             executor.submit(self._calculate_single_indicator, dataframe, cfg, use_cache)
        #             for cfg in indicators_config if cfg.get('enabled', False)
        #         ]


        #         for future in futures:
        #             name, res = future.result()
        #             # تنظيف النتيجة
        #             # results[name] = self._clean_indicator_result(res)
        #             pass
        else:
   
            for i, cfg in enumerate(indicators_config):
                if not cfg.get('enabled', True):
                    continue

                name, res = self._calculate_single_indicator(dataframe, cfg, use_cache)
                
                if cfg.get('id'):
                    unique_key = cfg.get('id')

                elif cfg.get('label'): # دعم الـ label من الـ JSON
                    unique_key = cfg.get('label')
                 
                else:
                    unique_key = name
        

                # تنظيف النتيجة
                results[unique_key] = self._clean_indicator_result(res)


        return results  # ✅ إرجاع results هنا



    
    def _clean_indicator_result(self, result):
      
        if isinstance(result, dict):
           
            return self._clean_dict(result)
        elif isinstance(result, pd.Series):
            return self._clean_series(result)
        elif isinstance(result, pd.DataFrame):
            return self._clean_dataframe(result)
        elif isinstance(result, (list, tuple)):
            return [self._clean_value(v) for v in result]
        elif isinstance(result, np.ndarray):
            return [self._clean_value(v) for v in result.tolist()]
        else:
            return self._clean_value(result)
    
    def _clean_value(self, val):
        """تنظيف قيمة واحدة"""
        if val is None:
            return None
        elif isinstance(val, (float, np.float32, np.float64)):
            if np.isinf(val) or np.isnan(val):
                return None
            # تقريب لتجنب أرقام الفاصلة العائمة الكبيرة جدًا
            if abs(val) > 1e308:  # تجاوز الحد الأقصى لـ JSON
                return None
            return round(float(val), 8)
        elif isinstance(val, (np.int32, np.int64, np.integer)):
            return int(val)
        elif isinstance(val, (pd.Timestamp, pd.DatetimeIndex)):
            return val.isoformat() if hasattr(val, 'isoformat') else str(val)
        else:
            return val
    
    def _clean_series(self, series: pd.Series):
        """تنظيف Series"""
        if series is None or series.empty:
            return []
        
        cleaned = []
        for val in series.tolist():
            cleaned.append(self._clean_value(val))
        return cleaned
    
    def _clean_dataframe(self, df: pd.DataFrame):
        """تنظيف DataFrame"""
        if df is None or df.empty:
            return []
        
        records = []
        for _, row in df.iterrows():
            record = {}
            for col in row.index:
                record[col] = self._clean_value(row[col])
            records.append(record)
        return records
    
    def _clean_dict(self, d: Dict):
        """تنظيف قاموس"""
        if not d:
            return {}
        
        cleaned = {}
        for key, value in d.items():
            cleaned[key] = self._clean_indicator_result(value)  # ✅ تنظيف متكرر
        return cleaned
    
    def calculate_trading_signals(
        self,
        dataframe: pd.DataFrame,
        indicator_configs: List[Dict[str, Any]],
        signal_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        توليد إشارات تداول من مجموعة مؤشرات
        
        Args:
            dataframe: البيانات
            indicator_configs: تكوينات المؤشرات
            signal_threshold: عتبة الإشارة
            
        Returns:
            Dict: إشارات التداول والبيانات التحليلية
        """
        # حساب جميع المؤشرات
        indicator_results = self.apply_indicators(
            dataframe, 
            indicator_configs, 
            use_cache=True
        )
        
        # استخراج الإشارات من النتائج
        signals_series = self._extract_signals(indicator_results, dataframe)
        
        # تحليل الإشارات
        signal_analysis = self._analyze_signals(signals_series, dataframe)
        
        # تنظيف النتائج
        clean_signals = self._clean_series(signals_series) if hasattr(signals_series, 'tolist') else []
        clean_analysis = self._clean_dict(signal_analysis) if signal_analysis else {}
        clean_indicators = self._clean_dict(indicator_results)
        
        # تجميع النتائج
        result = {
            "signals": clean_signals,
            "signal_analysis": clean_analysis,
            "indicators": clean_indicators,
            "last_signal": 0 if not clean_signals else int(clean_signals[-1]) if clean_signals else 0,
            "signal_strength": 0 if not clean_signals else abs(float(clean_signals[-1])) if clean_signals else 0
        }
        
        return result
    
    def _extract_signals(
        self, 
        indicator_results: Dict[str, Dict[str, Any]], 
        dataframe: pd.DataFrame
    ) -> pd.Series:
        """استخراج إشارات من نتائج المؤشرات"""
        if not indicator_results:
            return pd.Series([0] * len(dataframe), index=dataframe.index)
        
        # جمع الإشارات من جميع المؤشرات
        combined = pd.Series(0, index=dataframe.index)
        
        for name, result in indicator_results.items():
            if 'signals' in result and result['signals'] is not None:
                signals = pd.Series(result['signals'], index=dataframe.index)
                # تطبيع وجمع
                if not signals.empty:
                    signals_normalized = signals.fillna(0)
                    combined = combined.add(signals_normalized, fill_value=0)
        
        # تحويل إلى إشارات منفصلة
        discrete = pd.Series(0, index=combined.index)
        discrete[combined > 0.3] = 1
        discrete[combined < -0.3] = -1
        
        return discrete
    
    def _analyze_signals(
        self, 
        signals: pd.Series, 
        dataframe: pd.DataFrame
    ) -> Dict[str, Any]:
        """تحليل إشارات التداول"""
        if len(signals) == 0:
            return {}
        
        # تحليل الإشارات
        buy_signals = (signals == 1).sum()
        sell_signals = (signals == -1).sum()
        neutral_signals = (signals == 0).sum()
        
        total_signals = len(signals)
        
        # اتجاه الإشارات الأخيرة
        recent_signals = signals.iloc[-10:] if len(signals) >= 10 else signals
        signal_trend = "neutral"
        
        if len(recent_signals) > 0:
            buy_count = (recent_signals == 1).sum()
            sell_count = (recent_signals == -1).sum()
            
            if buy_count > sell_count:
                signal_trend = "bullish"
            elif sell_count > buy_count:
                signal_trend = "bearish"
        
        return {
            "buy_signals": int(buy_signals),
            "sell_signals": int(sell_signals),
            "neutral_signals": int(neutral_signals),
            "total_signals": int(total_signals),
            "buy_percentage": float(buy_signals / total_signals * 100) if total_signals > 0 else 0,
            "sell_percentage": float(sell_signals / total_signals * 100) if total_signals > 0 else 0,
            "signal_trend": signal_trend,
            "last_signal": int(signals.iloc[-1]) if len(signals) > 0 else 0
        }
    
    def _generate_cache_key(
        self, 
        dataframe: pd.DataFrame, 
        config: Dict[str, Any]
    ) -> str:
        """إنشاء مفتاح كاش فريد"""
        # استخدام هاش DataFrame والتكوين
        data_hash = hash(str(dataframe.iloc[-100:].to_dict()))
        config_hash = hash(str(config))
        
        return f"indicator_{config.get('name', 'unknown')}_{data_hash}_{config_hash}"
    
    def validate_dataframe(self, dataframe: pd.DataFrame) -> bool:
        """التحقق من صحة DataFrame"""
        required_columns = ['open', 'high', 'low', 'close']
        
        if dataframe is None or dataframe.empty:
            return False
        
        for col in required_columns:
            if col not in dataframe.columns:
                return False
        
        # التحقق من وجود قيم NaN
        if dataframe[required_columns].isnull().any().any():
            return False
        
        return True


