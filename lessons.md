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
- If you evaluate 1m strategies every 15 seconds, you must dedupe actions by candle. Otherwise crossover and breakout systems can enter and then immediately exit on the same bar simply because the worker re-reads the same signal state.
- For bar-based strategies, “evaluate frequently” and “act frequently” are not the same thing. A 15-second scheduler can still be useful for monitoring, but entries and exits should key off completed bars unless the strategy is explicitly intrabar-aware.
- Exit cooldowns belong at the execution-orchestration layer, not inside each strategy. That keeps strategies pure and makes the anti-churn rule consistent across implementations.
- Faster demo profiles are useful for showing the dashboard, but they should live behind explicit config or scripts. Demo tuning is for observability, not evidence of better trading performance.
- If removing fees and slippage turns a strategy from mildly positive into clearly negative, the core issue is turnover and cost structure, not the absence of an AI decision layer.
- A recent-sample parameter set that looks better is only a research lead. Treat it as a hypothesis that still needs out-of-sample validation, not as proof of edge.
- A scheduler “refresh” job is not a real refresh if it returns cached DB rows once `limit` bars already exist. For live paper-trading loops, refresh paths need an explicit forced fetch mode or they silently freeze market state.
- When a hard guard like max daily loss fires inside a scheduler loop, treat it as a first-class operating state rather than an exception flood. The order should remain rejected, but the scheduler should keep running cleanly.

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
- fixed timeframe identity and same-candle reprocessing issues that were causing paper-trading churn during rapid scheduler loops
- moved 1-minute strategy evaluation onto completed bars, added strategy-level post-exit cooldowns, and staggered market refresh jobs so the worker loop behaves more like a trading system and less like a polling storm
- updated README, HANDOFF, and frontend docs so operators are not following spot-only instructions against a derivatives-capable codebase
- separated dashboard demo tuning from lower-turnover research tuning so product demos stop contaminating strategy evaluation
- added lightweight paper-trade loss analysis and an Overview trade timeline because loss diagnosis needs to be visible from the product surface, not only from ad hoc SQL

## What We Would Do Differently In V2

- Add authenticated exchange websocket order and fill streams, not only public market-data streams.
- Add richer portfolio accounting with time-series equity snapshots and per-symbol attribution history.
- Add broker-specific integration test suites with sandbox credentials.
- Add walk-forward evaluation and more robust time-series cross-validation for ML experiments.
- Add a real generated Stitch design-system and screen source-of-truth flow once the MCP generation path is reliable.
