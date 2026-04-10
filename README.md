# Trade Automation Platform

Safety-first crypto trading automation with FastAPI, SQLAlchemy, PostgreSQL, Redis, APScheduler, CCXT, Bybit perpetual support, a React desktop operations dashboard, and explicit paper-trading defaults.

## Safety First

Live trading is risky and disabled by default.

- `TRADING_MODE=paper` is the default.
- `ENABLE_LIVE_TRADING=false` is the default.
- Live execution fails closed unless the explicit mode flag and the required credentials are both present.
- LLM-triggered execution is allowed only for backtests and paper mode when you explicitly enable it.
- LLM-triggered live trading is blocked by design.
- The system makes no profitability claims.

## What This Repository Can Do

- ingest historical crypto OHLCV through CCXT for spot and Bybit USDT perpetuals
- persist instruments, candles, quotes, depth snapshots, trades, orders, positions, optimizer runs, news items, and LLM decisions
- stream Bybit public market data through a dedicated websocket worker
- run EMA crossover, RSI mean reversion, breakout, and experimental ML filter strategies with long and short signal support
- simulate paper trading with leverage-aware perpetual accounting, long/short positions, and depth-aware fills
- optionally place live spot or Bybit perpetual orders behind explicit safety gates
- apply deterministic risk controls for drawdown, daily loss, leverage, liquidation distance, spread, slippage, exposure caps, cooldowns, and kill switch state
- run backtests for spot or perpetual instruments with leverage, liquidation thresholds, fees, and funding-aware accounting
- expose REST and websocket interfaces for monitoring, manual operations, optimizer runs, news review, and LLM review
- serve a desktop-first React operations dashboard from `frontend/`

## Stitch

The dashboard work is anchored to the Google Stitch project configured in this repo:

- Stitch project id: `1872692140714476366`

The coded frontend was built to match that desktop operations brief. Stitch project creation succeeded, but direct screen generation from the current MCP endpoint returned `invalid argument` responses during implementation, so the UI was coded directly while keeping the same design direction and project reference.

## Quick Start

### Local backend

```bash
cp .env.example .env
uv venv
source .venv/bin/activate
uv pip install -e .[dev]
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The checked-in `.env.example` is host-friendly for local backend work and uses SQLite by default. Docker Compose overrides database and Redis URLs inside containers.

### Local workers

Scheduler worker:

```bash
uv run python -m app.workers.runner
```

Bybit websocket worker:

```bash
STREAM_WORKER_ENABLED=true uv run python -m app.workers.stream_runner
```

### Local frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to `http://localhost:8000`.

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Services:

- API: [http://localhost:8000](http://localhost:8000)
- OpenAPI docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Frontend dashboard: [http://localhost:4173](http://localhost:4173)
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Important Environment Variables

Core runtime:

- `TRADING_MODE`: `paper` or `live`
- `ENABLE_LIVE_TRADING`: explicit live enable gate
- `DATABASE_URL`
- `REDIS_URL`
- `AUTO_CREATE_TABLES`
- `SCHEDULER_ENABLED`
- `STREAM_WORKER_ENABLED`

Spot execution:

- `EXCHANGE_NAME`
- `EXCHANGE_API_KEY`
- `EXCHANGE_API_SECRET`
- `EXCHANGE_API_PASSWORD`

Perpetual execution:

- `DERIVATIVES_EXCHANGE_NAME`
- `DERIVATIVES_API_KEY`
- `DERIVATIVES_API_SECRET`
- `BYBIT_WS_PUBLIC_URL`

Risk and execution:

- `MAX_RISK_PER_TRADE`
- `MAX_DAILY_LOSS_PCT`
- `MAX_DRAWDOWN_PCT`
- `MAX_GROSS_EXPOSURE_PCT`
- `MAX_NET_EXPOSURE_PCT`
- `MAX_SIDE_EXPOSURE_PCT`
- `MAX_LEVERAGE`
- `MIN_LIQUIDATION_BUFFER_PCT`
- `MAX_ABS_FUNDING_RATE`
- `KILL_SWITCH`

Optional intelligence:

- `NEWS_INGESTION_ENABLED`
- `OPTIMIZER_ENABLED`
- `LLM_FEATURES_ENABLED`
- `LLM_PROVIDER`
- `OPENAI_API_KEY`
- `CLAUDE_API_KEY`
- `LLM_AUTONOMY_PAPER`
- `LLM_AUTONOMY_BACKTEST`
- `LLM_AUTONOMY_LIVE`

## REST API Overview

Core:

- `GET /api/v1/health`
- `GET /api/v1/config`
- `GET /api/v1/strategies`
- `POST /api/v1/strategies/{name}/toggle`
- `GET /api/v1/paper/status`
- `GET /api/v1/risk/state`
- `GET /api/v1/events/recent`

Execution and state:

- `GET /api/v1/positions`
- `POST /api/v1/positions/{position_id}/close`
- `GET /api/v1/orders`
- `POST /api/v1/orders/manual`
- `POST /api/v1/orders/{order_id}/cancel`
- `GET /api/v1/trades`
- `GET /api/v1/pnl/summary`

Market and instruments:

- `GET /api/v1/instruments`
- `GET /api/v1/market/depth`
- `GET /api/v1/market/stream-status`

Research and automation:

- `POST /api/v1/backtests/run`
- `POST /api/v1/optimizer/run`
- `GET /api/v1/optimizer/latest`
- `GET /api/v1/news`
- `GET /api/v1/llm/decisions`
- `POST /api/v1/llm/decisions`
- `GET /api/v1/dashboard/summary`

Websocket channels:

- `GET /ws/events`
- `GET /ws/market`
- `GET /ws/execution`
- `GET /ws/system`

## Backtest Example

```bash
curl -X POST http://localhost:8000/api/v1/backtests/run \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_name": "ema_crossover",
    "symbol": "BTC/USDT",
    "timeframe": "5m",
    "instrument_type": "perpetual",
    "margin_mode": "isolated",
    "leverage": 2,
    "limit": 300
  }'
```

## Manual Paper Order Example

```bash
curl -X POST http://localhost:8000/api/v1/orders/manual \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC/USDT",
    "instrument_type": "perpetual",
    "position_side": "short",
    "quantity": 0.2,
    "reference_price": 100000,
    "leverage": 2
  }'
```

## Project Structure

```text
app/
  api/          FastAPI routes and dependency helpers
  core/         configuration, logging, enums, exceptions
  db/           SQLAlchemy session and models
  exchanges/    paper, CCXT spot, and Bybit perpetual adapters
  ml/           engineered features and lightweight model helpers
  schemas/      Pydantic request and response contracts
  services/     execution, risk, market data, optimizer, news, dashboard, LLM hooks
  strategies/   signal-generation layer
  utils/        indicators, fees, metrics, depth helpers, precision helpers
  workers/      scheduler jobs plus websocket stream runner
frontend/
  src/          React dashboard implementation
  Dockerfile    production-style static frontend container
tests/          backend regression coverage
```

## Demo Profiles And Trade Review

Dashboard demo profile:

```bash
uv run python scripts/tune_demo_mode.py --profile active-demo
```

Available profiles:

```bash
uv run python scripts/tune_demo_mode.py --list-profiles
```

Lower-turnover research preset:

```bash
uv run python scripts/tune_demo_mode.py --profile research-breakout-15m
```

The `research-breakout-15m` preset is based on recent paper-trade loss review. It is a research hypothesis only, not a profitability claim.

Paper-trade diagnosis:

```bash
uv run python scripts/analyze_paper_trades.py
```

This script summarizes paper-mode exits, fees, hold times, and strategy-level outcomes so you can see whether losses are being driven by cost, churn, or weak signal quality.

## Testing and Verification

Backend:

```bash
uv run pytest
DATABASE_URL=sqlite:///./data/verify.db AUTO_CREATE_TABLES=false uv run alembic upgrade head
```

Frontend:

```bash
cd frontend
npm run lint
npm run test
npm run build
```

## Current Assumptions

- Bybit USDT perpetuals are the first-class derivatives venue.
- Perpetual execution is one-way mode with isolated-margin assumptions in the current implementation.
- The frontend is desktop-first and responsive second.
- News ingestion is RSS-first and designed to be replaceable.
- LLM outputs are advisory intent sources, not direct execution authority.
