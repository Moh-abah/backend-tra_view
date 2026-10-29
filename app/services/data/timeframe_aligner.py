import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime

class TimeframeAligner:
    """
    هذه الكلاس مسئولة عن توحيد أطر زمنية متعددة (MTF) إلى إطار زمني واحد (Base TF).
    تستخدم قاعدة: نعمل دائماً على أصغر إطار زمني متاح (Base TF)،
    ونقوم بإسقاط الأطر الأعلى عليه.
    """
    
    def __init__(self, base_timeframe: str):
        self.base_timeframe = base_timeframe
        self.ratio_map = self._build_ratio_map(base_timeframe)

    def _build_ratio_map(self, base_tf: str) -> Dict[str, int]:
        """حساب معاملات التحويل بين الإطارات الزمنية"""
        # مثال: 1 ساعة = 12 شمعة 5 دقائق
        # هذه القيم تقريبية (Trading Days) لضبط البيانات
        # في الإنتاج، يجب استخدام قاعدة "مقارنة الفهارس" بدقة 100%
        map_rules = {
            '1m': {'1m': 1, '5m': 5, '15m': 15, '1h': 60},
            '5m': {'5m': 1, '15m': 3, '1h': 12},
            '15m': {'15m': 1, '1h': 4},
            '1h': {'1h': 1, '4h': 4}
        }
        return map_rules.get(base_tf, {})

    async def align_data(
        self, 
        base_data: pd.DataFrame, 
        higher_data_map: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        دمج البيانات العليا مع البيانات الأساسية.
        يفترض أن higher_data_map مفتاحه هو اسم الإطار (مثلاً '15m')
        """
        aligned_df = base_data.copy()
        
        for tf_name, higher_df in higher_data_map.items():
            if higher_df.empty:
                continue
                
            # 1. التأكد من فهرسة البيانات (Index Alignment)
            # نضبط فهرس البيانات العليا ليطابق البيانات الأساسية
            # (هذا مهم جداً لتفادي أخطاء `NaN` عند المقارنة)
            aligned_hf = higher_df.reindex(base_data.index, method='nearest')
            
            # 2. إعادة التسمية (Prefixing)
            # لإضافة اسم الإطار لأعمدة البيانات لتجنب التعارض (Collision)
            # مثلاً بدلاً من عمودين `close`، نحصل على `close` و `close_15m`
            renamed_df = aligned_hf.add_suffix(f'_{tf_name}')
            
            # 3. الدمج (Merging)
            aligned_df = pd.concat([aligned_df, renamed_df], axis=1)
            
        return aligned_df

    def resample_indicator_logic(self, params: Dict, current_tf: str, target_tf: str) -> Dict:
        """
        (ميزة متقدمة للتحسين) تعديل معاملات المؤشر بناءً على التحويل الزمني.
        مثال: إذا طلبنا SMA 50 على 1h، ونشغل الاستراتيجية على 15m.
        فترة الـ SMA يجب أن تكون 50 * (60/15) = 200 تقريباً.
        """
        ratio = self.ratio_map.get(current_tf, {}).get(target_tf, 1)
        
        if 'period' in params:
            params['period'] = int(params['period'] * ratio)
            
        return params