# app/models/backtest_run.py
from sqlalchemy import Column, String, DateTime, JSON, Float, Integer
from sqlalchemy.sql import func
from app.database import Base

class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(String, primary_key=True, index=True) # نفس backtest_id
    name = Column(String, nullable=False)
    
    # تخزين الملخص (Summary) كامل
    summary = Column(JSON, nullable=True)
    
    # تخزين بيانات الشارت (الشموع ونقاط الدخول والخروج) وهو ما طلبته بالتحديد
    chart_data = Column(JSON, nullable=True) 

    full_config = Column(JSON, nullable=True)
    
    # تواريخ التنفيذ
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # حقول إضافية للفرز والبحث السريع
    total_pnl_percent = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    total_trades = Column(Integer, nullable=True)
    timeframe = Column(String, nullable=True)
    symbol = Column(String, nullable=True)