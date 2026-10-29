# trading_backend\app\services\data_service.py
import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
import pandas as pd
from app.services.indicators import apply_indicators, calculate_trading_signals
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.redis_client import redis_client
from app.providers.binance_provider import BinanceProvider
from app.utils.converters import TimeframeConverter
import math
logger = logging.getLogger(__name__)


class DataService:
    """الخدمة الموحدة لإدارة البيانات"""
    def __init__(self, db: Optional[AsyncSession] = None):
        # db is optional: background/websocket paths (e.g. routers/websocket.py)
        # construct DataService(None) / DataService() without a session.
        # Methods that need persistence must call self._require_db() first.
        self.db = db
        self.providers = {}
        self.converter = TimeframeConverter()
        


        try:
            # استدعاء binance مباشرة (موجود بالأعلى)
            self.providers["crypto"] = BinanceProvider()
            logger.info("✅ BinanceProvider initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize BinanceProvider: {e}")


        try:
            from app.providers.us_stock_provider import USStockProvider
            self.providers["stocks"] = USStockProvider(use_alpha_vantage=True)
            logger.info("✅ USStockProvider initialized (Yahoo Finance + Alpha Vantage)")
        except Exception as e:
            logger.error(f"❌ Failed to initialize USStockProvider: {e}")
            raise

    def _require_db(self) -> AsyncSession:
        """
        Guard for methods that need a DB session: raises a clear 503 instead
        of an opaque AttributeError when DataService was created stateless.
        """
        if self.db is None:
            raise HTTPException(
                status_code=503,
                detail="database session required",
            )
        return self.db




    async def get_symbols(
        self, 
        market: str,
        filter_pattern: Optional[str] = None
    ) -> List[str]:
        logger.debug("ENTER get_symbols() with market = %s", market)
        """
        الحصول على الرموز مع فلترة
        """
        # التحقق من وجود المزود
        if market not in self.providers:
            raise HTTPException(
                status_code=400,
                detail=f"Market '{market}' is not supported."
            )
        
        provider = self.providers[market]
        cache_key = f"symbols:{market}"
        symbols = []

        # محاولة الحصول من الكاش، ولكن لا توقف التنفيذ
        try:
            cached = await redis_client.get_cached(cache_key)
            
            if cached:
                symbols = cached
                logger.info(f"Retrieved {len(symbols)} symbols from cache for market: {market}")
        except Exception as e:
            logger.warning(f"Cache error: {e}. Continuing without cache.")

        # إذا لم توجد في الكاش، الحصول من المزود
        if not symbols:
            try:
                symbols = await provider.get_symbols()
                logger.debug(f"provider returned {len(symbols)} symbols for market {market}")
                logger.info(f"Retrieved {len(symbols)} symbols from provider for market: {market}")
                # محاولة التخزين في الكاش، ولكن لا توقف التنفيذ
                try:
                    await redis_client.set_cached(cache_key, symbols, expire=3600)
                except Exception as e:
                    logger.warning(f"Failed to cache symbols: {e}")
            except Exception as e:
                logger.error(f"Failed to get symbols from provider: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve symbols from {market} provider"
                )

        # تطبيق الفلترة إذا وجدت
        if filter_pattern:
            symbols = [s for s in symbols if filter_pattern.upper() in s.upper()]

        return symbols
    

    
    async def get_live_price(
        self, 
        symbol: str, 
        market: str = "crypto"
    ) -> Dict:
        """
        الحصول على السعر الحالي مع الكاش بطريقة آمنة
        """
        cache_key = f"price:{market}:{symbol}"
        
        # محاولة الحصول من الكاش
        try:
            cached = await redis_client.get_cached(cache_key)
            if cached:
                cached["cached"] = True
                return cached
        except Exception as e:
            logger.warning(f"Cache read error: {e}. Continuing without cache.")
        
        # الحصول من المزود
        provider = self.providers.get(market)
        if not provider:
            raise ValueError(f"Unsupported market: {market}")
        
        data = await provider.get_live_price(symbol)
        
        # تخزين في الكاش (انتهاء بعد 10 ثواني)
        try:
            await redis_client.set_cached(cache_key, data, expire=10)
        except Exception as e:
            logger.warning(f"Cache write error: {e}. Continuing without caching.")
        
        return data





    async def stream_lives(self, symbol: str, timeframe: str, market: str = "crypto"):
        """
        بث بيانات حية (alias قديم لـ stream_live)

        Bugfix: referenced the nonexistent ``self.provider`` attribute. The
        providers live in the ``self.providers`` dict, so the correct one is
        selected by the ``market`` argument (defaults to crypto).
        """
        provider = self.providers.get(market)
        if not provider:
            raise ValueError(f"Unsupported market: {market}")

        async for tick in provider.stream_live(symbol, timeframe):
            yield tick



    async def stream_live(
        self,
        symbol: str,
        timeframe: str,
        market: str
    ):
        """
        بث بيانات حية
        """
        provider = self.providers.get(market)
        if not provider:
            raise ValueError(f"Unsupported market: {market}")
        
        async for data in provider.stream_live(symbol, timeframe):
            # تحويل إذا لزم الأمر
            if timeframe != "1m":
                # يمكن إضافة منطق التحويل هنا
                pass
            
            yield data
    

    async def get_multiple_prices(
        self,
        symbols: List[str],
        market: str
    ) -> Dict[str, Dict]:
        """
        الحصول على أسعار متعددة دفعة واحدة
        """
        results = {}
        
        for symbol in symbols:
            try:
                price = await self.get_live_price(symbol, market)
                results[symbol] = price
            except Exception as e:
                results[symbol] = {"error": str(e)}
        
        return results
    












    async def get_historical(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        days: int = 30,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        الحصول على بيانات تاريخية
        """
        cache_key = f"historical:{market}:{symbol}:{timeframe}:{days}"

        if use_cache:
            try:
                cached = await redis_client.get_cached(cache_key)
                if cached:
                    # rebuilding a potentially large DataFrame is CPU work — keep it
                    # off the event loop so /health and other requests never freeze.
                    return await asyncio.to_thread(pd.DataFrame, cached)
            except Exception as e:
                logger.warning(f"Cache read error: {e}. Continuing without cache.")
        
        # تحديد المزود
        provider = self.providers.get(market)
        if not provider:
            raise ValueError(f"Unsupported market: {market}")
        
        # حساب التواريخ
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        

        if market == "stocks":
            # تحويل timeframe إلى تنسيق Yahoo Finance
            timeframe_map = {
                "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1h": "1h", "4h": "4h", "1d": "1d"
            }
            
            stock_timeframe = timeframe_map.get(timeframe, "1h")
            period = f"{days}d"
            
            # الحصول على بيانات الأسهم باستخدام get_historical_data
            df = await provider.get_historical_data(
                symbol=symbol,
                timeframe=stock_timeframe,
                period=period,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d")
            )
            
            # التحقق من وجود البيانات
            if df.empty:
                raise ValueError(f"No historical data found for stock: {symbol}")
            
            # التأكد من وجود الأعمدة المطلوبة
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")
            
            # اختيار الأعمدة المطلوبة فقط
            df = df[required_columns]
            
        else:
         
            df = await provider.get_historicalcandl(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date
            )
        
        # تخزين في الكاش (انتهاء بعد ساعة)
        # NOTE: frames larger than 30k rows are NOT pushed to Redis — the
        # provider's disk (parquet) cache covers them; json.dumps of a year of
        # 1m candles (~100 MB) used to block the whole event loop for seconds.
        if use_cache and not df.empty and len(df) <= 30_000:
            try:
                await redis_client.set_cached(
                    cache_key,
                    df.to_dict('records'),
                    expire=3600
                )
            except Exception as e:
                logger.warning(f"Cache write error: {e}. Continuing without caching.")
        
        return df







    async def get_historical_last_version(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        start_date: datetime,
        end_date: datetime,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        الحصول على أحدث بيانات تاريخية (الاسم الصحيح للدالة)

        Canonical, correctly-spelled method. The legacy misspelled name
        `get_historicallastvirsion` remains as a deprecated alias below.
        """
        # Bugfix: the old cache key called start_date.isoformat() unguarded
        # (AttributeError when a caller passes None) — make it tolerant.
        start_iso = start_date.isoformat() if isinstance(start_date, datetime) else str(start_date)
        end_iso = end_date.isoformat() if isinstance(end_date, datetime) else str(end_date)
        cache_key = f"historical:{market}:{symbol}:{timeframe}:{start_iso}:{end_iso}"

        
        if use_cache:
            try:
                cached = await redis_client.get_cached(cache_key)
                if cached:
                    return await asyncio.to_thread(pd.DataFrame, cached)
            except Exception as e:
                logger.warning(f"Cache read error: {e}. Continuing without cache.")
        
        # تحديد المزود
        provider = self.providers.get(market)
        if not provider:
            raise ValueError(f"Unsupported market: {market}")
        


        if market == "stocks":
            # تحويل timeframe إلى تنسيق Yahoo Finance
            timeframe_map = {
                "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1h": "1h", "4h": "4h", "1d": "1d"
            }
            
            stock_timeframe = timeframe_map.get(timeframe, "1h")

            # Bugfix: `period` was referenced here but NEVER defined
            # (NameError crashed every stocks request). Derive it from the
            # requested window; fall back to a sensible default of "1y" when
            # the dates are missing/invalid. Yahoo uses start/end when both
            # are provided and `period` only as fallback.
            try:
                days_span = max((end_date - start_date).days, 1)
                period = f"{days_span}d"
            except (TypeError, AttributeError):
                period = "1y"

            history_kwargs = {"period": period}
            if isinstance(start_date, datetime) and isinstance(end_date, datetime):
                history_kwargs["start"] = start_date.strftime("%Y-%m-%d")
                history_kwargs["end"] = end_date.strftime("%Y-%m-%d")
            
            # الحصول على بيانات الأسهم باستخدام get_historical_data
            df = await provider.get_historical_data(
                symbol=symbol,
                timeframe=stock_timeframe,
                **history_kwargs
            )
            
            # التحقق من وجود البيانات
            if df.empty:
                raise ValueError(f"No historical data found for stock: {symbol}")
            
            # التأكد من وجود الأعمدة المطلوبة
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")
            
            # اختيار الأعمدة المطلوبة فقط
            df = df[required_columns]
            
        else:
         
            df = await provider.get_historicalcandl(
                symbol=symbol,
                timeframe=timeframe,
                start_date = start_date.astimezone(timezone.utc),
                end_date = end_date.astimezone(timezone.utc)

            )


            if df.empty:
                return df

            df['time'] = pd.to_datetime(df['time'], unit='ms', utc=True)
            df = df.set_index('time')

           


        # تخزين في الكاش (انتهاء بعد ساعة) — الأطر الكبيرة يغطيها كاش القرص في المزود
        if use_cache and not df.empty and len(df) <= 30_000:
            try:
                await redis_client.set_cached(
                    cache_key,
                    df.to_dict('records'),
                    expire=3600
                )
            except Exception as e:
                logger.warning(f"Cache write error: {e}. Continuing without caching.")
        
        return df
    






    async def get_historicallastvirsion(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        start_date: datetime,
        end_date: datetime,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        DEPRECATED (misspelled historical name) — kept only so existing callers
        (routers/strategies1.py, backtest/engine1.py) keep working.
        Use :meth:`get_historical_last_version` instead.
        """
        logger.warning(
            "get_historicallastvirsion() is deprecated (misspelled); "
            "use get_historical_last_version() instead"
        )
        return await self.get_historical_last_version(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            start_date=start_date,
            end_date=end_date,
            use_cache=use_cache,
        )

    async def get_data_with_indicators(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        indicators_config: List[Dict[str, Any]],
        days: int = 30,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        # الحصول على البيانات
        dataframe = await self.get_historical(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            days=days,
            use_cache=use_cache
        )
        
        if dataframe.empty:
            return {"error": "No data available"}
        
        # تنظيف DataFrame من قيم غير صالحة
        dataframe = clean_dataframe(dataframe)
        
        # تطبيق المؤشرات — CPU/pandas heavy: offload off the event loop
        # (bugfix: was executed directly inside this async path)
        indicator_results = await asyncio.to_thread(
            apply_indicators,
            dataframe=dataframe,
            indicators_config=indicators_config,
            use_cache=use_cache
        )
        
        # تحويل النتائج وتنظيفها
        indicators_dict = {}
        for name, result in indicator_results.items():
            if isinstance(result, dict):
                indicators_dict[name] = clean_dict(result)
            elif isinstance(result, pd.DataFrame):
                indicators_dict[name] = clean_dataframe(result).to_dict('records')
            else:
                # لو كانت قائمة أو أي نوع آخر
                indicators_dict[name] = result
        
        # تحويل الـ DataFrame النهائي إلى JSON-safe
        data_records = clean_dataframe(dataframe.reset_index()).to_dict('records')

        # استخراج تواريخ البداية/النهاية بأمان (قد يكون الـ index عددياً والتاريخ عموداً)
        def _iso(value):
            if value is None:
                return None
            if hasattr(value, "isoformat"):
                return value.isoformat()
            return str(value)

        first_ts = last_ts = None
        if len(dataframe) > 0:
            if isinstance(dataframe.index, pd.DatetimeIndex):
                first_ts, last_ts = dataframe.index[0], dataframe.index[-1]
            elif "time" in dataframe.columns:
                first_ts, last_ts = dataframe["time"].iloc[0], dataframe["time"].iloc[-1]
            else:
                first_ts, last_ts = dataframe.index[0], dataframe.index[-1]

        return {
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "data": data_records,
            "indicators": indicators_dict,
            "metadata": {
                "rows": len(dataframe),
                "start_date": _iso(first_ts),
                "end_date": _iso(last_ts)
            }
        }

    async def get_data_with_indicators_async(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        indicators_config: List[Dict[str, Any]],
        days: int = 30,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Explicitly-named async wrapper of :meth:`get_data_with_indicators`.
        The CPU/pandas indicator pipeline is offloaded to a worker thread
        inside, so calling this never blocks the event loop.
        """
        return await self.get_data_with_indicators(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            indicators_config=indicators_config,
            days=days,
            use_cache=use_cache,
        )


    async def get_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        limit: int = 50
    ) -> pd.DataFrame:
        """
        إرجاع آخر N شموع فقط
        تُستخدم للـ Signals و WebSocket
        """

        # نجلب أيام كافية لضمان عدد الشموع
        df = await self.get_historical(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            days=5,
            use_cache=False
        )



        if df.empty:
            raise ValueError("No market data available")

        if "datetime" in df.columns:
            df = df.rename(columns={"datetime": "time"})
        elif "timestamp" in df.columns:
            df = df.rename(columns={"timestamp": "time"})


        return df.tail(limit)



    async def get_trading_signals(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        indicators_config: List[Dict[str, Any]],
        days: int = 30
    ) -> Dict[str, Any]:
        """
        الحصول على إشارات التداول من المؤشرات
        
        Args:
            symbol: الرمز
            timeframe: الإطار الزمني
            market: السوق
            indicators_config: تكوينات المؤشرات
            days: عدد الأيام
            
        Returns:
            Dict: إشارات التداول
        """
        # الحصول على البيانات
        dataframe = await self.get_historical(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            days=days
        )
        
        if dataframe.empty:
            return {"error": "No data available"}
        
        # حساب إشارات التداول — CPU/pandas heavy: offload off the event loop
        signals = await asyncio.to_thread(
            calculate_trading_signals,
            dataframe=dataframe,
            indicator_configs=indicators_config
        )
        
        # إضافة معلومات السوق
        signals["symbol"] = symbol
        signals["market"] = market
        signals["timeframe"] = timeframe
        signals["current_price"] = float(dataframe['close'].iloc[-1]) if len(dataframe) > 0 else 0
        
        return signals    
    


def clean_value(val):
    if isinstance(val, float):
        if math.isinf(val) or math.isnan(val):
            return None
    return val

def clean_dict(d: dict):
    return {k: clean_value(v) for k, v in d.items()}

def clean_dataframe(df: pd.DataFrame):
    # استبدال inf و -inf و NaN بـ None
    return df.replace([float('inf'), float('-inf')], None).where(pd.notnull(df), None)



