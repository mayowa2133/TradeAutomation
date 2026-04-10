from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.core.enums import InstrumentType


class QuoteSnapshotRead(BaseModel):
    exchange: str
    symbol: str
    instrument_type: InstrumentType
    best_bid: float
    best_ask: float
    bid_size: float
    ask_size: float
    last_price: float | None
    mark_price: float | None
    index_price: float | None
    funding_rate: float | None
    spread_bps: float
    snapshot_time: datetime


class OrderBookSnapshotRead(BaseModel):
    exchange: str
    symbol: str
    instrument_type: InstrumentType
    sequence: int | None
    depth: int
    bids: list[list[float]]
    asks: list[list[float]]
    mid_price: float | None
    snapshot_time: datetime


class StreamStatusRead(BaseModel):
    stream_name: str
    symbol: str
    status: str
    stream_metadata: dict[str, Any]
    last_message_at: datetime | None
    last_heartbeat_at: datetime | None
    error_message: str | None
    updated_at: datetime
