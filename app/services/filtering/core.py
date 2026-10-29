from typing import Dict, List, Any, Optional, Tuple
import re
import asyncio
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from .schemas import (
    FilterCondition, FilterCriteria, FilterResult, FilterRule, 
    CompositeFilter, FilterType, FilterOperator
)
from app.services.data_service import DataService
from app.services.indicators import IndicatorCalculator

class FilteringEngine:
    """محرك فلترة متقدم"""
    
    def __init__(self, data_service: DataService = None):
        self.data_service = data_service
        self.indicator_calculator = IndicatorCalculator()
        
        # كاش للنتائج
        self.cache: Dict[str, Tuple[datetime, FilterResult]] = {}
        self.cache_ttl = 300  # 5 دقائق
        
        # إحصائيات
        self.stats = {
            "total_filters": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
    
    async def filter_symbols(
        self,
        market: str,
        criteria: FilterCriteria,
        use_cache: bool = True
    ) -> FilterResult:
        """
        فلترة الرموز بناءً على معايير متعددة
        
        Args:
            market: السوق (crypto, stocks)
            criteria: معايير الفلترة
            use_cache: استخدام الكاش
            
        Returns:
            FilterResult: نتيجة الفلترة
        """
        start_time = datetime.utcnow()
        
        # التحقق من الكاش
        cache_key = self._generate_cache_key(market, criteria)
        if use_cache and cache_key in self.cache:
            cached_time, cached_result = self.cache[cache_key]
            if (datetime.utcnow() - cached_time).seconds < self.cache_ttl:
                self.stats["cache_hits"] += 1
                return cached_result
        
        self.stats["cache_misses"] += 1
        self.stats["total_filters"] += 1
        
        # الحصول على جميع الرموز في السوق
        all_symbols = await self._get_all_symbols(market)
        
        if not all_symbols:
            return FilterResult(
                symbols=[],
                total_count=0,
                filtered_count=0,
                filtered_symbols=[],
                criteria=criteria,
                execution_time_ms=0
            )
        
        # فلترة أولية بالأنماط البسيطة
        filtered_symbols = await self._apply_basic_filters(
            all_symbols, market, criteria
        )
        
        # تطبيق فلاتر المؤشرات (إذا طلب)
        if criteria.required_indicators or criteria.indicator_filters:
            filtered_symbols = await self._apply_indicator_filters(
                filtered_symbols, market, criteria
            )
        
        # تطبيق فلاتر المستخدم
        if criteria.user_preferences:
            filtered_symbols = await self._apply_user_filters(
                filtered_symbols, market, criteria.user_preferences
            )
        
        # تطبيق الفلاتر المخصصة
        if criteria.custom_filters:
            filtered_symbols = await self._apply_custom_filters(
                filtered_symbols, market, criteria.custom_filters
            )
        
        # تطبيق الفلتر المركب
        if criteria.composite_filter:
            filtered_symbols = await self._apply_composite_filter(
                filtered_symbols, market, criteria.composite_filter
            )
        
        # تطبيق الترتيب والحدود
        sorted_symbols = await self._apply_sorting(
            filtered_symbols, criteria.sort_by, criteria.sort_order
        )
        
        # تطبيق الترقيم الصفحي
        start_idx = criteria.offset
        end_idx = start_idx + criteria.limit
        paginated_symbols = sorted_symbols[start_idx:end_idx]
        
        # الحصول على بيانات إضافية للرموز المفلترة
        symbols_with_data = await self._get_symbols_data(
            paginated_symbols, market
        )
        
        # حساب وقت التنفيذ
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # إنشاء النتيجة
        result = FilterResult(
            symbols=paginated_symbols,
            total_count=len(all_symbols),
            filtered_count=len(filtered_symbols),
            filtered_symbols=symbols_with_data,
            criteria=criteria,
            execution_time_ms=execution_time
        )
        
        # تخزين في الكاش
        if use_cache:
            self.cache[cache_key] = (datetime.utcnow(), result)
            
            # تنظيف الكاش القديم
            self._clean_cache()
        
        return result
    
    async def _get_all_symbols(self, market: str) -> List[str]:
        """الحصول على جميع الرموز في سوق معين"""
        if self.data_service:
            try:
                return await self.data_service.get_symbols(market)
            except Exception as e:
                print(f"Error getting symbols from data service: {e}")
        
        # رموز افتراضية للاختبار
        default_symbols = {
            "crypto": [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT",
                "SOLUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT",
                "LTCUSDT", "UNIUSDT", "LINKUSDT", "ATOMUSDT", "ETCUSDT"
            ],
            "stocks": [
                "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
                "FB", "NVDA", "JPM", "JNJ", "V",
                "PG", "UNH", "HD", "MA", "DIS"
            ]
        }
        
        return default_symbols.get(market, [])
    
    async def _apply_basic_filters(
        self,
        symbols: List[str],
        market: str,
        criteria: FilterCriteria
    ) -> List[str]:
        """تطبيق الفلاتر الأساسية

        Bugfix: كانت الأسعار تُجلب تسلسلياً ويُستخدم 0 كقيمة افتراضية عند فشل
        الجلب → كل الرموز تظهر بسعر 0 أو تُفلتر خطأً. الآن: جلب متوازٍ
        (asyncio.gather + حد تزامن) وتجاهل الرموز التي لا سعر صحيح لها.
        """
        filtered_symbols = []

        # 1) جلب الأسعار المطلوبة دفعة واحدة وبالتوازي (قبل الحلقة)
        prices: Dict[str, Optional[float]] = {}
        need_prices = bool(criteria.min_price or criteria.max_price)
        if need_prices and self.data_service:
            semaphore = asyncio.Semaphore(10)

            async def _safe_price(sym: str) -> tuple:
                async with semaphore:
                    try:
                        data = await asyncio.wait_for(
                            self.data_service.get_live_price(sym, market), timeout=8.0
                        )
                        price = data.get("price") if isinstance(data, dict) else None
                    except Exception:
                        price = None
                # السعر الصحيح فقط (يمنع أسعار الصفر الوهمية)
                prices[sym] = float(price) if isinstance(price, (int, float)) and price > 0 else None
                return sym, prices[sym]

            await asyncio.gather(*(_safe_price(s) for s in symbols))

        for symbol in symbols:
            include_symbol = True

            # 1. فلترة بنمط الرمز
            if criteria.symbol_pattern:
                if not self._match_pattern(symbol, criteria.symbol_pattern):
                    include_symbol = False

            # 2. فلترة بالسعر — الرمز بلا سعر صحيح يُتخطى بدل تمريره بسعر 0
            if include_symbol and need_prices:
                price = prices.get(symbol)
                if price is None:
                    include_symbol = False
                else:
                    if criteria.min_price and price < criteria.min_price:
                        include_symbol = False
                    if criteria.max_price and price > criteria.max_price:
                        include_symbol = False

            # 3. فلترة بالحجم (إذا توفرت البيانات)
            if include_symbol and criteria.min_volume_24h:
                # في التطبيق الحقيقي، نحتاج إلى بيانات الحجم
                pass

            if include_symbol:
                filtered_symbols.append(symbol)
        
        return filtered_symbols
    
    async def _apply_indicator_filters(
        self,
        symbols: List[str],
        market: str,
        criteria: FilterCriteria
    ) -> List[str]:
        """تطبيق فلاتر المؤشرات"""
        filtered_symbols = []
        
        # إذا لم تكن هناك مؤشرات مطلوبة، نرجع جميع الرموز
        if not criteria.required_indicators and not criteria.indicator_filters:
            return symbols
        
        tasks = []
        for symbol in symbols:
            task = self._evaluate_symbol_indicators(symbol, market, criteria)
            tasks.append((symbol, task))
        
        # تشغيل المهام بالتوازي
        for symbol, task in tasks:
            try:
                should_include = await task
                if should_include:
                    filtered_symbols.append(symbol)
            except Exception as e:
                print(f"Error evaluating indicators for {symbol}: {e}")
                continue
        
        return filtered_symbols
    
    async def _evaluate_symbol_indicators(
        self,
        symbol: str,
        market: str,
        criteria: FilterCriteria
    ) -> bool:
        """تقييم مؤشرات رمز معين"""
        try:
            # الحصول على بيانات حديثة
            data = await self.data_service.get_historical(
                symbol=symbol,
                timeframe="1h",  # إطار ساعة للفلترة
                market=market,
                days=7
            )
            
            if data.empty or len(data) < 20:
                return False
            
            # 1. التحقق من المؤشرات المطلوبة
            if criteria.required_indicators:
                # يمكن التحقق هنا إذا كانت المؤشرات متاحة لهذا الرمز
                pass
            
            # 2. تطبيق فلاتر المؤشرات المحددة
            if criteria.indicator_filters:
                for indicator_name, filter_config in criteria.indicator_filters.items():
                    # حساب المؤشر
                    indicator_config = [{"name": indicator_name, "params": {}}]
                    indicator_results = await self.indicator_calculator.apply_indicators(
                        data, indicator_config, use_cache=True
                    )
                    
                    if indicator_name not in indicator_results:
                        return False
                    
                    indicator_value = float(indicator_results[indicator_name].values.iloc[-1])
                    
                    # تطبيق الفلاتر
                    if "min" in filter_config and indicator_value < filter_config["min"]:
                        return False
                    if "max" in filter_config and indicator_value > filter_config["max"]:
                        return False
                    if "signal" in filter_config:
                        # يمكن إضافة منطق الإشارات هنا
                        pass
            
            return True
            
        except Exception as e:
            print(f"Error in indicator evaluation for {symbol}: {e}")
            return False
    
    async def _apply_user_filters(
        self,
        symbols: List[str],
        market: str,
        user_preferences: Dict[str, Any]
    ) -> List[str]:
        """تطبيق فلاتر تفضيلات المستخدم"""
        filtered_symbols = []
        
        for symbol in symbols:
            include_symbol = True
            
            # مثال: تفضيلات المستخدم
            if "excluded_symbols" in user_preferences:
                if symbol in user_preferences["excluded_symbols"]:
                    include_symbol = False
            
            if "preferred_sectors" in user_preferences:
                # يمكن إضافة منطق القطاعات هنا
                pass
            
            if "risk_tolerance" in user_preferences:
                # فلترة حسب تحمل المخاطر
                risk_level = user_preferences["risk_tolerance"]
                if risk_level == "low":
                    # فلترة الرموز عالية المخاطرة
                    pass
                elif risk_level == "high":
                    # فلترة الرموز منخفضة المخاطرة
                    pass
            
            if include_symbol:
                filtered_symbols.append(symbol)
        
        return filtered_symbols
    
    async def _apply_custom_filters(
        self,
        symbols: List[str],
        market: str,
        custom_filters: List[FilterRule]
    ) -> List[str]:
        """تطبيق الفلاتر المخصصة"""
        filtered_symbols = symbols.copy()
        
        for filter_rule in custom_filters:
            if not filter_rule.enabled:
                continue
            
            filtered_symbols = await self._apply_single_filter(
                filtered_symbols, market, filter_rule
            )
            
            if not filtered_symbols:
                break
        
        return filtered_symbols
    
    async def _apply_composite_filter(
        self,
        symbols: List[str],
        market: str,
        composite_filter: CompositeFilter
    ) -> List[str]:
        """تطبيق فلتر مركب"""
        if composite_filter.type == "and":
            filtered_symbols = symbols.copy()
            for subfilter in composite_filter.filters:
                if isinstance(subfilter, CompositeFilter):
                    filtered_symbols = await self._apply_composite_filter(
                        filtered_symbols, market, subfilter
                    )
                else:
                    filtered_symbols = await self._apply_single_filter(
                        filtered_symbols, market, subfilter
                    )
                
                if not filtered_symbols:
                    break
            
            return filtered_symbols
            
        else:  # "or"
            all_filtered = set()
            for subfilter in composite_filter.filters:
                if isinstance(subfilter, CompositeFilter):
                    filtered = await self._apply_composite_filter(
                        symbols, market, subfilter
                    )
                else:
                    filtered = await self._apply_single_filter(
                        symbols, market, subfilter
                    )
                
                all_filtered.update(filtered)
            
            return list(all_filtered)
    
    async def _apply_single_filter(
        self,
        symbols: List[str],
        market: str,
        filter_rule: FilterRule
    ) -> List[str]:
        """تطبيق فلتر فردي"""
        filtered_symbols = []
        
        for symbol in symbols:
            conditions_met = True
            
            for condition in filter_rule.conditions:
                # الحصول على قيمة الحقل للرمز
                field_value = await self._get_field_value(
                    symbol, market, condition.field
                )
                
                if field_value is None:
                    conditions_met = False
                    break
                
                # تقييم الشرط
                if not self._evaluate_condition(field_value, condition):
                    conditions_met = False
                    break
            
            if conditions_met:
                filtered_symbols.append(symbol)
        
        return filtered_symbols
    
    async def _get_field_value(
        self,
        symbol: str,
        market: str,
        field: str
    ) -> Optional[Any]:
        """الحصول على قيمة حقل لرمز معين"""
        try:
            # يمكن إضافة المزيد من الحقول هنا
            if field == "price":
                price_data = await self.data_service.get_live_price(symbol, market)
                return price_data.get("price")
            
            elif field == "volume_24h":
                # في التطبيق الحقيقي، نحتاج إلى بيانات الحجم
                return 1000000  # قيمة افتراضية
            
            elif field.startswith("indicator."):
                indicator_name = field.split(".")[1]
                # حساب المؤشر
                data = await self.data_service.get_historical(
                    symbol=symbol,
                    timeframe="1h",
                    market=market,
                    days=7
                )
                
                if data.empty:
                    return None
                
                indicator_config = [{"name": indicator_name, "params": {}}]
                indicator_results = await self.indicator_calculator.apply_indicators(
                    data, indicator_config, use_cache=True
                )
                
                if indicator_name in indicator_results:
                    return float(indicator_results[indicator_name].values.iloc[-1])
                
            return None
            
        except Exception as e:
            print(f"Error getting field value for {symbol}.{field}: {e}")
            return None
    
    def _evaluate_condition(self, field_value: Any, condition: FilterCondition) -> bool:
        """تقييم شرط فردي"""
        operator = condition.operator
        condition_value = condition.value
        
        try:
            if operator == FilterOperator.EQUALS:
                return field_value == condition_value
            elif operator == FilterOperator.NOT_EQUALS:
                return field_value != condition_value
            elif operator == FilterOperator.GREATER_THAN:
                return field_value > condition_value
            elif operator == FilterOperator.GREATER_THAN_EQUAL:
                return field_value >= condition_value
            elif operator == FilterOperator.LESS_THAN:
                return field_value < condition_value
            elif operator == FilterOperator.LESS_THAN_EQUAL:
                return field_value <= condition_value
            elif operator == FilterOperator.BETWEEN:
                return condition_value[0] <= field_value <= condition_value[1]
            elif operator == FilterOperator.IN:
                return field_value in condition_value
            elif operator == FilterOperator.NOT_IN:
                return field_value not in condition_value
            elif operator == FilterOperator.CONTAINS:
                return condition_value in str(field_value)
            elif operator == FilterOperator.STARTS_WITH:
                return str(field_value).startswith(condition_value)
            elif operator == FilterOperator.ENDS_WITH:
                return str(field_value).endswith(condition_value)
            elif operator == FilterOperator.MATCHES_PATTERN:
                return bool(re.match(condition_value, str(field_value)))
            else:
                return False
                
        except Exception as e:
            print(f"Error evaluating condition: {e}")
            return False
    
    async def _apply_sorting(
        self,
        symbols: List[str],
        sort_by: Optional[str],
        sort_order: str
    ) -> List[str]:
        """تطبيق الترتيب على الرموز"""
        if not sort_by or not symbols:
            return symbols
        
        # إذا كان الترتيب حسب السعر
        if sort_by == "price":
            try:
                symbols_with_prices = []
                for symbol in symbols:
                    # في التطبيق الحقيقي، نحصل على الأسعار
                    symbols_with_prices.append((symbol, 0))
                
                symbols_with_prices.sort(
                    key=lambda x: x[1],
                    reverse=(sort_order == "desc")
                )
                return [s[0] for s in symbols_with_prices]
                
            except Exception:
                return symbols
        
        return symbols
    
    async def _get_symbols_data(
        self,
        symbols: List[str],
        market: str
    ) -> List[Dict[str, Any]]:
        """الحصول على بيانات إضافية للرموز

        Bugfix: كان الجلب تسلسلياً وعند أي فشل يُدرَج سعر وهمي 0 — فتظهر
        لوحة الفلترة كلها بأسعار صفر. الآن: جلب متوازٍ (حد تزامن 10) والرمز
        الفاشل يظهر بسعر ``None`` (بدل 0 المضلل) مع البقاء في النتائج.
        """
        if not self.data_service:
            return [
                {"symbol": s, "price": None, "market": market, "change_24h": 0, "volume_24h": 0}
                for s in symbols
            ]

        semaphore = asyncio.Semaphore(10)
        results: List[Dict[str, Any]] = [None] * len(symbols)  # type: ignore[list-item]

        async def _one(index: int, symbol: str) -> None:
            async with semaphore:
                try:
                    price_data = await asyncio.wait_for(
                        self.data_service.get_live_price(symbol, market), timeout=8.0
                    )
                except Exception:
                    price_data = None
            if isinstance(price_data, dict) and isinstance(price_data.get("price"), (int, float)) \
                    and price_data["price"] > 0:
                results[index] = {
                    "symbol": symbol,
                    "price": price_data.get("price"),
                    "timestamp": price_data.get("timestamp"),
                    "market": market,
                    "change_24h": price_data.get("change_percent") or 0,
                    "volume_24h": price_data.get("volume") or 0,
                }
            else:
                # لا سعر صحيح → None بدل 0 (0 يعني "مجاني" وهو مضلل)
                results[index] = {
                    "symbol": symbol,
                    "price": None,
                    "market": market,
                    "change_24h": 0,
                    "volume_24h": 0,
                }

        await asyncio.gather(*(_one(i, s) for i, s in enumerate(symbols)))
        return results
    
    def _match_pattern(self, symbol: str, pattern: str) -> bool:
        """مطابقة رمز بنمط"""
        # تحويل نمط wildcard إلى regex
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        return bool(re.match(f"^{regex_pattern}$", symbol))
    
    def _generate_cache_key(self, market: str, criteria: FilterCriteria) -> str:
        """إنشاء مفتاح كاش فريد"""
        import hashlib
        
        criteria_str = f"{market}_{criteria.model_dump_json()}"
        return hashlib.md5(criteria_str.encode()).hexdigest()
    
    def _clean_cache(self):
        """تنظيف الكاش القديم"""
        current_time = datetime.utcnow()
        expired_keys = []
        
        for key, (cached_time, _) in self.cache.items():
            if (current_time - cached_time).seconds > self.cache_ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات المحرك"""
        return {
            **self.stats,
            "cache_size": len(self.cache),
            "cache_ttl": self.cache_ttl
        }