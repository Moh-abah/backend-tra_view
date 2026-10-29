# app/providers/alphavantage_client.py
import aiohttp
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import asyncio
import logging
import os
import time
from collections import deque

logger = logging.getLogger(__name__)

class AlphaVantageClient:
    """عميل Alpha Vantage للبيانات المتقدمة والمؤشرات"""

    # ---- Free-tier friendly client-side rate guard (bugfix: the client used
    # to hammer the API and only then discover the "Note" rate-limit response) ----
    MAX_REQUESTS_PER_MIN: int = 20
    RATE_WINDOW_S: float = 60.0

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ALPHA_VANTAGE_API_KEY')
        self.base_url = "https://www.alphavantage.co/query"
        self.session = None
        # Timestamps (time.monotonic) of recent requests, oldest first.
        self._request_timestamps: deque = deque()
    
    def _acquire_rate_slot(self) -> bool:
        """
        Reserve a request slot. Returns False when the free-tier budget
        (MAX_REQUESTS_PER_MIN per RATE_WINDOW_S) is exhausted — callers then
        back off instead of hammering the API.
        """
        now = time.monotonic()
        while self._request_timestamps and now - self._request_timestamps[0] > self.RATE_WINDOW_S:
            self._request_timestamps.popleft()
        if len(self._request_timestamps) >= self.MAX_REQUESTS_PER_MIN:
            return False
        self._request_timestamps.append(now)
        return True
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def make_request(self, params: Dict) -> Dict:
        """إرسال طلب إلى Alpha Vantage"""
        # Client-side rate guard: return an explicit error instead of firing
        # another request that would only earn another rate-limit note.
        if not self._acquire_rate_slot():
            logger.warning(
                "Alpha Vantage local rate guard hit (%d req/%ds); request for %s rejected",
                self.MAX_REQUESTS_PER_MIN, int(self.RATE_WINDOW_S), params.get("function"),
            )
            return {"error": "rate_limited"}

        if not self.session:
            self.session = aiohttp.ClientSession()
        
        params['apikey'] = self.api_key
        
        try:
            async with self.session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # التحقق من وجود رسالة خطأ
                    if "Error Message" in data:
                        logger.error(f"Alpha Vantage error: {data['Error Message']}")
                        return {"error": "api_error", "message": data["Error Message"]}
                    if "Note" in data:  # Rate limit
                        logger.warning(f"Alpha Vantage rate limit: {data['Note']}")
                        return {"error": "rate_limited", "note": data["Note"]}
                    if "Information" in data:
                        # Newer Alpha Vantage API uses the "Information" key for
                        # rate-limit/premium notices as well.
                        logger.warning(f"Alpha Vantage notice: {data['Information']}")
                        return {"error": "rate_limited", "note": data["Information"]}
                    
                    return data
                else:
                    logger.error(f"Alpha Vantage HTTP error: {response.status}")
                    return {"error": "http_error", "status": response.status}
        except Exception as e:
            logger.error(f"Alpha Vantage request error: {e}")
            return {}
    
    async def get_intraday(self, symbol: str, interval: str = "5min", outputsize: str = "compact") -> pd.DataFrame:
        """الحصول على البيانات داخل اليوم"""
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize
        }
        
        data = await self.make_request(params)
        
        if not data or f"Time Series ({interval})" not in data:
            return pd.DataFrame()
        
        time_series = data[f"Time Series ({interval})"]
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.columns = [col.split('. ')[1] for col in df.columns]
        df.index = pd.to_datetime(df.index)
        df = df.astype(float)
        df = df.sort_index()
        
        return df
    
    async def get_daily(self, symbol: str, outputsize: str = "compact") -> pd.DataFrame:
        """الحصول على البيانات اليومية"""
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": outputsize
        }
        
        data = await self.make_request(params)
        
        if not data or "Time Series (Daily)" not in data:
            return pd.DataFrame()
        
        time_series = data["Time Series (Daily)"]
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.columns = [col.split('. ')[1] for col in df.columns]
        df.index = pd.to_datetime(df.index)
        df = df.astype(float)
        df = df.sort_index()
        
        return df
    
    async def get_technical_indicator(
        self, 
        symbol: str, 
        indicator: str, 
        interval: str = "daily",
        time_period: int = 20,
        series_type: str = "close",
        **kwargs
    ) -> pd.DataFrame:
        """الحصول على مؤشر فني"""
        
        indicator_map = {
            "sma": "SMA",
            "ema": "EMA", 
            "wma": "WMA",
            "dema": "DEMA",
            "tema": "TEMA",
            "trima": "TRIMA",
            "kama": "KAMA",
            "mama": "MAMA",
            "t3": "T3",
            "macd": "MACD",
            "macdext": "MACDEXT",
            "stoch": "STOCH",
            "stochf": "STOCHF",
            "rsi": "RSI",
            "stochrsi": "STOCHRSI",
            "willr": "WILLR",
            "adx": "ADX",
            "adxr": "ADXR",
            "apo": "APO",
            "ppo": "PPO",
            "mom": "MOM",
            "bop": "BOP",
            "cci": "CCI",
            "cmo": "CMO",
            "roc": "ROC",
            "rocr": "ROCR",
            "aroon": "AROON",
            "aroonosc": "AROONOSC",
            "mf": "MFI",
            "trix": "TRIX",
            "ultosc": "ULTOSC",
            "dx": "DX",
            "minus_di": "MINUS_DI",
            "plus_di": "PLUS_DI",
            "minus_dm": "MINUS_DM",
            "plus_dm": "PLUS_DM",
            "bbands": "BBANDS",
            "midpoint": "MIDPOINT",
            "midprice": "MIDPRICE",
            "sar": "SAR",
            "trange": "TRANGE",
            "atr": "ATR",
            "natr": "NATR",
            "ad": "AD",
            "adosc": "ADOSC",
            "obv": "OBV",
            "ht_trendline": "HT_TRENDLINE",
            "ht_sine": "HT_SINE",
            "ht_trendmode": "HT_TRENDMODE",
            "ht_dcperiod": "HT_DCPERIOD",
            "ht_dcphase": "HT_DCPHASE",
            "ht_phasor": "HT_PHASOR"
        }
        
        if indicator not in indicator_map:
            logger.error(f"Indicator {indicator} not supported")
            return pd.DataFrame()
        
        params = {
            "function": indicator_map[indicator],
            "symbol": symbol,
            "interval": interval,
            "time_period": time_period,
            "series_type": series_type,
            **kwargs
        }
        
        data = await self.make_request(params)
        
        if not data or f"Technical Analysis: {indicator_map[indicator]}" not in data:
            return pd.DataFrame()
        
        tech_data = data[f"Technical Analysis: {indicator_map[indicator]}"]
        df = pd.DataFrame.from_dict(tech_data, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.astype(float)
        df = df.sort_index()
        
        return df
    
    async def get_fundamental_data(self, symbol: str) -> Dict:
        """الحصول على البيانات الأساسية"""
        params = {
            "function": "OVERVIEW",
            "symbol": symbol
        }
        
        data = await self.make_request(params)
        return data if data else {}
    
    async def get_earnings(self, symbol: str) -> Dict:
        """الحصول على بيانات الأرباح"""
        params = {
            "function": "EARNINGS",
            "symbol": symbol
        }
        
        data = await self.make_request(params)
        return data if data else {}
    
    async def get_income_statement(self, symbol: str) -> Dict:
        """الحصول على قائمة الدخل"""
        params = {
            "function": "INCOME_STATEMENT",
            "symbol": symbol
        }
        
        data = await self.make_request(params)
        return data if data else {}
    
    async def get_balance_sheet(self, symbol: str) -> Dict:
        """الحصول على الميزانية العمومية"""
        params = {
            "function": "BALANCE_SHEET",
            "symbol": symbol
        }
        
        data = await self.make_request(params)
        return data if data else {}
    
    async def get_cash_flow(self, symbol: str) -> Dict:
        """الحصول على التدفق النقدي"""
        params = {
            "function": "CASH_FLOW",
            "symbol": symbol
        }
        
        data = await self.make_request(params)
        return data if data else {}
    
    async def get_sector_performance(self) -> Dict:
        """الحصول على أداء القطاعات"""
        params = {
            "function": "SECTOR"
        }
        
        data = await self.make_request(params)
        return data if data else {}
    
    async def search_symbol(self, keywords: str) -> List[Dict]:
        """البحث عن الرموز"""
        params = {
            "function": "SYMBOL_SEARCH",
            "keywords": keywords
        }
        
        data = await self.make_request(params)
        
        if not data or "bestMatches" not in data:
            return []
        
        matches = data["bestMatches"]
        results = []
        
        for match in matches:
            results.append({
                "symbol": match.get("1. symbol", ""),
                "name": match.get("2. name", ""),
                "type": match.get("3. type", ""),
                "region": match.get("4. region", ""),
                "currency": match.get("8. currency", "")
            })
        
        return results
    
    async def get_global_quote(self, symbol: str) -> Dict:
        """الحصول على اقتباس عالمي"""
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol
        }
        
        data = await self.make_request(params)
        
        if not data or "Global Quote" not in data:
            return {}
        
        quote = data["Global Quote"]
        return {
            "symbol": quote.get("01. symbol", ""),
            "open": float(quote.get("02. open", 0)),
            "high": float(quote.get("03. high", 0)),
            "low": float(quote.get("04. low", 0)),
            "price": float(quote.get("05. price", 0)),
            "volume": int(quote.get("06. volume", 0)),
            "latest_trading_day": quote.get("07. latest trading day", ""),
            "previous_close": float(quote.get("08. previous close", 0)),
            "change": float(quote.get("09. change", 0)),
            "change_percent": quote.get("10. change percent", "0%")
        }