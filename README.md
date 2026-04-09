# Trade Automation MVP

Safety-first crypto trading automation built with FastAPI, SQLAlchemy, PostgreSQL, Redis, APScheduler, CCXT, Pandas, and scikit-learn/LightGBM. The system defaults to paper trading and keeps live execution disabled unless you explicitly enable it.

## Safety Warning

Live trading is risky and disabled by default.

- `TRADING_MODE=paper` is the default.
- `ENABLE_LIVE_TRADING=false` is the default.
- Live execution fails closed if the explicit enable flag is missing.
- Exchange credentials are never hardcoded and must be supplied through environment variables.
- The risk engine can block entries on kill switch, drawdown, daily loss, cooldown, session filter, position count, spread, and symbol allowlist checks.

This repository does not claim profitability. The included strategies are examples of modular execution and research workflows, not trading advice.

## What Is Included

- Historical OHLCV ingestion through CCXT with database persistence and optional Redis caching
- Strategy framework with EMA crossover, RSI mean reversion, breakout, and experimental ML-assisted direction filter
- Paper broker with fee-aware fills, limit-order handling, and persisted orders/trades/positions
- Optional live broker adapter behind explicit safety gating
- Event-driven backtesting with slippage, fees, equity curve, drawdown, and strategy metrics
- FastAPI monitoring/control surface
- APScheduler worker for periodic data refresh and signal evaluation
- Alembic migrations, pytest coverage, Dockerfile, and docker-compose stack
- Repository memory files for future human and AI contributors

## Quick Start

### Local development

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Install dependencies with `uv`:

```bash
uv venv
source .venv/bin/activate
uv pip install -e .[dev]
```

3. Run the API:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

4. Run the scheduler worker in a second terminal:

```bash
uv run python -m app.workers.runner
```

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Services:

- API: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Environment Variables

Key settings in `.env.example`:

- `TRADING_MODE`: `paper` or `live`
- `ENABLE_LIVE_TRADING`: must be `true` for live order placement
- `DATABASE_URL`: PostgreSQL in Docker, SQLite or PostgreSQL locally
- `REDIS_URL`: optional cache/event backend
- `EXCHANGE_NAME`: CCXT exchange id, default `kraken`
- `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`, `EXCHANGE_API_PASSWORD`: only needed for live trading
- `SYMBOL_ALLOWLIST`: comma-separated symbols allowed for entries
- `MAX_RISK_PER_TRADE`, `MAX_DAILY_LOSS_PCT`, `MAX_DRAWDOWN_PCT`: deterministic hard risk limits
- `SCHEDULER_ENABLED`: enables APScheduler jobs in the worker process
- `LLM_FEATURES_ENABLED`: keeps optional LLM hooks disabled by default

## Database and Migrations

Alembic is included for schema management:

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

For local convenience, the app can auto-create tables when `AUTO_CREATE_TABLES=true`, but Alembic remains the intended migration path.

## Running a Backtest

CLI:

```bash
uv run python scripts/run_backtest.py --strategy ema_crossover --symbol BTC/USDT --timeframe 5m --limit 300
```

API:

```bash
curl -X POST http://localhost:8000/api/v1/backtests/run \
  -H "Content-Type: application/json" \
  -d '{"strategy_name":"ema_crossover","symbol":"BTC/USDT","timeframe":"5m","limit":300}'
```

## Running a Paper Trade Demo

```bash
uv run python scripts/demo_paper_trade.py --strategy ema_crossover --symbol BTC/USDT --timeframe 5m
```

The demo fetches market data, evaluates the requested strategy, and only places a simulated paper order when the latest bar produces a valid entry signal and the risk engine approves it.

## Training the Experimental ML Filter

```bash
uv run python scripts/train_model.py --symbol BTC/USDT --timeframe 5m --limit 600
```

The ML path is intentionally lightweight and experimental. It uses engineered OHLCV features and a simple classifier. Missing or stale models fail safely by producing neutral signals.

## API Overview

- `GET /api/v1/health`
- `GET /api/v1/config`
- `GET /api/v1/strategies`
- `POST /api/v1/strategies/{name}/toggle`
- `POST /api/v1/backtests/run`
- `GET /api/v1/paper/status`
- `GET /api/v1/positions`
- `GET /api/v1/orders`
- `POST /api/v1/orders/{order_id}/cancel`
- `GET /api/v1/trades`
- `GET /api/v1/pnl/summary`
- `GET /api/v1/risk/state`
- `GET /api/v1/events/recent`
- `GET /ws/events`

## Project Structure

```text
app/
  api/          FastAPI routes and dependency helpers
  core/         configuration, logging, enums, exceptions
  db/           SQLAlchemy session/base/models
  exchanges/    paper and CCXT execution adapters
  ml/           feature engineering, train/load/predict helpers
  schemas/      Pydantic request/response models
  services/     market data, execution, risk, portfolio, backtesting, scheduling
  strategies/   strategy interface and concrete strategy implementations
  utils/        indicators, fees, metrics, timeframe helpers
  workers/      APScheduler tasks, jobs, and worker runner
scripts/        local automation scripts
tests/          deterministic tests with synthetic market data
```

## Testing

```bash
uv run pytest
```

The test suite covers:

- health endpoint
- config safety defaults
- strategy signal generation
- risk guardrails
- backtesting flow
- paper exchange execution

## Assumptions

- v1 supports long-only spot trading for execution and paper simulation.
- Market data uses CCXT public OHLCV endpoints.
- Redis is optional at runtime for local development but wired into Docker and the data layer.
- Live trading is intentionally narrow in scope and guarded more aggressively than paper trading.
