from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    DecisionSource,
    InstrumentType,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    TradingMode,
)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_order_id: str
    exchange_order_id: str | None
    strategy_name: str | None
    symbol: str
    instrument_type: InstrumentType
    margin_mode: MarginMode
    position_side: PositionSide
    source: DecisionSource
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    mode: TradingMode
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    limit_price: float | None
    fill_price: float | None
    fee_paid: float
    slippage_bps: float
    leverage: float
    reduce_only: bool
    post_only: bool
    tick_size: float | None
    lot_size: float | None
    min_notional: float | None
    liquidation_price: float | None
    funding_cost: float
    exchange_name: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class OrderCancelResponse(BaseModel):
    order_id: int
    status: OrderStatus
    message: str


class ManualOrderRequest(BaseModel):
    symbol: str
    instrument_type: InstrumentType = InstrumentType.PERPETUAL
    position_side: PositionSide = PositionSide.LONG
    quantity: float = Field(gt=0)
    reference_price: float = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = Field(default=None, gt=0)
    leverage: float | None = Field(default=None, gt=0)
