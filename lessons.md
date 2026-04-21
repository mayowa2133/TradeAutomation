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
- Execution enums and database enums have to evolve together. A new decision-source path that exists only in Python can still crash a healthy worker the first time a real stop-loss fires in Postgres.
- A scheduler “refresh” job is not a real refresh if it returns cached DB rows once `limit` bars already exist. For live paper-trading loops, refresh paths need an explicit forced fetch mode or they silently freeze market state.
- When a hard guard like max daily loss fires inside a scheduler loop, treat it as a first-class operating state rather than an exception flood. The order should remain rejected, but the scheduler should keep running cleanly.
- A market-data stream that says `connecting` for hours is worse than a clearly degraded stream. Operators need truthful websocket status so they know when the system is trading off REST refreshes instead of live depth updates.
- Public websocket clients need explicit recv timeouts and reconnect logic. Otherwise a silent connection can sit open forever and make the dashboard look healthier than the feed really is.
- “Research profile” does not mean “as selective as possible.” If a profile is so restrictive that it produces zero trades over a long paper session, it is not generating enough evidence to evaluate.
- Exchange sequence counters can exceed ordinary 32-bit integer assumptions. If order-book snapshot storage uses a narrow integer type, the stream can fail only under live load and never in small local tests.
- Failure reporting paths need their own guardrails. If an exception string is too large for the persistence field that records it, the monitoring layer can crash while trying to report the original problem.
- Breakout exits need to be side-aware. A generic “price left the channel” exit can conflict with the same bar’s entry condition and turn a trend-following rule into self-canceling noise.
- A minimum breakout-strength floor is a better first response than adding AI when the live issue is shallow channel pokes that barely clear the threshold.
- If a live paper run keeps losing on weaker symbols, prune the universe before adding more strategies. Candidate ranking is more useful than first-come execution once the worker is evaluating multiple valid entries at the same time.
- Symbol-specific lockouts are sometimes the correct fix. BTC shorts were losing enough that the research profile now disables them while still allowing ETH shorts under a stricter trend filter.
- Breakout quality filters work best when they are layered: higher-timeframe trend, ATR, and volume confirmation reduce weak entries more reliably than a single tightened threshold.
- A paper-state reset is a destructive operation. It should be a separate explicit script or operator action, not an implicit side effect of dashboard startup or scheduler recovery.
- If you want a true fresh paper baseline, clear event logs too. Otherwise the balance may reset while the dashboard still shows stale operational history.
- Dashboard operational views should prefer the current allowlist over raw historical rows. Otherwise stale state from previous experiments makes the system look noisier and less healthy than it really is.

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
- tuned the slower 15-minute breakout preset to widen the universe slightly and loosen confirmation just enough to improve sample generation without reverting to fee-heavy demo churn
- fixed stream-status reporting so stale Bybit websocket rows degrade or disconnect based on heartbeat/message age instead of showing a misleading forever-connecting state
- widened the order-book sequence type and normalized stored stream errors after the live Bybit stream exposed schema assumptions that were too small for production traffic
- fixed the live paper-trading stop-loss path after a real runtime exception exposed that `DecisionSource.RISK` existed in the execution logic but not in the enum or Postgres type
- split breakout exits into side-specific `exit_long` and `exit_short` signals and added a minimum breakout-strength filter after the 15-minute paper run showed simultaneous entry/exit states and low-quality micro-breakouts

## What We Would Do Differently In V2

- Add authenticated exchange websocket order and fill streams, not only public market-data streams.
- Add richer portfolio accounting with time-series equity snapshots and per-symbol attribution history.
- Add broker-specific integration test suites with sandbox credentials.
- Add walk-forward evaluation and more robust time-series cross-validation for ML experiments.
- Add a real generated Stitch design-system and screen source-of-truth flow once the MCP generation path is reliable.
