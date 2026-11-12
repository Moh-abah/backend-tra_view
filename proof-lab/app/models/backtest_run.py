# ساندبوكس إثبات R45 — نفس أعمدة الجدول الحقيقي كما تستخدمه الراوترات
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String

from app.database.session import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(String(64), primary_key=True)
    name = Column(String(255))
    summary = Column(JSON)
    chart_data = Column(JSON)
    full_config = Column(JSON)
    total_pnl_percent = Column(Float)
    win_rate = Column(Float)
    total_trades = Column(Integer)
    timeframe = Column(String(16))
    symbol = Column(String(32))
    created_at = Column(DateTime, default=_utcnow)
