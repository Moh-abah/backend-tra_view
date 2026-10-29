from app.services.strategy.schemas import (
    StrategyConfig,
    EntryRule,
    ExitRule,
    FilterRule,
    Condition,
    CompositeCondition,
    ConditionType,
    Operator,
    PositionSide,
    RiskManagement,
)
from app.services.indicators.base import IndicatorConfig, IndicatorType


def build_full_strategy() -> StrategyConfig:
    return StrategyConfig(
        # ===== معلومات أساسية =====
        name="EMA_RSI_CONFIRMATION_STRATEGY",
        version="1.0.0",
        description="Trend-following strategy using EMA crossover with RSI confirmation",
        author="Trading Engine",
        base_timeframe="1h",
        allowed_timeframes=["15m", "1h", "4h"],
        position_side=PositionSide.LONG,
        initial_capital=10000.0,
        commission_rate=0.001,

        # ===== المؤشرات =====
        indicators=[
            IndicatorConfig(
                name="ema_fast",
                type=IndicatorType.TREND,
                timeframe="1h",
                params={"period": 20},
            ),
            IndicatorConfig(
                name="ema_slow",
                type=IndicatorType.TREND,
                timeframe="1h",
                params={"period": 50},
            ),
            IndicatorConfig(
                name="rsi",
                type=IndicatorType.MOMENTUM,
                timeframe="1h",
                params={"period": 14},
            ),
            IndicatorConfig(
                name="volume",
                type=IndicatorType.VOLUME,
                timeframe="1h",
                params={},
            ),
        ],


        # ===== قواعد الدخول =====
        entry_rules=[
            EntryRule(
                name="ema_crossover_entry",
                weight=0.6,
                position_side=PositionSide.LONG,
                condition=Condition(
                    type=ConditionType.INDICATOR_CROSSOVER,
                    operator=Operator.CROSSOVER_ABOVE,
                    left_value="indicator:ema_fast",
                    right_value="indicator:ema_slow",
                    timeframe="1h",
                ),
            ),
            EntryRule(
                name="rsi_confirmation",
                weight=0.4,
                position_side=PositionSide.LONG,
                condition=Condition(
                    type=ConditionType.INDICATOR_VALUE,
                    operator=Operator.GREATER_THAN,
                    left_value="indicator:rsi",
                    right_value=50,
                    timeframe="1h",
                ),
            ),
        ],

        # ===== قواعد الخروج =====
        exit_rules=[
            ExitRule(
                name="stop_loss_exit",
                exit_type="stop_loss",
                value=2.0,
                condition=Condition(
                    type=ConditionType.PRICE_CROSSOVER,
                    operator=Operator.CROSSOVER_BELOW,
                    left_value="price",
                    right_value="indicator:ema_slow",
                    timeframe="1h",
                ),
            ),
            ExitRule(
                name="take_profit_exit",
                exit_type="take_profit",
                value=4.0,
                condition=Condition(
                    type=ConditionType.INDICATOR_VALUE,
                    operator=Operator.GREATER_THAN_EQUAL,
                    left_value="indicator:rsi",
                    right_value=70,
                    timeframe="1h",
                ),
            ),
        ],

        # ===== قواعد الفلترة =====
        filter_rules=[
            FilterRule(
                name="low_volume_block",
                action="block",
                condition=Condition(
                    type=ConditionType.VOLUME_CONDITION,
                    operator=Operator.LESS_THAN,
                    left_value="indicator:volume",
                    right_value=1000,
                    timeframe="1h",
                ),
            ),
        ],

        # ===== إدارة المخاطر =====
        risk_management=RiskManagement(
            stop_loss_percentage=2.0,
            take_profit_percentage=4.0,
            trailing_stop_percentage=1.5,
            max_position_size=0.1,
            max_daily_loss=5.0,
            max_concurrent_positions=3,
        ),

        # ===== إعدادات متقدمة =====
        require_confirmation=True,
        confirmation_timeframe="4h",
        max_signals_per_day=5,
    )
