# app/services/indicators/sma.py
import pandas as pd

def calculate_sma(data: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    حساب المتوسط المتحرك البسيط (SMA)
    
    :param data: DataFrame يحتوي على أعمدة 'close'
    :param period: الفترة (افتراضي 20)
    :return: Series تحتوي على قيم SMA
    """
    if 'close' not in data.columns:
        raise ValueError("DataFrame يجب أن يحتوي على عمود 'close'")
    
    return data['close'].rolling(window=period).mean()