# \app\core\live_stream.py
"""
نظام البث الحي المركزي.

- كريبتو: بث kline حقيقي عبر binance_kline_stream (WebSocket أصلي من Binance).
- أسهم: دفع حي عبر WS الباك اند — بولينج داخلي لسعر Yahoo كل ~5 ثوان ودفع
  فوري للمشتركين عند أي تغيّر (الفرونت يستقبل push حقيقيًا بلا polling).
- ticker stream العام (!ticker@arr) يبقى لنظرة السوق فقط وبإعادة اتصال مرنة.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Set, Optional, Callable, Any

from app.providers.binance_market_stream import stream_all_market
from app.providers.binance_kline_stream import binance_kline_stream

logger = logging.getLogger(__name__)


class LiveStreamManager:
    """مدير البث الحي المركزي"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _now_ms(self) -> int:
        return int(datetime.utcnow().timestamp() * 1000)

    def __init__(self):
        if self._initialized:
            return

        self._stream_task = None
        self._subscribers: Dict[str, Set[Callable]] = {}  # symbol -> [callbacks]
        self._active_streams: Set[str] = set()
        self._stream_data: Dict[str, Dict] = {}  # Latest data per symbol
        self._lock = asyncio.Lock()
        self._initialized = True

        # --- أسهم: دفع حي عبر WS ---
        self._stock_subscribers: Dict[str, Set[Callable]] = {}
        self._stock_tasks: Dict[str, asyncio.Task] = {}
        self._stock_last: Dict[str, Dict] = {}       # آخر tick مُرسل لكل رمز
        self._stock_cum_volume: Dict[str, float] = {}  # حجم اليوم التراكمي (لحساب الدلتا)
        self._stock_provider = None                  # USStockProvider كسول

        logger.info("✅ LiveStreamManager initialized")

    # ------------------------------------------------------------------
    # كريبتو: kline حقيقي
    # ------------------------------------------------------------------
    async def subscribe_kline(self, symbol: str, timeframe: str, callback: Callable):
        """اشتراك بث kline حقيقي من Binance لكل (رمز, فريم)."""
        await binance_kline_stream.subscribe(symbol, timeframe, callback)

    async def unsubscribe_kline(self, symbol: str, timeframe: str, callback: Callable):
        await binance_kline_stream.unsubscribe(symbol, timeframe, callback)

    # ------------------------------------------------------------------
    # أسهم: دفع حي عبر WS الباك اند
    # ------------------------------------------------------------------
    def _get_stock_provider(self):
        if self._stock_provider is None:
            from app.providers.us_stock_provider import USStockProvider
            self._stock_provider = USStockProvider(use_alpha_vantage=False)
        return self._stock_provider

    async def subscribe_stock(self, symbol: str, callback: Callable):
        """اشتراك دفع حي لسهم — يبدأ مهمة بولينج داخلية تدفع عبر WS."""
        symbol_u = symbol.upper()
        async with self._lock:
            first = symbol_u not in self._stock_subscribers or not self._stock_subscribers[symbol_u]
            self._stock_subscribers.setdefault(symbol_u, set()).add(callback)
            if first:
                task = asyncio.create_task(self._stock_push_loop(symbol_u))
                self._stock_tasks[symbol_u] = task
                logger.info(f"🟢 Stock live push started: {symbol_u}")

    async def unsubscribe_stock(self, symbol: str, callback: Callable):
        symbol_u = symbol.upper()
        async with self._lock:
            cbs = self._stock_subscribers.get(symbol_u)
            if cbs and callback in cbs:
                cbs.discard(callback)
            if cbs is not None and not cbs:
                self._stock_subscribers.pop(symbol_u, None)
                task = self._stock_tasks.pop(symbol_u, None)
                if task:
                    task.cancel()
                self._stock_last.pop(symbol_u, None)
                self._stock_cum_volume.pop(symbol_u, None)
                logger.info(f"🔴 Stock live push stopped: {symbol_u}")

    async def _stock_push_loop(self, symbol: str):
        """بولينج داخلي لسعر السهم + دفع فوري عند التغيّر (push حقيقي للعميل)."""
        provider = self._get_stock_provider()
        poll_seconds = 5.0
        heartbeat_seconds = 30.0
        last_push = 0.0
        consecutive_errors = 0

        while True:
            try:
                quote = await provider.get_live_price(symbol)
                now = self._now_ms()

                if quote and quote.get("price"):
                    price = float(quote["price"])
                    cum_v = float(quote.get("volume") or 0)
                    prev_cum = self._stock_cum_volume.get(symbol)
                    vol_delta = 0.0
                    if prev_cum is not None and cum_v >= prev_cum:
                        vol_delta = cum_v - prev_cum
                    self._stock_cum_volume[symbol] = cum_v

                    last = self._stock_last.get(symbol)
                    changed = (
                        last is None
                        or abs(float(last.get("price", 0)) - price) > 1e-9
                        or vol_delta > 0
                    )
                    # دفع عند التغيّر + نبضة كل 30 ثانية للحفاظ على الحيوية
                    if changed or (now - last_push) >= heartbeat_seconds * 1000:
                        tick = {
                            "symbol": symbol,
                            "price": price,
                            "volume": cum_v,
                            "volume_delta": vol_delta,
                            "change": float(quote.get("change") or 0),
                            "change_percent": float(quote.get("change_percent") or 0),
                            "bid": 0.0,
                            "ask": 0.0,
                            "time": now,
                            # ✅ الجولة 4: حالة السوق مع كل دفعة (open/closed/pre_market/...)
                            "market_status": str(quote.get("market_status") or "closed"),
                        }
                        self._stock_last[symbol] = tick
                        self._stream_data[symbol] = tick
                        await self._notify_stock_subscribers(symbol, tick)
                        last_push = now
                consecutive_errors = 0
            except asyncio.CancelledError:
                logger.info(f"🔴 Stock push cancelled: {symbol}")
                raise
            except Exception as e:  # noqa: BLE001
                consecutive_errors += 1
                if consecutive_errors <= 3 or consecutive_errors % 12 == 0:
                    logger.warning(f"⚠️ Stock push error [{symbol}]: {e}")
                await asyncio.sleep(min(30.0, poll_seconds * consecutive_errors))
                continue

            await asyncio.sleep(poll_seconds)

    async def _notify_stock_subscribers(self, symbol: str, data: Dict):
        callbacks = list(self._stock_subscribers.get(symbol, set()))
        if not callbacks:
            return
        results = await asyncio.gather(*(cb(data) for cb in callbacks),
                                       return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"❌ Error in stock price callback: {res}")

    # ------------------------------------------------------------------
    # ticker stream العام (لنظرة السوق — مستقل عن مسار الشارت)
    # ------------------------------------------------------------------
    async def start(self):
        """بدء النظام الرئيسي للبث الحي"""
        if self._stream_task is None or self._stream_task.done():
            self._stream_task = asyncio.create_task(self._global_stream_loop())
            logger.info("🚀 Global live stream started")

    async def stop(self):
        """إيقاف البث الحي"""
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
            logger.info("🛑 Global live stream stopped")

    async def subscribe(self, symbol: str, callback: Callable):
        """اشتراك في رمز معين (ticker العام — نظرة السوق)"""
        async with self._lock:
            if symbol not in self._subscribers:
                self._subscribers[symbol] = set()
            self._subscribers[symbol].add(callback)

            # إضافة إلى البث النشط
            self._active_streams.add(symbol)
            logger.debug(f"➕ Subscribed to {symbol}, total subscribers: {len(self._subscribers[symbol])}")

    async def unsubscribe(self, symbol: str, callback: Callable):
        """إلغاء الاشتراك"""
        async with self._lock:
            if symbol in self._subscribers and callback in self._subscribers[symbol]:
                self._subscribers[symbol].remove(callback)

                if not self._subscribers[symbol]:
                    del self._subscribers[symbol]

                # تحديث البث النشط
                await self._update_active_streams()
                logger.debug(f"➖ Unsubscribed from {symbol}")

    async def _update_active_streams(self):
        """تحديث الرموز النشطة بناءً على المشتركين"""
        self._active_streams = set(self._subscribers.keys())
        logger.debug(f"📊 Active streams updated: {len(self._active_streams)} symbols")

    async def _global_stream_loop(self):
        """الحلقة الرئيسية لبث ticker العام — مرنة: مهلة اتصال + إعادة محاولة."""
        logger.info("🔄 Starting global stream loop...")
        stall_count = 0

        while True:
            try:
                # حماية من التعليق الأبدي عند الاتصال (شبكة/حجب مؤقت):
                # ✅ الجولة 6.5: المهلة 45 ثانية — تمنح المولّد الداخلي فرصة
                # محاولتَي WS (12ث لكل رابط) ثم تفعيل وضع REST المضمون
                # (~2ث) قبل أي إلغاء خارجي. الـwatchdog الداخلي هو الفعّال
                # وهذا مجرد شبكة أمان أخيرة.
                from app.providers import binance_market_stream as _bms
                first = asyncio.ensure_future(self._consume_ticker_until_error())
                done, _ = await asyncio.wait({first}, timeout=45)
                if first not in done:
                    first.cancel()
                    stall_count += 1
                    backoff = min(30.0, 5.0 * (2 ** min(stall_count - 1, 3)))
                    logger.warning(
                        "⚠️ Ticker WS stalled (no first message in 45s, mode=%s) — retrying "
                        "with endpoint=%s (open_ok=%s, cycle=%d, backoff=%.0fs)",
                        getattr(_bms, "mode", "?"), _bms.last_endpoint or "?",
                        _bms.last_open_ok, stall_count, backoff)
                    await asyncio.sleep(backoff)
                    continue
                # انتهى المولد (خطأ/انقطاع) — إعادة محاولة بعد مهلة قصيرة
                stall_count = 0
                try:
                    first.result()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.error(f"⚠️ Ticker stream ended: {e}")
                await asyncio.sleep(3)

            except asyncio.CancelledError:
                logger.info("🔴 Global stream cancelled")
                break
            except Exception as e:  # noqa: BLE001
                logger.error(f"⚠️ Error in global stream: {e}")
                await asyncio.sleep(5)

    async def _consume_ticker_until_error(self):
        async for market_data in stream_all_market():
            if not market_data or "data" not in market_data:
                continue

            # معالجة كل عنصر في البيانات
            for item in market_data["data"]:
                symbol = item.get("symbol")
                if not symbol:
                    continue

                # تحديث أحدث البيانات
                self._stream_data[symbol] = {
                    "price": float(item.get("price", 0)),
                    "volume": float(item.get("volume", 0)),
                    "time": self._now_ms(),
                    "bid": float(item.get("bid", 0)),
                    "ask": float(item.get("ask", 0)),
                    "change": float(item.get("change24h", 0)),
                }

                # إرسال للمشتركين
                await self._notify_subscribers(symbol, self._stream_data[symbol])

            # تهدئة خفيفة لمنع استهلاك الـ CPU العالي مع مصفوفة السوق الكاملة
            await asyncio.sleep(0.05)

    async def _notify_subscribers(self, symbol: str, data: Dict):
        """إرسال البيانات للمشتركين"""
        if symbol not in self._subscribers:
            return

        callbacks = list(self._subscribers[symbol])  # نسخة للاستخدام

        # تشغيل جميع الـ callbacks بشكل متوازي
        tasks = [callback(data) for callback in callbacks]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.error(f"❌ Error in price update callback: {res}")

    async def get_latest_price(self, symbol: str) -> Optional[Dict]:
        """الحصول على آخر سعر لرمز معين"""
        return self._stream_data.get(symbol)

    def get_active_symbols(self) -> List[str]:
        """الحصول على الرموز النشطة"""
        return list(self._active_streams)


# المثيل العام
live_stream_manager = LiveStreamManager()
