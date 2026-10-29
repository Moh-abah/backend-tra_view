import re
import ast
from typing import Dict, List, Any, Optional, Tuple, Type
from dataclasses import dataclass
import pandas as pd
import numpy as np
from .base import BaseIndicator, IndicatorConfig, IndicatorResult, IndicatorType
from .registry import IndicatorRegistry

@dataclass
class PineFunction:
    """تمثيل دالة Pine Script"""
    name: str
    parameters: Dict[str, Any]
    body: str
    return_type: str

class PineScriptTranspiler:
    """محول مبسط من Pine Script إلى Python"""
    
    # تعيين دوال Pine إلى دوال Python
    PINE_TO_PYTHON_MAP = {
        # الدوال الرياضية
        'abs': 'abs',
        'sqrt': 'np.sqrt',
        'log': 'np.log',
        'log10': 'np.log10',
        'exp': 'np.exp',
        'pow': 'np.power',
        'round': 'round',
        'ceil': 'np.ceil',
        'floor': 'np.floor',
        
        # الدوال الإحصائية
        'min': 'np.minimum',
        'max': 'np.maximum',
        'sum': 'np.sum',
        'sma': 'pd.Series.rolling.mean',
        'ema': 'pd.Series.ewm',
        'wma': 'weighted_moving_average',
        'stdev': 'pd.Series.rolling.std',
        
        # دوال السلسلة الزمنية
        'close': 'close',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'volume': 'volume',
        'hl2': '(high + low) / 2',
        'hlc3': '(high + low + close) / 3',
        'ohlc4': '(open + high + low + close) / 4',
        
        # دوال المؤشرات
        'rsi': 'calculate_rsi',
        'macd': 'calculate_macd',
        'stoch': 'calculate_stochastic',
        'atr': 'calculate_atr',
        'bb': 'calculate_bollinger_bands',
        
        # دوال المنطق
        'iff': 'np.where',
        'crossover': 'crossover',
        'crossunder': 'crossunder',
        'rising': 'rising',
        'falling': 'falling',
    }
    
    def __init__(self):
        self.custom_functions: Dict[str, PineFunction] = {}
    
    def parse_pine_script(self, pine_code: str) -> Dict[str, Any]:
        """
        تحليل كود Pine Script واستخراج المكونات
        
        Args:
            pine_code: كود Pine Script
            
        Returns:
            Dict: المكونات المستخرجة
        """
        components = {
            "study_name": self._extract_study_name(pine_code),
            "inputs": self._extract_inputs(pine_code),
            "variables": self._extract_variables(pine_code),
            "functions": self._extract_functions(pine_code),
            "main_logic": self._extract_main_logic(pine_code),
            "plots": self._extract_plots(pine_code)
        }
        
        return components
    
    def _extract_study_name(self, code: str) -> str:
        """استخراج اسم الدراسة"""
        match = re.search(r'study\s*\(\s*title\s*=\s*["\'](.+?)["\']', code, re.IGNORECASE)
        return match.group(1) if match else "CustomIndicator"
    
    def _extract_inputs(self, code: str) -> Dict[str, Any]:
        """استخراج المدخلات"""
        inputs = {}
        
        # البحث عن تعريفات المدخلات
        input_pattern = r'input\.(.+?)\s*\([^)]*default\s*=\s*([^,)]+)'
        matches = re.finditer(input_pattern, code, re.IGNORECASE)
        
        for match in matches:
            input_type = match.group(1)  # float, int, bool, etc.
            input_name = self._extract_input_name(match.group(0))
            default_value = self._parse_default_value(match.group(2))
            
            inputs[input_name] = {
                "type": input_type,
                "default": default_value
            }
        
        return inputs
    
    def _extract_input_name(self, input_line: str) -> str:
        """استخراج اسم المدخل"""
        # نمط: input.float(defval=14, title="Period")
        match = re.search(r'defval\s*=\s*[^,]+,\s*title\s*=\s*["\'](.+?)["\']', input_line)
        if match:
            return match.group(1).replace(" ", "_").lower()
        
        # نمط بديل
        match = re.search(r'title\s*=\s*["\'](.+?)["\']', input_line)
        if match:
            return match.group(1).replace(" ", "_").lower()
        
        return "param"
    
    def _parse_default_value(self, value_str: str) -> Any:
        """تحليل القيمة الافتراضية"""
        value_str = value_str.strip()
        
        if value_str.lower() == 'true':
            return True
        elif value_str.lower() == 'false':
            return False
        elif '.' in value_str:
            try:
                return float(value_str)
            except:
                return value_str
        else:
            try:
                return int(value_str)
            except:
                return value_str
    
    def _extract_variables(self, code: str) -> Dict[str, str]:
        """استخراج المتغيرات"""
        variables = {}
        
        # البحث عن تعريفات المتغيرات
        var_pattern = r'(\w+)\s*=\s*(.+?)(?:\n|$)'
        lines = code.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('//') or line.startswith('study') or line.startswith('input'):
                continue
            
            match = re.match(var_pattern, line)
            if match:
                var_name = match.group(1)
                var_value = match.group(2).rstrip(';').strip()
                
                # تجنب دوال plot
                if not var_value.startswith('plot'):
                    variables[var_name] = var_value
        
        return variables
    
    def _extract_functions(self, code: str) -> Dict[str, PineFunction]:
        """استخراج الدوال المخصصة"""
        functions = {}
        
        # نمط دالة Pine Script
        func_pattern = r'(\w+)\s*\(([^)]*)\)\s*=>\s*\n?(.+?)(?=\n\w+\s*\(|\Z)'
        matches = re.finditer(func_pattern, code, re.DOTALL)
        
        for match in matches:
            func_name = match.group(1)
            params_str = match.group(2)
            body = match.group(3).strip()
            
            # تحليل المعاملات
            params = {}
            if params_str.strip():
                for param in params_str.split(','):
                    param = param.strip()
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[key.strip()] = self._parse_default_value(value.strip())
                    else:
                        params[param] = None
            
            functions[func_name] = PineFunction(
                name=func_name,
                parameters=params,
                body=body,
                return_type="float"  # افتراضي
            )
        
        return functions
    
    def _extract_main_logic(self, code: str) -> str:
        """استخراج المنطق الرئيسي"""
        lines = code.split('\n')
        logic_lines = []
        
        in_main_logic = False
        for line in lines:
            line = line.strip()
            
            # تخطي التعليقات والتعريفات
            if line.startswith('//') or line.startswith('study') or \
               line.startswith('input') or '=>' in line:
                continue
            
            # بدء المنطق الرئيسي بعد آخر تعريف
            if line and not line.startswith('plot'):
                in_main_logic = True
            
            if in_main_logic and line:
                logic_lines.append(line)
        
        return '\n'.join(logic_lines)
    
    def _extract_plots(self, code: str) -> List[Dict[str, Any]]:
        """استخراج تعريفات الرسوم البيانية"""
        plots = []
        
        plot_pattern = r'plot\s*\(([^)]+)\)'
        matches = re.finditer(plot_pattern, code, re.IGNORECASE)
        
        for match in matches:
            plot_content = match.group(1)
            
            # استخراج خصائص plot
            plot_data = {
                "series": self._extract_plot_series(plot_content),
                "title": self._extract_plot_title(plot_content),
                "color": self._extract_plot_color(plot_content),
                "linewidth": self._extract_plot_linewidth(plot_content)
            }
            
            plots.append(plot_data)
        
        return plots
    
    def _extract_plot_series(self, content: str) -> str:
        """استخراج سلسلة البيانات للرسم"""
        # أول عنصر في plot() هو عادة السلسلة
        parts = content.split(',')
        return parts[0].strip()
    
    def _extract_plot_title(self, content: str) -> str:
        """استخراج عنوان الرسم"""
        match = re.search(r'title\s*=\s*["\'](.+?)["\']', content)
        return match.group(1) if match else ""
    
    def _extract_plot_color(self, content: str) -> str:
        """استخراج لون الرسم"""
        match = re.search(r'color\s*=\s*(\w+)', content)
        return match.group(1) if match else "blue"
    
    def _extract_plot_linewidth(self, content: str) -> int:
        """استخراج عرض الخط"""
        match = re.search(r'linewidth\s*=\s*(\d+)', content)
        return int(match.group(1)) if match else 2
    
    def transpile_to_python(self, pine_code: str) -> str:
        """
        تحويل كود Pine Script إلى كود Python
        
        Args:
            pine_code: كود Pine Script
            
        Returns:
            str: كود Python مكافئ
        """
        components = self.parse_pine_script(pine_code)
        
        # بناء كود Python
        python_code = self._build_python_class(components)
        
        return python_code
    
    def _build_python_class(self, components: Dict[str, Any]) -> str:
        """بناء فئة Python من المكونات"""
        study_name = components["study_name"]
        inputs = components["inputs"]
        variables = components["variables"]
        functions = components["functions"]
        main_logic = components["main_logic"]
        plots = components["plots"]
        
        # اسم الفئة
        class_name = study_name.replace(" ", "").replace("-", "").replace("_", "")
        
        # بناء الكود
        python_code = f'''"""
مؤشر مخصص من Pine Script: {study_name}
تم إنشاؤه تلقائياً بواسطة PineScriptTranspiler
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from app.services.indicators.base import BaseIndicator, IndicatorResult, IndicatorConfig
from app.services.indicators.registry import IndicatorRegistry

@IndicatorRegistry.register(
    name="{study_name.lower().replace(' ', '_')}",
    display_name="{study_name}",
    description="مؤشر مخصص من Pine Script",
    category="custom"
)
class {class_name}Indicator(BaseIndicator):
    """{study_name} - مؤشر مخصص"""
    
    @classmethod
    def get_default_params(cls) -> Dict[str, Any]:
        """المعاملات الافتراضية"""
        return {{
{self._build_default_params(inputs)}
        }}
    
    @classmethod
    def get_required_columns(cls) -> List[str]:
        """الأعمدة المطلوبة"""
        return ['open', 'high', 'low', 'close', 'volume']
    
    def _pine_to_python(self, expression: str) -> str:
        """تحويل تعبير Pine إلى Python"""
        # استبدال دوال Pine
        for pine_func, python_func in self.PINE_TO_PYTHON_MAP.items():
            expression = expression.replace(pine_func, python_func)
        
        # استبدال المتغيرات الخاصة
        expression = expression.replace('close', 'data[\"close\"]')
        expression = expression.replace('open', 'data[\"open\"]')
        expression = expression.replace('high', 'data[\"high\"]')
        expression = expression.replace('low', 'data[\"low\"]')
        expression = expression.replace('volume', 'data[\"volume\"]')
        
        return expression
    
    def calculate(self, data: pd.DataFrame) -> IndicatorResult:
        """حساب المؤشر"""
        params = self.params
        
        # تهيئة المتغيرات
{self._build_variables_initialization(variables)}
        
        # حساب المنطق الرئيسي
{self._build_main_logic_calculation(main_logic, variables)}
        
        # تجهيز النتائج للرسم
{self._build_plot_results(plots)}
        
        return IndicatorResult(
            name=self.name,
            values={self._get_main_plot_series(plots)},
            metadata={self._build_metadata(plots)}
        )

{self._build_helper_functions()}
'''
        return python_code
    
    def _build_default_params(self, inputs: Dict[str, Any]) -> str:
        """بناء المعاملات الافتراضية"""
        params_code = []
        for name, info in inputs.items():
            default_value = info["default"]
            if isinstance(default_value, str):
                default_value = f"\"{default_value}\""
            params_code.append(f'            "{name}": {default_value},')
        
        return '\n'.join(params_code)
    
    def _build_variables_initialization(self, variables: Dict[str, str]) -> str:
        """بناء تهيئة المتغيرات"""
        init_code = []
        for var_name, var_expr in variables.items():
            python_expr = self._pine_to_python(var_expr)
            init_code.append(f'        {var_name} = {python_expr}')
        
        return '\n'.join(init_code) if init_code else '        pass'
    
    def _build_main_logic_calculation(self, main_logic: str, variables: Dict[str, str]) -> str:
        """بناء حساب المنطق الرئيسي"""
        if not main_logic:
            return '        # لا يوجد منطق رئيسي'
        
        # تحويل سطر بسطر
        lines = main_logic.split('\n')
        python_lines = []
        
        for line in lines:
            line = line.strip().rstrip(';')
            if line:
                python_line = self._pine_to_python(line)
                python_lines.append(f'        {python_line}')
        
        return '\n'.join(python_lines)
    
    def _build_plot_results(self, plots: List[Dict[str, Any]]) -> str:
        """بناء نتائج الرسم"""
        if not plots:
            return '        # لا توجد رسوم بيانية محددة'
        
        plot_code = []
        for i, plot in enumerate(plots):
            series = plot["series"]
            title = plot["title"] or f"plot_{i}"
            python_series = self._pine_to_python(series)
            plot_code.append(f'        {title} = {python_series}')
        
        return '\n'.join(plot_code)
    
    def _get_main_plot_series(self, plots: List[Dict[str, Any]]) -> str:
        """الحصول على السلسلة الرئيسية للرسم"""
        if plots:
            first_plot = plots[0]
            title = first_plot["title"] or "plot_0"
            return title
        return "pd.Series([0] * len(data), index=data.index)"
    
    def _build_metadata(self, plots: List[Dict[str, Any]]) -> str:
        """بناء البيانات الوصفية"""
        if not plots:
            return '{}'
        
        metadata_items = []
        for plot in plots:
            title = plot["title"] or "unnamed"
            series = plot["series"]
            metadata_items.append(f'            "{title}": {series}.tolist(),')
        
        return '{\n' + '\n'.join(metadata_items) + '\n        }'
    
    def _build_helper_functions(self) -> str:
        """بناء الدوال المساعدة"""
        helper_functions = '''
def weighted_moving_average(series, period):
    """المتوسط المتحرك المرجح"""
    weights = np.arange(1, period + 1)
    return series.rolling(window=period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), 
        raw=True
    )

def crossover(series1, series2):
    """اكتشاف التقاطع التصاعدي"""
    return (series1 > series2) & (series1.shift(1) <= series2.shift(1))

def crossunder(series1, series2):
    """اكتشاف التقاطع التنازلي"""
    return (series1 < series2) & (series1.shift(1) >= series2.shift(1))

def rising(series, length=1):
    """اكتشاف الارتفاع"""
    return series > series.shift(length)

def falling(series, length=1):
    """اكتشاف الانخفاض"""
    return series < series.shift(length)
'''
        return helper_functions
    
    def create_indicator_from_pine(
        self, 
        pine_code: str, 
        indicator_name: str = None
    ) -> Type[BaseIndicator]:
        """
        إنشاء مؤشر من كود Pine Script
        
        Args:
            pine_code: كود Pine Script
            indicator_name: اسم المؤشر (اختياري)
            
        Returns:
            Type[BaseIndicator]: فئة المؤشر المنشأة
        """
        python_code = self.transpile_to_pine(pine_code)
        
        # تنفيذ الكود الديناميكي
        exec_globals = {
            'pd': pd,
            'np': np,
            'BaseIndicator': BaseIndicator,
            'IndicatorResult': IndicatorResult,
            'IndicatorConfig': IndicatorConfig,
            'IndicatorRegistry': IndicatorRegistry,
            'IndicatorType': IndicatorType
        }
        
        exec(python_code, exec_globals)
        
        # العثور على الفئة المنشأة
        components = self.parse_pine_script(pine_code)
        study_name = components["study_name"]
        class_name = study_name.replace(" ", "").replace("-", "").replace("_", "")
        
        indicator_class = exec_globals.get(f'{class_name}Indicator')
        
        if not indicator_class:
            raise ValueError(f"Failed to create indicator class: {class_name}")
        
        return indicator_class