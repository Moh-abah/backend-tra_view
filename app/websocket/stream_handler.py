import asyncio
import json
import logging
import time
from typing import Dict, List, Any, Optional, Set, Callable
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict

from .schemas import (
    StreamMessage, StreamDataType,
    PriceStreamData, IndicatorStreamData,
    ConditionStreamData, SignalStreamData,
    EntryPointStreamData
)
from app.services.data_service import DataService
from app.services.indicators import apply_indicators
from app.services.strategy import run_strategy
from app.services.filtering import FilteringEngine

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30

class RealTimeStreamHandler:
    """معالج البث اللحظي - شبيه بـ TradingView"""
    
    def __init__(self, data_service: DataService, filtering_engine: FilteringEngine):
        self.data_service = data_service
        self.filtering_engine = filtering_engine
        
        # تخزين البثوث النشطة
        self.active_streams: Dict[str, Dict[str, Any]] = {}
        self.stream_tasks: Dict[str, asyncio.Task] = {}
        
        # المشتركون حسب الرمز والإطار الزمني
        self.subscribers: Dict[str, Set[Any]] = defaultdict(set)
        
        # كاش للبيانات
        self.price_cache: Dict[str, Dict] = {}
        self.indicator_cache: Dict[str, Dict] = {}
        
        # إحصائيات
        self.stats = {
            "total_messages_sent": 0,
            "active_connections": 0,
            "streams_started": 0,
            "streams_stopped": 0
        }
        
        # مهمة الـ heartbeat (كشف السوكيتات الميتة)
        self._heartbeat_task: Optional[asyncio.Task] = None
    
    async def start_stream(
        self,
        symbol: str,
        timeframe: str,
        market: str = "crypto",
        indicators_config: List[Dict[str, Any]] = None,
        strategy_config: Dict[str, Any] = None,
        stream_id: Optional[str] = None
    ) -> str:
        """
        بدء بث لحظي لرمز معين
        
        Args:
            symbol: الرمز
            timeframe: الإطار الزمني
            market: السوق
            indicators_config: تكوين المؤشرات
            strategy_config: تكوين الإستراتيجية
            stream_id: معرف البث (اختياري)
            
        Returns:
            str: معرف البث
        """
        stream_id = stream_id or f"{market}_{symbol}_{timeframe}_{int(time.time())}"
        
        if stream_id in self.active_streams:
            return stream_id
        
        # تهيئة إعدادات البث
        self.active_streams[stream_id] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "market": market,
            "indicators_config": indicators_config or [],
            "strategy_config": strategy_config,
            "start_time": datetime.utcnow(),
            "last_update": None,
            "message_count": 0,
            "status": "running"
        }
        
        # بدء مهمة البث
        # task = asyncio.create_task(self._stream_loop(stream_id))
        task = asyncio.create_task(self._live_stream_loop(stream_id))

        self.stream_tasks[stream_id] = task
        
        self.stats["streams_started"] += 1
        logger.info("📡 Stream started: %s", stream_id)
        
        # تشغيل الـ heartbeat مع أول بث (إن لم يكن يعمل)
        self._ensure_heartbeat()
        
        return stream_id
    


    async def _live_stream_loop(self, stream_id: str):
        """
        حلقة البث الحي — مصممة لتبقى حية:
        أي خطأ يُسجل ويُعاد المحاولة مع backoff بدل موت المهمة بصمت.
        """
        stream = self.active_streams.get(stream_id)
        if not stream:
            return

        symbol = stream["symbol"]
        timeframe = stream["timeframe"]
        market = stream["market"]

        backoff = 1.0  # يبدأ بثانية ويتضاعف حتى 30 ثانية

        while stream_id in self.active_streams:
            try:
                async for tick in self.data_service.stream_live(symbol, timeframe, market):
                    if stream_id not in self.active_streams:
                        return

                    if stream["status"] == "paused":
                        await asyncio.sleep(0.5)
                        continue

                    try:
                        await self._handle_live_tick(stream_id, tick)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # خطأ في معالجة tick واحد لا يقتل البث
                        logger.exception("Error handling live tick for stream %s", stream_id)
                        continue

                # انتهى الـ generator (انقطاع المزود) — نعيد المحاولة بعد مهلة
                logger.warning("Live stream source ended for %s, resubscribing in %.1fs", stream_id, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

            except asyncio.CancelledError:
                # إيقاف مقصود (stop_stream) — لا نعاود المحاولة
                logger.info("Live stream loop %s cancelled", stream_id)
                raise
            except Exception:
                logger.exception("Error in live stream loop %s — retrying in %.1fs", stream_id, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            else:
                # نجاح دورة كاملة — نعيد ضبط الـ backoff
                backoff = 1.0







    async def _handle_live_tick(self, stream_id: str, tick: dict):
        stream = self.active_streams[stream_id]
        symbol = stream["symbol"]
        timeframe = stream["timeframe"]

        # 1️⃣ تحديث السعر مباشرة
        price_msg = StreamMessage(
            type=StreamDataType.PRICE,
            symbol=symbol,
            timeframe=timeframe,
            data={
                "open": tick["open"],
                "high": tick["high"],
                "low": tick["low"],
                "close": tick["close"],
                "volume": tick["volume"],
                "timestamp": tick["timestamp"].isoformat()
            }
        )

        await self._broadcast_messages(stream_id, [price_msg])

        # 2️⃣ لا نحسب استراتيجيات إلا إذا الشمعة أغلقت
        if not tick["is_closed"]:
            return

        df = await self.data_service.get_historical(
            symbol=symbol,
            timeframe=timeframe,
            market=stream["market"],
            days=2
        )

        messages = await self._process_stream_data(
            stream_id,
            df,
            stream["indicators_config"],
            stream["strategy_config"]
        )

        await self._broadcast_messages(stream_id, messages)








    async def stop_stream(self, stream_id: str) -> bool:
        """إيقاف بث محدد"""
        if stream_id not in self.active_streams:
            return False
        
        # إيقاف المهمة
        if stream_id in self.stream_tasks:
            self.stream_tasks[stream_id].cancel()
            try:
                await self.stream_tasks[stream_id]
            except asyncio.CancelledError:
                pass
            del self.stream_tasks[stream_id]
        
        # إزالة من السجلات
        del self.active_streams[stream_id]
        
        # إزالة المشتركين
        if stream_id in self.subscribers:
            del self.subscribers[stream_id]
        
        self.stats["streams_stopped"] += 1
        logger.info("📡 Stream stopped: %s", stream_id)
        
        # إيقاف الـ heartbeat إذا لم يبق أي بث نشط
        if not self.active_streams and self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        
        return True
    
    async def subscribe(self, stream_id: str, websocket) -> bool:
        """اشتراك عميل في بث معين"""
        if stream_id not in self.active_streams:
            return False
        
        self.subscribers[stream_id].add(websocket)
        self.stats["active_connections"] = sum(len(subs) for subs in self.subscribers.values())
        
        # إرسال بيانات أولية للمشترك الجديد
        await self._send_initial_data(stream_id, websocket)
        
        logger.info("👥 New subscriber for stream %s", stream_id)
        return True
    
    async def unsubscribe(self, stream_id: str, websocket) -> bool:
        """إلغاء اشتراك عميل من بث"""
        if stream_id in self.subscribers and websocket in self.subscribers[stream_id]:
            self.subscribers[stream_id].remove(websocket)
            self.stats["active_connections"] = sum(len(subs) for subs in self.subscribers.values())
            return True
        return False
    
    # ------------------------------------------------------------------
    # Heartbeat — ping دوري كل 30 ثانية لكشف السوكيتات الميتة
    # ------------------------------------------------------------------
    def _ensure_heartbeat(self):
        """تشغيل مهمة الـ heartbeat مرة واحدة (كسول)."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def _heartbeat_loop(self):
        """إرسال {"type": "ping"} لكل المشتركين كل 30 ثانية،
        وإزالة أي سوكيت فاشل (كشف السوكيتات الميتة)."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                
                for stream_id, subscribers in list(self.subscribers.items()):
                    for websocket in list(subscribers):
                        try:
                            await websocket.send_text(json.dumps({
                                "type": "ping",
                                "timestamp": datetime.utcnow().isoformat()
                            }))
                        except Exception:
                            logger.info("Heartbeat failed for a subscriber on %s — removing", stream_id)
                            try:
                                await self.unsubscribe(stream_id, websocket)
                            except Exception:
                                subscribers.discard(websocket)
        except asyncio.CancelledError:
            logger.info("Heartbeat loop stopped")
            raise
        except Exception:
            logger.exception("Unexpected error in heartbeat loop")
    
    async def _stream_loop(self, stream_id: str):
        """الحلقة الرئيسية للبث"""
        stream_info = self.active_streams.get(stream_id)
        if not stream_info:
            return
        
        symbol = stream_info["symbol"]
        timeframe = stream_info["timeframe"]
        market = stream_info["market"]
        indicators_config = stream_info["indicators_config"]
        strategy_config = stream_info["strategy_config"]
        
        try:
            while stream_id in self.active_streams:
                # الحصول على أحدث البيانات
                data = await self._fetch_latest_data(symbol, timeframe, market)
                
                if data is not None and not data.empty:
                    # معالجة البيانات وإنشاء الرسائل
                    messages = await self._process_stream_data(
                            stream_id, data, indicators_config, strategy_config
                    )
                    
                    # إرسال الرسائل لجميع المشتركين
                    await self._broadcast_messages(stream_id, messages)
                    
                    # تحديث الإحصائيات
                    stream_info["last_update"] = datetime.utcnow()
                    stream_info["message_count"] += len(messages)
                    self.stats["total_messages_sent"] += len(messages)
                
                # الانتظار حسب الإطار الزمني
                await asyncio.sleep(self._get_stream_interval(timeframe))
                
        except asyncio.CancelledError:
            print(f"Stream {stream_id} cancelled")
        except Exception as e:
            print(f"Error in stream loop {stream_id}: {e}")
            # إعادة المحاولة بعد تأخير
            await asyncio.sleep(5)
            if stream_id in self.active_streams:
                asyncio.create_task(self._stream_loop(stream_id))
    
    async def _fetch_latest_data(
        self,
        symbol: str,
        timeframe: str,
        market: str
    ) -> Optional[pd.DataFrame]:
        """جلب أحدث البيانات"""
        try:
            # الحصول على بيانات تاريخية حديثة
            data = await self.data_service.get_historical(
                symbol=symbol,
                timeframe=timeframe,
                market=market,
                days=2  # يومين للتحليل
            )
            
            if data.empty or len(data) < 10:
                return None
            
            return data.tail(100)  # آخر 100 نقطة للتحليل
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None
    
    async def _process_stream_data(
        self,
        stream_id: str,
        data: pd.DataFrame,
        indicators_config: List[Dict[str, Any]],
        strategy_config: Dict[str, Any]
    ) -> List[StreamMessage]:
        """معالجة البيانات وإنشاء رسائل البث"""
        messages = []
        
        if data.empty:
            return messages
        
        stream_info = self.active_streams[stream_id]
        symbol = stream_info["symbol"]
        timeframe = stream_info["timeframe"]
        
        # 1. بيانات السعر
        price_message = await self._create_price_message(data, symbol, timeframe)
        messages.append(price_message)
        
        # 2. بيانات المؤشرات (إذا كانت موجودة)
        if indicators_config:
            indicator_messages = await self._create_indicator_messages(
                data, indicators_config, symbol, timeframe
            )
            messages.extend(indicator_messages)
        
        # 3. بيانات الإستراتيجية والإشارات (إذا كانت موجودة)
        if strategy_config:
            strategy_messages = await self._create_strategy_messages(
                data, strategy_config, symbol, timeframe
            )
            messages.extend(strategy_messages)
        
        # 4. رسالة حالة
        status_message = await self._create_status_message(stream_id, len(messages))
        messages.append(status_message)
        
        return messages
    
    async def _create_price_message(
        self,
        data: pd.DataFrame,
        symbol: str,
        timeframe: str
    ) -> StreamMessage:
        """إنشاء رسالة بيانات السعر"""
        latest = data.iloc[-1]
        
        price_data = PriceStreamData(
            open=float(latest['open']),
            high=float(latest['high']),
            low=float(latest['low']),
            close=float(latest['close']),
            volume=float(latest['volume']),
            timestamp=latest.name if hasattr(latest, 'name') else datetime.utcnow()
        )
        
        # تخزين في الكاش
        cache_key = f"{symbol}_{timeframe}_price"
        self.price_cache[cache_key] = price_data.dict()
        
        return StreamMessage(
            type=StreamDataType.PRICE,
            symbol=symbol,
            timeframe=timeframe,
            data=price_data.dict()
        )
    
    async def _create_indicator_messages(
        self,
        data: pd.DataFrame,
        indicators_config: List[Dict[str, Any]],
        symbol: str,
        timeframe: str
    ) -> List[StreamMessage]:
        """إنشاء رسائل المؤشرات (يتعامل دفاعياً مع dict/list/Series من apply_indicators)"""
        messages = []
        
        # حساب المؤشرات
        indicator_results = apply_indicators(
            dataframe=data,
            indicators_config=indicators_config,
            use_cache=True

        )
        
        for name, result in (indicator_results or {}).items():
            # apply_indicators يعيد dicts ({"name","values":{"data":..},..})
            # أو قوائم (مؤشرات متعددة الخطوط مثل Bollinger) — نطبّعها أولاً
            for entry in self._coerce_indicator_entries(name, result):
                indicator_message = self._build_indicator_message(entry, symbol, timeframe)
                if indicator_message is not None:
                    messages.append(indicator_message)
                    
                    # تخزين في الكاش
                    cache_key = f"{symbol}_{timeframe}_{entry['name']}"
                    self.indicator_cache[cache_key] = indicator_message.data
        
        return messages
    
    def _coerce_indicator_entries(self, name: str, result: Any) -> List[Dict[str, Any]]:
        """
        تطبيع نتيجة مؤشر إلى قائمة من:
        {"name": str, "data": List[float], "signals": Any, "metadata": dict}

        يدعم: dict مع values.data / values كـ Series / قوائم متعددة الخطوط /
        Series مباشرة / كائنات فيها .values و .signals.
        """
        entries: List[Dict[str, Any]] = []
        try:
            # 1) قائمة (مثل bollinger_bands → 3 خطوط)
            if isinstance(result, list):
                for i, item in enumerate(result):
                    sub_entries = self._coerce_indicator_entries(f"{name}_{i}", item)
                    entries.extend(sub_entries)
                return entries

            # 2) كائن له .values (IndicatorResult خام)
            if not isinstance(result, dict) and hasattr(result, "values"):
                entries.append({
                    "name": name,
                    "data": self._values_to_list(getattr(result, "values", None)),
                    "signals": getattr(result, "signals", None),
                    "metadata": getattr(result, "metadata", {}) or {},
                })
                return entries

            if not isinstance(result, dict):
                return entries

            values = result.get("values")

            # 3) values قاموس قياسي {"data": [...], ...}
            if isinstance(values, dict):
                data = values.get("data")
                if isinstance(data, (pd.Series, list, tuple)) or hasattr(data, "tolist"):
                    entries.append({
                        "name": name,
                        "data": self._values_to_list(data),
                        "signals": result.get("signals"),
                        "metadata": result.get("metadata") or {},
                    })
                return entries

            # 4) values قائمة/Series مباشرة
            if isinstance(values, (list, tuple, pd.Series)) or hasattr(values, "tolist"):
                entries.append({
                    "name": name,
                    "data": self._values_to_list(values),
                    "signals": result.get("signals"),
                    "metadata": result.get("metadata") or {},
                })
                return entries

            # 5) dict بمؤشرات فرعية (مثل {"upper": {...}, "lower": {...}})
            for key, sub_result in result.items():
                if isinstance(sub_result, dict):
                    entries.extend(self._coerce_indicator_entries(f"{name}_{key}", sub_result))
                elif isinstance(sub_result, list):
                    entries.extend(self._coerce_indicator_entries(f"{name}_{key}", sub_result))

            if not entries:
                # قد تكون values DataFrame أو شيء غير مدعوم — نحاول tolist()
                if values is not None and hasattr(values, "tolist"):
                    entries.append({
                        "name": name,
                        "data": self._values_to_list(values),
                        "signals": result.get("signals"),
                        "metadata": result.get("metadata") or {},
                    })

        except Exception:
            logger.exception("Failed to normalize indicator result for '%s'", name)
        return entries

    @staticmethod
    def _values_to_list(values: Any) -> List[Any]:
        """تحويل أي شكل قيم إلى list عادية."""
        try:
            if values is None:
                return []
            if isinstance(values, dict):
                values = values.get("data", [])
            if hasattr(values, "tolist"):
                return values.tolist()
            if isinstance(values, (list, tuple)):
                return list(values)
            return [values]
        except Exception:
            return []

    def _build_indicator_message(
        self, entry: Dict[str, Any], symbol: str, timeframe: str
    ) -> Optional[StreamMessage]:
        """بناء رسالة مؤشر من قاموس مطبّع، مع تجاهل القيم الفارغة/غير الرقمية."""
        data = entry.get("data") or []
        # آخر قيمتين رقميتين صالحتين (NaN/None تتجاهل)
        numeric = [v for v in data if isinstance(v, (int, float)) and not pd.isna(v)]
        if not numeric:
            return None

        latest_value = float(numeric[-1])
        previous_value = float(numeric[-2]) if len(numeric) > 1 else None

        # إشارة المؤشر (-1/0/1) من dict {"data": [...]}
        signal = 0
        signals = entry.get("signals")
        try:
            if isinstance(signals, dict):
                sig_data = signals.get("data") or []
                if sig_data:
                    signal = int(float(sig_data[-1]))
            elif signals is not None and not hasattr(signals, "empty"):
                signal = int(float(signals))
        except (TypeError, ValueError):
            signal = 0

        try:
            indicator_data = IndicatorStreamData(
                name=entry["name"],
                value=latest_value,
                previous_value=previous_value,
                values=numeric[-20:],  # آخر 20 قيمة صالحة للرسم
                metadata=entry.get("metadata") or {},
                signal=signal
            )
        except Exception:
            logger.exception("Failed to build IndicatorStreamData for '%s'", entry.get("name"))
            return None

        return StreamMessage(
            type=StreamDataType.INDICATOR,
            symbol=symbol,
            timeframe=timeframe,
            data=indicator_data.dict(),
            metadata={"indicator_name": entry["name"]}
        )
    
    async def _create_strategy_messages(
        self,
        data: pd.DataFrame,
        strategy_config: Dict[str, Any],
        symbol: str,
        timeframe: str
    ) -> List[StreamMessage]:
        """إنشاء رسائل الإستراتيجية والإشارات"""
        messages = []
        
        try:
            # تشغيل الإستراتيجية — run_strategy أصبح async ويجب انتظاره
            result = await run_strategy(
                data=data,
                strategy_config=strategy_config,
                live_mode=True,
                use_cache=True
            )
            
            # 1. رسائل الشروط
            for signal in (result.signals or [])[-5:]:  # آخر 5 إشارات
                condition_data = ConditionStreamData(
                    name=signal.rule_name,
                    is_met=True,
                    description=f"{signal.action.upper()} signal at {signal.price}",
                    current_value=signal.price,
                    threshold=signal.price,
                    conditions=[],  # يمكن إضافة الشروط الفرعية هنا
                    confidence=signal.strength
                )
                
                message = StreamMessage(
                    type=StreamDataType.CONDITION,
                    symbol=symbol,
                    timeframe=timeframe,
                    data=condition_data.dict(),
                    metadata={
                        "rule_name": signal.rule_name,
                        "signal_type": signal.action
                    }
                )
                messages.append(message)
            
            # 2. رسائل الإشارات (المفلترة)
            for signal in (result.filtered_signals or []):
                signal_data = SignalStreamData(
                    type="entry" if signal.action in ["buy", "sell"] else "exit",
                    action=signal.action,
                    strength=signal.strength,
                    price=signal.price,
                    timestamp=signal.timestamp,
                    conditions=[],  # يمكن إضافة الشروط هنا
                    entry_price=signal.price if signal.action == "buy" else None,
                    stop_loss=signal.price * 0.95 if signal.action == "buy" else None,
                    take_profit=signal.price * 1.1 if signal.action == "buy" else None
                )
                
                message = StreamMessage(
                    type=StreamDataType.SIGNAL,
                    symbol=symbol,
                    timeframe=timeframe,
                    data=signal_data.dict(),
                    metadata={
                        "signal_type": signal.action,
                        "rule_name": signal.rule_name
                    }
                )
                messages.append(message)
                
                # 3. إذا كانت إشارة شراء، أضف رسالة نقطة الدخول
                if signal.action == "buy":
                    entry_data = EntryPointStreamData(
                        price=signal.price,
                        stop_loss=signal.price * 0.95,
                        take_profit=signal.price * 1.1,
                        confidence=signal.strength,
                        risk_reward_ratio=3.0,
                        position_size=0.1,  # 10% من رأس المال
                        timestamp=signal.timestamp
                    )
                    
                    message = StreamMessage(
                        type=StreamDataType.ENTRY_POINT,
                        symbol=symbol,
                        timeframe=timeframe,
                        data=entry_data.dict(),
                        metadata={"entry_type": "buy"}
                    )
                    messages.append(message)
                    
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error creating strategy messages")
        
        return messages
    
    async def _create_status_message(self, stream_id: str, messages_count: int) -> StreamMessage:
        """إنشاء رسالة حالة"""
        stream_info = self.active_streams[stream_id]
        
        status_data = {
            "stream_id": stream_id,
            "status": "active",
            "uptime": (datetime.utcnow() - stream_info["start_time"]).total_seconds(),
            "messages_sent": stream_info["message_count"],
            "last_update": stream_info["last_update"].isoformat() if stream_info["last_update"] else None,
            "subscribers_count": len(self.subscribers.get(stream_id, []))
        }
        
        return StreamMessage(
            type=StreamDataType.STATUS,
            symbol=stream_info["symbol"],
            timeframe=stream_info["timeframe"],
            data=status_data
        )
    
    async def _broadcast_messages(self, stream_id: str, messages: List[StreamMessage]):
        """بث الرسائل لجميع المشتركين"""
        if stream_id not in self.subscribers or not self.subscribers[stream_id]:
            return
        
        subscribers = list(self.subscribers[stream_id])
        for message in messages:
            message_json = message.to_json()
            
            for websocket in subscribers:
                try:
                    await websocket.send_text(message_json)
                except Exception as e:
                    print(f"Error broadcasting to websocket: {e}")
                    # إزالة المشترك إذا كان هناك خطأ
                    await self.unsubscribe(stream_id, websocket)
    
    async def _send_initial_data(self, stream_id: str, websocket):
        """إرسال بيانات أولية للمشترك الجديد"""
        stream_info = self.active_streams.get(stream_id)
        if not stream_info:
            return
        
        symbol = stream_info["symbol"]
        timeframe = stream_info["timeframe"]
        
        # إرسال بيانات الكاش المخزنة
        initial_messages = []
        
        # بيانات السعر المخزنة
        price_key = f"{symbol}_{timeframe}_price"
        if price_key in self.price_cache:
            price_message = StreamMessage(
                type=StreamDataType.PRICE,
                symbol=symbol,
                timeframe=timeframe,
                data=self.price_cache[price_key]
            )
            initial_messages.append(price_message)
        
        # بيانات المؤشرات المخزنة
        for key, data in self.indicator_cache.items():
            if key.startswith(f"{symbol}_{timeframe}_"):
                indicator_name = key.replace(f"{symbol}_{timeframe}_", "")
                indicator_message = StreamMessage(
                    type=StreamDataType.INDICATOR,
                    symbol=symbol,
                    timeframe=timeframe,
                    data=data,
                    metadata={"indicator_name": indicator_name}
                )
                initial_messages.append(indicator_message)
        
        # بث الرسائل الأولية
        for message in initial_messages:
            try:
                await websocket.send_text(message.to_json())
            except Exception as e:
                logger.warning("Error sending initial data to %s: %s", getattr(message, 'symbol', '?'), e)
                break
    
    def _get_stream_interval(self, timeframe: str) -> int:
        """الحصول على فاصل البث المناسب للإطار الزمني"""
        intervals = {
            "1m": 10,     # 10 ثواني
            "5m": 30,     # 30 ثانية
            "15m": 60,    # دقيقة واحدة
            "30m": 120,   # دقيقتان
            "1h": 300,    # 5 دقائق
            "4h": 900,    # 15 دقيقة
            "1d": 3600,   # ساعة واحدة
            "1w": 7200,   # ساعتان
        }
        
        return intervals.get(timeframe, 60)
    
    def get_stream_info(self, stream_id: Optional[str] = None) -> Dict[str, Any]:
        """الحصول على معلومات البث"""
        if stream_id:
            if stream_id in self.active_streams:
                return {
                    **self.active_streams[stream_id],
                    "subscribers_count": len(self.subscribers.get(stream_id, []))
                }
            return {}
        
        # جميع البثوث
        streams_info = {}
        for sid, info in self.active_streams.items():
            streams_info[sid] = {
                **info,
                "subscribers_count": len(self.subscribers.get(sid, []))
            }
        
        return {
            "active_streams": streams_info,
            "stats": self.stats,
            "total_streams": len(self.active_streams)
        }