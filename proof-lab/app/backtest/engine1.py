# ساندبوكس إثبات R45 — المحرك القياسي بعقد BacktestEngine الحقيقي
import hashlib
import os
import time

MAX_MONTE_CARLO_SIMULATIONS = 10000
MAX_WALK_FORWARD_WINDOWS = 20


class BacktestEngine:
    def __init__(self, data_service):
        self.data_service = data_service
        self.last_df = None  # للتحقق من مطابقة مخطط DataFrame بعد الكاش

    async def run_backtest(self, config):
        from app.backtest.schemas import BacktestResult, VisualCandle

        delay = float(os.environ.get("SANDBOX_SIM_DELAY", "0") or 0)
        if delay:
            time.sleep(delay)

        df = await self.data_service.get_historical(
            symbol=config.symbols[0] if config.symbols else "BTCUSDT",
            timeframe=config.timeframe,
            market=config.market,
            days=config.days or 30,
        )
        self.last_df = df

        seed = int(hashlib.md5(str(config.name).encode()).hexdigest()[:6], 16)
        candles = df.to_dict("records") if df is not None else []
        n = len(candles)
        trades = max(1, n // 25)
        wins = trades * 11 // 23
        win_rate = round(100.0 * wins / trades, 2)
        pnl = round((seed % 3000) / 100.0 - 4.0, 2)

        return BacktestResult(
            id=hashlib.md5(f"{config.name}-{time.time()}".encode()).hexdigest()[:32],
            initial_capital=float(config.initial_capital),
            final_capital=round(float(config.initial_capital) * (1 + pnl / 100.0), 2),
            total_pnl=round(float(config.initial_capital) * pnl / 100.0, 2),
            total_pnl_percent=pnl,
            total_trades=trades,
            winning_trades=wins,
            losing_trades=trades - wins,
            win_rate=win_rate,
            max_drawdown_percent=round(abs(pnl) / 3.5 + 2.0, 2),
            sharpe_ratio=1.22,
            sortino_ratio=1.55,
            calmar_ratio=1.05,
            profit_factor=1.66,
            expectancy=31.2,
            annual_return_percent=round(pnl * 2.9, 2),
            execution_time_seconds=0.42,
            visual_candles=[
                VisualCandle(
                    time=int(float(c.get("time", 0)) / (1000.0 if float(c.get("time", 0)) > 1e11 else 1.0)),
                    open=float(c.get("open", 0)),
                    high=float(c.get("high", 0)),
                    low=float(c.get("low", 0)),
                    close=float(c.get("close", 0)),
                    volume=float(c.get("volume", 0)),
                )
                for c in candles[:4000]
            ],
            trade_points=[{"time": i, "type": "entry"} for i in range(trades)],
            equity_curve=[10000.0, 10000.0 + pnl],
            drawdown_curve=[0.0, abs(pnl) / 3.0],
        )

    async def run_walk_forward_analysis(self, config, periods):
        return []

    async def run_monte_carlo_simulation(self, config, simulations):
        return {"probability_profit": 0.61}
