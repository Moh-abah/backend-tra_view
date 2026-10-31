

# app/services/strategy/conditions.py

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from .schemas import Condition, CompositeCondition, Operator, ConditionType
import logging
logger = logging.getLogger(__name__)

class ConditionEvaluator:
    """محرك تقييم الشروط"""

    def __init__(self):
        # ==========================================================
        # ✅ كاش أداء (Performance Cache):
        # تحويل Series/columns إلى مصفوفات numpy مرة واحدة لكل مجموعة بيانات
        # بدلاً من .loc/.iloc لكل شمعة (كان يقلّب الأداء خطياً مع طول البيانات).
        # المفاتيح تعتمد على هوية الكائن (id) مع التحقق من الهوية لمنع إعادة
        # استخدام id قديم بعد garbage collection.
        # ==========================================================
        self._np_series_cache: Dict[int, tuple] = {}   # id(Series) -> (series_ref, ndarray, length)
        self._np_col_cache: Dict[tuple, Any] = {}      # (id(df), col) -> ndarray
        self._warned_refs: set = set()                 # تحذير واحد فقط لكل مرجع مفقود
        self.operator_functions = {
            Operator.GREATER_THAN: lambda x, y: x > y,
            Operator.GREATER_THAN_EQUAL: lambda x, y: x >= y,
            Operator.LESS_THAN: lambda x, y: x < y,
            Operator.LESS_THAN_EQUAL: lambda x, y: x <= y,
            Operator.EQUAL: lambda x, y: x == y,
            Operator.NOT_EQUAL: lambda x, y: x != y,
            Operator.CROSSOVER_ABOVE: self._crossover_above,
            Operator.CROSSOVER_BELOW: self._crossover_below,

            Operator.TOUCHES: lambda x, y: x <= y, 
        }

    def set_indicators_data(self, indicators_data):
        if not isinstance(indicators_data, dict):
            logger.warning(f"Expected dict for indicators_data but got {type(indicators_data)}. Using empty dict.")
            indicators_data = {}
        self.indicators_data = indicators_data
        logger.debug(f"Indicators data set: {list(self.indicators_data.keys())}")


    def evaluate(
        self,
        condition: Union[Condition, CompositeCondition],  # ✅ تقبل كليهما
        data: pd.DataFrame,
        indicators: dict,
        current_index: int
    ) -> bool:
        # 1. إذا كان CompositeCondition
        if isinstance(condition, CompositeCondition):
            if condition.type in ["logical_and", "and"]:
                # جميع الشروط يجب أن تكون True
                for sub_condition in condition.conditions:
                    if not self.evaluate(sub_condition, data, indicators, current_index):
                        return False
                return True
            elif condition.type in ["logical_or", "or"]:
                # يكفي شرط واحد True
                for sub_condition in condition.conditions:
                    if self.evaluate(sub_condition, data, indicators, current_index):
                        return True
                return False
            else:
                logger.error(f"Unknown composite condition type: {condition.type}")
                return False
        
        # 2. إذا كان Condition عادي
        elif isinstance(condition, Condition):
            # ✅ إصلاح: كان يُرجع False لكل الأنواع عند الشمعة 0 — فيمنع أي
            # استراتيجية من الدخول في الشمعة الأولى. الحجب مطلوب فقط لشروط
            # التقاطع (تحتاج شمعة سابقة للمقارنة)، أما مقارنات القيم فسليمة.
            crossover_types = {ConditionType.INDICATOR_CROSSOVER, ConditionType.PRICE_CROSSOVER}
            if current_index <= 0 and condition.type in crossover_types:
                return False

            left_value = self._get_value(condition.left_value, data, indicators, current_index)
            right_value = self._get_value(condition.right_value, data, indicators, current_index)

            if left_value is None or right_value is None:
                return False

            operator_func = self.operator_functions.get(condition.operator)
            if not operator_func:
                raise ValueError(f"Unknown operator: {condition.operator}")

            if condition.operator in [Operator.CROSSOVER_ABOVE, Operator.CROSSOVER_BELOW]:
                prev_left_value = self._get_value(condition.left_value, data, indicators, current_index - 1)
                prev_right_value = self._get_value(condition.right_value, data, indicators, current_index - 1)
                if prev_left_value is None or prev_right_value is None:
                    return False
                return operator_func(left_value, right_value, prev_left_value, prev_right_value)
            else:
                return operator_func(left_value, right_value)
        
        # 3. نوع غير معروف
        else:
            logger.error(f"Unknown condition type: {type(condition)}")
            return False        
        

    def evaluate_composite(
        self,
        composite: CompositeCondition,
        data: pd.DataFrame,
        indicators: Dict[str, pd.Series],
        current_index: int
    ) -> bool:
        """
        تقييم شرط مركب
        
        Args:
            composite: الشرط المركب
            data: بيانات السوق
            indicators: نتائج المؤشرات
            current_index: الفهرس الحالي
            
        Returns:
            bool: نتيجة التقييم
        """
        # logger.debug(f"Evaluating composite condition at index {current_index}")
        results = []
        
        for i, condition in enumerate(composite.conditions):
            if isinstance(condition, Condition):
                result = self.evaluate(condition, data, indicators, current_index)
                # logger.debug(f"Sub-condition {i} result: {result}")
            elif isinstance(condition, CompositeCondition):
                result = self.evaluate_composite(condition, data, indicators, current_index)
            else:
                raise TypeError(f"Unknown condition type: {type(condition)}")
            
            results.append(result)
        
        if composite.type == "and":
            final_result = all(results)
        elif composite.type == "or":
            final_result = any(results)
        else:
            raise ValueError(f"Unknown composite type: {composite.type}")
        
        # logger.debug(f"Composite condition final result: {final_result}")
        return final_result







    def _series_to_array(self, series: pd.Series) -> np.ndarray:
        """
        ✅ تحويل Series إلى مصفوفة numpy مرة واحدة (كاش بالهوية).
        مصفوفة numpy تُقرأ بـ O(1) عبر الفهرس العددي بدلاً من
        `current_date in index` + `.loc[...]` (بطيء جداً على 500k+ شمعة).
        """
        key = id(series)
        cached = self._np_series_cache.get(key)
        if cached is not None and cached[0] is series:
            return cached[1]
        try:
            arr = series.to_numpy(dtype=np.float64, na_value=np.nan, copy=False)
        except (TypeError, ValueError):
            arr = np.asarray(pd.to_numeric(series, errors='coerce').to_numpy(
                dtype=np.float64, na_value=np.nan, copy=False))
        # حد أقصى للكاش لمنع تضخم الذاكرة في الخدمات طويلة العمر (WS/Signals)
        if len(self._np_series_cache) > 512:
            self._np_series_cache.clear()
        self._np_series_cache[key] = (series, arr, len(series))
        return arr

    def _get_value(
        self,
        value: Any,
        data: pd.DataFrame,
        indicators: Dict[str, Any],
        index: int
    ) -> Optional[float]:

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            # ✅ دعم مقارنات السعر المباشرة: "price:close" / "price:open" /
            # "price:high" / "price:low" — مع كاش مصفوفات numpy
            if value.startswith('price:'):
                col = value.split(':', 1)[1].strip().lower()
                return self._column_value(data, col, index)

            # إذا كانت قيمة مؤشر
            if value.startswith('indicator:'):
                parts = value.split(':')

                # ✅ الجولة 11 (v2): صيغة ثلاثية الأجزاء indicator:<name>:<column>
                # مثال: "indicator:zigzag_channels:zz_pivot_low" → عمود ind_zz_pivot_low
                if len(parts) >= 3 and parts[2].strip():
                    col = parts[2].strip()
                    ind_col = col if col.startswith('ind_') else f"ind_{col}"
                    # 1) عمود ind_* المدمج في df (مؤشرات البنية — العقد الملزم)
                    if ind_col in data.columns:
                        return self._column_value(data, ind_col, index)
                    # 2) عمود مباشر بالاسم كما هو
                    if col in data.columns:
                        return self._column_value(data, col, index)
                    # 3) قاموس المؤشرات (ndarray/Series/dict)
                    indicator_data = None
                    for key in (ind_col, col, value):
                        indicator_data = indicators.get(key)
                        if indicator_data is not None:
                            break
                    if indicator_data is None:
                        if value not in self._warned_refs:
                            self._warned_refs.add(value)
                            logger.warning(
                                "Overlay column '%s' (from '%s') not found — أدرج المؤشر في strategy_config.indicators",
                                col, value,
                            )
                        return None
                    return self._value_from_indicator_data(indicator_data, index)

                # الصيغة القديمة ثنائية الأجزاء — indicator:<name> (توافق رجعي كامل)
                indicator_ref = parts[1]

                indicator_data = indicators.get(indicator_ref)

                # ✅ الجولة 11 (v2): fallback — اسم عمود تعاقدي مباشر
                # (مثل indicator:zz_pivot_low → عمود ind_zz_pivot_low في df)
                if indicator_data is None:
                    ind_col = f"ind_{indicator_ref}"
                    if ind_col in data.columns:
                        return self._column_value(data, ind_col, index)

                if indicator_data is None:
                    # ⚠️ تحذير مرة واحدة فقط لكل مرجع (كان يُطبع لكل شمعة!)
                    if indicator_ref not in self._warned_refs:
                        self._warned_refs.add(indicator_ref)
                        logger.warning(f"Indicator '{indicator_ref}' not found in indicators")
                    return None

                # مصفوفة numpy من الكاش — أسرع مسار (شائع في الباك تست)
                if isinstance(indicator_data, np.ndarray):
                    if 0 <= index < len(indicator_data):
                        val = indicator_data[index]
                        return None if np.isnan(val) else float(val)
                    return None

                if isinstance(indicator_data, pd.Series):
                    arr = self._series_to_array(indicator_data)
                    if 0 <= index < len(arr):
                        val = arr[index]
                        return None if np.isnan(val) else float(val)
                    return None

                # معالجة dict المؤشرات (أخذ أول Series صالح)
                elif isinstance(indicator_data, dict):
                    for key, val in indicator_data.items():
                        if isinstance(val, pd.Series):
                            arr = self._series_to_array(val)
                            if 0 <= index < len(arr):
                                v = arr[index]
                                if not np.isnan(v):
                                    return float(v)
                    return None

                return None

            # معالجة أسعار البيانات "price.close" (النقطة بدل النقطتين)
            elif value.startswith('price.'):
                price_field = value.split('.', 1)[1].strip().lower()
                return self._column_value(data, price_field, index)

            # معالجة الحقول المباشرة (اسم عمود في الـ DataFrame)
            elif value in data.columns:
                return self._column_value(data, value, index)

        return None

    def _value_from_indicator_data(self, indicator_data: Any, index: int) -> Optional[float]:
        """✅ الجولة 11 (v2): استخراج قيمة من بيانات مؤشر (ndarray/Series/dict).

        نفس منطق المسار القديم — فُصلت كي تستخدمه الصيغة ثلاثية الأجزاء."""
        import numpy as np
        if isinstance(indicator_data, np.ndarray):
            if 0 <= index < len(indicator_data):
                val = indicator_data[index]
                return None if np.isnan(val) else float(val)
            return None
        if isinstance(indicator_data, pd.Series):
            arr = self._series_to_array(indicator_data)
            if 0 <= index < len(arr):
                val = arr[index]
                return None if np.isnan(val) else float(val)
            return None
        if isinstance(indicator_data, dict):
            for key, val in indicator_data.items():
                if isinstance(val, pd.Series):
                    arr = self._series_to_array(val)
                    if 0 <= index < len(arr):
                        v = arr[index]
                        if not np.isnan(v):
                            return float(v)
            return None
        return None

    def _column_value(self, data: pd.DataFrame, col: str, index: int) -> Optional[float]:
        """
        قراءة عمود سعري/حقل مباشر عبر كاش numpy.
        يعالج الأعمدة المكررة (df[col] يعيد DataFrame) بأخذ العمود الأول.
        """
        if col not in data.columns or index < 0 or index >= len(data):
            return None
        key = (id(data), col)
        arr = self._np_col_cache.get(key)
        if arr is None:
            series = data[col]
            if isinstance(series, pd.DataFrame):  # أعمدة مكررة
                series = series.iloc[:, 0]
            arr = self._series_to_array(series)
            self._np_col_cache[key] = arr
        if 0 <= index < len(arr):
            val = arr[index]
            return None if np.isnan(val) else float(val)
        return None






















    
    def _crossover_above(
        self,
        left_value: float,
        right_value: float,
        prev_left_value: float = None,
        prev_right_value: float = None
    ) -> bool:
        """اكتشاف تقاطع من أسفل إلى أعلى"""
        if prev_left_value is None or prev_right_value is None:
            return False
        
        return (left_value > right_value and prev_left_value <= prev_right_value)
    
    def _crossover_below(
        self,
        left_value: float,
        right_value: float,
        prev_left_value: float = None,
        prev_right_value: float = None
    ) -> bool:
        """اكتشاف تقاطع من أعلى إلى أسفل"""
        if prev_left_value is None or prev_right_value is None:
            return False
        
        return (left_value < right_value and prev_left_value >= prev_right_value)
    
    def batch_evaluate(
        self,
        condition: Condition,
        data: pd.DataFrame,
        indicators: Dict[str, pd.Series]
    ) -> pd.Series:
        """
        تقييم شرط على مجموعة بيانات كاملة
        
        Args:
            condition: الشرط
            data: بيانات السوق الكاملة
            indicators: نتائج المؤشرات
            
        Returns:
            pd.Series: نتائج التقييم لكل صف
        """
        results = pd.Series(False, index=data.index)
        
        for i in range(1, len(data)):
            result = self.evaluate(condition, data, indicators, i)
            results.iloc[i] = result
        
        return results
    
    def validate_condition(
        self,
        condition: Condition,
        available_indicators: List[str],
        available_price_fields: List[str] = None
    ) -> Tuple[bool, str]:
        """
        التحقق من صحة الشرط
        
        Args:
            condition: الشرط المراد التحقق منه
            available_indicators: قائمة المؤشرات المتاحة
            available_price_fields: قائمة حقول السعر المتاحة
            
        Returns:
            Tuple[bool, str]: (صالح، رسالة خطأ)
        """
        if available_price_fields is None:
            available_price_fields = ['open', 'high', 'low', 'close', 'volume']
        
        # التحقق من القيم اليسرى
        left_valid, left_msg = self._validate_value(
            condition.left_value, available_indicators, available_price_fields
        )
        if not left_valid:
            return False, f"Left value error: {left_msg}"
        
        # التحقق من القيم اليمنى
        right_valid, right_msg = self._validate_value(
            condition.right_value, available_indicators, available_price_fields
        )
        if not right_valid:
            return False, f"Right value error: {right_msg}"
        
        return True, "Condition is valid"
    
    def _validate_value(
        self,
        value: Any,
        available_indicators: List[str],
        available_price_fields: List[str]
    ) -> Tuple[bool, str]:
        """التحقق من صحة قيمة"""
        if isinstance(value, (int, float)):
            return True, ""
        
        if isinstance(value, str):
            if value.startswith('indicator:'):
                indicator_ref = value.split(':')[1]
                # التحقق من المؤشرات الرئيسية
                for available in available_indicators:
                    if indicator_ref == available or indicator_ref in available:
                        return True, ""
               # return False, f"Indicator '{indicator_ref}' not in available indicators: {available_indicators}"
            
            elif value in available_price_fields:
                return True, ""
            
            elif value in ['price.close', 'price.open', 'price.high', 'price.low', 'price.volume']:
                return True, ""
            
            elif 'hl2' in value.lower() or 'hlc3' in value.lower():
                return True, ""
        
        return False, f"Invalid value format: {value}"