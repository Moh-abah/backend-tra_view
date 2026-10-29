import asyncio
import aiohttp
import pandas as pd
import json
from datetime import datetime

BASE_URL = "https://api.binance.com"

async def get_last_closed_candles(symbol: str, timeframe: str, limit: int = 10):
    """
    جلب آخر الشموع المغلقة فقط قبل الشمعة الحية (closed candles) 
    بدون استخدام datetime.utcnow().
    """
    interval_map = {
        "1m": "1m", "5m": "5m", "15m": "15m",
        "1h": "1h", "4h": "4h", "1d": "1d"
    }
    interval = interval_map.get(timeframe, "1h")

    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/api/v3/klines"
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit + 1  # نأخذ واحدة إضافية لنزيل الشمعة الحالية غير المغلقة
        }
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise Exception(f"Error fetching candles: {resp.status}")
            data = await resp.json()
            
            if not data:
                return pd.DataFrame()
            
            # تحويل إلى DataFrame
            df = pd.DataFrame(data, columns=[
                'open_time', 'open', 'high', 'low', 'close',
                'volume', 'close_time', 'quote_volume',
                'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_cols] = df[numeric_cols].astype(float)
            df['time'] = df['open_time'].astype(int)
            
       
            df = df.iloc[:-1] if len(df) > 1 else df
            
            return df

async def main():
    symbol = "ETHUSDT"  # العملة
    timeframe = "1m"     # فريم الدقيقة
    df = await get_last_closed_candles(symbol, timeframe, limit=10)
    
    # حفظ النتائج في ملف JSON
    result = df.to_dict('records')
    with open("last_closed_candles.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"✅ Last {len(result)} closed candles saved to last_closed_candles.json")

if __name__ == "__main__":
    asyncio.run(main())
