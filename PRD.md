# Product Requirements Document

## Product

Safety-first crypto trading automation MVP for short-horizon systematic trading research, paper execution, and tightly controlled live execution.

## Target User

- solo quant developer
- small engineering team building a systematic crypto stack
- operator who wants backtesting, paper trading, and observability before enabling live orders

## V1 Goals

- ingest crypto market data
- run modular strategies on 1m/5m/15m candles
- backtest strategies with fees and slippage
- execute paper trades by default
- expose a monitoring/control API
- persist orders, trades, positions, configs, and events
- allow optional live trading behind explicit safety flags

## Functional Requirements

- CCXT-based historical OHLCV ingestion
- normalized candle interface with symbol/timeframe support
- strategy plugin system with four initial strategies
- deterministic risk engine with hard blocks
- abstract exchange adapter with paper and live implementations
- portfolio state and PnL tracking
- backtest engine with exportable metrics/results
- FastAPI endpoints for health, config, strategies, backtests, positions, orders, trades, PnL, risk, and events
- optional LLM interface for explanations and summaries only

## Non-Functional Requirements

- Python 3.11
- typed codebase
- clear docs for future AI contributors
- production-style modular structure
- Docker Compose support
- pytest coverage for the safety-critical path
- explicit logging for trading lifecycle events

## Success Criteria

- The API starts locally.
- Tests pass on synthetic data without exchange access.
- Paper trading works end-to-end from signal to persisted position.
- Live trading remains disabled unless explicitly enabled and properly configured.
- The repository is understandable enough for another agent to extend without reverse-engineering hidden assumptions.

## Risks

- Overfitting strategies to historical noise
- Underestimating slippage and fee impact
- Exchange-specific behavior mismatches through CCXT
- Operational mistakes around live-mode configuration
- Agent-generated changes weakening safety invariants

## Assumptions

- v1 is crypto spot only and long-only on the execution path
- public market data endpoints are available through CCXT
- operators are comfortable running PostgreSQL and Redis locally via Docker
- ML support is experimental and should not be treated as a source of proven alpha
