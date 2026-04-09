from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.ml.train import train_direction_model
from app.services.data_service import DataService


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the experimental direction filter model.")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--limit", type=int, default=600)
    parser.add_argument("--model-name", default="direction_filter")
    args = parser.parse_args()

    settings = get_settings()
    init_db()
    with get_session_factory()() as db:
        data = DataService(db=db, settings=settings).get_historical_data(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=args.limit,
        )
    metadata = train_direction_model(data, model_name=args.model_name)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
