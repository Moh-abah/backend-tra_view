# app/services/live_monitor.py
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Set
import websockets

class LiveIndicatorMonitor:
    """
    النظام المركزي لإدارة المراقبة الحي للمؤشرات
    - يراقب الرموز النشطة
    - يحفظ حالة كل رمز
    - يبث التحديثات للمتصفحات
    """
    
    def __init__(self):
        # تخزين الحالة: {symbol: {indicators: [], clients: [], last_data: {}, ...}}
        self.active_symbols: Dict[str, Dict] = {}
        
        # المهام النشطة (لتتمكن من إيقافها)
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        
        # اتصالات WebSocket للمتصفحات
        self.websocket_clients: Set = set()
    
    async def add_symbol_for_monitoring(self, symbol: str, timeframe: str, 
                                       indicators: List[Dict], initial_data: Dict = None):
        """
        إضافة رمز للمراقبة الحي
        """
        
        if symbol in self.active_symbols:
            # الرمز مراقب بالفعل، تحديث المؤشرات فقط
            self.active_symbols[symbol]['indicators'] = indicators
            self.active_symbols[symbol]['timeframe'] = timeframe
            self.active_symbols[symbol]['last_data'] = initial_data
        else:
            # إضافة رمز جديد
            self.active_symbols[symbol] = {
                'symbol': symbol,
                'timeframe': timeframe,
                'indicators': indicators,
                'clients': [],  # قائمة WebSockets المتصلة
                'last_data': initial_data,  # آخر بيانات تاريخية
                'last_update': datetime.utcnow(),
                'is_active': True
            }
            
            # بدء مراقبة الرمز في الخلفية
            self.monitoring_tasks[symbol] = asyncio.create_task(
                self._monitor_symbol(symbol, timeframe)
            )
            
            print(f"✅ بدء المراقبة الحي لـ {symbol} على {timeframe}")
            print(f"   المؤشرات: {[ind.get('name') for ind in indicators]}")
    
    async def _monitor_symbol(self, symbol: str, timeframe: str):
        """
        مراقبة الرمز في الخلفية (تعمل باستمرار)
        """
        binance_ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{timeframe}"
        
        while True:
            try:
                async with websockets.connect(binance_ws_url) as ws:
                    print(f"📡 متصل بـ Binance WebSocket لـ {symbol}")
                    
                    async for message in ws:
                        if symbol not in self.active_symbols:
                            break  # توقف إذا تم إزالة الرمز
                        
                        # معالجة البيانات
                        kline_data = json.loads(message)
                        await self._process_new_candle(symbol, kline_data)
                        
            except Exception as e:
                print(f"⚠️ خطأ في مراقبة {symbol}: {e}")
                await asyncio.sleep(5)  # انتظار قبل إعادة المحاولة
    
    async def _process_new_candle(self, symbol: str, kline_data: dict):
        """
        معالجة شمعة جديدة من Binance
        """
        k = kline_data['k']
        
        # فقط عند اكتمال الشمعة
        if k['x']:  # is_closed
            candle_data = {
                'timestamp': datetime.fromtimestamp(k['t'] / 1000),
                'open': float(k['o']),
                'high': float(k['h']),
                'low': float(k['l']),
                'close': float(k['c']),
                'volume': float(k['v']),
                'complete': True
            }
            
            # 1. تحديث البيانات الأخيرة
            if symbol in self.active_symbols:
                # إضافة الشمعة الجديدة للبيانات التاريخية
                if self.active_symbols[symbol]['last_data'] and 'data' in self.active_symbols[symbol]['last_data']:
                    self.active_symbols[symbol]['last_data']['data'].append(candle_data)
                    
                    # الحفاظ على حجم معقول (آخر 1000 شمعة)
                    if len(self.active_symbols[symbol]['last_data']['data']) > 1000:
                        self.active_symbols[symbol]['last_data']['data'].pop(0)
                
                # 2. إعادة حساب المؤشرات مع البيانات الجديدة
                await self._recalculate_indicators(symbol, candle_data)
                
                # 3. إرسال التحديث لجميع المتصفحات المتصلة
                await self._broadcast_update(symbol)
    
    async def _recalculate_indicators(self, symbol: str, new_candle: dict):
        """
        إعادة حساب المؤشرات مع الشمعة الجديدة
        """
        from app.services.data_service import DataService
        from app.database import get_db
        
        if symbol not in self.active_symbols:
            return
        
        config = self.active_symbols[symbol]
        
        try:
            # استخدام DataService لإعادة الحساب
            async with get_db() as db:
                data_service = DataService(db)
                
                # نطلب آخر 50 شمعة فقط (لكفاءة الأداء)
                latest_data = await data_service.get_data_with_indicators(
                    symbol=symbol,
                    timeframe=config['timeframe'],
                    market="crypto",
                    indicators_config=config['indicators'],
                    days=1  # فقط آخر يوم للأداء
                )
                
                # حفظ البيانات المحدثة
                config['last_data'] = latest_data
                config['last_update'] = datetime.utcnow()
                
        except Exception as e:
            print(f"⚠️ خطأ في إعادة حساب المؤشرات لـ {symbol}: {e}")
    
    async def _broadcast_update(self, symbol: str):
        """
        إرسال التحديث لجميع المتصفحات المتصلة
        """
        if symbol not in self.active_symbols:
            return
        
        config = self.active_symbols[symbol]
        latest_data = config.get('last_data', {})
        
        # إرسال لجميع العملاء المتصلين
        for client in config['clients']:
            try:
                update_msg = {
                    'type': 'live_update',
                    'symbol': symbol,
                    'timestamp': datetime.utcnow().isoformat(),
                    'data': latest_data
                }
                
                await client.send_json(update_msg)
                
            except Exception as e:
                print(f"⚠️ خطأ في إرسال تحديث لـ {symbol}: {e}")
                # إزالة العميل إذا لم يعد متصلاً
                config['clients'].remove(client)
    
    async def add_websocket_client(self, symbol: str, websocket):
        """
        إضافة متصفح للاستماع للتحديثات
        """
        if symbol in self.active_symbols:
            self.active_symbols[symbol]['clients'].append(websocket)
            
            # إرسال البيانات الحالية فوراً
            if self.active_symbols[symbol]['last_data']:
                await websocket.send_json({
                    'type': 'current_state',
                    'symbol': symbol,
                    'data': self.active_symbols[symbol]['last_data']
                })
    
    def remove_websocket_client(self, symbol: str, websocket):
        """
        إزالة متصفح من القائمة
        """
        if symbol in self.active_symbols and websocket in self.active_symbols[symbol]['clients']:
            self.active_symbols[symbol]['clients'].remove(websocket)

# إنشاء نسخة وحيدة للنظام
live_monitor = LiveIndicatorMonitor()