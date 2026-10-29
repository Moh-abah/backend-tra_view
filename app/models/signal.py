from sqlalchemy import Column, String, Float, DateTime, Boolean, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from app.database import Base
import enum

class SignalType(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"

class SignalStrength(str, enum.Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"

class SignalStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    EXECUTED = "executed"
    CANCELLED = "cancelled"

class Signal(Base):
    __tablename__ = "signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String, nullable=False)
    type = Column(Enum(SignalType), nullable=False)
    strength = Column(Enum(SignalStrength), default=SignalStrength.MODERATE)
    strategy = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    entry_price = Column(Float)
    target_price = Column(Float)
    stop_loss = Column(Float)
    current_price = Column(Float)
    profit_loss = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    expiry = Column(DateTime)
    status = Column(Enum(SignalStatus), default=SignalStatus.ACTIVE)
    read = Column(Boolean, default=False)
    signal_metadata = Column("metadata", JSON, default={})
    
    # علاقة بالمستخدم (إذا كان النظام يحتوي على مستخدمين)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "type": self.type.value,
            "strength": self.strength.value,
            "strategy": self.strategy,
            "price": self.price,
            "entry_price": self.entry_price,
            "target": self.target_price,
            "stop_loss": self.stop_loss,
            "current_price": self.current_price,
            "profit_loss": self.profit_loss,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "status": self.status.value,
            "read": self.read,
            "metadata": self.signal_metadata,
            "user_id": str(self.user_id) if self.user_id else None
        }