from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import (
    DecisionSource,
    InstrumentType,
    MarginMode,
    OrderSide,
    PositionSide,
    TradeAction,
    TradingMode,
)


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    position_id: int | None
    strategy_name: str | None
    symbol: str
    instrument_type: InstrumentType
    margin_mode: MarginMode
    position_side: PositionSide
    source: DecisionSource
    side: OrderSide
    action: TradeAction
    mode: TradingMode
    leverage: float
    price: float
    quantity: float
    notional: float
    fee_paid: float
    funding_cost: float
    realized_pnl: float
    cash_flow: float
    trade_time: datetime
    notes: str | None
