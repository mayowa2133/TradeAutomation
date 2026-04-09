from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO
from typing import Any

import pandas as pd
import redis
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models.market_data import MarketData
from app.exchanges.ccxt_exchange import CCXTExchange
from app.utils.timeframes import validate_timeframe

logger = get_logger(__name__)


class DataService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self._redis_client: redis.Redis[str] | None = None

    def _redis(self) -> redis.Redis[str] | None:
        if self._redis_client is not None:
            return self._redis_client
        try:
            client = redis.from_url(self.settings.redis_url, decode_responses=True)
            client.ping()
            self._redis_client = client
        except Exception:
            self._redis_client = None
        return self._redis_client

    def _cache_key(self, symbol: str, timeframe: str, limit: int) -> str:
        return f"ohlcv:{self.settings.exchange_name}:{symbol}:{timeframe}:{limit}"

    def _rows_to_frame(self, rows: list[MarketData]) -> pd.DataFrame:
        records = [
            {
                "timestamp": row.timestamp,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
            for row in rows
        ]
        if not records:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        frame = pd.DataFrame.from_records(records)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.sort_values("timestamp").set_index("timestamp")
        return frame

    def load_from_db(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        rows = (
            self.db.query(MarketData)
            .filter(
                MarketData.exchange == self.settings.exchange_name,
                MarketData.symbol == symbol,
                MarketData.timeframe == timeframe,
            )
            .order_by(MarketData.timestamp.desc())
            .limit(limit)
            .all()
        )
        rows = list(reversed(rows))
        return self._rows_to_frame(rows)

    def persist_ohlcv(self, symbol: str, timeframe: str, frame: pd.DataFrame) -> None:
        timestamps = [ts.to_pydatetime() for ts in frame.index.to_list()]
        existing_rows = (
            self.db.query(MarketData.timestamp)
            .filter(
                MarketData.exchange == self.settings.exchange_name,
                MarketData.symbol == symbol,
                MarketData.timeframe == timeframe,
                MarketData.timestamp.in_(timestamps),
            )
            .all()
        )
        existing = {row[0] for row in existing_rows}
        for timestamp, row in frame.iterrows():
            timestamp_dt = timestamp.to_pydatetime()
            if timestamp_dt in existing:
                continue
            self.db.add(
                MarketData(
                    exchange=self.settings.exchange_name,
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp_dt,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        self.db.commit()

    def fetch_from_exchange(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        exchange = CCXTExchange(settings=self.settings, allow_private=False)
        candles = exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
        frame = pd.DataFrame(
            candles,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        frame = frame.set_index("timestamp")
        self.persist_ohlcv(symbol=symbol, timeframe=timeframe, frame=frame)
        cache = self._redis()
        if cache is not None:
            payload = frame.reset_index().to_json(date_format="iso", orient="records")
            cache.setex(self._cache_key(symbol, timeframe, limit), 30, payload)
        return frame

    def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        use_cached_only: bool = False,
    ) -> pd.DataFrame:
        validate_timeframe(timeframe)
        cache = self._redis()
        if cache is not None and not use_cached_only:
            cached = cache.get(self._cache_key(symbol, timeframe, limit))
            if cached:
                records = json.load(StringIO(cached))
                frame = pd.DataFrame.from_records(records)
                frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
                return frame.set_index("timestamp")

        frame = self.load_from_db(symbol=symbol, timeframe=timeframe, limit=limit)
        if len(frame) >= limit or use_cached_only:
            return frame.tail(limit)
        fetched = self.fetch_from_exchange(symbol=symbol, timeframe=timeframe, limit=limit)
        logger.info(
            "Fetched market data",
            extra={"event_type": "market_data_fetch", "symbol": symbol},
        )
        return fetched.tail(limit)

    def store_synthetic_data(
        self,
        symbol: str,
        timeframe: str,
        frame: pd.DataFrame,
        exchange_name: str | None = None,
    ) -> None:
        original_exchange = self.settings.exchange_name
        if exchange_name:
            self.settings.exchange_name = exchange_name
        try:
            self.persist_ohlcv(symbol=symbol, timeframe=timeframe, frame=frame)
        finally:
            self.settings.exchange_name = original_exchange
