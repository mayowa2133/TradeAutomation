# Handoff

## Current Status

The repository now contains a runnable expanded platform with:

- FastAPI monitoring and control API
- React + TypeScript frontend dashboard in `frontend/`
- SQLAlchemy models plus Alembic bootstrap migration
- paper trading default with live-trading fail-closed gates
- spot plus Bybit USDT perpetual execution paths
- websocket ingestion worker for Bybit public data
- four side-aware strategies
- backtesting for spot and perpetual instruments
- optimizer, news ingest, and LLM review hooks
- backend and frontend tests that run locally

## What Is Done

- Safety-first config defaults, explicit live gates, and live LLM lockout
- Persistence for instruments, candles, quotes, depth snapshots, funding rates, optimizer runs, news, and LLM decisions
- Paper exchange upgraded for depth-aware, leverage-aware spot and perpetual simulation
- Spot CCXT adapter plus Bybit perpetual adapter
- Strategy registry, strategy toggles, and side-aware signal handling
- Risk engine expanded for leverage, liquidation distance, funding sanity, and exposure caps
- Backtest service expanded for shorting, leverage, liquidation, and funding-aware accounting
- FastAPI endpoints for instruments, market depth, stream status, optimizer, news, LLM decisions, and dashboard summary
- Websocket endpoints for events, market, execution, and system state
- Scheduler worker plus dedicated stream worker
- Docker Compose stack for API, frontend, Postgres, Redis, scheduler worker, and stream worker
- Frontend dashboard with Overview, Market Monitor, Execution Desk, Research Lab, News + AI, and Settings + Safety views

## What Was Tightened During Audit

- repaired broken service contracts after the derivatives/domain expansion
- fixed the `StreamStatus.metadata` ORM break by renaming the persisted field
- aligned schemas, routes, and services with the new spot/perpetual model
- verified FastAPI startup with lifespan, not just raw import
- validated Alembic head upgrade against SQLite after the schema expansion
- validated docker-compose configuration after adding frontend and stream-worker services
- added regression coverage for precision handling, liquidation buffers, optimizer outputs, news ingest, dashboard endpoints, and perpetual paper trading
- fixed strategy-instance identity so `strategy + symbol + timeframe` positions no longer interfere with each other
- added same-candle action deduping in `ExecutionService.evaluate_strategy()` so 15-second scheduler loops do not enter/exit/re-enter on the same 1-minute bar
- fixed worker market-data refresh so scheduled refreshes can force an exchange fetch instead of reusing a full but stale OHLCV cache forever
- changed strategy evaluation to use completed bars by default, so 1-minute strategies act on bar close instead of every 15-second worker tick
- added per-strategy exit cooldown handling so a strategy instance cannot immediately re-enter on the next worker pass after an exit
- split market refresh scheduling into per-symbol/per-timeframe jobs with staggered start times, which removed the earlier APScheduler max-instances pressure
- normalized scheduled risk rejections so a daily-loss or other hard-risk block is treated as an expected evaluation outcome instead of a scheduler job failure
- added `scripts/tune_demo_mode.py` to apply a reproducible higher-activity paper-trading profile without weakening live-trading defaults
- expanded `scripts/tune_demo_mode.py` into named demo and research presets so dashboard demos and lower-turnover experiments use explicit profiles
- added `scripts/analyze_paper_trades.py` to summarize paper-mode losses by strategy, symbol, fees, hold times, and realized PnL
- added an Overview trade timeline panel that reconstructs the recent realized path from exit trades and shows the latest fills in one place
- replaced the template frontend with a real dashboard and verified lint, test, and production build
- updated README and frontend docs so local and docker instructions match the actual code paths

## Partially Done

- Live trading remains intentionally narrow and more conservative than paper mode
- Perpetual support is currently centered on Bybit linear USDT contracts
- Order-book simulation is depth-aware, but it is still not a full exchange queue-model simulator
- Stitch project creation succeeded, but automated screen generation from the current MCP endpoint returned invalid-argument responses during implementation

## Known Gaps

- No authenticated exchange websocket execution updates yet
- No derivatives sandbox/integration test suite against a real exchange
- No portfolio optimizer that rebalances across existing open positions automatically
- No historical replay UI or charting library beyond the current operational desk presentation
- No premium news provider integration yet; RSS is the current default
- Stitch MCP screen generation still needs investigation if you want the source-of-truth mockups generated directly inside Stitch
- The current demo paper account has already breached the configured daily-loss guard, so new entries stay blocked until the state is reset or the demo risk budget is adjusted
- The new Overview realized-path panel is reconstructed from recent exit trades. It is operationally useful, but it is not a replacement for persisted equity-history storage.
- Recent paper-trade review showed the fast 1-minute demo profile loses mainly because turnover and fees overwhelm a weak edge. The current improvement direction is slower 15-minute breakout settings on a narrower universe, not an AI execution overlay.

## Next Best Tasks

1. Add authenticated exchange websocket order/fill ingestion for live reconciliation.
2. Add a reset/demo-state workflow so paper trading can be restarted cleanly after the daily-loss breaker trips during dashboard demos.
3. Add equity-history persistence and richer charting/replay views in the frontend.
4. Add funding-history persistence and scheduled funding application for open paper positions.
5. Add docker-compose integration tests or smoke tests that cover API plus frontend together.
6. Investigate the Stitch MCP invalid-argument responses and backfill generated source screens into project `1872692140714476366`.

## How To Run

```bash
cp .env.example .env
uv pip install -e .[dev]
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Scheduler worker:

```bash
uv run python -m app.workers.runner
```

Stream worker:

```bash
STREAM_WORKER_ENABLED=true uv run python -m app.workers.stream_runner
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Docker:

```bash
docker compose up --build
```

Demo-tuned paper mode for dashboard walkthroughs:

```bash
uv run python scripts/tune_demo_mode.py --profile active-demo
```

Lower-turnover research preset:

```bash
uv run python scripts/tune_demo_mode.py --profile research-breakout-15m
```

Paper-trade diagnosis:

```bash
uv run python scripts/analyze_paper_trades.py
```

If the worker stops opening new demo trades after a noisy session, inspect `/api/v1/dashboard/summary`. The daily-loss guard will intentionally block fresh entries once realized losses exceed the configured threshold.

## How To Verify

```bash
uv run pytest
DATABASE_URL=sqlite:///./data/verify.db AUTO_CREATE_TABLES=false uv run alembic upgrade head
uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    print(client.get("/api/v1/dashboard/summary").status_code)
PY
cd frontend && npm run lint && npm run test && npm run build
```
