# app/models/strategy.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float
from sqlalchemy.sql import func
from app.database import Base

class Strategy(Base):
    """
    نموذج الاستراتيجية في قاعدة البيانات
    """
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    
    # معلومات أساسية
    name = Column(String(255), unique=True, index=True, nullable=False)
    version = Column(String(50), nullable=False, default="1.0.0")
    description = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    
    # إعدادات التداول
    base_timeframe = Column(String(20), nullable=False, default="1h")
    position_side = Column(String(20), nullable=False, default="long")  # long, short, both
    
    # تكوين الاستراتيجية (مخزن كـ JSON)
    config = Column(Text, nullable=False)  # JSON string
    
    # الحالة
    is_active = Column(Boolean, default=True)
    
    # التواريخ
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # إحصائيات (اختيارية)
    total_runs = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<Strategy(name='{self.name}', version='{self.version}', active={self.is_active})>"