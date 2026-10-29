# app/services/indicators/volume.py
import pandas as pd

def calculate_volume_ma(data: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    حساب متوسط حجم التداول المتحرك
    
    :param data: DataFrame يحتوي على أعمدة 'volume'
    :param period: الفترة (افتراضي 20)
    :return: Series تحتوي على قيم متوسط الحجم
    """
    if 'volume' not in data.columns:
        raise ValueError("DataFrame يجب أن يحتوي على عمود 'volume'")
    
    return data['volume'].rolling(window=period).mean()