# Architecture

## Overview

The system is a modular crypto trading backend centered on five runtime flows:

1. market data ingestion
2. strategy evaluation
3. deterministic risk gating
4. broker execution and portfolio persistence
5. monitoring, backtesting, and operational visibility

The architecture is intentionally split so that strategy logic cannot execute orders by itself, and optional LLM features cannot become the execution brain.

## Main Components

### Core

- `app/core/config.py`: environment-driven settings, safety defaults, mode gating
- `app/core/logging.py`: standard logging with optional JSON output
- `app/core/enums.py`: shared enum definitions for orders, positions, and trading mode
- `app/core/exceptions.py`: explicit error types

### Database

- SQLAlchemy models persist orders, trades, positions, market data, strategy config, strategy runs, event logs, and portfolio state
- Alembic manages schema migration history

### Market Data Layer

- `app/services/data_service.py` provides a normalized OHLCV interface
- Public CCXT clients fetch historical candles
- Market data is normalized into a pandas DataFrame and persisted in `market_data`
- Redis is used opportunistically for short-lived caching; the system still runs without it

### Strategy Layer

- `app/strategies/base.py` defines a common interface
- Concrete strategies:
  - EMA crossover momentum
  - RSI mean reversion
  - breakout
  - experimental ML-assisted direction filter
- `app/services/strategy_registry.py` owns registration, instantiation, and default DB config seeding

### Risk Engine

- `app/services/risk_service.py` is the final gate before new entries
- It enforces:
  - max risk per trade
  - max concurrent positions
  - max daily loss
  - max drawdown circuit breaker
  - spread/slippage checks
  - symbol allowlist
  - session filters
  - cooldown after stop loss
  - kill switch

### Execution Layer

- `app/exchanges/base.py` defines the adapter contract
- `app/exchanges/paper_exchange.py` simulates fills and limit order behavior
- `app/exchanges/ccxt_exchange.py` provides optional live execution through CCXT
- `app/services/execution_service.py` orchestrates:
  - strategy signal evaluation
  - risk approval
  - order submission
  - order/trade/position persistence
  - portfolio state recalculation

### Portfolio / State Layer

- `app/services/portfolio_service.py` computes cash, equity, realized PnL, unrealized PnL, and drawdown state
- Portfolio state is persisted in `portfolio_state` for risk checks and API visibility

### Backtesting Layer

- `app/services/backtest_service.py` runs an event-driven backtest over normalized candles
- It applies slippage and fees, tracks trades and equity, and returns summary metrics
- Strategy runs can be persisted in `strategy_runs`

### API Layer

- FastAPI provides monitoring and control endpoints
- A websocket endpoint streams recent event-log data for lightweight monitoring
- The API is intentionally operational, not a large front-end system

### Worker / Scheduling Layer

- APScheduler jobs run in a dedicated worker process
- Jobs refresh market data and evaluate enabled strategies at configured intervals
- Scheduler logic is isolated from the API process by default

### Optional LLM Layer

- `app/services/llm_service.py` exposes interfaces for:
  - market news summarization
  - signal explanation
  - trade rationale generation
  - anomaly review
  - daily summary generation
- This layer is disabled by default and cannot place or approve orders

## Data Flow

1. Worker requests recent OHLCV through `DataService`
2. Data is fetched from DB cache or CCXT, normalized, cached, and persisted
3. `StrategyRegistry` instantiates enabled strategies
4. A strategy emits entry/exit signals from the candle DataFrame
5. `ExecutionService` checks for an existing open position
6. New entry signals go through `RiskService`
7. Approved orders are sent to the selected exchange adapter
8. Orders, trades, positions, and portfolio state are persisted
9. Event logs are emitted for API and websocket visibility

## Order Lifecycle

1. Strategy or operator intent reaches `ExecutionService`
2. An `Order` row is created with a client order id and initial status
3. The exchange adapter simulates or submits the order
4. If filled:
  - a `Trade` fill event is recorded
  - an open `Position` is created or updated
  - `PortfolioState` is recalculated
  - an `EventLog` record is inserted
5. If unfilled:
  - the order remains `NEW`
  - it can later be canceled through the API

## Risk Checks Lifecycle

1. `ExecutionService` calculates intended quantity using strategy sizing
2. `RiskService.evaluate_entry` gathers:
  - current portfolio state
  - open position count
  - daily realized PnL
  - latest drawdown
  - recent stop-loss events
3. Each hard rule is evaluated in deterministic order
4. The first violation returns a rejection reason
5. Rejections are logged to `event_logs`

## Backtesting Lifecycle

1. Fetch or load OHLCV
2. Generate strategy signals
3. Walk candle by candle
4. Apply entry sizing, fees, and slippage
5. Mark stops, exits, and final liquidation
6. Produce summary metrics and trade history
7. Persist the run metadata for traceability

## Paper vs Live Trading Separation

- Paper trading uses `PaperExchange` and requires no credentials
- Live trading uses `CCXTExchange` and requires:
  - `TRADING_MODE=live`
  - `ENABLE_LIVE_TRADING=true`
  - all required exchange credentials
- Live startup emits a warning log
- The API exposes mode information so operators can verify the running posture

## Extension Points

Future support can be added cleanly:

- Forex or stocks:
  - add new broker adapters under `app/exchanges/`
  - extend symbol metadata and session calendars
- Polymarket:
  - implement a market data adapter and execution adapter with the same service boundaries
- News ingestion:
  - add a market-news service feeding the optional LLM interface
- Portfolio optimizer:
  - add a portfolio construction layer above strategy outputs, not inside execution
- Dashboard UI:
  - consume the FastAPI and websocket interfaces without changing risk or execution logic
