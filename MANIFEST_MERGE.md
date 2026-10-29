# 📦 بيان حزمة الدمج (Merge Manifest)

**تاريخ الحزم:** 2026-10-27 23:12 UTC  
**مقارنة مع:** المشروع الأصلي المنزّل من Google Drive  
**طريقة الدمج:** استخرج الـ ZIP فوق جذر مشروعك (نفس المسارات) — سيستبدل الملفات التالفة بالمعدلة ويضيف الجديدة.

**قبل الدمج:** خذ نسخة احتياطية، وأوقف الخدمة (uvicorn/celery workers).

**بعد الدمج:**
```bash
pip install -r requirements.txt        # بيئة نظيفة يُفضّل
python scripts/fetch_history.py        # (اختياري) جلب سنة بيانات BTC/ETH لكل الفريمات
uvicorn app.main:app --host 0.0.0.0 --port 8000
celery -A app.celery_app worker --loglevel=info   # للباك-تست غير المتزامن
```

---

## 🆕 ملفات جديدة (38)

- `.dockerignore` (0.9 KB)
- `.env.example` (3.4 KB)
- `README.md` (33.6 KB)
- `app/routers/mtf.py` (5.2 KB)
- `app/services/indicators/indicators/parametric.py` (5.6 KB)
- `app/services/mtf_analyzer.py` (23.8 KB)
- `app/utils/json_safe.py` (2.5 KB)
- `data/history/_integrity.json` (6.4 KB)
- `examples/backtest_request.json` (10.8 KB)
- `reports/FINAL_REPORT_AR.md` (8.0 KB)
- `reports/REPORT_BACKTEST_YEAR.md` (12.9 KB)
- `reports/REPORT_DATABASE_API.md` (2.6 KB)
- `reports/REPORT_MTF_SCENARIOS.md` (3.5 KB)
- `reports/REPORT_VALIDATION.md` (2.5 KB)
- `reports/backtest_results.json` (51.1 KB)
- `reports/mtf_scenario_results.json` (6.6 KB)
- `scripts/bench_backtest.py` (2.3 KB)
- `scripts/build_merge_package.py` (7.0 KB)
- `scripts/fetch_history.py` (9.3 KB)
- `scripts/generate_reports.py` (23.7 KB)
- `scripts/run_year_backtests.py` (10.4 KB)
- `scripts/test_mtf_scenarios.py` (14.2 KB)
- `scripts/validation/01_generate_test_data.py` (4.1 KB)
- `scripts/validation/02_validate_indicators.py` (12.7 KB)
- `scripts/validation/03_validate_backtest.py` (10.8 KB)
- `scripts/validation/04_builtin_strategies.py` (3.7 KB)
- `scripts/validation/05_new_strategies.py` (11.9 KB)
- `scripts/validation/06_benchmark.py` (6.6 KB)
- `scripts/validation/data/constant.csv` (16.7 KB)
- `scripts/validation/data/linear_down.csv` (30.9 KB)
- `scripts/validation/data/linear_up.csv` (31.4 KB)
- `scripts/validation/data/random_walk.csv` (83.6 KB)
- `scripts/validation/data/sawtooth.csv` (16.6 KB)
- `scripts/validation/data/v_shape.csv` (41.1 KB)
- `strategies/.gitkeep` (0.0 KB)
- `strategies/bollinger_oversold_sniper.json` (2.0 KB)
- `strategies/macd_zero_line_momentum.json` (2.3 KB)
- `strategies/volume_climax_reversal_pro.json` (2.0 KB)

## ✏️ ملفات معدلة (58)

- `.env.production`
- `.gitignore`
- `Dockerfile`
- `app/backtest/engine1.py`
- `app/backtest/metrics.py`
- `app/backtest/reports.py`
- `app/backtest/schemas.py`
- `app/celery_app.py`
- `app/config.py`
- `app/core/indicators.py`
- `app/core/live_stream.py`
- `app/core/managers.py`
- `app/database/__init__.py`
- `app/database/redis_client.py`
- `app/database/session.py`
- `app/dependencies.py`
- `app/main.py`
- `app/models/__init__.py`
- `app/models/signal.py`
- `app/providers/alphavantage_client.py`
- `app/providers/binance_indicators_stream.py`
- `app/providers/binance_market_stream.py`
- `app/providers/binance_provider.py`
- `app/providers/us_stock_provider.py`
- `app/providers/yahoo_client.py`
- `app/routers/api.py`
- `app/routers/backtest.py`
- `app/routers/filtering.py`
- `app/routers/indicators.py`
- `app/routers/market_data.py`
- `app/routers/settings.py`
- `app/routers/stock_analysis.py`
- `app/routers/strategies.py`
- `app/routers/strategies1.py`
- `app/routers/users.py`
- `app/routers/websocket.py`
- `app/schemas/user.py`
- `app/services/auth.py`
- `app/services/data_service.py`
- `app/services/filtering/core.py`
- `app/services/indicator_state_service.py`
- `app/services/indicators/__init__.py`
- `app/services/indicators/base.py`
- `app/services/indicators/calculator.py`
- `app/services/indicators/indicators/__init__.py`
- `app/services/indicators/indicators/indicators.py`
- `app/services/signals/engine.py`
- `app/services/strategy/__init__.py`
- `app/services/strategy/conditions.py`
- `app/services/strategy/schemas.py`
- `app/services/strategy/strategy_engine1.py`
- `app/tasks/backtest_tasks.py`
- `app/websocket/__init__.py`
- `app/websocket/chart_ws.py`
- `app/websocket/signals_ws.py`
- `app/websocket/stream_handler.py`
- `docker-compose.yml`
- `requirements.txt`

## ♻️ ملفات لم تتغير (46) — تُحزم أيضًا للاطمئنان

- `app/backtest/__init__.py`
- `app/markets/us/__init__.py`
- `app/markets/us/market_config.py`
- `app/markets/us/market_movers.py`
- `app/markets/us/symbol_registry.py`
- `app/metrics/normalizer.py`
- `app/models/backtest_run.py`
- `app/models/strategy.py`
- `app/models/user.py`
- `app/schemas/indicators.py`
- `app/schemas/signals.py`
- `app/services/chart_storage.py`
- `app/services/data_provider.py`
- `app/services/filtering/__init__.py`
- `app/services/filtering/schemas.py`
- `app/services/indicators/indicators/smc/smc_order_block.py`
- `app/services/indicators/pine_transpiler.py`
- `app/services/indicators/registry.py`
- `app/services/signals/__init__.py`
- `app/services/signals/candle_tracker.py`
- `app/services/signals/schemas.py`
- `app/services/signals/signal.py`
- `app/services/signals/state.py`
- `app/services/strategy/climax_stratigyes.json`
- `app/services/strategy/core.py`
- `app/services/strategy/full_strategy.py`
- `app/services/strategy/loader.py`
- `app/services/strategy/smcop.json`
- `app/services/strategy/strategys/__init__.py`
- `app/services/strategy/strategys/macd_strategy.py`
- `app/services/strategy/strategys/mean_reversion_strategy.py`
- `app/services/strategy/strategys/rsi_strategy.py`
- `app/services/strategy/strategys/test_strategy.py`
- `app/services/strategy/strategys/trend_strategy.py`
- `app/utils/converters.py`
- `app/utils/security.py`
- `app/websocket/manager.py`
- `app/websocket/schemas.py`
- `strategies/Multi-Timeframe MACD Complex Conditions`
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/run_tests.py`
- `tests/unit/routers/test_strategies.py`
- `tests/unit/services/test_strategy_service.py`
- `tests/unit/test_core_indicators.py`
- `tests/unit/test_indicators_base.py`

## 🗑️ ملفات حذفناها من مشروعنا (59) — لن يزيلها الدمج، احذفها يدويًا إن وجدت (نسخ قديمة/مكررة)

- `app/backtest/backtestsendbody copy 2.json`
- `app/backtest/backtestsendbody copy 3.json`
- `app/backtest/backtestsendbody copy 4.json`
- `app/backtest/backtestsendbody copy 5.json`
- `app/backtest/backtestsendbody copy.json`
- `app/backtest/backtestsendbody.json`
- `app/backtest/climaxbacktetst.json`
- `app/backtest/decision.py`
- `app/backtest/engine.py`
- `app/backtest/engine_copy.py`
- `app/backtest/golden.json`
- `app/backtest/s.json`
- `app/backtest/strategy_context.py`
- `app/chart/broadcaster.py`
- `app/chart/chart_hub.py`
- `app/chart/chart_session.py`
- `app/core/chart_storage.py`
- `app/core/streaming/market_stream.py`
- `app/database/models.py`
- `app/markets/candle_builder.py`
- `app/markets/candle_store.py`
- `app/markets/indicator_scheduler.py`
- `app/markets/models.py`
- `app/markets/runtime.py`
- `app/markets/timeframe.py`
- `app/models/portfolio.py`
- `app/models/settings.py`
- `app/providers/alpaca_provider.py`
- `app/providers/binance_market_streamca.py`
- `app/providers/stock_websocket.py`
- `app/providers/ws_server.py`
- `app/routers/backtest1.py`
- `app/routers/chart_snapshot.py`
- `app/routers/core.py`
- `app/routers/logging_config.py`
- `app/routers/signals.py`
- `app/services/candle_aggregator.py`
- `app/services/chart_manager.py`
- `app/services/data/timeframe_aligner.py`
- `app/services/indicators/core_indicators.py`
- `app/services/indicators/engine.py`
- `app/services/indicators/indicators.py`
- `app/services/indicators/processor.py`
- `app/services/indicators/reliable_calculator.py`
- `app/services/indicators/rsi.py`
- `app/services/indicators/sma.py`
- `app/services/indicators/trend.py`
- `app/services/indicators/volume.py`
- `app/services/live_monitor.py`
- `app/services/market/candle_tracker.py`
- `app/services/market_pipeline.py`
- `app/services/market_service.py`
- `app/services/strategy/climax_stratigyes copy.json`
- `app/services/strategy/core_copy.py`
- `app/services/strategy/smcop copy.json`
- `app/websocket/indicators_ws.py`
- `app/websocket/managersignal.py`
- `app/websocket/stock_handler.py`
- `tests/unit/test_trend_indicators.py`

> ملاحظة: ملفات "copy" القديمة (engine_copy.py, core_copy.py, backtest1/, strategies1/, إلخ) ضمن المحذوفات — حذفها ضروري لتجنب تعارض الاستيرادات.

## 📊 إحصائيات

| البند | العدد |
|---|---:|
| ملفات في الحزمة | 142 |
| جديدة | 38 |
| معدلة | 58 |
| غير متغيرة | 46 |
| محذوفة (احذفها يدويًا) | 59 |
