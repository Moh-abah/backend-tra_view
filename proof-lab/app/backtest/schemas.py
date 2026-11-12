# app/backtest/schemas.py — ساندبوكس إثبات R45 (مخططات مطابقة لعقد الاستخدام)
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class ExitStrategyBlock(BaseModel):
    strategy: Optional[str] = None
    strategy_params: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


class BacktestConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbols: List[str] = ["BTCUSDT"]
    timeframe: str = "1h"
    market: str = "crypto"
    days: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    initial_capital: float = 10000.0
    timezone: str = "UTC"
    tz_offset_minutes: int = 0
    name: str = "sandbox-backtest"
    strategy_config: Optional[Dict[str, Any]] = None
    exit_strategy: Optional[ExitStrategyBlock] = None
    generate_report: bool = False
    save_to_file: bool = False


class VisualCandle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    indicators: Dict[str, Any] = {}


class BacktestResult(BaseModel):
    id: str
    initial_capital: float = 10000.0
    final_capital: float = 10000.0
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    max_drawdown_percent: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    annual_return_percent: float = 0.0
    execution_time_seconds: float = 0.0
    volatility_annual: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0
    system_quality_number: float = 0.0
    kelly_criterion: float = 0.0
    fees_applied: float = 0.0
    fill_model: str = "next_open"
    math_audit: Dict[str, Any] = {}
    effective_config: Dict[str, Any] = {}
    visual_candles: List[VisualCandle] = []
    trade_points: List[Dict[str, Any]] = []
    equity_curve: List[float] = []
    drawdown_curve: List[float] = []
