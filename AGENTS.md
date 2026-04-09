# AGENTS.md

This repository is intended to be continued by human engineers and coding agents. Read this file before editing anything.

## Where To Look First

1. `README.md` for runtime and safety context
2. `architecture.md` for system boundaries and data flow
3. `app/core/config.py` for safety defaults and mode gating
4. `app/services/execution_service.py` and `app/services/risk_service.py` before touching trading behavior
5. `tests/` before changing any execution, sizing, or API contract

## Repo Priorities

- Preserve paper trading as the default mode.
- Keep live trading fail-closed.
- Favor deterministic guardrails over heuristic shortcuts.
- Keep the code modular enough for additional brokers and asset classes.
- Do not claim profitability or introduce unverifiable performance language.

## Coding Standards

- Python 3.11 only.
- Strong typing on public functions and service interfaces.
- Prefer small service classes over central god objects.
- Keep strategy code side-effect free. Strategies generate signals; services decide execution.
- Add tests for any risk rule, API contract, or persistence logic you change.
- Use JSON-serializable structures for persisted metadata and event payloads.

## System Boundaries

- `app/strategies`: signal generation only, no direct order placement
- `app/services/risk_service.py`: final gate before entry orders
- `app/exchanges`: broker/exchange adapters only
- `app/services/execution_service.py`: orchestrates strategy, risk, persistence, broker interaction
- `app/services/llm_service.py`: optional explanation/summarization hooks only, never direct execution authority

## Safety Constraints

- `TRADING_MODE=paper` is the expected default.
- `ENABLE_LIVE_TRADING` must remain `false` by default.
- Never introduce a code path that can place live orders when the explicit flag is off.
- If live mode is requested but any required credential is missing, fail closed with a configuration error.
- Do not bypass the risk engine for entry orders.
- Do not let LLM-integrated code trigger or approve execution directly.
- The kill switch must block new entries even if schedulers or APIs continue running.

## How To Make Changes Safely

1. Start with the existing tests.
2. Inspect affected services and the schemas they return.
3. Keep DB schema changes explicit through Alembic.
4. Update `README.md`, `HANDOFF.md`, or `lessons.md` if operational behavior changes.
5. Run at least the relevant tests plus FastAPI startup after significant edits.

## Live Trading Rules

- Treat live trading as opt-in, not configurable drift.
- Keep live execution narrow and observable.
- Log a startup warning whenever live trading is enabled.
- Never default to a live exchange adapter.
- Any new broker adapter must implement the same hard safety checks as the current CCXT adapter.

## Extension Points

- New exchange/broker adapters belong under `app/exchanges/`.
- New asset classes should extend the adapter and market data interfaces instead of modifying strategies directly.
- Optional LLM providers should implement the interfaces in `app/services/llm_service.py`.
- New strategies should register through `app/services/strategy_registry.py` and add tests.
