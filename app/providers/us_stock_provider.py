# app/providers/us_stock_provider.py
import asyncio
import logging
from datetime import datetime, timedelta, time as dtime
from typing import List, Dict, Optional, Any, AsyncGenerator
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import yfinance as yf

from .yahoo_client import YahooFinanceClient
from .alphavantage_client import AlphaVantageClient

logger = logging.getLogger(__name__)

# ✅ الجولة 4: منطقة السوق الأمريكي (يوم كامل DST تلقائياً)
_US_EASTERN = ZoneInfo("America/New_York")


def get_market_status(now: Optional[datetime] = None) -> str:
    """حالة سوق الأسهم الأمريكي: pre_market / open / post_market / closed.

    الجلسة المنتظمة 09:30-16:00 بتوقيت نيويورك، ما قبلها pre-market (04:00+)
    وما بعدها post-market (حتى 20:00). عطل نهاية الأسبوع = closed."""
    now_et = (now or datetime.now(_US_EASTERN)).astimezone(_US_EASTERN)
    if now_et.weekday() >= 5:  # السبت/الأحد
        return "closed"
    t = now_et.time()
    if dtime(9, 30) <= t < dtime(16, 0):
        return "open"
    if dtime(4, 0) <= t < dtime(9, 30):
        return "pre_market"
    if dtime(16, 0) <= t < dtime(20, 0):
        return "post_market"
    return "closed"

# ---------------------------------------------------------------------------
# Module-level (process-wide) caches.
#
# BUGFIX: the API layer builds a fresh USStockProvider per request
# (DataService → provider registry), so any cache stored on ``self`` was
# discarded together with the instance → top-movers re-fetched ~100 quotes
# (20-30s) on EVERY call despite the "60s cache". Keeping the cache at module
# level makes it survive across requests/instances for the lifetime of the
# worker process.
# ---------------------------------------------------------------------------
_MOVERS_CACHE: Dict[str, Any] = {}          # {"ts": float, "data": {...}}
_MOVERS_CACHE_TTL_S = 60.0

# كاش التاريخ الكامل لكل (رمز, فريم) — يحل مشكلة intraday للأسهم:
# سابقاً كان كل طلب يجلب نافذة ضيقة (AAPL 1h = 21 شمعة فقط، 1m/5m = 0) لأن
# yfinance يرفض start/end قديمة مع 1m/5m. الآن نجلب الفترة القصوى المسموحة
# لكل فريم مرة واحدة ونخدم منها محلياً (سرعة + عمق كامل + has_more دقيق).
_FULL_HIST_CACHE: Dict[str, Any] = {}       # "SYMBOL|tf" -> {"ts": float, "df": DataFrame}

# أقصى فترة يسمح بها Yahoo لكل فريم:
_FULL_PERIOD_BY_TF = {
    "1m": "7d",      # حد Yahoo الصارم لـ 1m
    "2m": "7d",      # عبر تجميع 1m
    "5m": "60d",
    "10m": "60d",    # عبر تجميع 5m
    "15m": "60d",
    "30m": "60d",
    "1h": "730d",
    "2h": "730d",    # عبر تجميع 1h
    "4h": "730d",    # عبر تجميع 1h
    "1d": "max",     # كامل تاريخ الشركة (IPO → اليوم)
    "1w": "max",
    "1M": "max",
}
_TTL_BY_TF_S = {"1m": 300.0, "2m": 300.0, "5m": 600.0, "10m": 600.0,
                "15m": 600.0, "30m": 600.0, "1h": 900.0, "2h": 900.0,
                "4h": 900.0, "1d": 3600.0, "1w": 3600.0, "1M": 3600.0}

_SECTORS_CACHE: Dict[str, Any] = {}          # {"ts": float, "data": [...]}
_SECTORS_CACHE_TTL_S = 300.0

# خريطة قطاعات مدمجة لأشهر الرموز (السجل المحلي لا يخزّن القطاع، وAlphaVantage
# SECTOR توقفت) — تُستخدم لبناء عينة القطاعات فوراً بدون أي نداء شبكة.
_BUILTIN_SECTOR_MAP: Dict[str, str] = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology", "AVGO": "Technology",
    "ORCL": "Technology", "CRM": "Technology", "ADBE": "Technology", "CSCO": "Technology",
    "ACN": "Technology", "AMD": "Technology", "INTC": "Technology", "MU": "Technology",
    "AMAT": "Technology", "LRCX": "Technology", "KLAC": "Technology", "ADI": "Technology",
    "PANW": "Technology", "SNPS": "Technology", "CDNS": "Technology", "FTNT": "Technology",
    "GOOGL": "Communication Services", "GOOG": "Communication Services", "META": "Communication Services",
    "NFLX": "Communication Services", "DIS": "Communication Services", "CMCSA": "Communication Services",
    "T": "Communication Services", "VZ": "Communication Services", "TMUS": "Communication Services",
    "AMZN": "Consumer Cyclical", "TSLA": "Consumer Cyclical", "HD": "Consumer Cyclical",
    "MCD": "Consumer Cyclical", "NKE": "Consumer Cyclical", "SBUX": "Consumer Cyclical",
    "BKNG": "Consumer Cyclical", "LOW": "Consumer Cyclical", "TJX": "Consumer Cyclical",
    "GM": "Consumer Cyclical", "F": "Consumer Cyclical",
    "WMT": "Consumer Defensive", "COST": "Consumer Defensive", "PG": "Consumer Defensive",
    "KO": "Consumer Defensive", "PEP": "Consumer Defensive", "PM": "Consumer Defensive",
    "MDLZ": "Consumer Defensive", "CL": "Consumer Defensive", "KHC": "Consumer Defensive",
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy", "EOG": "Energy",
    "PSX": "Energy", "MPC": "Energy", "OXY": "Energy",
    "JPM": "Financial Services", "BAC": "Financial Services", "WFC": "Financial Services",
    "GS": "Financial Services", "MS": "Financial Services", "C": "Financial Services",
    "V": "Financial Services", "MA": "Financial Services", "BRK-B": "Financial Services",
    "BLK": "Financial Services", "SCHW": "Financial Services", "AXP": "Financial Services",
    "SPGI": "Financial Services", "CB": "Financial Services", "PGR": "Financial Services",
    "UNH": "Healthcare", "JNJ": "Healthcare", "LLY": "Healthcare", "PFE": "Healthcare",
    "MRK": "Healthcare", "ABBV": "Healthcare", "TMO": "Healthcare", "ABT": "Healthcare",
    "DHR": "Healthcare", "AMGN": "Healthcare", "BMY": "Healthcare", "GILD": "Healthcare",
    "CAT": "Industrials", "BA": "Industrials", "GE": "Industrials", "HON": "Industrials",
    "UPS": "Industrials", "RTX": "Industrials", "DE": "Industrials", "LMT": "Industrials",
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities", "D": "Utilities",
    "PLD": "Real Estate", "AMT": "Real Estate", "CCI": "Real Estate", "SPG": "Real Estate",
    "LIN": "Basic Materials", "SHW": "Basic Materials", "FCX": "Basic Materials",
    "NEM": "Basic Materials", "DOW": "Basic Materials", "DD": "Basic Materials",
}


class USStockProvider:
    """المزود الرئيسي للأسهم الأمريكية - TradingView Style"""
    
    def __init__(self, use_alpha_vantage: bool = True):
        self.yahoo = YahooFinanceClient()
        self.alpha_vantage = None
        
        if use_alpha_vantage:
            try:
                self.alpha_vantage = AlphaVantageClient()
                logger.info("✅ AlphaVantageClient initialized")
            except Exception as e:
                logger.warning(f"⚠️ AlphaVantage initialization failed: {e}")
        
        logger.info("✅ USStockProvider initialized successfully")
    
    # ==================== البيانات الأساسية ====================
    


    async def get_symbols(self, category: Optional[str] = None) -> List[str]:
        """
        الحصول على الرموز حسب الفئة

        Bugfix: the old code accessed ``self.yahoo.base_symbols`` which does
        not exist on YahooFinanceClient (AttributeError). The registry has no
        categories, so any requested category is logged and all listed
        symbols are returned instead.
        """
        if category:
            logger.debug(
                "Symbol category '%s' requested but the registry is not "
                "categorized; returning all listed symbols", category
            )
        return await self.yahoo.get_all_symbols()
    







    async def get_live_price(self, symbol: str) -> Dict:
        """الحصول على السعر الحي — مع حالة السوق (الجولة 4)"""
        quote = await self.yahoo.get_live_quote(symbol)
        if isinstance(quote, dict):
            quote.setdefault("market_status", get_market_status())
        return quote




    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str = "1d",
        period: str = "1mo",
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> pd.DataFrame:
        """الحصول على البيانات التاريخية"""
        return await self.yahoo.get_historical_data(symbol, timeframe, period, start, end)

    async def get_full_history(self, symbol: str, timeframe: str = "1d") -> pd.DataFrame:
        """التاريخ الكامل المتاح للفريم (بأقصى فترة يسمح بها Yahoo) + كاش على مستوى الموديول.

        يعيد DataFrame بفهرس DatetimeIndex وأعمدة open/high/low/close/volume.
        الفريمات المركّبة (2m/10m/2h/4h) تُجلب من فريمها الأساسي ثم تُجمّع بالخارج
        عبر app.utils.dataframe_utils.resample_candles.
        """
        import time as _time
        from app.utils.dataframe_utils import is_composite_tf, composite_base_tf

        # فريمات لا يدعمها Yahoo أصلًا → تُجلب من فريم أدق ثم تُجمّع
        _YF_FALLBACK_BASE = {"2h": ("1h", 2), "4h": ("1h", 4), "3d": ("1d", 3)}

        sym = symbol.upper().strip()
        tf = (timeframe or "1d").strip()

        if is_composite_tf(tf):
            base_tf, _factor = composite_base_tf(tf)
        elif tf in _YF_FALLBACK_BASE:
            base_tf, _factor = _YF_FALLBACK_BASE[tf]
        else:
            base_tf, _factor = tf, 1
        cache_key = f"{sym}|{base_tf}"

        now = _time.time()
        cached = _FULL_HIST_CACHE.get(cache_key)
        ttl = _TTL_BY_TF_S.get(base_tf, 600.0)
        if cached and (now - cached.get("ts", 0)) < ttl and cached.get("df") is not None:
            df_base = cached["df"]
        else:
            period = _FULL_PERIOD_BY_TF.get(base_tf, "max")
            # لا نمرر start/end إطلاقاً — period فقط، وإلا رفض Yahoo للفريمات الدقيقة
            df_base = await self.get_historical_data(sym, base_tf, period=period)
            if (df_base is None or df_base.empty):
                # yfinance أحياناً يفشل مؤقتاً (rate-limit) — محاولة واحدة إضافية
                await asyncio.sleep(1.0)
                df_base = await self.get_historical_data(sym, base_tf, period=period)
            if df_base is not None and not df_base.empty:
                _FULL_HIST_CACHE[cache_key] = {"ts": now, "df": df_base}

        if df_base is None or df_base.empty:
            return pd.DataFrame()

        if is_composite_tf(tf) or tf in _YF_FALLBACK_BASE:
            from app.utils.dataframe_utils import resample_candles
            df_r = df_base.copy()
            df_r["time"] = (pd.to_datetime(df_r.index, utc=True).astype("int64") // 10**6)
            res = resample_candles(df_r, tf, time_col="time")
            res = res.set_index(pd.to_datetime(res["time"], unit="ms", utc=True))
            res = res.drop(columns=["time"])
            return res
        return df_base
    
# app/providers/us_stock_provider.py
    async def get_historical(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime = None
    ) -> pd.DataFrame:
        """
        دالة توافقية مع BinanceProvider للحصول على بيانات تاريخية
        
        Args:
            symbol: رمز السهم
            timeframe: الإطار الزمني (1m, 5m, 15m, 1h, 4h, 1d)
            start_date: تاريخ البداية
            end_date: تاريخ النهاية (اختياري)
        
        Returns:
            DataFrame: البيانات التاريخية
        """
        # تحويل timeframe إلى تنسيق Yahoo Finance
        timeframe_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "4h": "4h", "1d": "1d"
        }
        
        yf_interval = timeframe_map.get(timeframe, "1h")
        
        # تحويل التواريخ إلى strings
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d") if end_date else datetime.utcnow().strftime("%Y-%m-%d")
        
        # حساب عدد الأيام للفترة
        if end_date:
            days_diff = (end_date - start_date).days
        else:
            days_diff = (datetime.utcnow() - start_date).days
        
        period = f"{days_diff}d"
        
        # الحصول على البيانات
        df = await self.get_historical_data(
            symbol=symbol,
            timeframe=yf_interval,
            period=period,
            start=start_str,
            end=end_str
        )
        
        # التأكد من وجود الأعمدة المطلوبة
        if not df.empty:
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in df.columns:
                    logger.warning(f"Column {col} not found in data for {symbol}")
            
            # إرجاع الأعمدة المطلوبة فقط
            return df[[col for col in required_columns if col in df.columns]]
        
        return df




    async def get_company_info(self, symbol: str) -> Dict:
        """الحصول على معلومات الشركة"""
        return await self.yahoo.get_company_info(symbol)
    
    # ==================== المؤشرات الفنية ====================
    
    async def calculate_indicators(
        self,
        symbol: str,
        timeframe: str = "1d",
        period: str = "1mo",
        indicators: List[Dict] = None
    ) -> Dict:
        """حساب المؤشرات الفنية"""
        if indicators is None:
            indicators = [
                {"name": "sma", "params": {"period": 20}},
                {"name": "rsi", "params": {"period": 14}},
                {"name": "macd", "params": {}},
                {"name": "bollinger_bands", "params": {}}
            ]
        
        # الحصول على البيانات
        df = await self.get_historical_data(symbol, timeframe, period)
        
        if df.empty:
            return {"error": "No data available"}
        
        # حساب المؤشرات
        results = await self.yahoo.calculate_indicators(df, indicators)
        
        # تحويل النتائج إلى تنسيق قابل للتسلسل
        processed_results = {}
        for name, result in results.items():
            if isinstance(result, dict):
                processed_results[name] = {}
                for key, series in result.items():
                    processed_results[name][key] = series.dropna().to_dict()
            elif hasattr(result, 'to_dict'):
                processed_results[name] = result.dropna().to_dict()
            else:
                processed_results[name] = result
        
        # إضافة بيانات الشموع
        candles = []
        for idx, row in df.iterrows():
            candles.append({
                "time": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": int(row['volume'])
            })
        
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": candles,
            "indicators": processed_results,
            "metadata": {
                "start_date": df.index[0].isoformat(),
                "end_date": df.index[-1].isoformat(),
                "rows": len(df)
            }
        }
    
    async def get_technical_analysis(
        self,
        symbol: str,
        timeframe: str = "1d",
        period: str = "3mo"
    ) -> Dict:
        """تحليل فني متكامل"""
        df = await self.get_historical_data(symbol, timeframe, period)
        
        if df.empty:
            return {}
        
        analysis = {
            "trend": await self._analyze_trend(df),
            "momentum": await self._analyze_momentum(df),
            "volatility": await self._analyze_volatility(df),
            "volume": await self._analyze_volume(df),
            "signals": await self._generate_signals(df)
        }
        
        return analysis
    
    async def _analyze_trend(self, df: pd.DataFrame) -> Dict:
        """تحليل الاتجاه"""
        # المتوسطات المتحركة
        sma_20 = df['close'].rolling(window=20).mean().iloc[-1]
        sma_50 = df['close'].rolling(window=50).mean().iloc[-1]
        sma_200 = df['close'].rolling(window=200).mean().iloc[-1]
        
        current_price = df['close'].iloc[-1]
        
        trend = "sideways"
        if current_price > sma_20 > sma_50 > sma_200:
            trend = "strong_uptrend"
        elif current_price > sma_20 > sma_50:
            trend = "uptrend"
        elif current_price < sma_20 < sma_50 < sma_200:
            trend = "strong_downtrend"
        elif current_price < sma_20 < sma_50:
            trend = "downtrend"
        
        return {
            "direction": trend,
            "price_vs_sma20": (current_price / sma_20 - 1) * 100,
            "price_vs_sma50": (current_price / sma_50 - 1) * 100,
            "price_vs_sma200": (current_price / sma_200 - 1) * 100,
            "sma20": float(sma_20),
            "sma50": float(sma_50),
            "sma200": float(sma_200)
        }
    
    async def _analyze_momentum(self, df: pd.DataFrame) -> Dict:
        """تحليل الزخم"""
        # حساب RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # حساب MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        
        # حساب Stochastic
        low_14 = df['low'].rolling(window=14).min()
        high_14 = df['high'].rolling(window=14).max()
        stoch_k = 100 * ((df['close'] - low_14) / (high_14 - low_14))
        stoch_d = stoch_k.rolling(window=3).mean()
        
        return {
            "rsi": float(rsi.iloc[-1]),
            "rsi_status": "oversold" if rsi.iloc[-1] < 30 else "overbought" if rsi.iloc[-1] > 70 else "neutral",
            "macd": float(macd_line.iloc[-1]),
            "signal": float(signal_line.iloc[-1]),
            "macd_histogram": float(macd_line.iloc[-1] - signal_line.iloc[-1]),
            "stochastic_k": float(stoch_k.iloc[-1]),
            "stochastic_d": float(stoch_d.iloc[-1]),
            "momentum": (df['close'].iloc[-1] / df['close'].iloc[-20] - 1) * 100 if len(df) >= 20 else 0
        }
    
    async def _analyze_volatility(self, df: pd.DataFrame) -> Dict:
        """تحليل التقلب"""
        returns = df['close'].pct_change().dropna()
        
        volatility_20 = returns.tail(20).std() * np.sqrt(252) * 100  # سنوي
        volatility_50 = returns.tail(50).std() * np.sqrt(252) * 100
        
        # نطاقات بولينجر
        sma_20 = df['close'].rolling(window=20).mean()
        std_20 = df['close'].rolling(window=20).std()
        upper_band = sma_20 + (std_20 * 2)
        lower_band = sma_20 - (std_20 * 2)
        
        current_price = df['close'].iloc[-1]
        bb_position = (current_price - lower_band.iloc[-1]) / (upper_band.iloc[-1] - lower_band.iloc[-1]) * 100
        
        return {
            "volatility_20d": float(volatility_20),
            "volatility_50d": float(volatility_50),
            "atr": float(self._calculate_atr(df, 14).iloc[-1]),
            "bb_position": float(bb_position),
            "bb_width": float((upper_band.iloc[-1] - lower_band.iloc[-1]) / sma_20.iloc[-1] * 100)
        }
    
    async def _analyze_volume(self, df: pd.DataFrame) -> Dict:
        """تحليل الحجم"""
        avg_volume_20 = df['volume'].tail(20).mean()
        current_volume = df['volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1
        
        # OBV
        obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        
        return {
            "volume": int(current_volume),
            "avg_volume_20": int(avg_volume_20),
            "volume_ratio": float(volume_ratio),
            "obv": float(obv.iloc[-1]),
            "obv_trend": "up" if obv.iloc[-1] > obv.iloc[-5] else "down",
            "volume_status": "high" if volume_ratio > 1.5 else "low" if volume_ratio < 0.5 else "normal"
        }
    
    async def _generate_signals(self, df: pd.DataFrame) -> List[Dict]:
        """توليد إشارات التداول"""
        signals = []
        
        # إشارات RSI
        rsi = self._calculate_rsi(df, 14)
        if not rsi.empty:
            last_rsi = rsi.iloc[-1]
            if last_rsi < 30:
                signals.append({
                    "type": "buy",
                    "indicator": "rsi",
                    "strength": "strong",
                    "description": "RSI indicates oversold condition"
                })
            elif last_rsi > 70:
                signals.append({
                    "type": "sell",
                    "indicator": "rsi",
                    "strength": "strong",
                    "description": "RSI indicates overbought condition"
                })
        
        # إشارات MACD
        macd_result = self.yahoo._calculate_macd(df)
        if 'macd' in macd_result and 'signal' in macd_result:
            macd_line = macd_result['macd']
            signal_line = macd_result['signal']
            
            if macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-2] <= signal_line.iloc[-2]:
                signals.append({
                    "type": "buy",
                    "indicator": "macd",
                    "strength": "medium",
                    "description": "MACD crossover above signal line"
                })
            elif macd_line.iloc[-1] < signal_line.iloc[-1] and macd_line.iloc[-2] >= signal_line.iloc[-2]:
                signals.append({
                    "type": "sell",
                    "indicator": "macd",
                    "strength": "medium",
                    "description": "MACD crossover below signal line"
                })
        
        # إشارات بولينجر
        bb_result = self.yahoo._calculate_bollinger_bands(df)
        if 'upper' in bb_result and 'lower' in bb_result:
            current_price = df['close'].iloc[-1]
            upper_band = bb_result['upper'].iloc[-1]
            lower_band = bb_result['lower'].iloc[-1]
            
            if current_price < lower_band:
                signals.append({
                    "type": "buy",
                    "indicator": "bollinger",
                    "strength": "weak",
                    "description": "Price below lower Bollinger Band"
                })
            elif current_price > upper_band:
                signals.append({
                    "type": "sell",
                    "indicator": "bollinger",
                    "strength": "weak",
                    "description": "Price above upper Bollinger Band"
                })
        
        return signals
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """حساب ATR"""
        return self.yahoo._calculate_atr(df, period)
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """حساب RSI"""
        return self.yahoo._calculate_rsi(df, period)
    
    # ==================== بيانات Alpha Vantage المتقدمة ====================
    
    async def get_fundamental_data(self, symbol: str) -> Dict:
        """الحصول على البيانات الأساسية من Alpha Vantage"""
        if not self.alpha_vantage:
            return {}
        
        try:
            async with self.alpha_vantage as client:
                overview = await client.get_fundamental_data(symbol)
                earnings = await client.get_earnings(symbol)
                
                return {
                    "overview": overview,
                    "earnings": earnings
                }
        except Exception as e:
            logger.error(f"Error fetching fundamental data: {e}")
            return {}
    
    async def get_financial_statements(self, symbol: str) -> Dict:
        """الحصول على القوائم المالية"""
        if not self.alpha_vantage:
            return {}
        
        try:
            async with self.alpha_vantage as client:
                income = await client.get_income_statement(symbol)
                balance = await client.get_balance_sheet(symbol)
                cashflow = await client.get_cash_flow(symbol)
                
                return {
                    "income_statement": income,
                    "balance_sheet": balance,
                    "cash_flow": cashflow
                }
        except Exception as e:
            logger.error(f"Error fetching financial statements: {e}")
            return {}
    
    async def get_sector_analysis(self) -> Dict:
        """تحليل القطاعات — حساب محلي من سجل الرموز (AlphaVantage SECTOR توقفت).

        AlphaVantage أوقفت نقطة النهاية SECTOR (تُرجع {} دائماً) فكان
        /stocks/sectors يعيد 404 للأبد. الآن: نأخذ عينة رموز من السجل
        المحلي لكل قطاع ونحسب متوسط التغيّر اليومي عبر مكالمة yf.download
        واحدة (كاش 5 دقائق). الفشل يعيد {} كما كان.
        """
        now = datetime.now().timestamp()
        cached = _SECTORS_CACHE.get("data")
        if cached and (now - _SECTORS_CACHE.get("ts", 0)) < _SECTORS_CACHE_TTL_S:
            return cached

        # 1) جهّز عينة رموز لكل قطاع: من الخريطة المدمجة أولاً (فوري)،
        #    ثم من السجل المحلي إن توفّر القطاع فيه.
        sector_candidates: Dict[str, List[str]] = {}
        for symbol, sector in _BUILTIN_SECTOR_MAP.items():
            sector_candidates.setdefault(sector, []).append(symbol)

        unknown: List[str] = []
        try:
            all_symbols = await self.get_symbols()
        except Exception:  # noqa: BLE001
            all_symbols = []
        for symbol in all_symbols[:250]:
            if symbol in _BUILTIN_SECTOR_MAP:
                continue
            info = self.yahoo.symbol_registry.get(symbol) or {}
            sector = info.get("sector")
            if sector and sector not in ("N/A", ""):
                sector_candidates.setdefault(sector, []).append(symbol)
            elif len(unknown) < 40:
                unknown.append(symbol)

        # 2) اجلب القطاعات الفعلية لعدد محدود من الرموز "المجهولة" عبر
        #    معلومات yfinance (limit لتفادي الطلبات الكثيرة).
        if unknown and not sector_candidates:
            loop = asyncio.get_event_loop()
            semaphore = asyncio.Semaphore(10)

            async def _sector_of(sym: str) -> None:
                async with semaphore:
                    try:
                        info = await asyncio.wait_for(self.yahoo.get_company_info(sym), timeout=6.0)
                        sector = info.get("sector")
                        if sector:
                            sector_candidates.setdefault(sector, []).append(sym)
                    except Exception:  # noqa: BLE001
                        pass

            await asyncio.gather(*(_sector_of(s) for s in unknown))

        if not sector_candidates:
            return []

        # 3) عيّنة حتى 8 رموز لكل قطاع ثم مكالمة batch واحدة.
        sample: List[str] = []
        per_sector_samples: Dict[str, List[str]] = {}
        for sector, syms in sector_candidates.items():
            picks = syms[:8]
            per_sector_samples[sector] = picks
            sample.extend(picks)
        sample = list(dict.fromkeys(sample))[:80]

        try:
            loop = asyncio.get_event_loop()

            def _download() -> Optional[pd.DataFrame]:
                try:
                    return yf.download(
                        tickers=sample,
                        period="5d",
                        interval="1d",
                        group_by="ticker",
                        auto_adjust=True,
                        progress=False,
                        threads=True,
                    )
                except Exception:  # noqa: BLE001
                    return None

            raw = await asyncio.wait_for(loop.run_in_executor(None, _download), timeout=25.0)
            if raw is None or raw.empty:
                return []

            changes: Dict[str, float] = {}
            for symbol in sample:
                try:
                    frame = raw[symbol] if isinstance(raw.columns, pd.MultiIndex) else raw
                    closes = frame["Close"].dropna()
                    if len(closes) < 2:
                        continue
                    prev = float(closes.iloc[-2])
                    last = float(closes.iloc[-1])
                    if prev > 0 and last > 0:
                        changes[symbol] = ((last - prev) / prev) * 100.0
                except Exception:  # noqa: BLE001
                    continue

            sectors = []
            for sector, syms in per_sector_samples.items():
                vals = [changes[s] for s in syms if s in changes]
                if not vals:
                    continue
                sectors.append({
                    "sector": sector,
                    "average_change_percent": round(sum(vals) / len(vals), 3),
                    "symbols_sampled": len(vals),
                })

            sectors.sort(key=lambda s: s["average_change_percent"], reverse=True)
            if sectors:
                _SECTORS_CACHE["ts"] = now
                _SECTORS_CACHE["data"] = sectors
            return sectors
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error computing sector analysis: {e}")
            return []
    
    async def search_stocks(self, query: str) -> List[Dict]:
        """البحث عن الأسهم

        Bugfix: كان AlphaVantage يُستدعى أولاً وعند تجاوز حد 25 طلب/يوم
        يُرجع قائمة فارغة **بدون استثناء** فلا يصل التنفيذ لاحتياطي Yahoo
        (البحث المحلي بالاسم والرمز) — وكانت النتيجة 0 دائماً. الآن:
        النتيجة الفارغة من AV تُعامَل كفشل ويُجرَّب البحث المحلي.
        """
        if self.alpha_vantage:
            try:
                async with self.alpha_vantage as client:
                    results = await client.search_symbol(query)
                if results:
                    return results
                logger.info("AlphaVantage search empty for '%s' (rate-limited?) → local registry fallback", query)
            except Exception as e:
                logger.error(f"Error searching stocks via AlphaVantage: {e}")
        return await self.yahoo.search_symbols(query)
    
    # ==================== بيانات السوق العامة ====================
    
    async def get_market_summary(self) -> Dict:
        """ملخص السوق"""
        # ^GSPC/^IXIC/^DJI/^RUT are Yahoo index symbols — supported since
        # _validate_symbol bypasses the stock registry for "^"-prefixed symbols.
        indices = ["^GSPC", "^DJI", "^IXIC", "^RUT"]  # S&P 500, Dow Jones, NASDAQ, Russell 2000
        
        summary = {}
        for index in indices:
            try:
                quote = await self.get_live_price(index)
                summary[index] = {
                    "price": quote.get('price', 0),
                    "change": quote.get('change', 0),
                    "change_percent": quote.get('change_percent', 0)
                }
            except Exception as e:
                # Bugfix: was a bare `except: pass` that silently swallowed
                # failures; now we log and expose a partial result with the
                # error per index so the caller/monitoring can see it.
                logger.error(f"Market summary: failed to fetch index {index}: {e}")
                summary[index] = {"error": str(e)}
        
        return summary
    
    async def get_top_gainers_losers(self) -> Dict:
        """أكبر الرابحين والخاسرين — batch download + كاش على مستوى العملية.

        Bugfix 2 (على إصلاح الـ 56s): كان الكاش يُخزَّن على ``self`` بينما
        طبقة الـ API تنشئ مزوداً جديداً لكل طلب → الكاش لم يصب أبداً وكان
        كل استدعاء يستغرق 20-30 ثانية. الآن:

        1. كاش على مستوى الموديول (يبقى عبر الطلبات) — TTL 60 ثانية.
        2. مسار سريع: ``yf.download`` لدفعة واحدة (مكالمة شبكة واحدة لكل
           100 رمز) ويُحسب التغيّر من إغلاقي آخر يومين — أقل من 3 ثوانٍ.
        3. fallback إلى المسار المتوازي القديم إذا فشل الدفع الجماعي.
        """
        # 1) كاش على مستوى العملية (TTL 60 ثانية)
        now = datetime.now().timestamp()
        cached = _MOVERS_CACHE.get("data")
        if cached and (now - _MOVERS_CACHE.get("ts", 0)) < _MOVERS_CACHE_TTL_S:
            return cached

        common_symbols = await self.get_symbols()
        selected = list(common_symbols[:100])

        payload = await self._movers_via_batch(selected)
        if payload is None:
            payload = await self._movers_via_parallel_quotes(selected)

        # 2) خزّن بالكاش المشترك حتى لو كانت النتيجة فارغة (تفادي الهجوم
        #    على Yahoo عند تعطل مصدر البيانات) — لكن فقط إن وُجدت نتائج.
        if payload and (payload.get("gainers") or payload.get("losers")):
            _MOVERS_CACHE["ts"] = now
            _MOVERS_CACHE["data"] = payload
        return payload

    async def _movers_via_batch(self, selected: List[str]) -> Optional[Dict]:
        """مسار سريع: مكالمة download واحدة لكل الرموز (~1-2 ثانية)."""
        try:
            loop = asyncio.get_event_loop()

            def _download() -> Optional[pd.DataFrame]:
                try:
                    return yf.download(
                        tickers=selected,
                        period="5d",
                        interval="1d",
                        group_by="ticker",
                        auto_adjust=True,
                        progress=False,
                        threads=True,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Batch movers download failed")
                    return None

            raw = await asyncio.wait_for(loop.run_in_executor(None, _download), timeout=20.0)
            if raw is None or raw.empty:
                return None

            gainers: List[Dict[str, Any]] = []
            losers: List[Dict[str, Any]] = []

            for symbol in selected:
                try:
                    if isinstance(raw.columns, pd.MultiIndex):
                        if symbol not in raw.columns.get_level_values(0):
                            continue
                        frame = raw[symbol]
                    else:
                        frame = raw
                    closes = frame["Close"].dropna()
                    if len(closes) < 2:
                        continue
                    prev = float(closes.iloc[-2])
                    last = float(closes.iloc[-1])
                    if prev <= 0 or last <= 0:
                        continue
                    # حجم آخر يوم تداول (كان مفقوداً → عمود Volume فارغ في Markets)
                    vol = 0.0
                    if "Volume" in frame.columns:
                        vol_series = frame["Volume"].dropna()
                        if len(vol_series) > 0:
                            vol = float(vol_series.iloc[-1] or 0)
                    change_pct = ((last - prev) / prev) * 100.0
                    item = {"symbol": symbol, "change": change_pct, "price": last,
                            "volume": vol}
                    if change_pct > 2:
                        gainers.append(item)
                    elif change_pct < -2:
                        losers.append(item)
                except Exception:  # noqa: BLE001 — رمز تالف لا يُسقط الدفعة
                    continue

            return {
                "gainers": sorted(gainers, key=lambda x: x["change"], reverse=True)[:10],
                "losers": sorted(losers, key=lambda x: x["change"])[:10],
            }
        except Exception:  # noqa: BLE001 — المسار المتوازي يتولى الباقي
            logger.warning("Batch movers path failed; falling back to parallel quotes")
            return None

    async def _movers_via_parallel_quotes(self, selected: List[str]) -> Dict:
        """المسار الاحتياطي: أسعار متوازية (حد تزامن 15 + مهلة 6 ثوانٍ/رمز)."""
        semaphore = asyncio.Semaphore(15)

        async def _fetch_one(symbol: str) -> Optional[Dict[str, Any]]:
            async with semaphore:
                try:
                    quote = await asyncio.wait_for(self.get_live_price(symbol), timeout=6.0)
                except (asyncio.TimeoutError, Exception) as e:  # noqa: BLE001 — رمز فاشل لا يأسك الطلب كله
                    logger.debug("Movers: skip %s: %s", symbol, e)
                    return None
            price = quote.get("price") or 0
            change_pct = quote.get("change_percent") or 0
            if not price or price <= 0:  # أسعار صفر/سالبة = بيانات ناقصة → تجاهل
                return None
            return {
                "symbol": symbol,
                "change": change_pct,
                "price": price,
            }

        results = await asyncio.gather(*(_fetch_one(s) for s in selected))

        gainers: List[Dict[str, Any]] = []
        losers: List[Dict[str, Any]] = []
        for item in results:
            if not item:
                continue
            change_pct = item["change"]
            if change_pct > 2:
                gainers.append(item)
            elif change_pct < -2:
                losers.append(item)

        return {
            "gainers": sorted(gainers, key=lambda x: x["change"], reverse=True)[:10],
            "losers": sorted(losers, key=lambda x: x["change"])[:10],
        }
    
    # ==================== دعم WebSocket ====================
    
    async def stream_live_data(
        self,
        symbol: str,
        interval: int = 5  # تحديث كل 5 ثواني
    ) -> AsyncGenerator[Dict, None]:
        """بث بيانات حية محاكاة"""
        while True:
            try:
                quote = await self.get_live_price(symbol)
                yield quote
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error in live stream: {e}")
                await asyncio.sleep(1)
    
    # ==================== أدوات الرسم البياني ====================
    
    async def get_chart_data(
        self,
        symbol: str,
        timeframe: str = "1d",
        period: str = "1mo",
        indicators: List[Dict] = None
    ) -> Dict:
        """الحصول على بيانات الرسم البياني المتكاملة"""
        data = await self.calculate_indicators(symbol, timeframe, period, indicators)
        
        if "error" in data:
            return data
        
        # إعداد بيانات الرسم البياني
        chart_data = {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": data["candles"],
            "indicators": data["indicators"],
            "analysis": await self.get_technical_analysis(symbol, timeframe, period),
            "company_info": await self.get_company_info(symbol),
            "current_quote": await self.get_live_price(symbol)
        }
        
        return chart_data