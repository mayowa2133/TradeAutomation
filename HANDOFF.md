# Handoff

## Current Status

The repository now contains a runnable MVP with:

- FastAPI API surface
- SQLAlchemy models and Alembic migration
- paper trading default
- explicit live-trading gating
- market data ingestion through CCXT
- four strategies
- event-driven backtesting
- APScheduler worker
- pytest coverage for the core safety path

## What Is Done

- Safety-first config defaults and live fail-closed checks
- Order, trade, position, strategy config, market data, event log, and portfolio persistence
- Paper exchange execution with fee/slippage accounting and cancel support
- Strategy registry with persisted enable/disable state
- Risk service for deterministic entry blocking
- Monitoring endpoints, websocket event stream, and scripts
- Dockerfile and docker-compose stack for API, Postgres, Redis, and worker

## What Was Tightened During Audit

- aligned imports and package boundaries across services, routes, and tests
- verified FastAPI app import/startup path
- checked docker-compose env/runtime consistency against `.env.example`
- aligned README commands with the actual scripts, routes, and worker process
- updated docs so the current behavior matches the code
- fixed the broken paper limit-order cancel test so it exercises the real `OrderType.LIMIT` flow
- removed obsolete Compose `version` metadata and made `.env.example` the required baseline env file with `.env` as an optional override
- verified Alembic upgrade execution against SQLite for schema sanity before handoff

## Partially Done

- Live trading adapter is intentionally narrow and focused on spot order placement only
- Redis is optional in local runtime and currently used for cache acceleration rather than a hard dependency
- Websocket streaming is lightweight and based on event-log polling, not a dedicated event bus

## Known Gaps

- No advanced portfolio optimization
- No exchange websocket ingestion yet; market data is currently polling-based
- No UI dashboard beyond the API and websocket feed
- No multi-asset basket backtesting
- No shorting/margin logic in execution; v1 is long-only spot

## Next Best Tasks

1. Add exchange websocket ingestion for lower-latency candles/tickers.
2. Add stop-loss and take-profit order synchronization to live trading adapters.
3. Add richer account snapshots and equity history for analytics dashboards.
4. Add more realistic order-book slippage models.
5. Add integration tests against docker-compose services.

## How To Run

```bash
cp .env.example .env
uv pip install -e .[dev]
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Worker:

```bash
uv run python -m app.workers.runner
```

Docker:

```bash
docker compose up --build
```

## How To Verify

```bash
uv run pytest
uv run python -c "from app.main import app; print(app.title)"
curl http://localhost:8000/api/v1/health
```
