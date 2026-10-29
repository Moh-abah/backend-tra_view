# Trading Backend API — منصة التداول الخلفية

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-green)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](#license)

A production-oriented trading platform backend: real-time crypto (Binance WebSocket), US stock data (Yahoo Finance / AlphaVantage), a large technical-indicator library (including SMC order blocks and harmonic patterns), a strategy + signal + filtering engine, backtesting with quantitative metrics, and JWT-secured CRUD APIs for users, watchlists, portfolios, and settings.

## الملخص بالعربية

هذا المشروع هو الواجهة الخلفية لمنصة تداول مبنية على **FastAPI**:

- بيانات العملات الرقمية اللحظية عبر **Binance WebSocket**، وأسعار الأسهم الأمريكية عبر **Yahoo Finance / AlphaVantage**.
- أكثر من **20 مؤشرًا فنيًا** بما فيها كتل الأوامر (SMC Order Blocks) والنماذج التوافقية (Harmonic Patterns).
- محرك استراتيجيات + محرك إشارات + محرك فلترة أسهم (Filtering Engine).
- اختبار خلفي (Backtesting) بمقاييس كمية: **Sharpe / Sortino / Calmar / أقصى تراجع / VaR**، مع تنفيذ غير متزامن عبر **Celery**.
- مصادقة **JWT**، WebSocket للبث اللحظي، CRUD كامل للقوائم والمحافظ والإعدادات.
- قاعدة بيانات **PostgreSQL/Neon** مع **Redis/Upstash** للتخزين المؤقت والـ Celery.

> ⚠️ المشروع قيد إعادة الهيكلة حاليًا (انظر قسم [Known Limitations](#known-limitations--ملاحظات-ومحددات)).

---

## Features

- **Real-time crypto market data** via Binance WebSocket streams (klines, tickers, indicators).
- **US stock data** via Yahoo Finance (`yfinance`) with AlphaVantage fallback.
- **20+ technical indicators** — RSI, MACD, Bollinger Bands, ATR, OBV, EMA/SMA, and more — plus **SMC order blocks** and **harmonic patterns** detection.
- **Strategy engine** — YAML/JSON strategy configs, validation, upload, run from file or DB.
- **Signal engine** — automated signal generation and live signal streaming.
- **Backtesting** — single run, walk-forward, Monte Carlo, strategy comparison, and report generation (plotly) with metrics: **Sharpe, Sortino, Calmar, max drawdown, VaR** and more; heavy runs execute asynchronously via **Celery**.
- **Filtering engine** — screen symbols by configurable criteria (bulk + single market scans).
- **CRUD APIs** — watchlists, portfolios, user settings, custom indicators, filters, API keys.
- **JWT authentication** — access/refresh tokens, password reset, email verification (SMTP).
- **WebSocket streams** — chart data, live market overview, indicators, signals, filters.
- **Docker + docker-compose** — Redis with healthchecks, backend + Celery worker, non-root image.

## Architecture

```
                        ┌──────────────────────────────────────────────┐
                        │                  CLIENTS                     │
                        │        (REST/JSON  +  WebSocket)             │
                        └──────────────┬───────────────┬───────────────┘
                                       │               │
                        ┌──────────────▼───────────────▼───────────────┐
                        │              FASTAPI  (app/main.py)          │
                        │  routers: users · settings · strategies ·    │
                        │  backtest · indicators · filtering · market  │
                        │  data · websocket · stocks · core/api        │
                        └──────┬───────────────┬───────────────┬───────┘
                               │               │               │
              ┌────────────────▼───┐   ┌───────▼────────┐  ┌───▼──────────────┐
              │  SERVICES LAYER    │   │  WEBSOCKET      │  │  CELERY WORKER   │
              │  auth · signals ·  │   │  chart streams  │  │  async backtests │
              │  strategy ·        │   │  market overview│  │  (tasks/)        │
              │  indicators ·      │   │  signals / ws   │  └───┬──────────────┘
              │  filtering · data  │   └───────┬────────┘      │
              └──────┬─────────────┘           │               │
                     │                         │               │
        ┌────────────▼─────────────────────────▼───────────────▼──────────┐
        │                      PROVIDERS (app/providers)                   │
        │  binance_provider · binance_market_stream · yahoo_client ·       │
        │  alphavantage_client · stock_websocket · us_stock_provider       │
        └────────────┬───────────────────────────────┬────────────────────┘
                     │                               │
        ┌────────────▼──────────┐        ┌───────────▼───────────┐
        │  PostgreSQL / Neon    │        │  Redis / Upstash      │
        │  (SQLAlchemy async)   │        │  cache · Celery broker│
        │  asyncpg / aiosqlite  │        │  (redis.asyncio)      │
        └───────────────────────┘        └───────────────────────┘
```

## Quick Start

### 1) Local (virtualenv)

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit values (or use the existing .env)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Health: <http://localhost:8000/health>

### 2) Docker Compose

```bash
docker compose up -d --build
docker compose logs -f backend
```

This starts `redis` (healthchecked), `backend`, and `celery-worker`.
The backend image is non-root, exposes **8000**, and self-checks `/health`.

### 3) Database & Redis notes

- **PostgreSQL**: works with a hosted **Neon** database (`DATABASE_URL` in `.env`) or a local
  PostgreSQL — uncomment the `postgres` service in `docker-compose.yml`.
- **Redis**: local `redis://localhost:6379/0`, in-compose `redis://redis:6379/0`, or hosted
  **Upstash**. If Redis is unreachable the API degrades gracefully (cache misses only).
- **SQLite fallback**: `aiosqlite` is installed so local tests can run with
  `DATABASE_URL=sqlite+aiosqlite:///./dev.db`.
- **Celery**: async backtests require the `celery-worker` service and a reachable broker.

## API Endpoints

Base URL: `http://localhost:8000` — API prefix: `/api/v1` (`settings.API_V1_PREFIX`).
Interactive docs at `/docs`. Paths below reflect the currently mounted routers in `app/main.py`.

### Root / system (app/main.py)

| Method | Path             | Description                                  |
|--------|------------------|----------------------------------------------|
| GET    | `/`              | API info (version, docs, WS root)            |
| GET    | `/health`        | Health check (used by Docker HEALTHCHECK)    |
| GET    | `/debug/routes`  | Dump all registered routes (debug only)      |

### Users & auth — `app/routers/users.py` → `/api/v1/users`

| Method | Path                                | Description                                   |
|--------|-------------------------------------|-----------------------------------------------|
| POST   | `/register`                         | Register a new user                           |
| POST   | `/refresh`                          | Exchange refresh token for new access token   |
| GET    | `/me`                               | Current user profile                          |
| PUT    | `/me`                               | Update current user profile                   |
| POST   | `/me/change-password`               | Change password                               |
| DELETE | `/me`                               | Delete own account                            |
| GET    | `/verify-email/{token}`             | Verify email address                          |
| POST   | `/request-password-reset`           | Request password-reset email                  |
| POST   | `/reset-password`                   | Reset password with token                     |
| GET    | `/`                                 | List users (admin)                            |
| GET    | `/{user_id}`                        | Get user by ID (admin)                        |
| PUT    | `/{user_id}`                        | Update user (admin)                           |
| DELETE | `/{user_id}`                        | Delete user (admin)                           |

> Note: `POST /login` is currently commented out in the code (known bug — the OAuth2 scheme
> points at it). Being fixed by the auth refactor; token endpoints above remain functional.

### Settings (watchlists / strategies / indicators / filters / portfolios / API keys) — `app/routers/settings.py` → `/api/v1/settings`

| Method | Path                                          | Description                          |
|--------|-----------------------------------------------|--------------------------------------|
| GET    | `/watchlists`                                 | List watchlists                      |
| POST   | `/watchlists`                                 | Create watchlist                     |
| GET    | `/watchlists/{watchlist_id}`                  | Get watchlist                        |
| PUT    | `/watchlists/{watchlist_id}`                  | Update watchlist                     |
| DELETE | `/watchlists/{watchlist_id}`                  | Delete watchlist                     |
| POST   | `/watchlists/{watchlist_id}/symbols/{symbol}` | Add symbol to watchlist              |
| DELETE | `/watchlists/{watchlist_id}/symbols/{symbol}` | Remove symbol from watchlist         |
| GET    | `/strategies`                                 | List saved strategies                |
| POST   | `/strategies`                                 | Create strategy                      |
| GET    | `/strategies/{strategy_id}`                   | Get strategy                         |
| PUT    | `/strategies/{strategy_id}`                   | Update strategy                      |
| DELETE | `/strategies/{strategy_id}`                   | Delete strategy                      |
| POST   | `/strategies/{strategy_id}/duplicate`         | Duplicate a strategy                 |
| GET    | `/indicators`                                 | List custom indicators               |
| POST   | `/indicators`                                 | Create custom indicator              |
| GET    | `/indicators/{indicator_id}`                  | Get custom indicator                 |
| PUT    | `/indicators/{indicator_id}`                  | Update custom indicator              |
| DELETE | `/indicators/{indicator_id}`                  | Delete custom indicator              |
| POST   | `/indicators/{indicator_id}/test`             | Test an indicator on sample data     |
| GET    | `/filters`                                    | List filter settings                 |
| POST   | `/filters`                                    | Create filter settings               |
| GET    | `/filters/{filter_id}`                        | Get filter settings                  |
| PUT    | `/filters/{filter_id}`                        | Update filter settings               |
| DELETE | `/filters/{filter_id}`                        | Delete filter settings               |
| POST   | `/filters/{filter_id}/run`                    | Execute a saved filter               |
| GET    | `/portfolios`                                 | List portfolios                      |
| POST   | `/portfolios`                                 | Create portfolio                     |
| GET    | `/portfolios/{portfolio_id}`                  | Get portfolio                        |
| PUT    | `/portfolios/{portfolio_id}`                  | Update portfolio                     |
| DELETE | `/portfolios/{portfolio_id}`                  | Delete portfolio                     |
| GET    | `/api-keys`                                   | List stored provider API keys        |
| POST   | `/api-keys`                                   | Store a provider API key (encrypted) |
| GET    | `/api-keys/{api_key_id}`                      | Get API key metadata                 |
| PUT    | `/api-keys/{api_key_id}`                      | Update API key                       |
| DELETE | `/api-keys/{api_key_id}`                      | Delete API key                       |
| POST   | `/api-keys/{api_key_id}/test`                 | Test a stored API key                |

### Market data — `app/routers/market_data.py` → `/api/v1/market`

| Method    | Path                                        | Description                            |
|-----------|---------------------------------------------|----------------------------------------|
| GET       | `/status`                                   | Provider/connection status             |
| GET       | `/symbols`                                  | List available symbols                 |
| GET       | `/historical/{market}/{symbol}`             | Historical OHLCV candles               |
| GET       | `/price/{market}/{symbol}`                  | Latest price snapshot                  |
| WEBSOCKET | `/ws/live/{market}/{symbol}`                | Live stream for one symbol             |

### Backtesting (v1) — `app/routers/backtest.py` → `/api/v1/backtest`

| Method | Path                        | Description                                   |
|--------|-----------------------------|-----------------------------------------------|
| POST   | `/run`                      | Run a backtest (synchronous)                  |
| POST   | `/walk-forward`             | Walk-forward optimization run                 |
| POST   | `/monte-carlo`              | Monte Carlo simulation                        |
| POST   | `/compare`                  | Compare multiple strategies                   |
| GET    | `/results/{backtest_id}`    | Fetch stored results                          |
| GET    | `/report/{backtest_id}`     | Generate an HTML/plotly report                |
| GET    | `/available-metrics`        | List all supported performance metrics        |

### Backtesting (v2, Celery-backed) — `app/routers/backtest1.py` → `/api/v1/backtest1`

| Method | Path                              | Description                                   |
|--------|-----------------------------------|-----------------------------------------------|
| POST   | `/run`                            | Queue async backtest (Celery task)            |
| GET    | `/status/{task_id}`               | Poll Celery task status                       |
| GET    | `/{backtest_id}/chart-data`       | Chart series for a stored backtest            |
| GET    | `/list`                           | List stored backtests                         |
| GET    | `/get/{backtest_id}`              | Get one stored backtest                       |
| DELETE | `/delete/{backtest_id}`           | Delete a stored backtest                      |
| POST   | `/walk-forward`                   | Async walk-forward run                        |
| POST   | `/monte-carlo`                    | Async Monte Carlo run                         |
| GET    | `/metrics`                        | Available metrics & explanations              |

### Strategies — `app/routers/strategies.py` → `/api/v1/strategies`

| Method | Path                            | Description                                  |
|--------|---------------------------------|----------------------------------------------|
| POST   | `/run`                          | Run a strategy config against market data    |
| POST   | `/validate`                     | Validate a strategy config                   |
| POST   | `/save`                         | Save strategy to file                        |
| POST   | `/upload`                       | Upload a strategy file                       |
| GET    | `/list`                         | List loaded strategies                       |
| PUT    | `/update/{strategy_name}`       | Update a saved strategy                      |
| POST   | `/reload/{strategy_name}`       | Reload strategy from disk                    |
| GET    | `/examples/{example_name}`      | Fetch a built-in example config              |

### Strategies (DB-backed) — `app/routers/strategies1.py` → `/api/v1/strategies1`

| Method | Path                                    | Description                              |
|--------|-----------------------------------------|------------------------------------------|
| POST   | `/run`                                  | Run strategy (file/inline config)        |
| POST   | `/validate`                             | Validate strategy config                 |
| POST   | `/save`                                 | Save strategy to file storage            |
| POST   | `/upload`                               | Upload strategy file                     |
| POST   | `/save_to_db`                           | Persist strategy to database             |
| GET    | `/list_from_db`                         | List DB strategies                       |
| GET    | `/get_from_db/{strategy_name}`          | Get DB strategy                          |
| PUT    | `/update_in_db/{strategy_name}`         | Update DB strategy                       |
| DELETE | `/delete_from_db/{strategy_name}`       | Delete DB strategy                       |
| POST   | `/run_from_db`                          | Run a DB-stored strategy                 |

### Indicators — `app/routers/indicators.py` → `/api/v1/indicators`

| Method | Path                              | Description                                       |
|--------|-----------------------------------|---------------------------------------------------|
| POST   | `/apply`                          | Apply indicator(s) to OHLCV data                  |
| POST   | `/pine/transpile`                 | Transpile Pine Script-like definitions            |
| POST   | `/signals`                        | Compute indicator-derived signals                 |
| GET    | `/{indicator_name}/params`        | Get parameter schema for an indicator             |

### Stock analysis — `app/routers/stock_analysis.py` → mounted at `/api/v1/stocks` *

| Method | Path                    | Description                                  |
|--------|-------------------------|----------------------------------------------|
| GET    | `/symbols`              | List US stock symbols (NASDAQ list)          |
| GET    | `/chart/{symbol}`       | Chart data for a stock                       |
| GET    | `/analysis/{symbol}`    | Technical analysis summary                   |
| GET    | `/company/{symbol}`     | Company profile                              |
| GET    | `/market/summary`       | Overall market summary                       |
| GET    | `/market/top-movers`    | Top gainers/losers                           |
| GET    | `/search`               | Search symbols                               |
| GET    | `/sectors`              | Sector performance                           |

\* This router declares an internal `/stocks` prefix **and** is mounted with the
`/api/v1/stocks` prefix, so effective paths are currently `/api/v1/stocks/stocks/...`
(known duplication quirk queued for the code-refactor agents).

### Filtering engine — `app/routers/filtering.py` → `/api/v1/filtering`

| Method | Path                  | Description                                    |
|--------|-----------------------|------------------------------------------------|
| POST   | `/symbols`            | Filter symbols by criteria                     |
| GET    | `/markets`            | List filterable markets                        |
| GET    | `/criteria/examples`  | Example filter criteria                        |
| GET    | `/stats`              | Filtering engine statistics                    |
| POST   | `/bulk`               | Bulk filter across markets                     |

### Core / misc

| Method    | Path                          | Description                          | Mounted by          |
|-----------|-------------------------------|--------------------------------------|---------------------|
| GET       | `/api/v1/symbols`             | Supported symbols                    | `api.py` + `core.py` (duplicate mount) |
| GET       | `/api/v1/status`              | System status                        | `api.py`            |
| GET       | `/api/v1/health`              | API-level health                     | `api.py`            |
| GET       | `/api/v1/chart/snapshot/{symbol}` | Chart snapshot (via WS router include) | `chart_snapshot.py` |

## WebSocket Endpoints

Mounted at prefix `/ws` (`app/routers/websocket.py` + `app/websocket/chart_ws.py`):

| Protocol | Path                              | Description                                        |
|----------|-----------------------------------|----------------------------------------------------|
| WS       | `/ws/chart/{symbol}`              | Live chart data (klines + indicators)              |
| WS       | `/ws/indicators/{symbol}`         | Live indicator values for a symbol                 |
| WS       | `/ws/market-overview`             | Aggregated market overview stream                  |
| WS       | `/ws/market-overviewalls`         | Market overview, all symbols variant               |
| WS       | `/ws/market-data_overview`        | Market data overview stream (legacy variant)       |
| WS       | `/ws/signals`                     | Live trading signals stream                        |
| WS       | `/ws/stream/{symbol}/{timeframe}` | Live kline stream for a symbol/timeframe           |
| WS       | `/ws/filter`                      | Live filtering results stream                      |
| WS       | `/ws/filters`                     | Live multi-filter stream                           |
| WS       | `/ws/stream`                      | Managed live stream (control-message driven)       |
| WS       | `/ws/market-overview` (api.py)    | Also mounted at `/api/v1/market-overview`          |
| GET      | `/ws/stream/active`               | List active streams (REST)                         |
| POST     | `/ws/stream/start`                | Start a managed stream (REST control)              |
| POST     | `/ws/stream/stop/{stream_id}`     | Stop a managed stream (REST control)               |
| GET      | `/ws/chart-states`                | Persisted indicator chart states                   |
| POST     | `/ws/cleanup-chart-states`        | Clean up persisted chart states                    |

## Environment Variables

Copy `.env.example` → `.env` (dev) or `.env.production` (prod). Real secrets stay gitignored.

| Variable                        | Example / Default                                   | Purpose                                        |
|---------------------------------|-----------------------------------------------------|------------------------------------------------|
| `DEBUG`                         | `false`                                             | Debug mode (must be `false` in prod)           |
| `DISABLE_AUTH`                  | `false`                                             | Skip JWT checks — dev only!                    |
| `LOG_LEVEL`                     | `INFO`                                              | Logging verbosity                              |
| `DATABASE_URL`                  | `postgresql+asyncpg://...neon.tech/neondb?sslmode=require` | Async Postgres URL (Neon/local/sqlite+aiosqlite) |
| `REDIS_URL`                     | `redis://localhost:6379/0`                          | Redis/Upstash URL (cache + Celery default)     |
| `SECRET_KEY`                    | (random 48-byte urlsafe token)                      | JWT signing secret                             |
| `ALGORITHM`                     | `HS256`                                             | JWT algorithm                                  |
| `ACCESS_TOKEN_EXPIRE_MINUTES`   | `30`                                                | Access token TTL                               |
| `REFRESH_TOKEN_EXPIRE_DAYS`     | `7`                                                 | Refresh token TTL                              |
| `ENCRYPTION_KEY`                | Fernet key                                          | Encrypts stored provider API keys              |
| `CORS_ORIGINS`                  | `["http://localhost:3000"]`                         | CORS allow-list (JSON array)                   |
| `ALLOWED_ORIGINS`               | same as above                                       | Legacy alias kept in env files                 |
| `BINANCE_WS_URL`                | `wss://stream.binance.com:9443/ws`                  | Binance WebSocket base                         |
| `BINANCE_API_URL`               | `https://api.binance.com`                           | Binance REST base                              |
| `ALPHA_VANTAGE_API_KEY`         | (your key)                                          | US stock data fallback (free: 25 req/day)      |
| `ALPACA_API_KEY`                | *(empty)*                                           | Unused (Alpaca provider disabled)              |
| `ALPACA_SECRET_KEY`             | *(empty)*                                           | Unused (Alpaca provider disabled)              |
| `POLYGON_API_KEY`               | (your key)                                          | Optional market data provider                  |
| `CELERY_BROKER_URL`             | `redis://localhost:6379/1`                          | Celery broker                                  |
| `CELERY_RESULT_BACKEND`         | `redis://localhost:6379/2`                          | Celery results                                 |
| `SMTP_SERVER` / `SMTP_PORT`     | `smtp.gmail.com` / `587`                            | Email sending (verification/reset)             |
| `SMTP_USERNAME` / `SMTP_PASSWORD`| *(credentials)*                                    | SMTP credentials                               |
| `EMAIL_FROM`                    | `no-reply@example.com`                              | Sender address                                 |

## Security Notes

- **Secrets live only in `.env` / `.env.production`** — both are gitignored and excluded from
  Docker builds via `.dockerignore`. Never hardcode keys in source or commit them.
- **Rotate keys regularly** — especially `SECRET_KEY` (JWTs), `ENCRYPTION_KEY` (stored API keys:
  rotating it invalidates previously stored keys), and provider API keys.
- **`DEBUG=false` and `DISABLE_AUTH=false` in production.** `DISABLE_AUTH=true` disables all JWT
  checks and exists purely for sandboxed development.
- Generate secrets with:
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- The Docker image runs as a non-root user (`trader`, uid 1000) and contains no baked secrets.
- CORS is an explicit allow-list (`CORS_ORIGINS`) — avoid `"*"` in production.

## Project Structure

```
trading-backend/
├── app/
│   ├── main.py              # FastAPI app, router mounting, middleware, /health
│   ├── config.py            # pydantic-settings (env-driven configuration)
│   ├── celery_app.py        # Celery instance (async backtest tasks)
│   ├── database/            # SQLAlchemy async session, models, redis client
│   ├── models/              # ORM models: user, portfolio, strategy, signal, ...
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routers/             # HTTP + WS endpoints (users, settings, backtest, ...)
│   ├── services/            # auth, signals, strategy, indicators, filtering, data
│   ├── providers/           # binance, yahoo, alphavantage, stock WS providers
│   ├── backtest/            # engines, performance metrics, report generation
│   ├── core/                # streaming managers, chart storage, indicator registry
│   ├── websocket/           # chart WS handler & shared connection managers
│   ├── tasks/               # Celery task definitions
│   └── utils/               # security helpers (Fernet), misc utilities
├── strategies/              # saved strategy files (volume-mounted in Docker)
├── tests/                   # pytest suite (unit/)
├── data/                    # static reference data (NASDAQ symbol lists)
├── logs/ · reports/ · chart_storage/   # runtime output (gitignored)
├── requirements.txt         # pinned dependencies (grouped, with dev/test section)
├── .env.example             # documented environment template
├── Dockerfile               # python:3.11-slim, non-root, HEALTHCHECK
├── docker-compose.yml       # redis + backend + celery-worker (healthchecks)
└── .dockerignore / .gitignore
```

## Known Limitations (ملاحظات ومحددات)

Honest list — several items are being fixed by parallel refactor tasks:

- **Login endpoint disabled**: `POST /api/v1/users/login` is commented out while the OAuth2
  password scheme still points at it; the auth flow is mid-refactor.
- **Sync ORM misuse**: several routers use sync `db.query(...)` on `AsyncSession` — being
  converted to async `select()` (worklog bugs B1–B22).
- **Duplicated modules**: `backtest` vs `backtest1`, `strategies` vs `strategies1`, multiple
  market-overview WS variants — deduplication is planned.
- **Stock-analysis double prefix**: effective paths are `/api/v1/stocks/stocks/...` (see table).
- **AlphaVantage free tier**: 25 requests/day and strict rate limits; Yahoo Finance may throttle
  or change markup without notice.
- **Binance regional restrictions**: some regions block `stream.binance.com` — configure
  `BINANCE_WS_URL` accordingly.
- **Single-node state**: WebSocket stream managers and indicator state are in-process (and/or
  Redis) — horizontal scaling needs a shared-state strategy.
- **No Celery Beat schedule**: periodic tasks are not configured; `celery-beat` is intentionally
  disabled in compose (see comment there for re-enabling).
- **`config.py` currently reads `.env.production`** as its env file — inconsistent with the
  documented dev flow; queued for the config refactor task.


## ما الجديد في هذا الإصدار (v2 — Professionalization Round 8)

### 1) منظومة الفريمات المتعددة MTF (جديدة كليًا)
- `app/services/mtf_analyzer.py` — يركّب RSI/MACD/EMA-cross/SMA-cross/Stochastic/Bollinger/trend_filter/liquidity على أي عدد فريمات بأوزان خفيف(×1)/متوسط(×2)/ثقيل(×3).
- `POST /api/v1/mtf/analyze` — تحليل كامل مع تفصيل كل (فريم×مؤشر) وثقة موحدة وبوابات رفض.
- اختبارات: `python scripts/test_mtf_scenarios.py` → 18/18 PASS.

### 2) أداء المحرك O(n²)→O(n)
- قرار الاستراتيجية: 2.35ms → **0.009ms ثابتة** (×260).
- باك-تست سنة كاملة على فريم الدقيقة (527,040 شمعة): **32–56 ثانية** (كان مستحيلًا).
- السبب الجذري المصلح: deepcopy لـ df.attrs عند كل وصول عمود + سجلات debug حثيثة تبني index.tolist() كاملة لكل قراءة مؤشر + قاموس مؤشرات يُبنى لكل تقييم + VisualCandle لكل شمعة (أصبحت عينات فوق 20k شمعة — الصفقات/equity دقيقة 100%).

### 3) نقطة /backtest/run لا تعلق بعد الآن
- فحص broker سريع (2s) → 503 فوري برسالة واضحة عندما يكون Redis/Celery غير متاح.

### 4) أدوات بيانات وتقارير احترافية
- `scripts/fetch_history.py` — جلب سنة BTC/ETH لكل الفريمات مع تقرير سلامة (فجوات/NaN/صلاحية OHLC) → `data/history/` (Parquet).
- `scripts/run_year_backtests.py` — مصفوفة باك-تست كاملة (84 تشغيلًا) بحفظ تدريجي ذرّي وقابل للاستئناف.
- `scripts/generate_reports.py` — توليد تقارير Markdown تلقائيًا من ملفات النتائج.
- `scripts/build_merge_package.py` — حزمة دمج ZIP ببيان (جديد/معدل/محذوف) مقارنةً بالمشروع الأصلي.
- التقارير في `reports/`: الباك-تست السنوي، سيناريوهات MTF، التحقق الرياضي (113/113)، قواعد البيانات وAPI، والتقرير النهائي العربي.

---
## License

MIT — placeholder. See `LICENSE` (to be added).

---
© Trading Backend Project — for internal/educational use. Trading involves risk; this software
does not provide financial advice.
