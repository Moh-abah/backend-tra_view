import pandas as pd
from typing import Dict

class TimeframeConverter:
    """محول إطارات الزمنية"""
    
    @staticmethod
    def convert_dataframe(
        df: pd.DataFrame,
        from_tf: str,
        to_tf: str
    ) -> pd.DataFrame:
        """
        تحويل DataFrame من إطار زمني إلى آخر
        """
        # تحويل to_tf إلى دقائق
        tf_minutes = {
            "1m": 1, "5m": 5, "15m": 15,
            "30m": 30, "1h": 60, "4h": 240,
            "1d": 1440, "1w": 10080
        }
        
        if to_tf not in tf_minutes:
            raise ValueError(f"Unsupported timeframe: {to_tf}")
        
        # إعادة العينة
        rule = f"{tf_minutes[to_tf]}T" if to_tf != "1d" else "1D"
        
        resampled = df.resample(rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return resampled
    
    @staticmethod
    def convert_tick_to_timeframe(
        ticks: list,
        timeframe: str
    ) -> pd.DataFrame:
        """
        تحويل بيانات Tick إلى إطار زمني محدد
        """
        if not ticks:
            return pd.DataFrame()
        
        # تحويل إلى DataFrame
        df = pd.DataFrame(ticks)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        # إعادة العينة حسب الإطار الزمني
        return TimeframeConverter.convert_dataframe(df, "1m", timeframe)