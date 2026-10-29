# \app\websocket\chart_ws.py

import asyncio
import json
import logging
import sqlite3
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.live_stream import live_stream_manager
from app.core.managers import chart_manager
from app.schemas.indicators import ChartSubscription, IndicatorConfig

logger = logging.getLogger(__name__)
router = APIRouter()

class ChartStateDB:
    """قاعدة بيانات لحفظ حالة الشارت والمؤشرات"""
    GLOBAL_KEY = "GLOBAL_USER_INDICATORS"
    def __init__(self, db_path: str = "chart_states.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """تهيئة قاعدة البيانات وإنشاء الجداول"""
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # جدول لحالة الشارت
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chart_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chart_key TEXT UNIQUE NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                indicators TEXT NOT NULL,  -- JSON list of indicators
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول للتاريخ (للاحتفاظ بأكثر من حالة لكل شارت)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chart_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chart_key TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                indicators TEXT NOT NULL,
                saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Database initialized at {self.db_path}")

    def save_global_indicators(self, indicators: List[Dict]) -> bool:
        """حفظ المؤشرات بشكل عام لتطبيقها على جميع الشارتات"""
        try:
            indicators_json = json.dumps(indicators)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # نستخدم المفتاح الثابت "GLOBAL_USER_INDICATORS"
            cursor.execute('''
                INSERT OR REPLACE INTO chart_states 
                (chart_key, symbol, timeframe, indicators, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (self.GLOBAL_KEY, "GLOBAL", "GLOBAL", indicators_json))
            
            conn.commit()
            conn.close()
            logger.info(f"💾 Saved {len(indicators)} global indicators")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save global indicators: {e}")
            return False
    
    def load_global_indicators(self) -> Optional[List[Dict]]:
        """تحميل المؤشرات العامة المحفوظة"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT indicators FROM chart_states 
                WHERE chart_key = ? 
                ORDER BY last_updated DESC 
                LIMIT 1
            ''', (self.GLOBAL_KEY,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                indicators = json.loads(result[0])
                logger.info(f"📂 Loaded global indicators: {len(indicators)} indicators")
                return indicators
            return None
        except Exception as e:
            logger.error(f"❌ Failed to load global indicators: {e}")
            return None
 
    
    def generate_chart_key(self, symbol: str, timeframe: str) -> str:
        """إنشاء مفتاح فريد للشارت"""
        key_str = f"{symbol}_{timeframe}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def save_chart_state(self, symbol: str, timeframe: str, indicators: List[Dict]) -> bool:
        """حفظ حالة الشارت والمؤشرات"""
        try:
            chart_key = self.generate_chart_key(symbol, timeframe)
            indicators_json = json.dumps(indicators)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # حفظ أو تحديث الحالة الحالية
            cursor.execute('''
                INSERT OR REPLACE INTO chart_states 
                (chart_key, symbol, timeframe, indicators, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (chart_key, symbol, timeframe, indicators_json))
            
            # حفظ نسخة في التاريخ (احتفاظ بالسجل)
            cursor.execute('''
                INSERT INTO chart_history (chart_key, symbol, timeframe, indicators)
                VALUES (?, ?, ?, ?)
            ''', (chart_key, symbol, timeframe, indicators_json))
            
            # الاحتفاظ فقط بآخر 10 سجلات لكل شارت
            cursor.execute('''
                DELETE FROM chart_history 
                WHERE id NOT IN (
                    SELECT id FROM chart_history 
                    WHERE chart_key = ? 
                    ORDER BY saved_at DESC 
                    LIMIT 10
                ) AND chart_key = ?
            ''', (chart_key, chart_key))
            
            conn.commit()
            conn.close()
            logger.info(f"💾 Saved chart state for {symbol}/{timeframe} with {len(indicators)} indicators")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save chart state: {e}")
            return False
    
    def load_chart_state(self, symbol: str, timeframe: str) -> Optional[List[Dict]]:
        """تحميل حالة الشارت والمؤشرات المحفوظة"""
        try:
            chart_key = self.generate_chart_key(symbol, timeframe)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT indicators FROM chart_states 
                WHERE chart_key = ? 
                ORDER BY last_updated DESC 
                LIMIT 1
            ''', (chart_key,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                indicators = json.loads(result[0])
                logger.info(f"📂 Loaded chart state for {symbol}/{timeframe}: {len(indicators)} indicators")
                return indicators
            return None
        except Exception as e:
            logger.error(f"❌ Failed to load chart state: {e}")
            return None
    
    def get_all_chart_states(self) -> Dict[str, Any]:
        """الحصول على جميع حالات الشارت المحفوظة"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT symbol, timeframe, indicators, last_updated 
                FROM chart_states 
                ORDER BY last_updated DESC
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            states = {}
            for symbol, timeframe, indicators_json, last_updated in results:
                key = f"{symbol}_{timeframe}"
                states[key] = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "indicators": json.loads(indicators_json),
                    "last_updated": last_updated
                }
            
            return states
        except Exception as e:
            logger.error(f"❌ Failed to get all chart states: {e}")
            return {}
    
    def cleanup_old_states(self, days_old: int = 30):
        """تنظيف الحالات القديمة"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM chart_history 
                WHERE saved_at < datetime('now', ?)
            ''', (f'-{days_old} days',))
            
            cursor.execute('''
                DELETE FROM chart_states 
                WHERE last_updated < datetime('now', ?)
            ''', (f'-{days_old} days',))
            
            conn.commit()
            conn.close()
            logger.info(f"🧹 Cleaned up chart states older than {days_old} days")
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old states: {e}")

# إنشاء مثيل قاعدة البيانات
chart_state_db = ChartStateDB()

class WebSocketManager:
    """مدير اتصالات WebSocket"""
    
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        self.chart_manager = chart_manager
    
    async def connect(self, websocket: WebSocket, connection_id: str, symbol: str, timeframe: str):
        """إضافة اتصال جديد"""
        key = f"{symbol}_{timeframe}"
        if key not in self.active_connections:
            self.active_connections[key] = {}
        
        self.active_connections[key][connection_id] = websocket
        
        # إضافة المشترك للشارت
        chart = await self.chart_manager.get_or_create_chart(symbol, timeframe)
        chart.subscribers.add(connection_id)
        
        return key
    
    async def disconnect(self, connection_id: str, symbol: str, timeframe: str):
        """إزالة اتصال"""
        key = f"{symbol}_{timeframe}"
        
        if key in self.active_connections and connection_id in self.active_connections[key]:
            del self.active_connections[key][connection_id]
            
            # إذا لم يكن هناك اتصالات، تنظيف
            if not self.active_connections[key]:
                del self.active_connections[key]
                await self.chart_manager.cleanup(symbol, timeframe)
        
        # إزالة من المشتركين
        chart_key = self.chart_manager.get_chart_key(symbol, timeframe)
        if chart_key in self.chart_manager.charts:
            self.chart_manager.charts[chart_key].subscribers.discard(connection_id)
    
    async def send_to_connection(self, connection_id: str, key: str, message: Dict):
        """إرسال رسالة لاتصال محدد"""
        if key in self.active_connections and connection_id in self.active_connections[key]:
            try:
                await self.active_connections[key][connection_id].send_json(message)
            except Exception as e:
                logger.error(f"❌ Error sending to connection {connection_id}: {e}")
                await self.disconnect(connection_id, *key.split("_"))
    
    async def broadcast(self, key: str, message: Dict, exclude: Optional[str] = None):
        """بث رسالة لجميع المشتركين"""
        if key not in self.active_connections:
            return
        
        tasks = []
        for conn_id, websocket in self.active_connections[key].items():
            if conn_id == exclude:
                continue
            
            try:
                tasks.append(websocket.send_json(message))
            except Exception as e:
                logger.error(f"❌ Error broadcasting to {conn_id}: {e}")
                # تنظيف الاتصال الفاشل
                asyncio.create_task(self.disconnect(conn_id, *key.split("_")))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

# المثيل العام
ws_manager = WebSocketManager()

async def load_saved_indicators(symbol: str, timeframe: str) -> List[Dict]:
    """تحميل المؤشرات المحفوظة للشارت (sqlite متزامن → to_thread حتى لا يسد الـ loop)"""
    saved_indicators = await asyncio.to_thread(chart_state_db.load_chart_state, symbol, timeframe)
    if saved_indicators:
        logger.info(f"📂 Loaded {len(saved_indicators)} saved indicators for {symbol}/{timeframe}")
        return saved_indicators
    return []

async def save_current_indicators(symbol: str, timeframe: str, chart_manager):
    """حفظ المؤشرات الحالية للشارت"""
    try:
        chart_key = chart_manager.get_chart_key(symbol, timeframe)
        if chart_key not in chart_manager.charts:
            logger.warning(f"Chart {chart_key} not found")
            return False
            
        chart = chart_manager.charts[chart_key]
        indicators = []
        
        # الطريقة 1: البحث في indicators_results
        if hasattr(chart, 'indicators_results') and chart.indicators_results:
            for indicator_name, indicator_data in chart.indicators_results.items():
                try:
                    indicator_info = {
                        "name": indicator_name,
                        "type": indicator_data.get("type", "trend"),
                        "params": indicator_data.get("params", {})
                    }
                    indicators.append(indicator_info)
                except Exception as e:
                    logger.warning(f"Could not process indicator {indicator_name}: {e}")
        
        # الطريقة 2: البحث في indicators إذا كانت قائمة
        elif hasattr(chart, 'indicators') and isinstance(chart.indicators, list):
            for indicator in chart.indicators:
                if isinstance(indicator, dict):
                    indicator_info = {
                        "name": indicator.get("name"),
                        "type": indicator.get("type", "trend"),
                        "params": indicator.get("params", {})
                    }
                    indicators.append(indicator_info)
        
        # الطريقة 3: البحث في active_indicators
        elif hasattr(chart, 'active_indicators') and isinstance(chart.active_indicators, dict):
            for indicator_name, indicator_config in chart.active_indicators.items():
                if isinstance(indicator_config, dict):
                    indicator_info = {
                        "name": indicator_name,
                        "type": indicator_config.get("type", "trend"),
                        "params": indicator_config.get("params", {})
                    }
                    indicators.append(indicator_info)
        
        # حفظ في قاعدة البيانات
        if indicators:
            await asyncio.to_thread(chart_state_db.save_chart_state, symbol, timeframe, indicators)
            logger.info(f"💾 Saved {len(indicators)} indicators for {symbol}/{timeframe}")
            return True
        else:
            # إذا لم نجد أي مؤشرات، نحفظ قائمة فارغة
            await asyncio.to_thread(chart_state_db.save_chart_state, symbol, timeframe, [])
            logger.info(f"💾 Saved empty indicators list for {symbol}/{timeframe}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Failed to save indicators: {e}")
        import traceback
        logger.error(traceback.format_exc())
    return False

@router.websocket("/chart/{symbol}")
async def chart_websocket(websocket: WebSocket, symbol: str):
    """WebSocket للشارت الحي"""
    await websocket.accept()
    connection_id = str(uuid4())
    key = None
    saved_indicators_task = None
    on_close_callback = None
    
    try:
        # 1. تهيئة النظام
        await chart_manager.initialize()
        chart_manager.set_ws_manager(ws_manager)
        
        # استقبال بيانات التهيئة
        init_data = await websocket.receive_json()
        timeframe = init_data.get("timeframe", "1m")
        requested_indicators = init_data.get("indicators", [])
        
        logger.info(f"📩 Received Init: {symbol} | TF: {timeframe} | Requested Indicators: {len(requested_indicators)}")
        
        # 2. تحميل المؤشرات المحفوظة إذا لم يتم إرسال مؤشرات جديدة
        # indicators_to_use = requested_indicators
        # using_saved_indicators = False

        # if not requested_indicators:
        #     saved_indicators = await load_saved_indicators(symbol, timeframe)
        #     if saved_indicators:
        #         indicators_to_use = saved_indicators
        #         using_saved_indicators = True
        #         logger.info(f"🔄 Using saved indicators: {len(saved_indicators)} indicators")


        # 2. تحميل المؤشرات المحفوظة (العامة) إذا لم يتم إرسال مؤشرات جديدة
        indicators_to_use = requested_indicators
        using_saved_indicators = False

        if not requested_indicators:
            # ✅ التعديل: التغيير إلى load_global_indicators
            saved_indicators = await asyncio.to_thread(chart_state_db.load_global_indicators)
            if saved_indicators:
                indicators_to_use = saved_indicators
                using_saved_indicators = True
                logger.info(f"🔄 Using GLOBAL saved indicators: {len(saved_indicators)} indicators")

        # 3. إنشاء الشارت
        chart = await chart_manager.get_or_create_chart(symbol, timeframe, market=init_data.get("market", "crypto"))
        
        # 4. إنشاء كائن الاشتراك
        subscription = ChartSubscription(
            symbol=symbol,
            timeframe=timeframe,
            market=init_data.get("market", "crypto"),
            indicators=indicators_to_use
        )
        
        # 5. الاتصال بـ WebSocket Manager
        key = await ws_manager.connect(websocket, connection_id, symbol, timeframe)
        
        # 6. إضافة المؤشرات المحفوظة  
        for indicator_config in indicators_to_use:
            try:
                if isinstance(indicator_config, dict):
                    await chart_manager.add_indicator(symbol, timeframe, indicator_config)
                elif hasattr(indicator_config, 'dict'):
                    await chart_manager.add_indicator(symbol, timeframe, indicator_config.dict())
            except Exception as e:
                logger.error(f"⚠️ Failed to add indicator {indicator_config}: {e}")
        
        def _now_ms():
            return int(datetime.utcnow().timestamp() * 1000)
        
        logger.info(f"✅ New connection: {connection_id} for {key} with {len(indicators_to_use)} indicators")
        
        # 7. إضافة callback لإغلاق الشمعة (نحتفظ بمرجع له لإزالته عند تغيير الفريم/القطع)
        def create_broadcast_callback(conn_id: str, chart_key: str):
            async def broadcast_on_close(candle_data: Dict, chart_state):
                # حفظ المؤشرات الحالية عند إغلاق الشمعة
                await save_current_indicators(chart_state.symbol, chart_state.timeframe, chart_manager)
                
                # الحصول على بيانات الشارت المحدثة
                chart_data = await chart_manager.get_chart_data(
                    chart_state.symbol, chart_state.timeframe
                )
                
                # بث التحديث لجميع المشتركين
                await ws_manager.broadcast(chart_key, {
                    "type": "candle_close",
                    "symbol": chart_state.symbol,
                    "timeframe": chart_state.timeframe,
                    "candle": candle_data,
                    "indicators": chart_state.indicators_results,
                    "time": _now_ms()
                }, exclude=conn_id)
            
            return broadcast_on_close
        
        on_close_callback = create_broadcast_callback(connection_id, key)
        chart_manager.add_on_close_callback(
            subscription.symbol,
            subscription.timeframe,
            on_close_callback
        )
       
        # 8. إرسال البيانات الأولية
        chart_data = await chart_manager.get_chart_data(symbol, timeframe)
        
        await websocket.send_json({
            "type": "chart_initialized",
            "symbol": subscription.symbol,
            "timeframe": subscription.timeframe,
            "market": subscription.market,
            "data": chart_data,
            "saved_indicators_used": not bool(requested_indicators) and bool(indicators_to_use),
            "indicators_count": len(indicators_to_use),
            "time": _now_ms()
        })


        # 9. إذا كنا نستخدم مؤشرات محفوظة، نرسل indicator_added بعد 3 ثواني

        if using_saved_indicators:
            # إنشاء مهمة منفصلة لإرسال indicator_added بعد تأخير
            async def send_saved_indicators():
                try:
                    await asyncio.sleep(3)  # انتظار 3 ثواني
                    chart_data = await chart_manager.get_chart_data(symbol, timeframe)
                    indicators_results = chart_data.get("indicators_results", {})
                    for indicator_config in indicators_to_use:
                        indicator_dict = indicator_config if isinstance(indicator_config, dict) else indicator_config.dict()
                        indicator_name = indicator_dict.get("name", "unknown")

                        
                        await asyncio.sleep(0.5)

                        indicator_data = {}
                        if indicator_name in indicators_results:
                            indicator_data = {
                                indicator_name: indicators_results[indicator_name]
                            }                        
                        await websocket.send_json({
                            "type": "indicator_added",
                            "indicator": indicator_name,
                            "indicators_results": indicator_data,
                            "saved": True,
                            "time": _now_ms()
                        })
                        logger.info(f"✅ Sent indicator_added for saved indicator: {indicator_name}")
                
                # ✅ إضافة: هذه الأهم لإيقاف المهمة بهدوء عند إغلاق الاتصال
                except asyncio.CancelledError:
                    pass 
                
                except Exception as e:
                    logger.error(f"❌ Failed to send saved indicators: {e}")
            
            # ✅ تعديل: ربط المهمة بالمتحول saved_indicators_task
            saved_indicators_task = asyncio.create_task(send_saved_indicators())
                
        # 9. حلقة معالجة الرسائل
        while True:
            try:
                data = await websocket.receive_json()
                action = data.get("action")
                
                if action == "add_indicator":
                    # إضافة مؤشر جديد
                    indicator_config = data.get("indicator")
                    if not indicator_config:
                        continue

                    indicator_dict = indicator_config.dict() if hasattr(indicator_config, 'dict') else indicator_config                    
                    success = await chart_manager.add_indicator(symbol, timeframe, indicator_dict)

                    if success:
                        current_chart_data = await chart_manager.get_chart_data(symbol, timeframe)
                        await asyncio.to_thread(
                            chart_state_db.save_global_indicators,
                            current_chart_data.get("indicators", [])
                        )
                        # حفظ الحالة الحالية بعد إضافة المؤشر
                        # await save_current_indicators(symbol, timeframe, chart_manager)
                    
                        updated_data = await chart_manager.get_chart_data(symbol, timeframe)
                        await websocket.send_json({
                            "type": "indicator_added",
                            "indicator": indicator_dict.get("name"),
                            "indicators_results": updated_data["indicators_results"],
                            "saved": True,  # تم الحفظ تلقائياً
                            "time": _now_ms()
                        })
                        logger.info(f"✅ Indicator {indicator_dict.get('name')} added and saved for {symbol}")
                
                elif action == "remove_indicator":
                    # إزالة مؤشر
                    indicator_name = data.get("indicator_name")
                    if indicator_name:
                        success = await chart_manager.remove_indicator(symbol, timeframe, indicator_name)
                        if success:

                            current_chart_data = await chart_manager.get_chart_data(symbol, timeframe)

                            chart_indicators = current_chart_data.get("indicators", {})

                            if indicator_name in chart_indicators:
                                del chart_indicators[indicator_name] 
                                print(f"🗑️ [WS] Force removed {indicator_name} from DB snapshot")
                        
                            
                            await asyncio.to_thread(chart_state_db.save_global_indicators, chart_indicators)
                            # حفظ الحالة بعد الإزالة
                       
                            await websocket.send_json({
                                "type": "indicator_removed",
                                "indicators_results": current_chart_data.get("indicators_results", {}),
                                "indicator": indicator_name,
                                "saved": True,
                                "time": _now_ms()
                            })

                elif action == "update_indicator":
                    # ✅ إضافة جديدة: تعديل معلمات مؤشر موجود
                    indicator_name = data.get("name")
                    new_params = data.get("params")
                    
                    if indicator_name and new_params:
                        success = await chart_manager.update_indicator(symbol, timeframe, indicator_name, new_params)
                        if success:
                            # ✅ حفظ التعديل في القائمة العامة
                            current_chart_data = await chart_manager.get_chart_data(symbol, timeframe)
                            await asyncio.to_thread(
                                chart_state_db.save_global_indicators,
                                current_chart_data.get("indicators", [])
                            )
                            
                            await websocket.send_json({
                                "type": "indicator_updated",
                                "indicator": indicator_name,
                                "params": new_params,
                                "indicators_results": current_chart_data["indicators_results"],
                                "time": _now_ms()
                            })


                elif action == "save_indicators":
                    # طلب حفظ يدوي للمؤشرات
                    success = await save_current_indicators(symbol, timeframe, chart_manager)
                    await websocket.send_json({
                        "type": "indicators_saved",
                        "success": success,
                        "message": "Indicators saved successfully" if success else "Failed to save indicators",
                        "time": _now_ms()
                    })
                
                elif action == "load_indicators":
                    # طلب تحميل المؤشرات المحفوظة
                    saved_indicators = await load_saved_indicators(symbol, timeframe)
                    await websocket.send_json({
                        "type": "saved_indicators",
                        "indicators": saved_indicators,
                        "count": len(saved_indicators),
                        "time": _now_ms()
                    })
                
                elif action == "clear_indicators":
                    # مسح جميع المؤشرات المحفوظة
                    await asyncio.to_thread(chart_state_db.save_global_indicators, [])
                   
                    await chart_manager.clear_indicators(symbol, timeframe)
                    await websocket.send_json({
                        "type": "indicators_cleared",
                        "message": "All indicators cleared and saved",
                        "time": _now_ms()
                    })
                
                elif action == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "time": _now_ms()
                    })
                
                # elif action == "update_timeframe":
                #     new_timeframe = data.get("new_timeframe")
                #     if new_timeframe:
                #         # حفظ الحالة الحالية قبل التغيير
                #         await save_current_indicators(symbol, timeframe, chart_manager)
                        
                #         await websocket.send_json({
                #             "type": "timeframe_changed",
                #             "old_timeframe": timeframe,
                #             "new_timeframe": new_timeframe,
                #             "saved": True,
                #             "time": _now_ms()
                #         })
                elif action == "update_timeframe":
                    new_timeframe = data.get("new_timeframe")
                    if new_timeframe:
                        # 1. حفظ المؤشرات الحالية في القائمة العامة (ضمان التحديث)
                        current_chart_data = await chart_manager.get_chart_data(symbol, timeframe)
                        await asyncio.to_thread(
                            chart_state_db.save_global_indicators,
                            current_chart_data.get("indicators", [])
                        )
                        
                        # 2. إزالة callback الشمعة-المغلقة القديم قبل ترك الشارت القديم (منع التسريب)
                        chart_manager.remove_on_close_callback(symbol, timeframe, on_close_callback)
                        
                        # 3. فصل الاتصال عن الشارت القديم ( Cleanup )
                        await ws_manager.disconnect(connection_id, symbol, timeframe)
                        
                        # 4. تحديث متغير الفريم
                        timeframe = new_timeframe
                        
                        # 5. الحصول على أو إنشاء الشارت الجديد
                        chart = await chart_manager.get_or_create_chart(symbol, timeframe, market="crypto")
                        
                        # 6. إعادة الاشتراك في الاتصال بالفاتش سوكيت مانجر
                        key = await ws_manager.connect(websocket, connection_id, symbol, timeframe)
                        
                        # 7. جلب المؤشرات العامة وتطبيقها على الشارت الجديد
                        global_indicators = await asyncio.to_thread(chart_state_db.load_global_indicators)
                        applied_count = 0
                        if global_indicators:
                            for indicator_config in global_indicators:
                                try:
                                    await chart_manager.add_indicator(symbol, timeframe, indicator_config)
                                    applied_count += 1
                                except Exception as e:
                                    logger.error(f"⚠️ Failed to load indicator {indicator_config.get('name')} on TF switch: {e}")
                        
                        # 8. إعادة تعيين الـ Callback للشموع المغلقة للشارت الجديد (استبدال، لا تراكم)
                        on_close_callback = create_broadcast_callback(connection_id, key)
                        chart_manager.add_on_close_callback(
                            symbol,
                            timeframe,
                            on_close_callback
                        )
                        
                        # 9. إرسال البيانات المحدثة للفرونت إند
                        fresh_data = await chart_manager.get_chart_data(symbol, timeframe)
                        await websocket.send_json({
                            "type": "timeframe_changed",
                            "old_timeframe": data.get("old_timeframe"), # أو القيمة القديمة المخزنة
                            "new_timeframe": new_timeframe,
                            "symbol": symbol,
                            "data": fresh_data,
                            "indicators_applied": applied_count,
                            "time": _now_ms()
                        })
                        logger.info(f"🔄 Switched to {new_timeframe}, applied {applied_count} global indicators.")                
                elif data.get("type") == "price_update":
                    if chart.live_candle:
                        candle_data = chart.live_candle.copy()
                        last_time = chart.candles[-1]["time"] if chart.candles else 0
                        if candle_data["time"] <= last_time:
                            candle_data["time"] = last_time + 1
                        
                        await ws_manager.broadcast(key, {
                            "type": "price_update",
                            "live_candle": candle_data,
                            "indicators": chart.indicators_results,
                            "time": _now_ms()
                        })
                    
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON decode error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format",
                    "time": _now_ms()
                })

            except Exception as e:
                # الانقطاع الطبيعي للعميل (1000/1001) ليس خطأ — سجل هادئ بدون إزعاج
                code = getattr(e, "rc", None) or getattr(e, "code", None)
                e_str = str(e)
                is_normal_close = (
                    isinstance(e, WebSocketDisconnect)
                    or code in (1000, 1001, 1005, 1006)
                    or "(1001" in e_str
                    or "(1000" in e_str
                )
                if is_normal_close:
                    logger.info(f"🔴 Chart WS client disconnected: {connection_id} ({e_str})")
                else:
                    logger.error(f"⚠️ Error processing message: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"🔴 Disconnected: {connection_id}")
        # حفظ المؤشرات عند انقطاع الاتصال
        if key:
            await save_current_indicators(symbol, timeframe, chart_manager)
        
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        
    finally:
        # التنظيف
        if saved_indicators_task and not saved_indicators_task.done():
            saved_indicators_task.cancel()
        # إزالة callback الإغلاق الخاص بهذا الاتصال (منع تسريب callbacks)
        try:
            if on_close_callback is not None:
                chart_manager.remove_on_close_callback(symbol, timeframe, on_close_callback)
        except Exception:
            pass
        if key:
            await ws_manager.disconnect(connection_id, symbol, timeframe)
            logger.info(f"🧹 Cleaned up connection: {connection_id}")

@router.get("/chart-states")
async def get_chart_states():
    """واجهة للحصول على جميع حالات الشارت المحفوظة (للتطوير فقط)"""
    states = await asyncio.to_thread(chart_state_db.get_all_chart_states)
    return {
        "success": True,
        "count": len(states),
        "states": states
    }

@router.post("/cleanup-chart-states")
async def cleanup_states(days_old: int = 30):
    """واجهة لتنظيف الحالات القديمة"""
    await asyncio.to_thread(chart_state_db.cleanup_old_states, days_old)
    return {
        "success": True,
        "message": f"Cleaned up states older than {days_old} days"
    }