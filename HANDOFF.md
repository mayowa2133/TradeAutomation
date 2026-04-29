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
- tuned the `research-breakout-15m` preset to narrow the symbol universe to `BTC/USDT` and `ETH/USDT`, add candidate ranking, disable BTC shorts, and keep the slower 15-minute paper sample focused on the strongest majors instead of the noisier alt pairs
- added higher-timeframe trend confirmation plus ATR/volume quality filters to the breakout strategy so the remaining shorts only trigger in a more clearly bearish regime and late weak breakouts get filtered out earlier
- added `scripts/analyze_paper_trades.py` to summarize paper-mode losses by strategy, symbol, fees, hold times, and realized PnL
- added `scripts/reset_paper_state.py` so the paper account can be cleared and reinitialized cleanly after a demo session or daily-loss shutdown
- extended `scripts/reset_paper_state.py` to clear event logs as well, so weekly paper baselines do not inherit stale operational noise in the dashboard
- dashboard and market-status endpoints now filter stream-health rows to the active symbol allowlist so stale ADA/SOL/XRP rows stop polluting the BTC/ETH research view
- added an Overview trade timeline panel that reconstructs the recent realized path from exit trades and shows the latest fills in one place
- hardened websocket stream health reporting so stale or silent Bybit public streams stop appearing as indefinitely `connecting`
- added websocket receive-timeout reconnect logic and heartbeat-aware stream status serialization for dashboard and API consumers
- fixed Bybit order-book persistence for large exchange sequence values and bounded stored stream-status error text so the public stream worker no longer crashes on those two failure modes
- fixed the broken risk-exit path by adding `DecisionSource.RISK` in code and in the Postgres enum migration, so stop-loss and liquidation exits now persist instead of crashing the scheduler worker
- redesigned breakout exits to be side-specific and added a minimum breakout-strength filter so the 15-minute research profile stops flagging the same bar as both breakout entry and generic exit
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
- The dashboard stream-health view is now filtered to the active allowlist, and the paper reset script also clears stale stream-status rows outside that allowlist
- The paper reset script now clears event logs too, so a weekly reset gives you a cleaner dashboard baseline instead of carrying forward old operational messages.
- The new Overview realized-path panel is reconstructed from recent exit trades. It is operationally useful, but it is not a replacement for persisted equity-history storage.
- Recent paper-trade review showed the fast 1-minute demo profile loses mainly because turnover and fees overwhelm a weak edge. The current improvement direction is slower 15-minute breakout settings on a slightly wider but still selective universe, not an AI execution overlay.
- Public market-data websocket status is now reported more honestly, but authenticated execution streams and deeper venue-specific reconnection handling are still future work.
- The repaired 15-minute breakout runtime is operationally cleaner than the earlier version, but the first post-fix paper sample is still net negative. The current narrowed research setup is intentionally focused on `BTC/USDT` and `ETH/USDT`, with ranked candidates and slower market refreshes to reduce Bybit pressure.
- The updated 15-minute breakout runtime now uses BTC short lockout plus higher-timeframe trend and ATR/volume quality filters. That should reduce the weakest entries, but it still needs a longer paper sample before anyone should treat it as validated for real money.

## Next Best Tasks

1. Add authenticated exchange websocket order/fill ingestion for live reconciliation.
2. Extend the reset/demo-state workflow if you want a softer reset that preserves closed-trade history while still clearing live paper positions and PnL state.
3. Add equity-history persistence and richer charting/replay views in the frontend.
4. Add funding-history persistence and scheduled funding application for open paper positions.
5. Add docker-compose integration tests or smoke tests that cover API plus frontend together.
6. Investigate the Stitch MCP invalid-argument responses and backfill generated source screens into project `1872692140714476366`.
7. Re-run the repaired `research-breakout-15m` profile for a longer sample and decide whether the next improvement should be tighter breakout-quality filters, a different exit model, or a further correlation-aware ranking pass.

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

Recent runtime note:

- `2026-04-11` repair pass added the `risk` exit source, side-specific breakout exits, and `min_breakout_strength_pct=0.001` to the research breakout preset.
- The first repaired runtime sample confirmed that a stop-driven `ADA/USDT` exit was persisted as a `risk` exit instead of crashing the worker.
- `2026-04-29` runtime review found a profitable dust-sized ETH short remainder that was repeatedly hitting take-profit but failing close normalization because `0.009999999999999787` rounded below the `0.01` lot size. Precision rounding now snaps tiny float artifacts at increment boundaries, partial-exit fee allocation now uses original entry quantity instead of current remaining quantity, and regression coverage protects both cases.

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
