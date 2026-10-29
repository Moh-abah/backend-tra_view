# app\services\strategy\core.py
from typing import Dict, List, Any, Optional, Tuple, Union
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from dataclasses import dataclass
from enum import Enum
import asyncio

from .schemas import (
    StrategyConfig, EntryRule, ExitRule, FilterRule,
    Condition, CompositeCondition, PositionSide
)
from .conditions import ConditionEvaluator
from app.services.indicators import apply_indicators, IndicatorCalculator
from app.services.indicators.base import IndicatorResult
import logging
logger = logging.getLogger(__name__)

@dataclass
class TradeSignal:
    """إشارة تداول"""
    timestamp: datetime
    action: str  # 'buy', 'sell', 'close'
    price: float
    reason: str
    rule_name: str
    strength: float = 1.0  # قوة الإشارة (0-1)
    metadata: Dict[str, Any] = None

@dataclass
class StrategyResult:
    """نتيجة تشغيل الإستراتيجية"""
    signals: List[TradeSignal]
    filtered_signals: List[TradeSignal]
    indicators: Dict[str, IndicatorResult]
    metrics: Dict[str, Any]
    raw_data: pd.DataFrame

class StrategyEngine:
    """محرك تشغيل الإستراتيجيات"""
    
    def __init__(self, strategy_config: StrategyConfig):
        self.config = strategy_config
        self.condition_evaluator = ConditionEvaluator()
        # self.indicator_calculator = IndicatorCalculator()
        
        # كاش للعمليات
        self._indicators_cache: Dict[str, pd.Series] = {}
        self._condition_cache: Dict[str, pd.Series] = {}
        
        # حالة الإستراتيجية
        self.current_position: Optional[Dict[str, Any]] = None
        self.trade_history: List[Dict[str, Any]] = []
 
    async def run_strategy(
        self,
        data: pd.DataFrame,
        live_mode: bool = False,
        use_cache: bool = True
    ) -> StrategyResult:
        """تشغيل الإستراتيجية مع إصلاحات كاملة"""
        if data.empty or len(data) < 2:
            raise ValueError("Insufficient data to run strategy")

        logger.info("🚀 بدء حساب المؤشرات...")
        logger.info(f"📊 عدد الشموع: {len(data)}, الأعمدة: {data.columns.tolist()}")
        logger.info(f"📊 أول 5 شموع:\n{data.head()}")

        
        # حساب المؤشرات مع التعامل الصحيح مع الأخطاء
        try:
            # حساب المؤشرات الأساسية
            indicators_results = await self._calculate_indicators(data, use_cache)
            
            # تأكيد أن النتيجة هي dict
            if not isinstance(indicators_results, dict):
                logger.error(f"⚠️ نتائج المؤشرات ليست dict: {type(indicators_results)}")
                indicators_results = {}
            
            # تحويل إلى تنسيق متوافق مع ConditionEvaluator
            self.indicators_data = {}
            for name, result in indicators_results.items():
                try:
                    if isinstance(result, pd.Series):
                        self.indicators_data[name] = result
                    elif isinstance(result, (list, np.ndarray)):
                        self.indicators_data[name] = pd.Series(result, index=data.index[:len(result)])
                    elif isinstance(result, dict):
                        # البحث عن أول قيمة صالحة في الـ dict
                        for key, val in result.items():
                            if isinstance(val, (pd.Series, list, np.ndarray)):
                                if isinstance(val, pd.Series):
                                    self.indicators_data[name] = val
                                else:
                                    self.indicators_data[name] = pd.Series(val, index=data.index[:len(val)])
                                break
                        else:
                            self.indicators_data[name] = pd.Series([np.nan] * len(data), index=data.index)
                    else:
                        # التعامل مع الأنواع غير المتوقعة
                        self.indicators_data[name] = pd.Series([np.nan] * len(data), index=data.index)
                        logger.warning(f"⚠️ نوع غير متوقع للمؤشر '{name}': {type(result)}")
                except Exception as e:
                    logger.error(f"⚠️ خطأ في معالجة المؤشر '{name}': {e}")
                    self.indicators_data[name] = pd.Series([np.nan] * len(data), index=data.index)
            
            # التحقق النهائي من المؤشرات
            if not isinstance(self.indicators_data, dict):
                logger.error(f"❌ indicators_data ليس dict: {type(self.indicators_data)}")
                self.indicators_data = {}
            
            logger.info(f"✅ تم حساب {len(self.indicators_data)} مؤشر بنجاح")
            
            # تهيئة ConditionEvaluator مع البيانات الصحيحة
            self.condition_evaluator.set_indicators_data(self.indicators_data)
            
            # إنشاء نسخة من البيانات مع المؤشرات للمساعدة في التصحيح
            data_with_indicators = data.copy()
            for indicator_name, series in self.indicators_data.items():
                if not series.empty:
                    data_with_indicators[f'indicator_{indicator_name}'] = series
            
        except Exception as e:
            logger.exception(f"❌ خطأ فادح في حساب المؤشرات: {e}")
            self.indicators_data = {}
            data_with_indicators = data.copy()
        
        logger.info("🚀 بدء توليد الإشارات...")
        
        try:
            # توليد الإشارات
            all_signals = await self._generate_signals(data, self.indicators_data, live_mode)
            
            # تطبيق الفلاتر
            filtered_signals = await self._apply_filters(
                data, 
                self.indicators_data, 
                all_signals
            )
            
            # حساب المقاييس
            metrics = await self._calculate_metrics(data, filtered_signals)
            
        except Exception as e:
            logger.exception(f"❌ خطأ في توليد الإشارات: {e}")
            all_signals = []
            filtered_signals = []
            metrics = {"error": str(e), "total_signals": 0}
        
        return StrategyResult(
            signals=all_signals,
            filtered_signals=filtered_signals,
            indicators=indicators_results,
            metrics=metrics,
            raw_data=data
        )
    




    async def _calculate_indicators(self, data: pd.DataFrame, use_cache: bool) -> Dict[str, pd.Series]:
        """حساب المؤشرات مع معالجة شاملة للأخطاء حسب شكل البيانات القادم من apply_indicators مع برينت لتأكيد النتائج"""

        if not hasattr(self, '_indicators_cache'):
            self._indicators_cache = {}

        if use_cache and hasattr(self, '_last_cache_key') and hasattr(self, '_indicators_cache'):
            cache_key = hash(tuple(data.index[-1:]) + tuple(data.columns))
            if self._last_cache_key == cache_key:
                logger.info("🔄 استخدام المؤشرات من الكاش")
                return self._indicators_cache

        indicators: Dict[str, pd.Series] = {}
        required_indicators = list({cfg.name for cfg in self.config.indicators})

        # جمع مؤشرات القواعد
        for rule in self.config.entry_rules + self.config.exit_rules + self.config.filter_rules:
            condition = rule.condition
            conditions_list = [condition]
            if isinstance(condition, CompositeCondition):
                conditions_list = condition.conditions
            for cond in conditions_list:
                for val in [cond.left_value, cond.right_value]:
                    if isinstance(val, str) and val.startswith("indicator:"):
                        required_indicators.append(val.split(":")[1])

        required_indicators = list(set(required_indicators))
        logger.info(f"📋 المؤشرات المطلوبة: {required_indicators}")

        try:
            # استدعاء apply_indicators
            all_indicators = apply_indicators(
                dataframe=data,
                indicators_config=self.config.indicators,
                use_cache=use_cache,
                return_raw=True
            )

            # التعامل مع كل مؤشر مهما كان هيكله
            for ind_name in required_indicators:
                raw_values: list = [None] * len(data)

                if ind_name in all_indicators:
                    result = all_indicators[ind_name]

                    if isinstance(result, IndicatorResult):
                        raw_values = result.values.get("data", [None])
                    elif isinstance(result, dict):
                        raw_values = result.get("values", {}).get("data", [None])
                    elif isinstance(result, pd.Series):
                        raw_values = result.tolist()
                    elif isinstance(result, list):
                        raw_values = result

                # طباعة Debug للقيم قبل التحويل
                print(f"🔹 {ind_name} أول 5 قيم: {raw_values[:5]} ... آخر 5 قيم: {raw_values[-5:]}")

                # padding إذا طول البيانات أقل من طول DataFrame
                padding_len = max(0, len(data) - len(raw_values))
                series_values = [None] * padding_len + raw_values[:len(data)]
                indicators[ind_name] = pd.Series(series_values, index=data.index)

                # طباعة Debug بعد التحويل إلى pd.Series
                print(f"🔹 {ind_name} pd.Series sample: {indicators[ind_name].head(5).tolist()} ... {indicators[ind_name].tail(5).tolist()}")

            # حفظ الكاش
            if use_cache:
                self._indicators_cache = {k: v.copy() for k, v in indicators.items()}
                self._last_cache_key = hash(tuple(data.index[-1:]) + tuple(data.columns))

        except Exception as e:
            logger.exception(f"❌ خطأ في حساب المؤشرات: {e}")
            print(f"❌ خطأ في حساب المؤشرات: {e}")
            for ind_name in required_indicators:
                indicators[ind_name] = pd.Series([None] * len(data), index=data.index)

        return indicators




    async def _generate_signals(
        self,
        data: pd.DataFrame,
        indicators: Dict[str, pd.Series],
        live_mode: bool = False
    ) -> List[TradeSignal]:
        """توليد إشارات التداول مع تحسينات"""
        
        signals = []
        
        # التحقق من صحة المؤشرات
        if not isinstance(indicators, dict):
            logger.error(f"❌ المؤشرات ليست dict: {type(indicators)}")
            return signals
        
        # تحديد النقاط التي يجب فحصها
        if live_mode:
            indices_to_check = [len(data) - 1]
        else:
            indices_to_check = range(len(data))
        
        print(f"🔍 فحص {len(indices_to_check)} نقطة بيانات")
        
        for idx in indices_to_check:
            try:
                # تأكد من أن الفهرس ضمن النطاق
                if idx >= len(data):
                   

                    continue
               

                # تقييم قواعد الدخول
                entry_signals = await self._evaluate_entry_rules(data, indicators, idx)
                signals.extend(entry_signals)
                
                # تقييم قواعد الخروج (إذا كان هناك مركز مفتوح)
                if self.current_position:
                    exit_signals = await self._evaluate_exit_rules(data, indicators, idx)
                    signals.extend(exit_signals)
                    
            except Exception as e:
                logger.error(f"❌ خطأ في فهرس {idx}: {e}")
                continue
        
        print(f"✅ تم توليد {len(signals)} إشارة")
        return signals



    async def _evaluate_entry_rules(
        self,
        data: pd.DataFrame,
        indicators: Dict[str, pd.Series],
        current_index: int
    ) -> List[TradeSignal]:
        """تقييم قواعد الدخول مع تحسينات"""
        
        signals = []
        
        # التحقق من صحة المؤشرات
        if not isinstance(indicators, dict):
            print(f"❌ المؤشرات ليست dict في _evaluate_entry_rules: {type(indicators)}")
            return signals
        
        for rule in self.config.entry_rules:
            if not rule.enabled:
                continue
            
            # التحقق من جهة المركز
            if self.config.position_side == PositionSide.LONG and rule.position_side == PositionSide.SHORT:
                continue
            if self.config.position_side == PositionSide.SHORT and rule.position_side == PositionSide.LONG:
                continue
            
            try:
                # تقييم الشرط
                condition_met = False
                
                if isinstance(rule.condition, Condition):
                    # تمرير المؤشرات بشكل صحيح
                    condition_met = self.condition_evaluator.evaluate(
                        rule.condition, 
                        data, 
                        indicators, 
                        current_index
                    )
                elif isinstance(rule.condition, CompositeCondition):
                    condition_met = self.condition_evaluator.evaluate_composite(
                        rule.condition, 
                        data, 
                        indicators, 
                        current_index
                    )
                
                if condition_met:
                    # إنشاء إشارة
                    signal = TradeSignal(
                        timestamp=data.index[current_index],
                        action="buy" if rule.position_side in [PositionSide.LONG, PositionSide.BOTH] else "sell",
                        price=data['close'].iloc[current_index] if 'close' in data.columns else data.iloc[current_index, 3],
                        reason=f"قاعدة دخول: {rule.name}",
                        rule_name=rule.name,
                        strength=rule.weight,
                        metadata={
                            "position_side": rule.position_side,
                            "rule_weight": rule.weight,
                            "index": current_index
                        }
                    )
                    signals.append(signal)
                    logger.info(f"✅ إشارة دخول في الفهرس {current_index}: {rule.name}")
                    
            except Exception as e:
                logger.error(f"❌ خطأ في تقييم قاعدة الدخول '{rule.name}': {e}")
                continue
        
        return signals


    async def _evaluate_exit_rules(
        self,
        data: pd.DataFrame,
        indicators: Dict[str, pd.Series],
        current_index: int
    ) -> List[TradeSignal]:
        """تقييم قواعد الخروج"""
        signals = []
        
        for rule in self.config.exit_rules:
            if not rule.enabled:
                continue
            
            # تقييم الشرط
            condition_met = False
            if isinstance(rule.condition, Condition):
                condition_met = self.condition_evaluator.evaluate(
                    rule.condition, data, indicators, current_index
                )
            elif isinstance(rule.condition, CompositeCondition):
                condition_met = self.condition_evaluator.evaluate_composite(
                    rule.condition, data, indicators, current_index
                )
            
            if condition_met:
                # إنشاء إشارة خروج
                signal = TradeSignal(
                    timestamp=data.index[current_index],
                    action="close",
                    price=data['close'].iloc[current_index],
                    reason=f"Exit rule triggered: {rule.name} ({rule.exit_type})",
                    rule_name=rule.name,
                    strength=1.0,
                    metadata={
                        "exit_type": rule.exit_type,
                        "exit_value": rule.value
                    }
                )
                signals.append(signal)
        
        return signals
    
    async def _apply_filters(
        self,
        data: pd.DataFrame,
        indicators: Dict[str, pd.Series],
        signals: List[TradeSignal]
    ) -> List[TradeSignal]:
        """تطبيق قواعد الفلترة على الإشارات"""
        if not self.config.filter_rules:
            return signals
        
        filtered_signals = []
        
        for signal in signals:
            # العثور على الفهرس المقابل للإشارة
            try:
                signal_idx = data.index.get_loc(signal.timestamp)
            except KeyError:
                continue  # تخطي الإشارة إذا لم نجد الوقت
            
            # تقييم جميع قواعد الفلترة
            should_allow = True
            
            for filter_rule in self.config.filter_rules:
                if not filter_rule.enabled:
                    continue
                
                # تقييم شرط الفلترة
                condition_met = False
                if isinstance(filter_rule.condition, Condition):
                    condition_met = self.condition_evaluator.evaluate(
                        filter_rule.condition, data, indicators, signal_idx
                    )
                elif isinstance(filter_rule.condition, CompositeCondition):
                    condition_met = self.condition_evaluator.evaluate_composite(
                        filter_rule.condition, data, indicators, signal_idx
                    )
                
                # تطبيق إجراء الفلترة
                if condition_met:
                    if filter_rule.action == "block":
                        should_allow = False
                        break
                    elif filter_rule.action == "delay":
                        # يمكن تطبيق منطق التأخير هنا
                        pass
            
            if should_allow:
                filtered_signals.append(signal)
        
        return filtered_signals
    
    async def _calculate_metrics(
        self,
        data: pd.DataFrame,
        signals: List[TradeSignal]
    ) -> Dict[str, Any]:
        """حساب مقاييس أداء الإستراتيجية"""
        if not signals:
            return {
                "total_signals": 0,
                "entry_signals": 0,
                "exit_signals": 0,
                "signal_frequency": 0,
                "message": "No signals generated"
            }
        
        # تصنيف الإشارات
        entry_signals = [s for s in signals if s.action in ['buy', 'sell']]
        exit_signals = [s for s in signals if s.action == 'close']
        
        # حساب توقيت الإشارات
        if len(signals) > 1:
            time_diffs = []
            for i in range(1, len(signals)):
                diff = (signals[i].timestamp - signals[i-1].timestamp).total_seconds() / 3600
                time_diffs.append(diff)
            
            avg_time_between_signals = np.mean(time_diffs) if time_diffs else 0
        else:
            avg_time_between_signals = 0
        
        # حساب قوة الإشارات
        signal_strengths = [s.strength for s in signals]
        avg_signal_strength = np.mean(signal_strengths) if signal_strengths else 0
        
        # توزيع الإشارات حسب القاعدة
        signals_by_rule = {}
        for signal in signals:
            rule_name = signal.rule_name
            signals_by_rule[rule_name] = signals_by_rule.get(rule_name, 0) + 1
        
        return {
            "total_signals": len(signals),
            "entry_signals": len(entry_signals),
            "exit_signals": len(exit_signals),
            "signal_frequency": len(signals) / len(data) if len(data) > 0 else 0,
            "avg_time_between_signals_hours": avg_time_between_signals,
            "avg_signal_strength": avg_signal_strength,
            "signals_by_rule": signals_by_rule,
            "first_signal": signals[0].timestamp.isoformat() if signals else None,
            "last_signal": signals[-1].timestamp.isoformat() if signals else None
        }
    
    def get_strategy_summary(self) -> Dict[str, Any]:
        """الحصول على ملخص الإستراتيجية"""
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": self.config.description,
            "base_timeframe": self.config.base_timeframe,
            "position_side": self.config.position_side,
            "indicators_count": len(self.config.indicators),
            "entry_rules_count": len(self.config.entry_rules),
            "exit_rules_count": len(self.config.exit_rules),
            "filter_rules_count": len(self.config.filter_rules),
            "risk_management": self.config.risk_management.dict(),
            "created_at": self.config.created_at.isoformat(),
            "updated_at": self.config.updated_at.isoformat()
        }