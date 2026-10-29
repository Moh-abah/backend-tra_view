# from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
# from typing import List, Optional, Dict, Any
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import or_, and_
# from datetime import datetime, timedelta
# import asyncio
# import json

# from app.database import get_db
# from app.models.signal import Signal, SignalType, SignalStatus, SignalStrength
# from app.schemas.signals import SignalCreate, SignalUpdate, SignalResponse, SignalStats
# from app.services.data_service import DataService
# from app.services.indicators import IndicatorCalculator
# from app.websocket.managersignal import ConnectionManager

# router = APIRouter(tags=["signals"])
# manager = ConnectionManager()

# # مؤشرات افتراضية للإشارات التلقائية
# DEFAULT_INDICATORS = [
#     {"name": "rsi", "params": {"period": 14, "overbought": 70, "oversold": 30}},
#     {"name": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
#     {"name": "bb", "params": {"period": 20, "std": 2}}
# ]

# @router.get("/", response_model=List[SignalResponse])
# async def get_signals(
#     skip: int = 0,
#     limit: int = 100,
#     type: Optional[SignalType] = None,
#     status: Optional[SignalStatus] = None,
#     strength: Optional[SignalStrength] = None,
#     symbol: Optional[str] = None,
#     strategy: Optional[str] = None,
#     start_date: Optional[datetime] = None,
#     end_date: Optional[datetime] = None,
#     read: Optional[bool] = None,
#     db: AsyncSession = Depends(get_db)
# ):
#     """الحصول على الإشارات مع إمكانية التصفية"""
#     from sqlalchemy import select
    
#     query = select(Signal)
    
#     # تطبيق الفلاتر
#     if type:
#         query = query.where(Signal.type == type)
#     if status:
#         query = query.where(Signal.status == status)
#     if strength:
#         query = query.where(Signal.strength == strength)
#     if symbol:
#         query = query.where(Signal.symbol == symbol.upper())
#     if strategy:
#         query = query.where(Signal.strategy == strategy)
#     if read is not None:
#         query = query.where(Signal.read == read)
#     if start_date:
#         query = query.where(Signal.timestamp >= start_date)
#     if end_date:
#         query = query.where(Signal.timestamp <= end_date)
    
#     # الترتيب والحد
#     query = query.order_by(Signal.timestamp.desc()).offset(skip).limit(limit)
    
#     result = await db.execute(query)
#     signals = result.scalars().all()
    
#     return [signal.to_dict() for signal in signals]

# @router.get("/stats", response_model=SignalStats)
# async def get_signal_stats(db: AsyncSession = Depends(get_db)):
#     """الحصول على إحصائيات الإشارات"""
#     from sqlalchemy import func, select
    
#     # إجمالي الإشارات
#     total_query = select(func.count()).select_from(Signal)
#     total_result = await db.execute(total_query)
#     total = total_result.scalar()
    
#     # الإشارات النشطة
#     active_query = select(func.count()).where(Signal.status == SignalStatus.ACTIVE)
#     active_result = await db.execute(active_query)
#     active = active_result.scalar()
    
#     # إشارات البيع والشراء
#     buy_query = select(func.count()).where(Signal.type == SignalType.BUY)
#     buy_result = await db.execute(buy_query)
#     buy = buy_result.scalar()
    
#     sell_query = select(func.count()).where(Signal.type == SignalType.SELL)
#     sell_result = await db.execute(sell_query)
#     sell = sell_result.scalar()
    
#     # نسبة النجاح (إشارات مغلقة بربح)
#     profit_query = select(func.count()).where(
#         and_(
#             Signal.status == SignalStatus.EXECUTED,
#             Signal.profit_loss > 0
#         )
#     )
#     profit_result = await db.execute(profit_query)
#     profitable = profit_result.scalar()
    
#     executed_query = select(func.count()).where(Signal.status == SignalStatus.EXECUTED)
#     executed_result = await db.execute(executed_query)
#     executed = executed_result.scalar()
    
#     win_rate = (profitable / executed * 100) if executed > 0 else 0
    
#     return SignalStats(
#         total=total,
#         active=active,
#         buy=buy,
#         sell=sell,
#         win_rate=round(win_rate, 2)
#     )

# @router.post("/", response_model=SignalResponse)
# async def create_signal(
#     signal_data: SignalCreate,
#     db: AsyncSession = Depends(get_db)
# ):
#     """إنشاء إشارة جديدة"""
#     from sqlalchemy.dialects.postgresql import insert
    
#     signal_dict = signal_data.dict()
    
#     # حساب الربح/الخسارة إذا كان هناك سعر حالي
#     if signal_dict.get('current_price') and signal_dict.get('entry_price'):
#         if signal_dict['type'] == SignalType.BUY.value:
#             signal_dict['profit_loss'] = signal_dict['current_price'] - signal_dict['entry_price']
#         else:
#             signal_dict['profit_loss'] = signal_dict['entry_price'] - signal_dict['current_price']
    
#     # إنشاء الإشارة
#     stmt = insert(Signal).values(**signal_dict).returning(Signal)
#     result = await db.execute(stmt)
#     signal = result.scalar()
#     await db.commit()
    
#     # إرسال الإشارة عبر WebSocket
#     await manager.broadcast_signal(signal.to_dict())
    
#     return signal.to_dict()

# @router.get("/{signal_id}", response_model=SignalResponse)
# async def get_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
#     """الحصول على إشارة محددة"""
#     from sqlalchemy import select
    
#     query = select(Signal).where(Signal.id == signal_id)
#     result = await db.execute(query)
#     signal = result.scalar()
    
#     if not signal:
#         raise HTTPException(status_code=404, detail="Signal not found")
    
#     return signal.to_dict()

# @router.patch("/{signal_id}", response_model=SignalResponse)
# async def update_signal(
#     signal_id: str,
#     signal_update: SignalUpdate,
#     db: AsyncSession = Depends(get_db)
# ):
#     """تحديث إشارة"""
#     from sqlalchemy import update
    
#     update_data = signal_update.dict(exclude_unset=True)
    
#     # إعادة حساب الربح/الخسارة إذا تم تحديث السعر
#     if 'current_price' in update_data:
#         query = select(Signal).where(Signal.id == signal_id)
#         result = await db.execute(query)
#         signal = result.scalar()
        
#         if signal and signal.entry_price:
#             if signal.type == SignalType.BUY:
#                 update_data['profit_loss'] = update_data['current_price'] - signal.entry_price
#             else:
#                 update_data['profit_loss'] = signal.entry_price - update_data['current_price']
    
#     stmt = update(Signal).where(Signal.id == signal_id).values(**update_data)
#     await db.execute(stmt)
#     await db.commit()
    
#     # جلب الإشارة المحدثة
#     query = select(Signal).where(Signal.id == signal_id)
#     result = await db.execute(query)
#     signal = result.scalar()
    
#     return signal.to_dict()

# @router.post("/{signal_id}/read")
# async def mark_signal_as_read(signal_id: str, db: AsyncSession = Depends(get_db)):
#     """وضع علامة مقروء على إشارة"""
#     from sqlalchemy import update
    
#     stmt = update(Signal).where(Signal.id == signal_id).values(read=True)
#     await db.execute(stmt)
#     await db.commit()
    
#     return {"message": "Signal marked as read"}

# @router.post("/read-all")
# async def mark_all_signals_as_read(db: AsyncSession = Depends(get_db)):
#     """وضع علامة مقروء على جميع الإشارات"""
#     from sqlalchemy import update
    
#     stmt = update(Signal).values(read=True)
#     await db.execute(stmt)
#     await db.commit()
    
#     return {"message": "All signals marked as read"}

# @router.delete("/{signal_id}")
# async def delete_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
#     """حذف إشارة"""
#     from sqlalchemy import delete
    
#     stmt = delete(Signal).where(Signal.id == signal_id)
#     await db.execute(stmt)
#     await db.commit()
    
#     return {"message": "Signal deleted"}

# @router.post("/generate/auto")
# async def generate_signals_automatically(
#     symbols: List[str] = Query(["BTCUSDT", "ETHUSDT"]),
#     timeframe: str = "1h",
#     market: str = "crypto",
#     days: int = 7,
#     db: AsyncSession = Depends(get_db)
# ):
#     """توليد إشارات تلقائية من المؤشرات"""
#     data_service = DataService(db)
#     calculator = IndicatorCalculator()
    
#     all_signals = []
    
#     for symbol in symbols:
#         try:
#             # جلب البيانات مع المؤشرات
#             data = await data_service.get_data_with_indicators(
#                 symbol=symbol,
#                 timeframe=timeframe,
#                 market=market,
#                 indicators_config=DEFAULT_INDICATORS,
#                 days=days
#             )
            
#             # تحليل البيانات للحصول على إشارات
#             if 'rsi' in data.columns and 'macd' in data.columns:
#                 # مثال: توليد إشارات بناءً على RSI و MACD
#                 for i in range(len(data)):
#                     rsi = data['rsi'].iloc[i] if not pd.isna(data['rsi'].iloc[i]) else 50
#                     macd = data['macd'].iloc[i] if not pd.isna(data['macd'].iloc[i]) else 0
                    
#                     signal = None
                    
#                     # إشارة شراء: RSI أقل من 30 و MACD إيجابي
#                     if rsi < 30 and macd > 0:
#                         signal = SignalCreate(
#                             symbol=symbol,
#                             type=SignalType.BUY,
#                             strength=SignalStrength.STRONG,
#                             strategy="RSI+MACD",
#                             price=data['close'].iloc[i],
#                             target_price=data['close'].iloc[i] * 1.05,
#                             stop_loss=data['close'].iloc[i] * 0.95,
#                             current_price=data['close'].iloc[i],
#                             metadata={
#                                 "rsi": float(rsi),
#                                 "macd": float(macd),
#                                 "timeframe": timeframe,
#                                 "generated_at": datetime.utcnow().isoformat()
#                             }
#                         )
                    
#                     # إشارة بيع: RSI أعلى من 70 و MACD سلبي
#                     elif rsi > 70 and macd < 0:
#                         signal = SignalCreate(
#                             symbol=symbol,
#                             type=SignalType.SELL,
#                             strength=SignalStrength.STRONG,
#                             strategy="RSI+MACD",
#                             price=data['close'].iloc[i],
#                             target_price=data['close'].iloc[i] * 0.95,
#                             stop_loss=data['close'].iloc[i] * 1.05,
#                             current_price=data['close'].iloc[i],
#                             metadata={
#                                 "rsi": float(rsi),
#                                 "macd": float(macd),
#                                 "timeframe": timeframe,
#                                 "generated_at": datetime.utcnow().isoformat()
#                             }
#                         )
                    
#                     if signal:
#                         # حفظ الإشارة في قاعدة البيانات
#                         stmt = insert(Signal).values(**signal.dict()).returning(Signal)
#                         result = await db.execute(stmt)
#                         saved_signal = result.scalar()
#                         await db.commit()
                        
#                         all_signals.append(saved_signal.to_dict())
                        
#                         # إرسال عبر WebSocket
#                         await manager.broadcast_signal(saved_signal.to_dict())
                        
#         except Exception as e:
#             print(f"Error generating signals for {symbol}: {e}")
#             continue
    
#     return {"generated": len(all_signals), "signals": all_signals}

# @router.websocket("/ws/live")
# async def websocket_endpoint(websocket: WebSocket):
#     """WebSocket للإشارات الحية"""
#     await manager.connect(websocket)
#     try:
#         while True:
#             # يمكنك إضافة منطق للتحكم في الرسائل الواردة
#             data = await websocket.receive_text()
#             message = json.loads(data)
            
#             if message.get("type") == "subscribe":
#                 # إضافة العميل إلى قناة معينة
#                 await manager.subscribe(websocket, message.get("channel", "signals"))
                
#     except WebSocketDisconnect:
#         manager.disconnect(websocket)