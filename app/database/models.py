from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.sql import func
from .session import Base

class MarketData(Base):
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    timeframe = Column(String)  # 1m, 5m, 1h, etc.
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    timestamp = Column(DateTime(timezone=True), index=True)
    source = Column(String)  # binance, alpaca, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class TradingSignal(Base):
    __tablename__ = "trading_signals"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    signal_type = Column(String)  # BUY, SELL, HOLD
    strength = Column(Float)  # 0-1
    indicator = Column(String)  # RSI, MACD, etc.
    price = Column(Float)
    timestamp = Column(DateTime(timezone=True), index=True)
    is_executed = Column(Boolean, default=False)