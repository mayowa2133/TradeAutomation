# Implementation Plan

## Phase 1: Safe Core Runtime

- Implement environment-driven config and logging
- Build database models, session management, and Alembic migration
- Implement paper exchange, risk engine, portfolio state, and execution service

## Phase 2: Trading Research Surface

- Build market data ingestion/persistence
- Implement strategy interface and first four strategies
- Add event-driven backtesting with realistic fee/slippage handling

## Phase 3: API and Operations

- Expose monitoring/control APIs
- Add websocket event stream
- Add APScheduler worker for recurring data refresh and signal evaluation

## Phase 4: Validation

- Add deterministic test fixtures
- Cover safety defaults, health, risk, strategies, backtesting, and paper execution
- Verify app startup and local Docker workflow

## Immediate Priorities

1. Keep the live path fail-closed.
2. Preserve deterministic risk rejection logic.
3. Keep the code modular enough for later broker expansion.
4. Make local development friction low with scripts and Docker support.

## Testing Priorities

- Config defaults and live-trading gating
- Strategy signal correctness on synthetic data
- Paper exchange fee/slippage accounting
- Risk engine rejection conditions
- Backtest metrics and result shape
- FastAPI health and monitoring endpoints

## Deployment Priorities

- Docker Compose for local operations
- PostgreSQL schema migrations through Alembic
- Clear env separation between paper and live mode
- Worker/API process split so scheduled jobs are not coupled to HTTP lifecycle
