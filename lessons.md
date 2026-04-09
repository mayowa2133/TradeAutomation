# Lessons

## Core Engineering Lessons

- Separate strategy generation from execution. Strategies should not own broker side effects.
- Keep live trading safety checks at the configuration and execution layers, not only in documentation.
- A serious MVP benefits more from deterministic controls and observability than from a larger feature surface.
- Persisting event logs pays off quickly when auditing risk rejections and paper fills.

## Trading-Specific Pitfalls

- Overfitting is the default failure mode for naive strategy iteration. Backtests here are for engineering validation, not proof of edge.
- Slippage matters even in liquid crypto pairs, especially on short-horizon systems. The backtester and paper broker both apply slippage explicitly.
- Fee drag is material on 1m/5m systems and must be modeled on both entry and exit.
- Exchange behavior differs across symbols, lot sizes, order status semantics, and balance reporting. The adapter boundary exists to isolate that variance.

## Agent Misuse Risks

- Do not let an LLM become the trade execution decision-maker.
- Do not allow generated natural-language rationales to bypass risk rules.
- Do not hallucinate profitability from a single backtest run.
- Do not widen live-trading permissions without tests and explicit operator review.

## What We Fixed In The Audit

- tightened route-to-service references so API documentation matches implemented endpoints
- checked for missing imports and broken package initialization paths
- ensured the worker, API, README, and compose stack use the same operational commands
- aligned docs with the actual paper-trading-first posture and long-only execution scope
- replaced an invalid limit-order test path with a real resting-order cancel flow
- removed a Compose footgun by letting the stack boot from `.env.example` even before a custom `.env` exists
- validated the Alembic head migration directly instead of assuming the model metadata and migration stayed in sync

## What We Would Do Differently In V2

- Add websocket market data ingestion and dedicated event streaming infrastructure.
- Add richer portfolio accounting with time-series equity snapshots.
- Add broker-specific integration test suites with sandbox credentials.
- Add walk-forward evaluation and more robust time-series cross-validation for ML experiments.
- Add instrument metadata services for tick size, step size, and trading calendar constraints.
