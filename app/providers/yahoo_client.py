# app/providers/yahoo_client.py
from pathlib import Path
from app.markets.us.symbol_registry import USSymbolRegistry
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import warnings

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


YAHOO_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "1d": "1d",
    "1w": "1wk",
    "1M": "1mo",
}

# Fallback registry used only when the NASDAQ listing CSV is missing, so the
# client keeps working (degraded but functional) instead of crashing.
DEFAULT_US_SYMBOLS = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.", "AMZN": "Amazon.com, Inc.",
    "NVDA": "NVIDIA Corporation", "META": "Meta Platforms, Inc.",
    "TSLA": "Tesla, Inc.", "AMD": "Advanced Micro Devices, Inc.",
    "NFLX": "Netflix, Inc.", "INTC": "Intel Corporation",
    "CSCO": "Cisco Systems, Inc.", "ADBE": "Adobe Inc.",
    "ORCL": "Oracle Corporation", "CRM": "Salesforce, Inc.",
    "QCOM": "QUALCOMM Incorporated", "TXN": "Texas Instruments Incorporated",
    "JPM": "JPMorgan Chase & Co.", "BAC": "Bank of America Corporation",
    "WFC": "Wells Fargo & Company", "V": "Visa Inc.",
    "MA": "Mastercard Incorporated", "DIS": "The Walt Disney Company",
    "KO": "The Coca-Cola Company", "PEP": "PepsiCo, Inc.",
    "XOM": "Exxon Mobil Corporation", "CVX": "Chevron Corporation",
    "BA": "The Boeing Company", "CAT": "Caterpillar Inc.",
    "GS": "The Goldman Sachs Group, Inc.", "MS": "Morgan Stanley",
}

class YahooFinanceClient:
    """عميل Yahoo Finance المتكامل مع جميع وظائف التحليل الفني"""

    # ---- Search caps (bugfix: search used to fire one network call per match
    # across up to 300 symbols sequentially) ----
    MAX_SEARCH_RESULTS = 10        # hard cap on returned matches
    MAX_DETAILED_RESULTS = 5       # max matches enriched via network get_company_info
    COMPANY_INFO_TIMEOUT_S = 3.0   # per-symbol network timeout
    SEARCH_TIMEOUT_S = 20.0        # overall search deadline guard

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "60m": "60m", "1h": "60m", "2h": "2h", "4h": "4h",
            "1d": "1d", "1w": "1wk", "1M": "1mo", "3M": "3mo"
        }

        from app.markets.us.symbol_registry import USSymbolRegistry
        self.symbol_registry = USSymbolRegistry()

        self._load_symbol_registry()

    def _load_symbol_registry(self) -> None:
        """
        Load the NASDAQ symbol list anchored to the project root (bugfix:
        the old code used the CWD-relative path 'data/nasdaq-listed-symbols.csv',
        which broke whenever the process was started from another directory).
        Falls back to a small embedded default symbol list if the CSV is absent.
        """
        # app/providers/yahoo_client.py -> parents[0]=providers, [1]=app, [2]=backend root
        csv_path = Path(__file__).resolve().parents[2] / "data" / "nasdaq-listed-symbols.csv"
        try:
            if csv_path.is_file():
                self.symbol_registry.load_from_files(str(csv_path))
                logger.info(f"Symbol registry loaded {len(self.symbol_registry.symbols_only())} symbols from {csv_path}")
                return
            logger.warning(f"NASDAQ symbols CSV not found at {csv_path}; using embedded default symbol list")
        except Exception as e:
            logger.warning(f"Failed to load symbol registry from {csv_path}: {e}; using embedded default symbol list")

        for symbol, name in DEFAULT_US_SYMBOLS.items():
            self.symbol_registry._symbols[symbol] = {
                "symbol": symbol,
                "name": name,
                "exchange": "NASDAQ",
                "market": "us_stocks",
                "type": "stock",
            }

    # ==================== البيانات الأساسية ====================

    def _validate_symbol(self, symbol: str):
        """
        Validate a US market symbol against the NASDAQ registry.

        Index symbols (Yahoo "^"-prefixed, e.g. ^GSPC/^IXIC/^DJI/^RUT) are NOT
        stocks in the NASDAQ listing, so they bypass registry validation
        (bugfix: get_market_summary used to fail _validate_symbol and silently
        return nothing because of a bare except).
        """
        if not symbol:
            raise ValueError("Empty symbol")
        if symbol.startswith("^"):
            return  # Yahoo index symbol — intentionally not in the stock registry
        if not self.symbol_registry.exists(symbol):
            raise ValueError(f"Symbol {symbol} not listed in US market")

    async def get_historical_data(
        self,
        symbol: str,
        interval: str = "1d",
        period: str = "1mo",
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> pd.DataFrame:

        self._validate_symbol(symbol)

        yahoo_interval = YAHOO_INTERVAL_MAP.get(interval)
        if not yahoo_interval:
            raise ValueError(f"Unsupported interval: {interval}")

        try:
            ticker = yf.Ticker(symbol)

            params = {
                "interval": yahoo_interval,
                # yfinance >= 0.2.51 flipped auto_adjust default to True, which
                # returns split/dividend-adjusted OHLC and breaks raw-candle
                # semantics (ATR/levels). Pin it explicitly.
                "auto_adjust": False,
            }
            if start and end:
                params["start"] = start
                params["end"] = end
            else:
                params["period"] = period

            df = await self._run_in_thread(lambda: ticker.history(**params))

            if df.empty:
                return pd.DataFrame()

            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })

            df = df[["open", "high", "low", "close", "volume"]]
            df = df.dropna()
            df.index = pd.to_datetime(df.index)

            return df

        except Exception as e:
            logger.error(f"Yahoo historical error [{symbol}]: {e}")
            return pd.DataFrame()


    async def get_live_quote(self, symbol: str) -> Dict:
        self._validate_symbol(symbol)

        try:
            ticker = yf.Ticker(symbol)

            # yfinance >= 0.2.40 FastInfo supports mapping-style camelCase access
            # (.get("lastPrice") etc.); the volume key was renamed "lastVolume",
            # so we try both for cross-version compatibility.
            info = await self._run_in_thread(lambda: ticker.fast_info)

            price = info.get("lastPrice")
            prev = info.get("previousClose")

            if price is None or prev is None:
                raise ValueError("Incomplete market data")

            change = price - prev
            change_pct = (change / prev) * 100 if prev else 0

            volume = info.get("lastVolume")
            if volume is None:
                volume = info.get("volume")

            return {
                "symbol": symbol,
                "price": float(price),
                "previous_close": float(prev),
                "change": float(change),
                "change_percent": float(change_pct),
                "high": info.get("dayHigh"),
                "low": info.get("dayLow"),
                "volume": volume,
                "market_cap": info.get("marketCap"),
                "currency": "USD",
                "timestamp": datetime.utcnow().isoformat(),
                "source": "yahoo_finance"
            }

        except Exception as e:
            logger.error(f"Live quote failed [{symbol}]: {e}")
            raise
        

    async def get_company_info(self, symbol: str) -> Dict:
        self._validate_symbol(symbol)
        base_info = self.symbol_registry.get(symbol)

        try:
            ticker = yf.Ticker(symbol)
            info = await self._run_in_thread(lambda: ticker.info)

            return {
                "symbol": symbol,
                "name": info.get("longName", base_info.get("name")),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "employees": info.get("fullTimeEmployees"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
                "website": info.get("website"),
                "country": "US",
                "currency": "USD",
                "exchange": base_info.get("exchange"),
                "type": base_info.get("type")
            }

        except Exception as e:
            logger.error(f"Company info error [{symbol}]: {e}")
            return base_info or {}

    # ==================== المؤشرات الفنية ====================
    
    async def calculate_indicators(self, df: pd.DataFrame, indicators: List[Dict]) -> Dict:
        """حساب المؤشرات الفنية على البيانات"""
        if df.empty:
            return {}
        
        results = {}
        
        for indicator in indicators:
            name = indicator.get('name')
            params = indicator.get('params', {})
            
            try:
                if name == 'sma':
                    results[name] = self._calculate_sma(df, **params)
                elif name == 'ema':
                    results[name] = self._calculate_ema(df, **params)
                elif name == 'rsi':
                    results[name] = self._calculate_rsi(df, **params)
                elif name == 'macd':
                    results[name] = self._calculate_macd(df, **params)
                elif name == 'bollinger_bands':
                    results[name] = self._calculate_bollinger_bands(df, **params)
                elif name == 'stochastic':
                    results[name] = self._calculate_stochastic(df, **params)
                elif name == 'atr':
                    results[name] = self._calculate_atr(df, **params)
                elif name == 'obv':
                    results[name] = self._calculate_obv(df, **params)
                elif name == 'vwap':
                    results[name] = self._calculate_vwap(df, **params)
                elif name == 'ichimoku':
                    results[name] = self._calculate_ichimoku(df, **params)
                elif name == 'parabolic_sar':
                    results[name] = self._calculate_parabolic_sar(df, **params)
                elif name == 'supertrend':
                    results[name] = self._calculate_supertrend(df, **params)
                
            except Exception as e:
                logger.error(f"Error calculating indicator {name}: {e}")
                results[name] = pd.Series([np.nan] * len(df), index=df.index)
        
        return results
    
    def _calculate_sma(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """المتوسط المتحرك البسيط"""
        return df['close'].rolling(window=period).mean()
    
    def _calculate_ema(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """المتوسط المتحرك الأسي"""
        return df['close'].ewm(span=period, adjust=False).mean()
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """مؤشر القوة النسبية"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """مؤشر MACD"""
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def _calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Dict:
        """نطاقات بولينجر"""
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return {
            'upper': upper_band,
            'middle': sma,
            'lower': lower_band
        }
    
    def _calculate_stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict:
        """مؤشر ستوكاستيك"""
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        
        k = 100 * ((df['close'] - low_min) / (high_max - low_min))
        d = k.rolling(window=d_period).mean()
        
        return {
            'k': k,
            'd': d
        }
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """متوسط المدى الحقيقي"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        
        return true_range.rolling(window=period).mean()
    
    def _calculate_obv(self, df: pd.DataFrame) -> pd.Series:
        """حجم الرصيد"""
        obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        return obv
    
    def _calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """متوسط السعر المرجح بحجم التداول"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        return vwap
    
    def _calculate_ichimoku(self, df: pd.DataFrame) -> Dict:
        """سحابة إيشيموكو"""
        high_9 = df['high'].rolling(window=9).max()
        low_9 = df['low'].rolling(window=9).min()
        tenkan_sen = (high_9 + low_9) / 2
        
        high_26 = df['high'].rolling(window=26).max()
        low_26 = df['low'].rolling(window=26).min()
        kijun_sen = (high_26 + low_26) / 2
        
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)
        
        high_52 = df['high'].rolling(window=52).max()
        low_52 = df['low'].rolling(window=52).min()
        senkou_span_b = ((high_52 + low_52) / 2).shift(26)
        
        chikou_span = df['close'].shift(-26)
        
        return {
            'tenkan_sen': tenkan_sen,
            'kijun_sen': kijun_sen,
            'senkou_span_a': senkou_span_a,
            'senkou_span_b': senkou_span_b,
            'chikou_span': chikou_span
        }
    
    def _calculate_parabolic_sar(self, df: pd.DataFrame, acceleration: float = 0.02, maximum: float = 0.2) -> pd.Series:
        """بارابوليك SAR"""
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        sar = np.zeros(len(df))
        ep = np.zeros(len(df))
        af = np.zeros(len(df))
        
        # Initial values
        sar[0] = low[0]
        ep[0] = high[0]
        af[0] = acceleration
        trend = 1  # 1 for uptrend, -1 for downtrend
        
        for i in range(1, len(df)):
            if trend == 1:
                sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
                
                if sar[i] > low[i]:
                    sar[i] = low[i]
                    trend = -1
                    ep[i] = low[i]
                    af[i] = acceleration
                else:
                    if high[i] > ep[i-1]:
                        ep[i] = high[i]
                        af[i] = min(af[i-1] + acceleration, maximum)
                    else:
                        ep[i] = ep[i-1]
                        af[i] = af[i-1]
            else:
                sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
                
                if sar[i] < high[i]:
                    sar[i] = high[i]
                    trend = 1
                    ep[i] = high[i]
                    af[i] = acceleration
                else:
                    if low[i] < ep[i-1]:
                        ep[i] = low[i]
                        af[i] = min(af[i-1] + acceleration, maximum)
                    else:
                        ep[i] = ep[i-1]
                        af[i] = af[i-1]
        
        return pd.Series(sar, index=df.index)
    
    def _calculate_supertrend(self, df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Dict:
        """سوبرتريند"""
        hl2 = (df['high'] + df['low']) / 2
        atr = self._calculate_atr(df, period)
        
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)
        
        supertrend = np.zeros(len(df))
        trend = np.zeros(len(df))
        
        supertrend[0] = upper_band[0]
        trend[0] = 1
        
        for i in range(1, len(df)):
            if df['close'][i-1] <= supertrend[i-1]:
                if df['close'][i] > upper_band[i]:
                    supertrend[i] = lower_band[i]
                    trend[i] = 1
                else:
                    supertrend[i] = min(upper_band[i], supertrend[i-1])
                    trend[i] = -1
            else:
                if df['close'][i] < lower_band[i]:
                    supertrend[i] = upper_band[i]
                    trend[i] = -1
                else:
                    supertrend[i] = max(lower_band[i], supertrend[i-1])
                    trend[i] = 1
        
        return {
            'supertrend': pd.Series(supertrend, index=df.index),
            'trend': pd.Series(trend, index=df.index)
        }
    
    # ==================== أدوات مساعدة ====================
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """تنظيف وإعداد DataFrame"""
        df = df.copy()
        
        # إعادة تسمية الأعمدة
        df.columns = [col.lower() for col in df.columns]
        
        # التأكد من وجود جميع الأعمدة المطلوبة
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                df[col] = np.nan
        
        # إزالة الصفوف الفارغة
        df = df.dropna(subset=['open', 'high', 'low', 'close'])
        
        # إعادة الفهرس
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        
        return df
    
    async def _run_in_thread(self, func, *args, **kwargs):
        """تشغيل دالة في thread منفصل"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, lambda: func(*args, **kwargs))
    






    # async def get_all_symbols(self) -> List[str]:
    #     """الحصول على جميع الرموز المتاحة"""
    #     all_symbols = []
    #     for category in self.base_symbols.values():
    #         all_symbols.extend(category)
    #     return sorted(list(set(all_symbols)))
    



    async def get_all_symbols(self):
        symbols = self.symbol_registry.symbols_only()
        # تحويل كل القيم لنصوص وتصفيه أي NaN أو فراغات
        symbols = [str(s).strip() for s in symbols if pd.notna(s) and str(s).strip() != ""]
        return sorted(symbols)

    async def search_symbols(self, query: str) -> List[Dict]:
        """
        البحث عن الرموز (بالرمز أو باسم الشركة)

        Bugfix: كان البحث يطابق رمز السهم فقط (``query in ticker``) — فلما
        يفشل AlphaVantage (حد 25 طلب/يوم يعيد إشعاراً بدل bestMatches) كان
        البحث عن "apple" يُرجع 0 نتائج رغم وجود AAPL. الآن: مطابقة على
        الرمز وأسماء الشركات من السجل المحلي، مع ترتيب تطابقات الرمز أولاً.
        """
        query = (query or "").upper().strip()
        if not query:
            return []

        all_symbols = await self.get_all_symbols()

        symbol_matches: List[str] = []
        name_matches: List[str] = []
        for s in all_symbols:
            if query in s:
                symbol_matches.append(s)
                if len(symbol_matches) >= self.MAX_SEARCH_RESULTS:
                    break
        if len(symbol_matches) < self.MAX_SEARCH_RESULTS:
            for s in all_symbols:
                if s in symbol_matches:
                    continue
                info = self.symbol_registry.get(s) or {}
                name = str(info.get("name") or "").upper()
                if name and query in name:
                    name_matches.append(s)
                    if len(symbol_matches) + len(name_matches) >= self.MAX_SEARCH_RESULTS:
                        break

        matches = (symbol_matches + name_matches)[: self.MAX_SEARCH_RESULTS]

        results: List[Dict] = []
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.SEARCH_TIMEOUT_S

        for i, symbol in enumerate(matches):
            # Basic info from the local registry (no network).
            registry_info = self.symbol_registry.get(symbol) or {}
            basic = {
                "symbol": symbol,
                "name": registry_info.get("name") or symbol,
                "sector": "N/A",
            }

            # Network enrichment only for the first few matches and only while
            # inside the overall timeout budget.
            if i < self.MAX_DETAILED_RESULTS and loop.time() < deadline:
                try:
                    info = await asyncio.wait_for(
                        self.get_company_info(symbol),
                        timeout=self.COMPANY_INFO_TIMEOUT_S,
                    )
                    basic["name"] = info.get("name") or basic["name"]
                    basic["sector"] = info.get("sector") or "N/A"
                except Exception as e:
                    logger.warning(f"Company info failed during search [{symbol}]: {e}; returning basic info")
            elif i < self.MAX_DETAILED_RESULTS:
                logger.debug("Search deadline reached; skipping detailed lookup")

            results.append(basic)

        return results