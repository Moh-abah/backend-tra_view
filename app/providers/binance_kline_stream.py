# app/providers/binance_kline_stream.py
"""
بث Kline حقيقي من Binance (WebSocket أصلي) — Multiplexer مركزي.

المعمارية:
- اتصال WS واحد إلى /stream مع اشتراك ديناميكي (SUBSCRIBE/UNSUBSCRIBE) لكل
  زوج (رمز, فريم) — نفس بروتوكول TradingView backends.
- failover تلقائي بين نقاط النهاية: stream.binance.com:9443 → :443 →
  data-stream.binance.vision:9443 → data-stream.binance.vision.
- إعادة اتصال تلقائية بتراجع أُسّي (backoff) مع إعادة إرسال كل الاشتراكات.
- عدّاد مراجع لكل stream: أول مشترك يشغّل SUBSCRIBE، وآخر مغادرة تشغّل
  UNSUBSCRIBE — بلا تسريبات اتصالات.

الأحداث الحقيقية من Binance kline:
  {"stream":"btcusdt@kline_1m","data":{"e":"kline","E":...,"s":"BTCUSDT",
   "k":{"t":open_ms,"T":close_ms,"s":sym,"i":"1m","o":..,"h":..,"l":..,
        "c":..,"v":vol,"x":false|true,"q":..,"n":..}}}
x=true تعني شمعة مغلقة رسميًا (المصدر الوحيد الموثوق لإغلاق الشموع).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

import websockets

logger = logging.getLogger(__name__)

# نقاط النهاية بالترتيب — نديرها دوريًا عند تكرار الفشل
WS_ENDPOINTS: List[str] = [
    "wss://stream.binance.com:9443/stream",
    "wss://stream.binance.com:443/stream",
    "wss://data-stream.binance.vision:9443/stream",
    "wss://data-stream.binance.vision/stream",
]

OPEN_TIMEOUT_S = 10.0
PING_INTERVAL_S = 20.0
PING_TIMEOUT_S = 20.0
BACKOFF_START_S = 1.0
BACKOFF_MAX_S = 20.0
SUBSCRIBE_BATCH = 80          # حد Binance الآمن لكل رسالة SUBSCRIBE
ENDPOINT_ROTATE_AFTER = 3     # نقلة لنقطة أخرى بعد 3 فشل متتالٍ

KlineCallback = Callable[[Dict[str, Any]], Awaitable[None]]


class BinanceKlineStream:
    """Multiplexer واحد لكل بثوث kline في العملية."""

    _instance: Optional["BinanceKlineStream"] = None

    def __new__(cls) -> "BinanceKlineStream":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # stream_name (btcusdt@kline_1m) -> {"refs": int, "key": (SYMBOL, TF)}
        self._streams: Dict[str, Dict[str, Any]] = {}
        # (SYMBOL, TF) -> set(callbacks)
        self._callbacks: Dict[Tuple[str, str], Set[KlineCallback]] = {}
        self._ws: Optional[Any] = None
        self._task: Optional[asyncio.Task] = None
        self._subscribed: Set[str] = set()       # streams المفعّلة على الاتصال الحالي
        self._pending: Set[str] = set()          # بانتظار SUBSCRIBE بعد الاتصال
        self._ws_id = 0                          # معرّف طلب متزايد
        self._lock = asyncio.Lock()
        self._stopping = False

    # ------------------------------------------------------------------ API
    async def subscribe(self, symbol: str, timeframe: str, callback: KlineCallback) -> None:
        """إضافة مشترك على kline stream حقيقي لـ (رمز, فريم)."""
        symbol_u = symbol.upper()
        tf = timeframe.lower()
        key = (symbol_u, tf)
        stream_name = f"{symbol_u.lower()}@kline_{tf}"

        async with self._lock:
            self._callbacks.setdefault(key, set()).add(callback)
            info = self._streams.get(stream_name)
            if info is None:
                self._streams[stream_name] = {"refs": 1, "key": key}
                self._pending.add(stream_name)
                logger.info(f"🟢 kline stream requested: {stream_name} (first subscriber)")
            else:
                info["refs"] += 1

            self._ensure_task()

        # إن كان الاتصال حيًا، أرسل SUBSCRIBE فورًا خارج القفل
        await self._flush_pending()

    async def unsubscribe(self, symbol: str, timeframe: str, callback: KlineCallback) -> None:
        symbol_u = symbol.upper()
        tf = timeframe.lower()
        key = (symbol_u, tf)
        stream_name = f"{symbol_u.lower()}@kline_{tf}"

        async with self._lock:
            cbs = self._callbacks.get(key)
            if cbs and callback in cbs:
                cbs.discard(callback)
            if cbs is not None and not cbs:
                self._callbacks.pop(key, None)

            info = self._streams.get(stream_name)
            if info is None:
                return
            info["refs"] = max(0, info["refs"] - 1)
            if info["refs"] == 0:
                self._streams.pop(stream_name, None)
                if stream_name in self._pending:
                    self._pending.discard(stream_name)
                elif stream_name in self._subscribed:
                    await self._send_unsubscribe_locked([stream_name])
                    logger.info(f"🔴 kline stream released: {stream_name} (no subscribers)")

    def stats(self) -> Dict[str, Any]:
        return {
            "connected": self._ws is not None,
            "streams": {name: info["refs"] for name, info in self._streams.items()},
            "pending": sorted(self._pending),
        }

    # -------------------------------------------------------------- internals
    def _ensure_task(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run_loop())
            logger.info("🚀 BinanceKlineStream loop started")

    async def _flush_pending(self) -> None:
        """إرسال SUBSCRIBE للقوائم المعلّقة إن كان الاتصال حيًا."""
        async with self._lock:
            if self._ws is None or not self._pending:
                return
            batch = sorted(self._pending)
            self._pending.clear()
            await self._send_subscribe_locked(batch)

    async def _send_subscribe_locked(self, names: List[str]) -> None:
        if self._ws is None:
            self._pending.update(names)
            return
        try:
            for i in range(0, len(names), SUBSCRIBE_BATCH):
                self._ws_id += 1
                await self._ws.send(json.dumps({
                    "method": "SUBSCRIBE",
                    "params": names[i:i + SUBSCRIBE_BATCH],
                    "id": self._ws_id,
                }))
            self._subscribed.update(names)
            logger.info(f"📡 SUBSCRIBE sent: {len(names)} streams (total {len(self._subscribed)})")
        except Exception as e:  # noqa: BLE001 — الاتصال سيسقط ويُعاد الاشتراك
            logger.warning(f"SUBSCRIBE send failed ({e}) — requeued")
            self._pending.update(names)

    async def _send_unsubscribe_locked(self, names: List[str]) -> None:
        if self._ws is None:
            self._subscribed.difference_update(names)
            return
        try:
            for i in range(0, len(names), SUBSCRIBE_BATCH):
                self._ws_id += 1
                await self._ws.send(json.dumps({
                    "method": "UNSUBSCRIBE",
                    "params": names[i:i + SUBSCRIBE_BATCH],
                    "id": self._ws_id,
                }))
            self._subscribed.difference_update(names)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"UNSUBSCRIBE send failed ({e})")
            self._subscribed.difference_update(names)

    async def _run_loop(self) -> None:
        """حلقة الاتصال الرئيسية: اتصال → اشتراك → استهلاك → إعادة اتصال."""
        endpoint_idx = 0
        consecutive_failures = 0
        backoff = BACKOFF_START_S

        while not self._stopping:
            url = WS_ENDPOINTS[endpoint_idx % len(WS_ENDPOINTS)]
            try:
                logger.info(f"🔌 Connecting kline WS: {url}")
                async with websockets.connect(
                    url,
                    open_timeout=OPEN_TIMEOUT_S,
                    ping_interval=PING_INTERVAL_S,
                    ping_timeout=PING_TIMEOUT_S,
                    max_size=2 ** 22,
                ) as ws:
                    async with self._lock:
                        self._ws = ws
                        # إعادة إرسال كل الاشتراكات النشطة على الاتصال الجديد
                        fresh = sorted(set(self._streams.keys()))
                        self._subscribed.clear()
                        if fresh:
                            await self._send_subscribe_locked(fresh)
                        # + المعلّقة الجديدة التي وصلت أثناء الانقطاع
                        if self._pending:
                            batch = sorted(self._pending)
                            self._pending.clear()
                            await self._send_subscribe_locked(batch)
                    backoff = BACKOFF_START_S
                    consecutive_failures = 0

                    async for raw in ws:
                        await self._dispatch_raw(raw)

            except asyncio.CancelledError:
                logger.info("🔴 BinanceKlineStream loop cancelled")
                raise
            except Exception as e:  # noqa: BLE001
                consecutive_failures += 1
                if consecutive_failures % ENDPOINT_ROTATE_AFTER == 0:
                    endpoint_idx += 1
                    logger.warning(
                        f"🔁 Rotating kline WS endpoint (failures={consecutive_failures})")
                logger.warning(f"⚠️ kline WS error: {type(e).__name__}: {e}")
            finally:
                async with self._lock:
                    self._ws = None
                    self._subscribed.clear()

            if self._stopping:
                break
            await asyncio.sleep(backoff)
            backoff = min(BACKOFF_MAX_S, backoff * 2)

    async def _dispatch_raw(self, raw: Any) -> None:
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            return
        data = msg.get("data") if isinstance(msg, dict) else None
        if not isinstance(data, dict) or data.get("e") != "kline":
            return  # ack أو أحداث غير kline
        k = data.get("k") or {}
        symbol = data.get("s")
        tf = k.get("i")
        if not symbol or not tf:
            return

        event = {
            "symbol": symbol,
            "timeframe": tf,
            "time": int(k.get("t", 0)),          # فتح الشمعة ms
            "close_time": int(k.get("T", 0)),    # إغلاقها ms
            "open": float(k.get("o", 0) or 0),
            "high": float(k.get("h", 0) or 0),
            "low": float(k.get("l", 0) or 0),
            "close": float(k.get("c", 0) or 0),
            "volume": float(k.get("v", 0) or 0),
            "quote_volume": float(k.get("q", 0) or 0),
            "trades": int(k.get("n", 0) or 0),
            "is_closed": bool(k.get("x", False)),
            "event_time": int(data.get("E", 0)) or int(time.time() * 1000),
        }

        callbacks = self._callbacks.get((symbol, tf.lower()))
        if not callbacks:
            return
        results = await asyncio.gather(
            *(cb(event) for cb in list(callbacks)), return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"❌ kline callback error: {res}")


# المثيل العام (singleton)
binance_kline_stream = BinanceKlineStream()
