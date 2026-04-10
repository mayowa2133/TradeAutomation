from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import InstrumentType, MarginMode


class InstrumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exchange: str
    symbol: str
    exchange_symbol: str
    instrument_type: InstrumentType
    margin_mode: MarginMode
    base_asset: str
    quote_asset: str
    settle_asset: str | None
    contract_size: float
    tick_size: float
    lot_size: float
    min_notional: float
    max_leverage: float
    maintenance_margin_rate: float
    active: bool
    raw: dict
    updated_at: datetime
