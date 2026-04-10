from __future__ import annotations

import json
from io import StringIO

import pandas as pd
import redis
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import InstrumentType
from app.core.logging import get_logger
from app.db.models.market_data import MarketData
from app.exchanges.bybit_perp_exchange import BybitPerpExchange
from app.exchanges.ccxt_exchange import CCXTExchange
from app.services.instrument_service import InstrumentService
from app.utils.timeframes import validate_timeframe

logger = get_logger(__name__)


class DataService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.instrument_service = InstrumentService(db=db, settings=settings)
        self._redis_client: redis.Redis[str] | None = None

    def _exchange_name(self, instrument_type: InstrumentType) -> str:
        return (
            self.settings.derivatives_exchange_name
            if instrument_type == InstrumentType.PERPETUAL
            else self.settings.exchange_name
        )

    def _public_exchange(self, instrument_type: InstrumentType):
        if instrument_type == InstrumentType.PERPETUAL:
            return BybitPerpExchange(settings=self.settings, allow_private=False)
        return CCXTExchange(settings=self.settings, allow_private=False)

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

    def _cache_key(self, symbol: str, timeframe: str, limit: int, instrument_type: InstrumentType) -> str:
        return f"ohlcv:{self._exchange_name(instrument_type)}:{instrument_type.value}:{symbol}:{timeframe}:{limit}"

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
        return frame.sort_values("timestamp").set_index("timestamp")

    def load_from_db(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        instrument_type: InstrumentType,
    ) -> pd.DataFrame:
        rows = (
            self.db.query(MarketData)
            .filter(
                MarketData.exchange == self._exchange_name(instrument_type),
                MarketData.symbol == symbol,
                MarketData.timeframe == timeframe,
                MarketData.instrument_type == instrument_type,
            )
            .order_by(MarketData.timestamp.desc())
            .limit(limit)
            .all()
        )
        return self._rows_to_frame(list(reversed(rows)))

    def persist_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        frame: pd.DataFrame,
        instrument_type: InstrumentType,
    ) -> None:
        timestamps = [ts.to_pydatetime() for ts in frame.index.to_list()]
        existing_rows = (
            self.db.query(MarketData.timestamp)
            .filter(
                MarketData.exchange == self._exchange_name(instrument_type),
                MarketData.symbol == symbol,
                MarketData.timeframe == timeframe,
                MarketData.instrument_type == instrument_type,
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
                    exchange=self._exchange_name(instrument_type),
                    symbol=symbol,
                    timeframe=timeframe,
                    instrument_type=instrument_type,
                    timestamp=timestamp_dt,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        self.db.commit()

    def fetch_from_exchange(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        instrument_type: InstrumentType,
    ) -> pd.DataFrame:
        instrument = self.instrument_service.ensure_instrument(symbol, instrument_type)
        exchange = self._public_exchange(instrument_type)
        candles = exchange.fetch_ohlcv(instrument.exchange_symbol, timeframe=timeframe, limit=limit)
        frame = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        frame = frame.set_index("timestamp")
        self.persist_ohlcv(symbol=symbol, timeframe=timeframe, frame=frame, instrument_type=instrument_type)
        cache = self._redis()
        if cache is not None:
            cache.setex(
                self._cache_key(symbol, timeframe, limit, instrument_type),
                30,
                frame.reset_index().to_json(date_format="iso", orient="records"),
            )
        logger.info(
            "Fetched market data",
            extra={"event_type": "market_data_fetch", "symbol": symbol},
        )
        return frame

    def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        use_cached_only: bool = False,
        refresh: bool = False,
    ) -> pd.DataFrame:
        validate_timeframe(timeframe)
        cache = self._redis()
        if cache is not None and not use_cached_only and not refresh:
            cached = cache.get(self._cache_key(symbol, timeframe, limit, instrument_type))
            if cached:
                records = json.load(StringIO(cached))
                frame = pd.DataFrame.from_records(records)
                frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
                return frame.set_index("timestamp")

        if refresh and not use_cached_only:
            return self.fetch_from_exchange(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                instrument_type=instrument_type,
            ).tail(limit)

        frame = self.load_from_db(symbol=symbol, timeframe=timeframe, limit=limit, instrument_type=instrument_type)
        if len(frame) >= limit or use_cached_only:
            return frame.tail(limit)
        return self.fetch_from_exchange(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            instrument_type=instrument_type,
        ).tail(limit)

    def store_synthetic_data(
        self,
        symbol: str,
        timeframe: str,
        frame: pd.DataFrame,
        instrument_type: InstrumentType = InstrumentType.SPOT,
    ) -> None:
        self.persist_ohlcv(symbol=symbol, timeframe=timeframe, frame=frame, instrument_type=instrument_type)
