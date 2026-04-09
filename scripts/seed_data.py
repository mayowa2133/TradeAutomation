from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.services.data_service import DataService


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and persist historical OHLCV data.")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()

    settings = get_settings()
    init_db()
    with get_session_factory()() as db:
        frame = DataService(db=db, settings=settings).get_historical_data(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=args.limit,
        )
        print(f"Stored {len(frame)} rows for {args.symbol} {args.timeframe}.")


if __name__ == "__main__":
    main()
