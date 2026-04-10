# Lessons

## Core Engineering Lessons

- Separate strategy generation from execution. Strategies should not own broker side effects.
- Keep live trading safety checks at the configuration and execution layers, not only in documentation.
- A serious MVP benefits more from deterministic controls and observability than from a larger feature surface.
- Persisting event logs pays off quickly when auditing risk rejections and paper fills.
- When you generalize from spot into derivatives, portfolio accounting has to change before UI and execution can be trusted. Cash, collateral, equity, and exposure are not interchangeable.
- Precision metadata is a first-order concern. Treating broker decimal precision as a step size will create invalid orders even when the rest of the execution path looks correct.

## Trading-Specific Pitfalls

- Overfitting is the default failure mode for naive strategy iteration. Backtests here are for engineering validation, not proof of edge.
- Slippage matters even in liquid crypto pairs, especially on short-horizon systems. The backtester and paper broker both apply slippage explicitly, and depth-aware simulation is better than candle-only assumptions when you have the data.
- Fee drag is material on 1m/5m systems and must be modeled on both entry and exit.
- Exchange behavior differs across symbols, lot sizes, tick sizes, leverage limits, order status semantics, and balance reporting. The adapter boundary exists to isolate that variance.
- Funding is easy to ignore and expensive to forget. Perpetual accounting that omits funding costs or credits will drift away from reality.
- Liquidation distance is not just another metric for the dashboard. It is a hard constraint that must be checked before entry sizing is accepted.

## Agent Misuse Risks

- Do not let an LLM become the trade execution decision-maker.
- Do not allow generated natural-language rationales to bypass risk rules.
- Do not hallucinate profitability from a single backtest run.
- Do not widen live-trading permissions without tests and explicit operator review.
- Do not assume a connected design tool MCP means every generation endpoint works. Treat external design-tool automation as best effort and keep the coded UI path unblocked.

## What We Fixed In The Audit

- tightened route-to-service references so the expanded derivatives and dashboard endpoints match real implementations
- fixed the SQLAlchemy reserved-name break in `StreamStatus` before it became a runtime-only failure in production
- validated the FastAPI lifespan path, not just module import, after startup became responsible for more initialization work
- aligned docker-compose, Alembic, workers, and frontend packaging after the repo became multi-service
- added regression tests for new risk, optimizer, news, perpetual, and dashboard behavior instead of relying on the original MVP-only suite
- updated README, HANDOFF, and frontend docs so operators are not following spot-only instructions against a derivatives-capable codebase

## What We Would Do Differently In V2

- Add authenticated exchange websocket order and fill streams, not only public market-data streams.
- Add richer portfolio accounting with time-series equity snapshots and per-symbol attribution history.
- Add broker-specific integration test suites with sandbox credentials.
- Add walk-forward evaluation and more robust time-series cross-validation for ML experiments.
- Add a real generated Stitch design-system and screen source-of-truth flow once the MCP generation path is reliable.
