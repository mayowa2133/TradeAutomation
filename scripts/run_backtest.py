from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.services.backtest_service import BacktestService
from app.services.data_service import DataService
from app.services.strategy_registry import StrategyRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a backtest from the CLI.")
    parser.add_argument("--strategy", default="ema_crossover")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()

    settings = get_settings()
    init_db()
    with get_session_factory()() as db:
        registry = StrategyRegistry()
        data = DataService(db=db, settings=settings).get_historical_data(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=args.limit,
        )
        result = BacktestService(settings=settings, registry=registry, db=db).run_backtest(
            strategy_name=args.strategy,
            symbol=args.symbol,
            timeframe=args.timeframe,
            market_data=data,
            persist_run=True,
        )
        print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))


if __name__ == "__main__":
    main()
