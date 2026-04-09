from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import OrderSide, OrderStatus, OrderType, TradingMode


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_order_id: str
    exchange_order_id: str | None
    strategy_name: str | None
    symbol: str
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    mode: TradingMode
    quantity: float
    limit_price: float | None
    fill_price: float | None
    fee_paid: float
    slippage_bps: float
    exchange_name: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class OrderCancelResponse(BaseModel):
    order_id: int
    status: OrderStatus
    message: str
