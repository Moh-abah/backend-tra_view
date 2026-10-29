# app/core/streaming/market_stream.py
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Awaitable
import aiohttp
import json
from collections import defaultdict

class MarketDataStreamer:
    """بث بيانات السوق مع تجميع حسب timeframe"""
    
    def __init__(self):
        self._streams: Dict[str, Dict] = defaultdict(dict)
        self._candle_buffers: Dict[str, List] = defaultdict(list)
        self._on_candle_close_callbacks = defaultdict(list)
        
    async def start_stream(
        self,
        symbol: str,
        timeframe: str,
        on_candle_close: Optional[Callable[[Dict], Awaitable[None]]] = None
    ):
        """بدء بث لرمز معين"""
        stream_key = f"{symbol}_{timeframe}"
        
        if stream_key in self._streams:
            return  # البث يعمل بالفعل
        
        if on_candle_close:
            self._on_candle_close_callbacks[stream_key].append(on_candle_close)
        
        # بدء مهمة البث
        task = asyncio.create_task(
            self._stream_task(symbol, timeframe)
        )
        
        self._streams[stream_key] = {
            "task": task,
            "symbol": symbol,
            "timeframe": timeframe,
            "started_at": datetime.utcnow()
        }
        
        print(f"📡 بدء البث لـ {symbol} ({timeframe})")
    
    async def _stream_task(self, symbol: str, timeframe: str):
        """مهمة البث الرئيسية"""
        stream_key = f"{symbol}_{timeframe}"
        timeframe_minutes = self._parse_timeframe(timeframe)
        
        # اتصال WebSocket بـ Binance
        ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@trade"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(ws_url) as websocket:
                    current_candle = None
                    candle_start_time = None
                    
                    async for msg in websocket:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            
                            # استخراج بيانات الصفقة
                            trade_data = {
                                "price": float(data['p']),
                                "volume": float(data['q']),
                                "timestamp": datetime.fromtimestamp(data['T'] / 1000),
                                "symbol": symbol
                            }
                            
                            # تجميع في شموع
                            current_candle = await self._aggregate_to_candle(
                                trade_data, 
                                timeframe_minutes,
                                current_candle,
                                candle_start_time
                            )
                            
                            if current_candle and current_candle.get('closed', False):
                                # إغلاق الشمعة - استدعاء callbacks
                                await self._notify_candle_close(
                                    stream_key, 
                                    current_candle
                                )
                                current_candle = None
                                
            except Exception as e:
                print(f"❌ خطأ في بث {symbol}: {e}")
                await asyncio.sleep(5)
                # إعادة المحاولة
                await self.start_stream(symbol, timeframe)
    
    async def _aggregate_to_candle(
        self,
        trade: Dict,
        timeframe_minutes: int,
        current_candle: Optional[Dict],
        candle_start_time: Optional[datetime]
    ) -> Optional[Dict]:
        """تجميع الصفقات في شمعة"""
        trade_time = trade['timestamp']
        
        if not current_candle:
            # بدء شمعة جديدة
            candle_start_time = self._align_to_timeframe(trade_time, timeframe_minutes)
            
            return {
                'open': trade['price'],
                'high': trade['price'],
                'low': trade['price'],
                'close': trade['price'],
                'volume': trade['volume'],
                'timestamp': candle_start_time.isoformat(),
                'closed': False,
                'trades': 1
            }
        
        # تحديث الشمعة الحالية
        current_candle['high'] = max(current_candle['high'], trade['price'])
        current_candle['low'] = min(current_candle['low'], trade['price'])
        current_candle['close'] = trade['price']
        current_candle['volume'] += trade['volume']
        current_candle['trades'] += 1
        
        # التحقق إذا حان وقت إغلاق الشمعة
        candle_end_time = candle_start_time + timedelta(minutes=timeframe_minutes)
        
        if trade_time >= candle_end_time:
            current_candle['closed'] = True
            current_candle['close_time'] = candle_end_time.isoformat()
        
        return current_candle
    
    async def _notify_candle_close(self, stream_key: str, candle: Dict):
        """إشعار جميع المشتركين بإغلاق الشمعة"""
        if stream_key in self._on_candle_close_callbacks:
            for callback in self._on_candle_close_callbacks[stream_key]:
                try:
                    await callback(candle)
                except Exception as e:
                    print(f"Error in candle close callback: {e}")