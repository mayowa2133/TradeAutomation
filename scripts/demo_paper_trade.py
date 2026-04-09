from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.services.execution_service import ExecutionService
from app.services.strategy_registry import StrategyRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one strategy evaluation pass in paper mode.")
    parser.add_argument("--strategy", default="ema_crossover")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()

    settings = get_settings()
    init_db()
    with get_session_factory()() as db:
        registry = StrategyRegistry()
        result = ExecutionService(db=db, settings=settings, registry=registry).evaluate_strategy(
            strategy_name=args.strategy,
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=args.limit,
        )
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
