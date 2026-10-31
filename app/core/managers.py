# \app\core\managers.py
"""
مدير الشارت المركزي مع دعم البث الحي والتحديثات
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
from app.core.live_stream import live_stream_manager
from app.core.indicators import indicator_manager
from app.providers.binance_provider import BinanceProvider
from app.utils.dataframe_utils import (
    align_time_ms,
    composite_base_tf,
    is_composite_tf,
    resample_candles,
    sanitize_candle_time_ms,
)

logger = logging.getLogger(__name__)


def indicator_id(indicator_dict: Any) -> str:
    """معرّف موحد ومستقر للمؤشر (name + hash المعاملات) — يُصدَّر لكل الرسائل.
    نفس الخوارزمية في كل الخادم حتى تبقى المعرّفات متطابقة عبر الجلسات."""
    if not isinstance(indicator_dict, dict):
        return f"indicator_{uuid4().hex[:8]}"
    name = str(indicator_dict.get("name") or "unknown")
    try:
        params_json = json.dumps(indicator_dict.get("params") or {},
                                 sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        params_json = ""
    digest = hashlib.md5(f"{name}:{params_json}".encode()).hexdigest()[:8]
    return f"{name}_{digest}"


class Timeframe(Enum):
    """الإطارات الزمنية المدعومة (بما في ذلك الفريمات المخصصة والمدمجة)"""
    # الثواني
    SEC30 = "30s"
    
    # الدقائق
    MIN1 = "1m"
    MIN2 = "2m"
    MIN3 = "3m"
    MIN5 = "5m"
    MIN10 = "10m"
    MIN15 = "15m"
    MIN30 = "30m"
    
    # الساعات
    HOUR1 = "1h"
    HOUR2 = "2h"
    HOUR3 = "3h"
    HOUR4 = "4h"
    HOUR6 = "6h"
    HOUR8 = "8h"  # مدعوم من بايننس مباشرة
    HOUR12 = "12h"
    
    # الأيام
    DAY1 = "1d"
    DAY2 = "2d"
    DAY3 = "3d"
    
    # الأسابيع
    WEEK1 = "1w"
    WEEK2 = "2w"
    
    # الشهور (لاحظ استخدام M كبير لتمييز الشهر عن الدقيقة)
    MONTH1 = "1M"



@dataclass
class ChartState:
    """حالة الشارت"""
    symbol: str
    timeframe: str
    candles: List[Dict] = field(default_factory=list)
    live_candle: Optional[Dict] = None
    indicators: List[Dict] = field(default_factory=list)
    last_update: datetime = field(default_factory=datetime.utcnow)
    subscribers: Set[str] = field(default_factory=set)  # Connection IDs
    on_close_callbacks: List[Callable] = field(default_factory=list)

    price_handler: Optional[Callable] = None
    indicators_results: Dict = field(default_factory=dict)
    # نوع السوق: crypto / stocks (يُضبط عند إنشاء الشارت)
    market: Optional[str] = None
    # نوع البث الحي: kline (Binance kline حقيقي) / stock (دفع أسهم) / ticker
    stream_kind: Optional[str] = None
    # الفريم الأساسي للبث عند الفريمات المركّبة (2m يبث 1m ...)
    base_timeframe: Optional[str] = None
    # تجميع الفريمات المركّبة: آخر شمعة أساسية وحجمها التراكمي
    kline_agg: Dict = field(default_factory=dict)
    # حالة السوق للأسهم: open / closed / pre_market / post_market (None للكريبتو = مفتوح دائماً)
    market_status: Optional[str] = None
    # آخر اقتباس أسهم (price/change_percent/volume) لحقوله في price_update
    last_quote: Optional[Dict] = None

class ChartManager:
    """مدير الشارت المركزي"""
    
    def __init__(self):
        self.charts: Dict[str, ChartState] = {}  # key = "symbol_timeframe"
        self.candle_locks: Dict[str, asyncio.Lock] = {}
        self.initialized = False
        self.crypto_provider = BinanceProvider()
        self._stock_provider = None  # USStockProvider كسول (للأسهم فقط)
        self.ws_manager: Optional["WebSocketManager"] = None
      
    def set_ws_manager(self, ws_manager: "WebSocketManager"):
        """ربط WebSocketManager بعد الإنشاء لتجنب circular import"""
        self.ws_manager = ws_manager        
    
    async def initialize(self):
        """تهيئة النظام"""
        if not self.initialized:
            await live_stream_manager.start()
            self.initialized = True
            logger.info("✅ ChartManager initialized")


    def get_chart_key(self, symbol: str, timeframe: Any) -> str:
        """تحويل الـ timeframe إلى نص مهما كان نوعه لضمان دقة المفتاح"""
        if isinstance(timeframe, Timeframe):
            tf_str = timeframe.value
        elif hasattr(timeframe, 'value'): # حماية إضافية لأي Enum آخر
            tf_str = timeframe.value
        else:
            tf_str = str(timeframe)
        
        # التأكد من إزالة أي زوائد مثل "Timeframe.MIN1" وتحويلها لـ "1m"
        if "Timeframe." in tf_str:
            # هذه حالة احترازية إذا مرر النص كـ "Timeframe.MIN1"
            mapping = { "Timeframe.MIN1": "1m", "Timeframe.MIN5": "5m" } # وهكذا..
            tf_str = mapping.get(tf_str, tf_str)

        return f"{symbol}_{tf_str}"
    
    async def get_or_create_chart(
        self,
        symbol: str,
        timeframe: str,
        market: str = "crypto",
        num_last_candles: int = 5000, 
        initial_candles: Optional[List[Dict]] = None
    ) -> ChartState:
        """الحصول على شارت أو إنشاء جديد مع آخر N شمعة مغلقة فقط قبل الشمعة الحية.

        البث الحي:
        - كريبتو: kline حقيقي من Binance (WebSocket أصلي) للفريم نفسه، وللفريمات
          المركّبة (2m/10m/2d/2w/1M) يُبث الفريم الأساسي وتُبنى الشموع بالتجميع.
        - أسهم: دفع حي عبر WS الباك اند (بولينج داخلي + push فوري) + تاريخ كامل.
        """
        key = self.get_chart_key(symbol, timeframe)
        tf_str = timeframe.value if hasattr(timeframe, 'value') else str(timeframe)

        if key not in self.charts:
            chart = ChartState(symbol=symbol, timeframe=tf_str, candles=initial_candles or [])
            # ✅ الجولة 4: حفظ السوق على حالة الشارت (يصل مع get_chart_data)
            chart.market = str(market).lower()
            self.charts[key] = chart
            self.candle_locks[key] = asyncio.Lock()

            if market == "crypto":
                # كريبتو: kline حقيقي — الفريم الأساسي للمركّب
                base_tf, _factor = composite_base_tf(tf_str) if is_composite_tf(tf_str) else (tf_str, 1)
                chart.base_timeframe = base_tf
                chart.stream_kind = "kline"

                if not initial_candles:
                    try:
                        if is_composite_tf(tf_str):
                            chart.candles = await self._load_composite_initial_candles(
                                symbol, tf_str, num_last_candles)
                        else:
                            df_last_closed = await self.crypto_provider.get_last_closed_candles(
                                symbol=symbol,
                                timeframe=tf_str,
                                limit=num_last_candles
                            )
                            if not df_last_closed.empty:
                                df_last_closed = df_last_closed.sort_values('time')
                                chart.candles = df_last_closed.to_dict('records')
                    except Exception as e:
                        logger.error(f"❌ Failed to load last {num_last_candles} closed candles for {key}: {e}")

                handler = self._create_kline_handler(symbol, tf_str)
                chart.price_handler = handler
                await live_stream_manager.subscribe_kline(symbol, base_tf, handler)
                logger.info(f"📊 Chart {key} created — REAL kline stream {symbol}@kline_{base_tf} + {len(chart.candles)} closed candles")

                # ✅ الجولة 4: تعويض ذاتي — إن فشل الجلب الأولي (حظر/تهدئة Binance)
                # مهمة خلفية تعيد المحاولة ثم تبث chart_backfilled بالتاريخ الكامل،
                # فلا يبقى الشارت فارغاً حتى انقطاع العميل (كان سبب "السلوك غير المتسق").
                if len(chart.candles) < num_last_candles:
                    asyncio.create_task(self._backfill_chart_history(
                        key, symbol, tf_str, num_last_candles))

            elif market in ("stocks", "stock"):
                # أسهم: تاريخ كامل + دفع حي عبر WS الباك اند
                chart.stream_kind = "stock"
                if not initial_candles:
                    try:
                        chart.candles = await self._load_stock_initial_candles(
                            symbol, tf_str, num_last_candles)
                    except Exception as e:
                        logger.error(f"❌ Failed to load stock history for {key}: {e}")

                handler = self._create_price_handler(symbol, tf_str)
                chart.price_handler = handler
                await live_stream_manager.subscribe_stock(symbol, handler)
                logger.info(f"📊 Chart {key} created — stock live push + {len(chart.candles)} closed candles")

                # ✅ الجولة 4: نفس التعويض الذاتي للأسهم عند فشل yfinance المؤقت
                if len(chart.candles) < num_last_candles:
                    asyncio.create_task(self._backfill_chart_history(
                        key, symbol, tf_str, num_last_candles, is_stock=True))

            else:
                # سوق غير معروف: مسار ticker العام (توافق خلفي)
                handler = self._create_price_handler(symbol, tf_str)
                chart.price_handler = handler
                await live_stream_manager.subscribe(symbol, handler)
                chart.stream_kind = "ticker"
                logger.info(f"📊 Chart {key} created and subscribed to ticker stream.")

        return self.charts[key]

    async def _backfill_chart_history(
        self,
        key: str,
        symbol: str,
        tf_str: str,
        num_last_candles: int,
        is_stock: bool = False,
    ):
        """✅ الجولة 4: تعويذ ذاتي للتاريخ المفقود + بث chart_backfilled.

        تُستدعى مهمة خلفية عند إنشاء الشارت بتاريخ أقل من المطلوب (حظر/تهدئة
        مزود). تعيد المحاولة دورياً حتى تمتلئ الشموع، ثم:
        1) تدمج التاريخ في الشارت (إن كان لا يزال حياً)
        2) تعيد حساب المؤشرات كاملة
        3) تبث رسالة chart_backfilled للفرونت بالبيانات الجاهزة
        """
        max_attempts = 12
        delay_s = 60.0
        try:
            for attempt in range(1, max_attempts + 1):
                await asyncio.sleep(delay_s)
                chart = self.charts.get(key)
                if chart is None:
                    return  # الشارت حُذف (لا مشتركين) — لا داعي للتعويض
                if len(chart.candles) >= num_last_candles:
                    return
                logger.info(f"🔁 Backfill attempt {attempt}/{max_attempts} for {key} "
                            f"({len(chart.candles)}/{num_last_candles} candles)")
                try:
                    if is_stock:
                        fresh = await self._load_stock_initial_candles(symbol, tf_str, num_last_candles)
                    else:
                        if is_composite_tf(tf_str):
                            fresh = await self._load_composite_initial_candles(
                                symbol, tf_str, num_last_candles)
                        else:
                            df = await self.crypto_provider.get_last_closed_candles(
                                symbol=symbol, timeframe=tf_str, limit=num_last_candles)
                            fresh = []
                            if df is not None and not df.empty:
                                df = df.sort_values('time')
                                fresh = df.to_dict('records')
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"⚠️ Backfill fetch failed for {key}: {e}")
                    fresh = []

                if not fresh:
                    continue
                chart = self.charts.get(key)
                if chart is None:
                    return
                # دمج: حافظ على الشموع الحية/الجديدة الموجودة، وأضف القديمة الناقصة
                existing = {int(c.get("time", 0)): c for c in chart.candles}
                for c in fresh:
                    t = int(c.get("time", 0) or 0)
                    if t and t not in existing:
                        existing[t] = c
                merged = sorted(existing.values(), key=lambda c: int(c.get("time", 0)))
                chart.candles = merged[-num_last_candles:]

                # إعادة حساب المؤشرات كاملة ثم بث البيانات الجاهزة
                results = {}
                if chart.indicators:
                    try:
                        results = await indicator_manager.calculate_indicators(
                            candles=chart.candles,
                            indicators_config=chart.indicators,
                            symbol=chart.symbol,
                            timeframe=chart.timeframe,
                            on_close=True,
                        )
                        if results:
                            chart.indicators_results = results
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"⚠️ Backfill indicator calc failed for {key}: {e}")

                if self.ws_manager:
                    from app.core.managers import indicator_id as _iid
                    id_map = {
                        _iid(ind): (ind.get("name") if isinstance(ind, dict) else str(ind))
                        for ind in chart.indicators if isinstance(ind, dict)
                    }
                    await self.ws_manager.broadcast(key, {
                        "type": "chart_backfilled",
                        "symbol": chart.symbol,
                        "timeframe": chart.timeframe,
                        "candles": chart.candles[-num_last_candles:],
                        "indicators_results": self._rekey_results_by_id(chart, results),
                        "indicators_id_map": id_map,
                        "total_candles": len(chart.candles),
                        "time": self._now_ms(),
                    })
                logger.info(f"✅ Backfill complete for {key}: {len(chart.candles)} candles")
                return
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"⚠️ Backfill task error for {key}: {e}")

    async def _load_composite_initial_candles(
        self, symbol: str, tf_str: str, num_last_candles: int
    ) -> List[Dict]:
        """تاريخ الفريمات المركّبة: جلب الفريم الأساسي وتجميعه محلياً."""
        base_tf, factor = composite_base_tf(tf_str)
        # عدد شموع الأساس لكل bucket (2m×2 | 10m×2 | 2d×2 | 2w×14 | 1M×31)
        per_bucket = factor or 2
        base_limit = min(num_last_candles * per_bucket, 60_000)
        df_base = await self.crypto_provider.get_last_closed_candles(
            symbol=symbol, timeframe=base_tf, limit=base_limit)
        if df_base is None or df_base.empty:
            return []
        df_base = df_base.sort_values("time").tail(60_000)
        res = resample_candles(df_base, tf_str, time_col="time")
        if res.empty:
            return []
        res = res.tail(num_last_candles)
        return [
            {
                "time": int(r["time"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume", 0) or 0),
            }
            for _, r in res.iterrows()
        ]

    async def _load_stock_initial_candles(
        self, symbol: str, tf_str: str, num_last_candles: int
    ) -> List[Dict]:
        """تاريخ كامل للأسهم (intraday + يومي) من كاش التاريخ الكامل."""
        if self._stock_provider is None:
            from app.providers.us_stock_provider import USStockProvider
            self._stock_provider = USStockProvider(use_alpha_vantage=False)

        df = await self._stock_provider.get_full_history(symbol, tf_str)
        if df is None or df.empty:
            return []
        df = df.dropna(how="any").sort_index().tail(num_last_candles)

        records: List[Dict] = []
        for idx, row in df.iterrows():
            try:
                # ✅ الجولة 4: طابع موحّد — epoch-ms محاذاة الفريم (بلا ميكروثانية/±tz/بقايا)
                t_ms = sanitize_candle_time_ms(int(pd.Timestamp(idx).value // 10**6), tf_str)
                records.append({
                    "time": t_ms,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0) or 0),
                })
            except Exception:  # noqa: BLE001 — صف تالف لا يُسقط التحميل
                continue
        records.sort(key=lambda c: c["time"])
        return records


    def _calculate_lookback(self, timeframe: str, count: int) -> timedelta:
        """دالة مساعدة لحساب الفارق الزمني المطلوب لكل إطار"""
        unit = timeframe[-1] # m, h, d
        try:
            value = int(timeframe[:-1])
        except ValueError:
            value = 1

        if unit == 'm':
            return timedelta(minutes=value * count)
        elif unit == 'h':
            return timedelta(hours=value * count)
        elif unit == 'd':
            return timedelta(days=value * count)
        else:
            return timedelta(days=count) # افتراضي

    def _create_price_handler(self, symbol: str, timeframe: str) -> Callable:
        """إنشاء معالج للبيانات الحية (أسهم/ticker) — نبضات سعر تُجمّع محلياً"""
        async def handle_price_update(price_data: Dict):
            key = self.get_chart_key(symbol, timeframe)
            
            if key not in self.charts:
                logger.warning(f"💡 Received price update but chart {key} not ready yet")
                return
            
            chart = self.charts[key]
            
            async with self.candle_locks[key]:
                await self._update_chart_candle(chart, price_data)
        
        return handle_price_update

    def _create_kline_handler(self, symbol: str, chart_timeframe: str) -> Callable:
        """معالج kline حقيقي من Binance.

        يستقبل أحداث kline للفريم الأساسي (نفس الفريم للفريمات الأصلية، أو
        1m/1d/1w للفريمات المركّبة) ويبني الشموع الحقيقية:
        - kline مفتوح (x=false) → تحديث الشمعة الحية + بث price_update.
        - kline مغلق (x=true) → إغلاق رسمي + مؤشرات + بث candle_close.
        """
        async def handle_kline(kline: Dict):
            key = self.get_chart_key(symbol, chart_timeframe)
            if key not in self.charts:
                return
            chart = self.charts[key]

            async with self.candle_locks[key]:
                if kline.get("timeframe") == chart.timeframe:
                    await self._apply_kline(chart, kline)
                else:
                    await self._apply_kline_composite(chart, kline)

        return handle_kline

    async def _apply_kline(self, chart: ChartState, kline: Dict):
        """تطبيق kline حقيقي للفريم نفسه (دقيق 100% من Binance)."""
        closed = bool(kline.get("is_closed"))
        candle = {
            "time": int(kline["time"]),
            "open": float(kline["open"]),
            "high": float(kline["high"]),
            "low": float(kline["low"]),
            "close": float(kline["close"]),
            "volume": float(kline.get("volume", 0) or 0),
        }

        if closed:
            # شمعة مغلقة رسمياً — استبدال/إلحاق ثم مؤشرات + بث candle_close
            if chart.candles and int(chart.candles[-1]["time"]) == candle["time"]:
                chart.candles[-1] = candle
            else:
                chart.candles.append(candle)
            if len(chart.candles) > 5000:
                chart.candles = chart.candles[-5000:]
            if chart.live_candle and int(chart.live_candle.get("time", 0)) == candle["time"]:
                chart.live_candle = None
            await self._calculate_indicators_on_close(chart)
            latest = self._extract_latest_indicator_values(chart.indicators_results)
            key = self.get_chart_key(chart.symbol, chart.timeframe)
            await self.ws_manager.broadcast(key, {
                "type": "candle_close",
                "symbol": chart.symbol,
                "timeframe": chart.timeframe,
                "candle": candle,
                "indicators": self._rekey_results_by_id(chart, latest),
                "market_status": chart.market_status,
                "time": self._now_ms(),
            })
        else:
            # شمعة حية — قيم حقيقية من Binance مباشرة
            chart.live_candle = candle
            await self._broadcast_price_update(chart)

    async def _apply_kline_composite(self, chart: ChartState, kline: Dict):
        """بناء شموع فريم مركّب (2m/10m/2d/2w/1M) من kline الفريم الأساسي.

        كل حدث kline أساسي يحمل الحجم التراكمي لشمعته — نحسب الدلتا ثم ندمجها
        في bucket الفريم المركّب (محاذاة تقويمية صحيحة حتى للأسابيع/الشهور).
        """
        agg = chart.kline_agg
        base_time = int(kline["time"])
        if agg.get("base_time") == base_time:
            dv = max(0.0, float(kline.get("volume", 0) or 0) - float(agg.get("base_v", 0) or 0))
        else:
            dv = float(kline.get("volume", 0) or 0)
        agg["base_time"] = base_time
        agg["base_v"] = float(kline.get("volume", 0) or 0)

        try:
            bucket = int(align_time_ms(base_time, chart.timeframe))
        except Exception:  # noqa: BLE001
            bucket = base_time

        o = float(kline["open"]); h = float(kline["high"])
        l = float(kline["low"]);  c = float(kline["close"])

        if chart.live_candle is None or bucket > int(chart.live_candle["time"]):
            if chart.live_candle is not None and bucket > int(chart.live_candle["time"]):
                # إغلاق رسمي للـ bucket السابق عند بدء bucket جديد
                await self._close_current_candle(chart)
            chart.live_candle = {
                "time": bucket, "open": o, "high": h, "low": l,
                "close": c, "volume": dv,
            }
        elif bucket == int(chart.live_candle["time"]):
            lc = chart.live_candle
            lc["high"] = max(float(lc["high"]), h)
            lc["low"] = min(float(lc["low"]), l)
            lc["close"] = c
            lc["volume"] = float(lc.get("volume", 0) or 0) + dv
        else:
            return  # حدث قديم من bucket مُغلق — تجاهل

        await self._broadcast_price_update(chart)

    async def _broadcast_price_update(self, chart: ChartState):
        """بث price_update مع آخر قيم المؤشرات (نفس شكل الرسالة السابق).

        ✅ الجولة 4 (إصلاح المؤشرات-null):
        - إذا كانت chart.indicators_results فارغة (سباق التهيئة: المؤشرات أُضيفت قبل
          جاهزية الشموع، أو لم تُغلق أي شمعة بعد) نحسب مرة واحدة على كامل التاريخ
          ونخزّنها — فلا تبقى النتائج فارغة حتى أول إغلاق شمعة.
        - مفاتيح `indicators` في الرسالة أصبحت indicator_id موحدة (لا الاسم)."""
        latest_indicators = {}
        if chart.indicators:
            try:
                # ✅ Bootstrap: النتائج فارغة وشموع متوفرة → حساب كامل فوري وتخزين
                if not chart.indicators_results and chart.candles:
                    bootstrap = await indicator_manager.calculate_indicators(
                        candles=chart.candles,
                        indicators_config=chart.indicators,
                        symbol=chart.symbol,
                        timeframe=chart.timeframe,
                        on_close=True,
                    )
                    if bootstrap:
                        chart.indicators_results = bootstrap
                        logger.info(
                            f"✅ Bootstrap indicators persisted for {chart.symbol}_{chart.timeframe} "
                            f"({len(chart.candles)} candles)"
                        )

                temp_candles = chart.candles + ([chart.live_candle] if chart.live_candle else [])
                full_indicators = await indicator_manager.calculate_indicators(
                    candles=temp_candles[-100:],
                    indicators_config=chart.indicators,
                    symbol=chart.symbol,
                    timeframe=chart.timeframe,
                    on_close=False
                )
                latest_indicators = self._extract_latest_indicator_values(full_indicators)
            except Exception as e:  # noqa: BLE001 — خطأ مؤشرات لا يوقف بث السعر
                logger.warning(f"⚠️ live indicator calc failed for {chart.symbol}_{chart.timeframe}: {e}")

        chart.last_update = datetime.utcnow()
        key = self.get_chart_key(chart.symbol, chart.timeframe)
        msg = {
            "type": "price_update",
            "symbol": chart.symbol,
            "timeframe": chart.timeframe,
            "live_candle": chart.live_candle,
            "indicators": self._rekey_results_by_id(chart, latest_indicators),
            "market_status": chart.market_status,
            "time": self._now_ms(),
        }
        # ✅ الجولة 4: حقول الاقتباس للأسهم (None للكريبتو — الشكل موحد)
        quote = getattr(chart, "last_quote", None)
        if quote:
            msg.update({
                "price": quote.get("price"),
                "change_percent": quote.get("change_percent"),
                "change": quote.get("change"),
                "volume": quote.get("volume"),
            })
        await self.ws_manager.broadcast(key, msg)
    
# مع اضافه اخر تحديث للموشر 
    async def _update_chart_candle(self, chart: ChartState, price_data: Dict):
        """تحديث شمعة الشارت من نبضة سعر (أسهم/ticker) — إغلاق بمحاذاة bucket الحقيقية.

        الإصلاحات:
        - الإغلاق السابق كان يقارن فارق زمني (الآن: بداية bucket جديدة = إغلاق).
        - الشمعة المغلقة كانت تُزاح bucket كاملة للأمام (off-by-one) — صُحح.
        - الحجم كان يجمع الحجم التراكمي لـ 24h كل نبضة (تضخيم وهمي) — الآن دلتا.
        """
        now_ms = self._now_ms()
        price = float(price_data.get("price", 0) or 0)
        if price <= 0:
            return
        vol_delta = float(price_data.get("volume_delta",
                                         price_data.get("volume", 0) or 0) or 0)
        vol_delta = max(0.0, vol_delta)

        try:
            candle_time = int(align_time_ms(now_ms, chart.timeframe))
        except Exception:  # noqa: BLE001
            tf_min = self._timeframe_to_minutes(chart.timeframe)
            tf_ms = tf_min * 60 * 1000
            candle_time = (now_ms // int(tf_ms)) * int(tf_ms)

        # إن لم يكن هناك شمعة حية، نبدأ واحدة جديدة
        if chart.live_candle is None:
            chart.live_candle = {
                "time": candle_time,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": vol_delta,
            }
        elif candle_time > int(chart.live_candle["time"]):
            # بدء bucket جديد → إغلاق الشمعة الحالية رسمياً (بوقتها الصحيح)
            await self._close_current_candle(chart)
            chart.live_candle = {
                "time": candle_time,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": vol_delta,
            }
        else:
            # تحديث الشمعة الحالية
            candle = chart.live_candle
            candle["high"] = max(float(candle["high"]), price)
            candle["low"] = min(float(candle["low"]), price)
            candle["close"] = price
            candle["volume"] = float(candle.get("volume", 0) or 0) + vol_delta

        # ✅ الجولة 4: حالة السوق تمر مع كل نبضة أسهم لتصل للفرونت في نفس الدفعة
        ms = price_data.get("market_status")
        if ms:
            chart.market_status = str(ms)
        # ✅ الجولة 4: حقول الاقتباس للرسالة (change_percent / حجم تراكمي / آخر سعر)
        chart.last_quote = {
            "price": price,
            "change_percent": float(price_data.get("change_percent", 0) or 0),
            "change": float(price_data.get("change", 0) or 0),
            "volume": float(price_data.get("volume", 0) or 0),
        }

        await self._broadcast_price_update(chart)



    async def _close_current_candle(self, chart: ChartState):
        """إغلاق الشمعة الحية: إلحاق بوقتها الأصلي (بداية bucket) + مؤشرات + بث.

        إصلاح: كانت الدالة تستقبل close_time وتعدّل وقت الشمعة إليه — ما كان
        يزيح كل شمعة مغلقة bucket كاملة للأمام. الآن الوقت يبقى كما هو.
        """
        if chart.live_candle is None:
            return

        closed = chart.live_candle.copy()

        # حماية من التكرار: نفس وقت آخر شمعة مغلقة → استبدال
        if chart.candles and int(chart.candles[-1]["time"]) == int(closed["time"]):
            chart.candles[-1] = closed
        else:
            chart.candles.append(closed)

        if len(chart.candles) > 5000:
            chart.candles = chart.candles[-5000:]

        # --- تحديث المؤشرات رسمياً عند الإغلاق ---
        await self._calculate_indicators_on_close(chart)

        # ✅ نأخذ القيم الجديدة فقط للإرسال
        latest_results = self._extract_latest_indicator_values(chart.indicators_results)
        # بث رسالة إغلاق الشمعة
        key = self.get_chart_key(chart.symbol, chart.timeframe)
        await self.ws_manager.broadcast(key, {
            "type": "candle_close",
            "symbol": chart.symbol,
            "timeframe": chart.timeframe,
            "candle": closed,
            "indicators": self._rekey_results_by_id(chart, latest_results),
            "market_status": chart.market_status,
            "time": self._now_ms()
        })
        chart.live_candle = None





    async def _calculate_indicators_on_close(self, chart: ChartState):
        """حساب المؤشرات وتحديث النتائج في حالة الشارت"""
        if not chart.indicators:
            logger.info(f"⚠️ No indicators configured for {chart.symbol}, skipping calculation.")
            return

        if not chart.candles:
            logger.warning(f"⚠️ No candles available for {chart.symbol} to calculate indicators.")
            return

        try:
            logger.info(f"🔄 Calculating {len(chart.indicators)} indicators for {chart.symbol}...")

            # ✅ الجولة 4: حساب على كامل التاريخ (حتى 5000 شمعة) بدل آخر 500 —
            # النتائج تبقى دائماً محاذاة لعدد الشموع المعروض بالكامل، ولا تنكمش
            # المصفوفات بعد أول إغلاق شمعة (كان سبب رسم المؤشرات فارغة جزئياً).
            calculation_candles = chart.candles

            results = await indicator_manager.calculate_indicators(
                candles=calculation_candles,
                indicators_config=chart.indicators,
                symbol=chart.symbol,
                timeframe=chart.timeframe,
                on_close=True
            )

            chart.indicators_results = results
            logger.info(f"✅ Calculation successful! Results keys: {list(results.keys())}")

        except Exception as e:
            chart.indicators_error = str(e)[:300]
            logger.error(f"❌ Indicator calculation error: {e}", exc_info=True)



    async def add_indicator(
        self,
        symbol: str,
        timeframe: Any,
        indicator_config: Dict[str, Any]
    ) -> bool:
        """إضافة مؤشر وحسابه فوراً بناءً على التاريخ المتاح"""
        key = self.get_chart_key(symbol, timeframe)
        
        if key not in self.charts:
            logger.error(f"❌ Chart {key} not found.")
            return False
        
        chart = self.charts[key]
        indicator_name = indicator_config.get('name')

        # ✅ الجولة 5: تطهير التكوين عند الحقن — يُصلح type الفاسد الوارد من
        # العملاء (مثل "oscillator") هنا فيمنع فشل الحساب والحفظ السام معاً.
        try:
            from app.services.indicators.base import sanitize_indicator_config
            indicator_config = sanitize_indicator_config(indicator_config)
        except Exception:  # noqa: BLE001
            pass

        # ✅ الجولة 4: ختم كل تكوين بمعرف مستقر (name_hash) — الحاسبة تعيد النتائج
        # بهذا المفتاح فلا يتصادم مؤشران بنفس الاسم ومعاملات مختلفة (RSI 14 + RSI 7).
        config = dict(indicator_config)
        if not config.get('id'):
            config['id'] = indicator_id(config)
        new_id = config['id']

        # 1. التأكد من عدم التكرار بالمعرف (لا بالاسم!) ثم الإضافة
        exists = any(
            str(ind.get('id') or indicator_id(ind)) == new_id
            for ind in chart.indicators if isinstance(ind, dict)
        )
        if not exists:
            chart.indicators.append(config)
            logger.info(f"📌 Indicator {indicator_name} ({new_id}) registered for {key}")

        # 2. الحساب الفوري إذا كانت الشموع جاهزة
        if chart.candles and len(chart.candles) > 0:
            try:
                logger.info(f"🔄 Calculating {indicator_name} on {len(chart.candles)} candles...")
                
                # نستخدم دالة الحساب الجماعي (تأكد أنها تعيد نتائج للمؤشر الجديد)
                results = await indicator_manager.calculate_indicators(
                    candles=chart.candles,
                    indicators_config=chart.indicators, # ستحسب الجميع بما فيهم الجديد
                    symbol=symbol,
                    timeframe=timeframe,
                    on_close=True 
                )
                
                if results:
                    chart.indicators_results.update(results)
                    logger.info(f"✅ {indicator_name} values calculated successfully.")
                    return True
            except Exception as e:
                logger.error(f"❌ Error calculating {indicator_name}: {e}")
                return False
        else:
            logger.warning(f"⏳ {indicator_name} added but candles not ready yet.")
            
        return True

    async def remove_indicator(
        self,
        symbol: str,
        timeframe: Any,
        indicator_name: str,
        target_id: Optional[str] = None,
    ) -> bool:
        """إزالة مؤشر من الشارت.

        ✅ الجولة 4: عند تمرير target_id (name_hash) تُزال نسخة واحدة فقط —
        حتى مع مؤشرين بنفس الاسم (RSI 14 + RSI 7). بلا معرف: السلوك القديم بالاسم."""
        key = self.get_chart_key(symbol, timeframe)

        if key not in self.charts:
            return False

        chart = self.charts[key]

        def _match(ind: Dict) -> bool:
            if not isinstance(ind, dict):
                return False
            if target_id:
                return (
                    str(ind.get('id') or '') == target_id
                    or indicator_id(ind) == target_id
                )
            return ind.get('name') == indicator_name

        # إزالة من قائمة الإعدادات
        before = len(chart.indicators)
        chart.indicators = [ind for ind in chart.indicators if not _match(ind)]
        removed_any = len(chart.indicators) != before

        # إزالة النتائج المحسوبة (مفتاح النتائج = المعرف بعد الختم، أو الاسم قديماً)
        for rkey in (target_id, indicator_name):
            if rkey and rkey in chart.indicators_results:
                del chart.indicators_results[rkey]
                removed_any = True
        # مفاتيح متعددة المخرجات مثل "{id}_0"
        if target_id:
            for rk in [k for k in chart.indicators_results
                       if isinstance(k, str) and k.startswith(target_id)]:
                del chart.indicators_results[rk]
                removed_any = True

        logger.info(f"🗑️ Removed indicator {target_id or indicator_name} from {key}")
        return removed_any



    async def clear_indicators(
        self,
        symbol: str,
        timeframe: Any
    ) -> bool:
        """مسح جميع المؤشرات من الشارت"""
        key = self.get_chart_key(symbol, timeframe)
        
        if key not in self.charts:
            return False
        
        chart = self.charts[key]
        chart.indicators = []
        chart.indicators_results = {}
        
        logger.info(f"🧹 Cleared all indicators from {key}")
        return True
        

    async def update_indicator(
        self,
        symbol: str,
        timeframe: Any,
        indicator_name: str,
        new_params: Dict[str, Any]
    ) -> bool:
        """تعديل معلمات مؤشر موجود وإعادة حسابه"""
        key = self.get_chart_key(symbol, timeframe)
        
        if key not in self.charts:
            logger.error(f"❌ Chart {key} not found.")
            return False
        
        chart = self.charts[key]
        
        # 1. البحث عن المؤشر في القائمة وتحديثه
        found = False
        old_id = None
        for ind in chart.indicators:
            if ind.get('name') == indicator_name:
                old_id = str(ind.get('id') or indicator_id(ind))
                ind['params'] = new_params
                # ✅ الجولة 4: إعادة ختم المعرف (المعاملات الجديدة = معرف جديد)
                ind['id'] = indicator_id(ind)
                found = True
                logger.info(f"🔧 Updated params for {indicator_name} in {key} "
                            f"({old_id} → {ind['id']})")
                break

        if not found:
            logger.warning(f"⚠️ Indicator {indicator_name} not found in chart.")
            return False

        # تنظيف نتائج المعرف القديم (المعاملات الجديدة = مفتاح جديد)
        if old_id:
            for rk in [k for k in list(chart.indicators_results.keys())
                       if isinstance(k, str) and (k == old_id or k.startswith(old_id))]:
                del chart.indicators_results[rk]
        
        # 2. إعادة حساب جميع المؤشرات لضمان التزامن
        if chart.candles and len(chart.candles) > 0:
            try:
                results = await indicator_manager.calculate_indicators(
                    candles=chart.candles,
                    indicators_config=chart.indicators,
                    symbol=symbol,
                    timeframe=timeframe,
                    on_close=True 
                )
                
                if results:
                    chart.indicators_results = results
                    logger.info(f"✅ Recalculated indicators after update.")
                    return True
            except Exception as e:
                logger.error(f"❌ Error recalculating indicators: {e}")
                return False
                
        return True


    def add_on_close_callback(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable
    ):
        """إضافة callback عند إغلاق الشمعة"""
        key = self.get_chart_key(symbol, timeframe)
        
        if key in self.charts:
            # منع التسجيل المكرر لنفس الـ callback (إعادة التسجيل = استبدال)
            if callback not in self.charts[key].on_close_callbacks:
                self.charts[key].on_close_callbacks.append(callback)
    
    def remove_on_close_callback(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable
    ) -> bool:
        """إزالة callback إغلاق الشمعة (يستخدم عند تغيير الفريم أو قطع الاتصال لمنع التسريب)"""
        if callback is None:
            return False
        
        key = self.get_chart_key(symbol, timeframe)
        
        if key in self.charts:
            callbacks = self.charts[key].on_close_callbacks
            if callback in callbacks:
                callbacks.remove(callback)
                return True
        return False
    
    async def get_chart_data(
        self,
        symbol: str,
        timeframe: str,
        include_live: bool = True
    ) -> Dict[str, Any]:
        """الحصول على بيانات الشارت"""
        key = self.get_chart_key(symbol, timeframe)
        
        if key not in self.charts:
            return {}
        
        chart = self.charts[key]
        
        # تجهيز البيانات
        candles = chart.candles.copy()
        if include_live and chart.live_candle:
            live_candle = chart.live_candle.copy()
            last_time = int(candles[-1]["time"]) if candles else 0
            live_time = int(live_candle.get("time", 0) or 0)

            if candles and live_time == last_time:
                # ✅ الجولة 4: الشمعة الحية في نفس bucket آخر شمعة مغلقة → ندمجها
                # مكانها بدل إلحاق صف مكرر بوقت +1ms (كان يفسد طوابع أسهم اليومية).
                merged = dict(candles[-1])
                merged.update({
                    "open": float(live_candle.get("open", merged.get("open", 0))) or merged.get("open", 0),
                    "high": max(float(merged.get("high", 0)), float(live_candle.get("high", 0) or 0)),
                    "low": min(float(merged.get("low", 0)), float(live_candle.get("low", 0) or 0)) if float(live_candle.get("low", 0) or 0) > 0 else merged.get("low", 0),
                    "close": float(live_candle.get("close", merged.get("close", 0))) or merged.get("close", 0),
                    "volume": float(live_candle.get("volume", 0) or 0) or merged.get("volume", 0),
                    "is_live": True,
                })
                candles[-1] = merged
            elif live_time > last_time or not candles:
                # bucket جديد فعلاً → ألحقها كصف جديد محاذى
                candles.append(live_candle)
            # live_time < last_time → حدث قديم، تجاهل
        
        return {
            "symbol": chart.symbol,
            "timeframe": chart.timeframe,
            "market": getattr(chart, "market", None) or None,
            "market_status": chart.market_status,
            "candles": candles[-5000:], 
            "indicators": chart.indicators,
            "indicators_results": chart.indicators_results,
            "metadata": {
                "total_candles": len(candles),
                "last_update": int(chart.last_update.timestamp() * 1000),
                "subscribers": len(chart.subscribers)
            }
        }

    def get_chart_indicators_results(self, symbol: str, timeframe: Any) -> Dict:
        """قراءة مباشرة لنتائج المؤشرات المخزنة (بلا حساب) — الجولة 4"""
        chart = self.charts.get(self.get_chart_key(symbol, timeframe))
        if not chart:
            return {}
        return dict(chart.indicators_results or {})

    async def calculate_full_indicators(self, symbol: str, timeframe: Any) -> Dict:
        """حساب فوري لكامل المؤشرات على كامل التاريخ المخزن وتخزينه — الجولة 4.

        تُستخدم في chart_initialized و indicator_added لضمان أن القيم الحقيقية
        تصل دائماً (وليس null) حتى لو لم تُغلق أي شمعة بعد أو سبقت المؤشرات
        جاهزية الشموع."""
        chart = self.charts.get(self.get_chart_key(symbol, timeframe))
        if not chart or not chart.candles or not chart.indicators:
            return {}
        results = await indicator_manager.calculate_indicators(
            candles=chart.candles,
            indicators_config=chart.indicators,
            symbol=chart.symbol,
            timeframe=chart.timeframe,
            on_close=True,
        )
        if results:
            chart.indicators_results = results
        return results
    
    # def _timeframe_to_minutes(self, timeframe: str) -> int:
    #     """تحويل timeframe إلى دقائق"""
    #     timeframe_map = {
    #         "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    #         "1h": 60, "4h": 240, "1d": 1440
    #     }
    #     return timeframe_map.get(timeframe, 1)



    def _timeframe_to_minutes(self, timeframe) -> float:
        """
        تحويل timeframe إلى دقائق (مع دعم الثواني والأسابيع والشهور)

        الحرف الصغير m = دقائق (1m → 1)، والحرف الكبير M = شهر (1M → 43200 ≈ 30 يوم).
        بقية الوحدات غير حساسة لحالة الأحرف: s ثواني، h ساعات، d أيام، w أسابيع، y سنوات.
        """
        if timeframe is None:
            return 1.0

        # دعم تمرير Enum (مثل Timeframe.MONTH1)
        tf = timeframe.value if hasattr(timeframe, "value") else timeframe
        tf = str(tf).strip()

        if not tf:
            return 1.0

        # استخراج الرقم والوحدة (الوحدة تبقى بحالتها الأصلية للتمييز بين m/M)
        unit = tf[-1]
        try:
            value = int(tf[:-1])
        except ValueError:
            value = 1

        unit_lower = unit.lower()

        # ثواني → كسر من الدقيقة
        if unit_lower == 's':
            return value / 60.0

        # تمييز 1m (دقيقة) عن 1M (شهر) — حساس لحالة الأحرف
        if unit == 'm':
            return float(value)          # دقيقة
        if unit == 'M':
            return float(value * 43200)  # شهر ≈ 30 يوم

        if unit_lower == 'h':
            return float(value * 60)
        if unit_lower == 'd':
            return float(value * 1440)
        if unit_lower == 'w':
            return float(value * 10080)
        if unit_lower == 'y':
            return float(value * 525600)

        # الافتراضي: دقيقة واحدة
        return 1.0



    async def cleanup(self, symbol: str, timeframe: str):
        """تنظيف الشارت وإلغاء اشتراك البث حسب نوعه"""
        key = self.get_chart_key(symbol, timeframe)
        
        if key in self.charts:
            chart = self.charts[key]
            # إلغاء الاشتراك من البث الحي حسب النوع
            if chart.price_handler:
                try:
                    if chart.stream_kind == "kline":
                        await live_stream_manager.unsubscribe_kline(
                            symbol, chart.base_timeframe or timeframe, chart.price_handler)
                    elif chart.stream_kind == "stock":
                        await live_stream_manager.unsubscribe_stock(
                            symbol, chart.price_handler)
                    else:
                        await live_stream_manager.unsubscribe(symbol, chart.price_handler)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"⚠️ cleanup unsubscribe failed for {key}: {e}")
            
            # حذف الشارت
            del self.charts[key]
            
            if key in self.candle_locks:
                del self.candle_locks[key]
            logger.info(f"🧹 Cleaned up chart: {key}")
 




    def _now_ms(self) -> int:
        return int(datetime.utcnow().timestamp() * 1000)

    def _align_time(self, ts_ms: int, timeframe_min: int) -> int:
        tf_ms = timeframe_min * 60 * 1000
        return (ts_ms // tf_ms) * tf_ms

    def _rekey_results_by_id(self, chart: ChartState, results: Dict) -> Dict:
        """✅ الجولة 4: توحيد مفاتيح نتائج المؤشرات على indicator_id (لا الاسم).

        - المفتاح الأساسي: indicator_id (name_hash) ثابت عبر الجلسات.
        - نتائج المؤشرات متعددة المخرجات (مثل bollinger_upper) تُربط بمؤشرها
          الأصلي عبر بادئة الاسم، وإلا تبقى بمفتاحها كما هي.
        - كل قيمة تحمل داخلها "name" الأصلي دائماً للتوافق العكسي."""
        if not results:
            return results
        entries = chart.indicators if isinstance(chart.indicators, list) else []
        name_to_id: Dict[str, str] = {}
        id_to_name: Dict[str, str] = {}
        for ind in entries:
            if isinstance(ind, dict) and ind.get("name"):
                try:
                    _id = indicator_id(ind)
                    name_to_id[str(ind["name"])] = _id
                    id_to_name[_id] = str(ind["name"])
                except Exception:  # noqa: BLE001
                    name_to_id[str(ind["name"])] = str(ind["name"])

        out: Dict[str, Any] = {}
        for res_key, val in results.items():
            # مطابقة تماماً → المعرف. المفاتيح الملحقة (bollinger_x_0) تبقى كما هي
            # لأنها تحمل المعرف/الاسم أصلاً ولا يجوز انهيارها على مفتاح واحد.
            mapped = name_to_id.get(res_key) if res_key not in name_to_id.values() else res_key
            if isinstance(val, dict) and "name" in val:
                val = dict(val)
                val.setdefault("indicator_id", mapped or res_key)
                # ✅ الجولة 5: name نظيف (rsi) بدل مفتاح المعرف (rsi_66b862bf) —
                # كان الفرونت يعرض "66B862BF" في رؤوس اللوحات ويضطر لتحليل المعرف.
                _mk = mapped or res_key
                if val.get("name") == _mk and _mk in id_to_name:
                    val["name"] = id_to_name[_mk]
            out[mapped or res_key] = val
        return out


    def _extract_latest_indicator_values(self, full_indicators: Dict) -> Dict:
        """استخراج القيم الجديدة فقط من نتائج المؤشرات الكاملة"""
        latest_indicators = {}
        
        for indicator_name, indicator_data in full_indicators.items():
            latest_indicators[indicator_name] = {
                "name": indicator_name,
                "values": [],
                "signals": {"data": [], "index": [], "dtype": "int64"},
                "metadata": {}
            }

            if indicator_name == "smc_order_block":
                latest_indicators[indicator_name]["metadata"] = indicator_data["metadata"]
                continue

            
            # أخذ آخر قيمة من values
            if indicator_data.get("values") and len(indicator_data["values"]) > 0:
                latest_indicators[indicator_name]["values"] = [indicator_data["values"][-1]]
            
            # أخذ آخر إشارة
            if indicator_data.get("signals"):
                signals = indicator_data["signals"]
                if signals.get("data") and len(signals["data"]) > 0:
                    latest_indicators[indicator_name]["signals"]["data"] = [signals["data"][-1]]
                if signals.get("index") and len(signals["index"]) > 0:
                    latest_indicators[indicator_name]["signals"]["index"] = [signals["index"][-1]]
            
            # ✅ تعديل مهم: إرسال metadata كاملاً للمؤشرات المركبة مثل بولينجر
            if indicator_name == "bb" and indicator_data.get("metadata"):
                metadata = indicator_data["metadata"]
                latest_indicators[indicator_name]["metadata"] = {
                    "sma": [metadata.get("sma", [])[-1]] if metadata.get("sma") else [],
                    "upper_band": [metadata.get("upper_band", [])[-1]] if metadata.get("upper_band") else [],
                    "lower_band": [metadata.get("lower_band", [])[-1]] if metadata.get("lower_band") else [],
                    "band_width": [metadata.get("band_width", [])[-1]] if metadata.get("band_width") else [],
                    "period": metadata.get("period", 20),
                    "std": metadata.get("std", 2)
                }

            if indicator_name == "macd" and indicator_data.get("metadata"):
                meta = indicator_data["metadata"]
                latest_indicators[indicator_name]["metadata"] = {
                    "macd_line": [meta["macd_line"][-1]] if meta.get("macd_line") else [],
                    "signal_line": [meta["signal_line"][-1]] if meta.get("signal_line") else [],
                    "histogram": [meta["histogram"][-1]] if meta.get("histogram") else [],
                    "fast": meta.get("fast"),
                    "slow": meta.get("slow"),
                    "signal": meta.get("signal"),
                }


        return latest_indicators

# المثيل العام
chart_manager = ChartManager()