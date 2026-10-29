from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.session import Base

class User(Base):
    """نموذج المستخدم"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # العلاقات
    strategies = relationship("UserStrategy", back_populates="user", cascade="all, delete-orphan")
    indicators = relationship("UserIndicator", back_populates="user", cascade="all, delete-orphan")
    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    filter_settings = relationship("FilterSettings", back_populates="user", cascade="all, delete-orphan")
    portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

class UserStrategy(Base):
    """إستراتيجيات المستخدم المحفوظة"""
    __tablename__ = "user_strategies"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    strategy_config = Column(JSON, nullable=False)  # تكوين الإستراتيجية كـ JSON
    category = Column(String, default="custom")  # custom, template, imported
    tags = Column(JSON, default=[])  # قائمة الوسوم
    is_public = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)
    backtest_results = Column(JSON, nullable=True)  # نتائج الباك-تيست
    performance_score = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # العلاقات
    user = relationship("User", back_populates="strategies")

class UserIndicator(Base):
    """مؤشرات المستخدم المخصصة"""
    __tablename__ = "user_indicators"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    indicator_code = Column(Text, nullable=False)  # كود Pine Script أو Python
    indicator_type = Column(String, default="custom")  # custom, pine_script, python
    parameters = Column(JSON, default={})  # معاملات المؤشر
    category = Column(String, default="custom")
    is_public = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # العلاقات
    user = relationship("User", back_populates="indicators")

class Watchlist(Base):
    """قائمة مراقبة المستخدم"""
    __tablename__ = "watchlists"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    symbols = Column(JSON, default=[])  # قائمة الرموز
    market = Column(String, default="crypto")  # crypto, stocks
    is_default = Column(Boolean, default=False)
    color = Column(String, default="#3B82F6")  # لون القائمة
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # العلاقات
    user = relationship("User", back_populates="watchlists")

class FilterSettings(Base):
    """إعدادات الفلترة المحفوظة"""
    __tablename__ = "filter_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    filter_criteria = Column(JSON, nullable=False)  # معايير الفلترة
    market = Column(String, default="crypto")
    is_default = Column(Boolean, default=False)
    last_run = Column(DateTime(timezone=True), nullable=True)
    last_results = Column(JSON, nullable=True)  # نتائج آخر فلترة
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # العلاقات
    user = relationship("User", back_populates="filter_settings")

class Portfolio(Base):
    """محفظة المستخدم"""
    __tablename__ = "portfolios"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    initial_capital = Column(Float, default=10000.0)
    current_capital = Column(Float, default=10000.0)
    currency = Column(String, default="USD")
    risk_level = Column(String, default="medium")  # low, medium, high
    strategy_allocation = Column(JSON, default={})  # توزيع الإستراتيجيات
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # العلاقات
    user = relationship("User", back_populates="portfolios")
    positions = relationship("Position", back_populates="portfolio", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="portfolio", cascade="all, delete-orphan")

class Position(Base):
    """مراكز المحفظة"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    symbol = Column(String, nullable=False)
    market = Column(String, default="crypto")
    position_type = Column(String, default="long")  # long, short
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    pnl = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    status = Column(String, default="open")  # open, closed
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    
    # العلاقات
    portfolio = relationship("Portfolio", back_populates="positions")

class Transaction(Base):
    """معاملات المحفظة"""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    type = Column(String, nullable=False)  # buy, sell, deposit, withdrawal
    symbol = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    fee = Column(Float, default=0.0)
    description = Column(Text, nullable=True)
    status = Column(String, default="completed")  # pending, completed, cancelled
    executed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # العلاقات
    portfolio = relationship("Portfolio", back_populates="transactions")

class APIKey(Base):
    """مفاتيح API للمستخدم"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    exchange = Column(String, nullable=False)  # binance, alpaca, etc.
    api_key = Column(String, nullable=False)
    api_secret = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    permissions = Column(JSON, default=["read"])  # read, trade, withdraw
    last_used = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # العلاقات
    user = relationship("User", back_populates="api_keys")

class Notification(Base):
    """إشعارات المستخدم"""
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String, default="info")  # info, warning, success, error
    category = Column(String, default="system")  # system, trade, alert
    is_read = Column(Boolean, default=False)
    priority = Column(String, default="medium")  # low, medium, high
    # metadata = Column(JSON, nullable=True)
    meta_info = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True), nullable=True)
    
    # العلاقات
    user = relationship("User", back_populates="notifications")