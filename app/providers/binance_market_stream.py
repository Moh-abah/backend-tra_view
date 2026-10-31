# app/providers/binance_market_stream.py
"""
الجولة 6.5 — بث نظرة السوق: WS مرن + سقوط تلقائي لوضع REST المضمون.

التاريخ المُثبت بالقياس الحي (سجلات الإنتاج 2026-10-30/31):
1) إطارات !ticker@arr الكاملة (~1-2MB/ث) تعلق صامتة: الاتصال يُفتح بنجاح
   لكن **أول إطار لا يصل أبداً** — حتى !miniTicker@arr (إطارات ~14KB) علِقت
   على شبكة خادم الإنتاج رغم نجاحها من شبكات خارجية (أول إطار ~1.3ث).
   في المقابل: REST على api.binance.com يعمل على الإنتاج **بلا أي انقطاع**
   (دليل: نقطة /candles تجلب شموعاً حقيقية في كل طلب).
2) الدوران بين روابط WS كان يحدث فقط عند إعادة إنشاء المولّد — بينما راوتر
   /ws/market-overview يستهلك مولّداً واحداً بـ async for فيعلق للأبد.

الحل النهائي هنا (ثلاث طبقات):
- الطبقة 1: Watchdog لأول إطار (12ث) داخل المولّد نفسه — أي رابط لا يرسل
  إطاراً يُستبدل تلقائياً بالرابط التالي بلا تدخل من أي مستهلك.
- الطبقة 2: بعد فشل محاولتَي WS متتاليتين في تسليم أول إطار → تفعيل وضع
  **REST fallback دائم**: بولينج /api/v3/ticker/24hr كل 7 ثوانٍ وإعادة نفس
  شكل الرسالة حرفياً — نظرة السوق تعمل مهما كانت شبكة WS محجوبة.
- الطبقة 3: شكل الرسالة الثابت حرفياً في الوضعين — عقد الفرونت لا يُمَس:
  {type, timestamp, time, data: [{symbol, price, change24h, volume}]}
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import AsyncIterator, Dict, List

import aiohttp

logger = logging.getLogger(__name__)

# روابط WS بالترتيب — miniTicker أولاً (إطارات صغيرة). الدوران داخلي عند الفشل.
WS_ENDPOINTS: List[str] = [
    "wss://data-stream.binance.vision/ws/!miniTicker@arr",
    "wss://data-stream.binance.vision:9443/ws/!miniTicker@arr",
    "wss://stream.binance.com:443/ws/!miniTicker@arr",
    "wss://stream.binance.com:9443/ws/!miniTicker@arr",
    "wss://data-stream.binance.vision/ws/!ticker@arr",
    "wss://data-stream.binance.vision:9443/ws/!ticker@arr",
    "wss://stream.binance.com:443/ws/!ticker@arr",
    "wss://stream.binance.com:9443/ws/!ticker@arr",
]

# REST fallback — القناة المثبتة عملها على الإنتاج (نفس مصدر نقطة الشموع)
REST_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"
REST_POLL_S = 7.0            # نفس إيقاع MARKET_OVERVIEW_INTERVAL في الراوتر
REST_HTTP_TIMEOUT_S = 20.0
REST_ERROR_SLEEP_S = 3.0

OPEN_TIMEOUT_S = 10.0            # فشل سريع عند تعذر فتح WS
FIRST_FRAME_TIMEOUT_S = 12.0     # ⭐ أول إطار خلال 12ث وإلا ندير الرابط
RETRY_SLEEP_S = 2.0
WS_FAILURES_BEFORE_REST = 2      # محاولتا WS فاشلتان متتاليتان → وضع REST دائم

_endpoint_idx = 0
_ws_failures = 0                 # محاولات WS متتالية لم تسلّم أول إطار
last_endpoint: str = ""          # آخر رابط حُاول — يظهر في سجلات live_stream
last_open_ok: bool = False       # هل نجح فتح آخر اتصال فعلاً؟
mode: str = "ws"                 # "ws" أو "rest_fallback" — للتشخيص


def current_endpoint() -> str:
    """الرابط المرشح التالي — يُحرّك المؤشر عند كل محاولة."""
    global _endpoint_idx
    url = WS_ENDPOINTS[_endpoint_idx % len(WS_ENDPOINTS)]
    _endpoint_idx += 1
    return url


def _pct_from_ohl(item: Dict) -> float:
    """تقدير تغير 24 ساعة من open→close (لـ miniTicker الذي لا يرسل P)."""
    try:
        o = float(item.get("o") or 0)
        c = float(item.get("c") or 0)
        return round((c - o) / o * 100, 4) if o > 0 else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _payload(rows: List[Dict]) -> Dict:
    """شكل الرسالة الثابت للفرونت (عقد لا يُمَس) — مستخدم في الوضعين."""
    now = datetime.utcnow()
    return {
        "type": "market_overview",
        # Both keys are provided so every consumer (ISO-string or epoch-ms) works.
        "timestamp": now.isoformat(),
        "time": int(now.timestamp() * 1000),
        "data": rows,
    }


def _rows_from_ws_frame(data, is_mini: bool) -> List[Dict]:
    rows: List[Dict] = []
    for d in data if isinstance(data, list) else []:
        try:
            rows.append({
                "symbol": d["s"],
                "price": float(d["c"]),
                "change24h": _pct_from_ohl(d) if is_mini else float(d.get("P", 0)),
                "volume": float(d["v"]),
            })
        except Exception:  # noqa: BLE001 — عنصر تالف لا يقتل الدفعة
            continue
    return rows


def _rows_from_rest(items) -> List[Dict]:
    """تحويل استجابة /api/v3/ticker/24hr إلى نفس صفوف WS حرفياً.
    volume: حجم الأصل الأساسي (نفس حقل v في WS)، change24h: نسبة جاهزة من Binance."""
    rows: List[Dict] = []
    for d in items if isinstance(items, list) else []:
        try:
            rows.append({
                "symbol": d["symbol"],
                "price": float(d.get("lastPrice") or 0),
                "change24h": float(d.get("priceChangePercent") or 0),
                "volume": float(d.get("volume") or 0),
            })
        except Exception:  # noqa: BLE001
            continue
    return rows


async def _rest_fallback_loop() -> AsyncIterator[Dict]:
    """وضع REST الدائم: بولينج تقرير 24 ساعة الكامل — نفس شكل رسائل WS حرفياً."""
    global mode
    mode = "rest_fallback"
    logger.warning(
        "🛟 Market ticker: WS array streams blocked on this network — "
        "activating PERMANENT REST fallback (%s every %.0fs)", REST_TICKER_URL, REST_POLL_S)
    timeout = aiohttp.ClientTimeout(total=REST_HTTP_TIMEOUT_S)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                t0 = time.monotonic()
                async with session.get(REST_TICKER_URL) as resp:
                    resp.raise_for_status()
                    items = await resp.json(content_type=None)
                rows = _rows_from_rest(items)
                if rows:
                    logger.info(
                        "🛟 Market ticker REST frame: %d symbols in %.2fs",
                        len(rows), time.monotonic() - t0)
                    yield _payload(rows)
                else:
                    logger.warning("🛟 Market ticker REST frame empty — retrying")
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — نبقى في وضع REST مهما حدث
                logger.error("🛟 Market ticker REST poll failed: %s — retry in %.0fs",
                             e, REST_ERROR_SLEEP_S)
                await asyncio.sleep(REST_ERROR_SLEEP_S)
                continue
            await asyncio.sleep(REST_POLL_S)


async def stream_all_market() -> AsyncIterator[Dict]:
    """مولّد بث نظرة السوق — WS مرن ثم REST مضمون، بلا تعليق أبدي أبداً.

    الضمانات:
    - أول إطار خلال FIRST_FRAME_TIMEOUT_S وإلا ننتقل للرابط التالي تلقائياً.
    - بعد WS_FAILURES_BEFORE_REST محاولات بلا إطار → وضع REST الدائم
      (نفس شكل الرسائل — القناة المثبتة عملها على شبكة الإنتاج).
    - الانقطاع بعد بث ناجح → محاولة الرابط التالي (لا نعيد الرابط الذي انقطع).
    """
    global last_endpoint, last_open_ok, _ws_failures, mode
    while True:
        # ---- وضع REST بعد إثبات حجب WS على هذه الشبكة ----
        if _ws_failures >= WS_FAILURES_BEFORE_REST:
            async for payload in _rest_fallback_loop():
                yield payload
            return  # لا يُصل أبداً — الحلقة الداخلية دائمة

        # ---- محاولة WS واحدة ----
        url = current_endpoint()
        last_endpoint = url
        last_open_ok = False
        mode = "ws"
        is_mini = "miniTicker" in url
        logger.info("🔌 Connecting market ticker WS: %s", url)
        try:
            async with websockets_connect(url) as ws:
                last_open_ok = True
                logger.info("🟢 Market ticker WS connected: %s", url)
                try:
                    first_raw = await asyncio.wait_for(
                        ws.recv(), timeout=FIRST_FRAME_TIMEOUT_S)
                except asyncio.TimeoutError:
                    _ws_failures += 1
                    logger.warning(
                        "⚠️ Market ticker WS no first frame in %.0fs [%s] — "
                        "rotating endpoint (%d/%d)",
                        FIRST_FRAME_TIMEOUT_S, url,
                        _ws_failures, WS_FAILURES_BEFORE_REST)
                    await asyncio.sleep(RETRY_SLEEP_S)
                    continue
                first_rows = _rows_from_ws_frame(_safe_json(first_raw), is_mini)
                if first_rows:
                    _ws_failures = 0
                    logger.info("📡 Market ticker first frame: %d symbols (%.0fKB)",
                                len(first_rows), len(first_raw) / 1024)
                    yield _payload(first_rows)
                async for raw in ws:
                    try:
                        rows = _rows_from_ws_frame(_safe_json(raw), is_mini)
                    except Exception:  # noqa: BLE001 — إطار تالف لا يقتل البث
                        continue
                    if rows:
                        yield _payload(rows)
                logger.warning("⚠️ Market ticker WS closed by peer [%s] — rotating", url)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — فشل فتح/انقطاع مبكر
            _ws_failures += 1
            logger.error("⚠️ Market ticker WS ended [%s]: %s (%d/%d)",
                         url, e, _ws_failures, WS_FAILURES_BEFORE_REST)
            await asyncio.sleep(RETRY_SLEEP_S)


def _safe_json(raw: str):
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def websockets_connect(url: str):
    """غلاف websockets.connect بالإعدادات المثبتة — دالة عادية تُعيد
    كائن Connect (async context manager جاهز) لا coroutine."""
    import websockets
    return websockets.connect(
        url,
        open_timeout=OPEN_TIMEOUT_S,
        ping_interval=20,
        ping_timeout=20,
        max_size=None,          # إطارات !ticker@arr تتجاوز 1MB — بلا حد
        compression=None,       # تقليل زمن المعالجة لحجم البيانات الكبير
    )
