# CLAUDE.md

Claude or any other agent should reason about this repository as a safety-critical trading system with a research layer attached, not as a generic CRUD app.

## Inspect Before Editing

1. `app/core/config.py`
2. `app/core/enums.py`
3. `app/services/risk_service.py`
4. `app/services/execution_service.py`
5. `app/services/backtest_service.py`
6. `app/services/strategy_registry.py`
7. The relevant tests under `tests/`

## Invariants

- Paper mode remains the default.
- Live trading must require both `TRADING_MODE=live` and `ENABLE_LIVE_TRADING=true`.
- Missing exchange credentials in live mode are fatal.
- Strategies do not execute trades directly.
- LLM hooks remain optional and non-authoritative.
- Risk blocks must be explicit, logged, and observable through the API.
- Backtests and paper trading must both account for fees and slippage.

## Avoid Hallucinating

- Do not invent profitability.
- Do not assume exchange order semantics beyond what the adapter implements.
- Do not pretend that the ML model is robust or production-alpha. It is experimental.
- Do not document endpoints or env vars that are not present in code.

## Editing Guidance

- Check schema, service, and route alignment together.
- If you change a DB model, inspect Alembic migration coverage.
- If you change strategy params, check both tests and default config seeding.
- If you touch execution or risk logic, re-run the paper exchange, risk, and backtest tests.

## Expected Validation Before Finishing

- `uv run pytest`
- `uv run python -c "from app.main import app; print(app.title)"`
- Relevant scripts if runtime behavior changed

## Live Trading Caution

Assume any accidental live-order path is a severe bug. If an intended change even mildly weakens the live safety gates, stop and redesign it.
