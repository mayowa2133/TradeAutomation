from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import OrderSide, TradeAction, TradingMode


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    position_id: int | None
    strategy_name: str | None
    symbol: str
    side: OrderSide
    action: TradeAction
    mode: TradingMode
    price: float
    quantity: float
    notional: float
    fee_paid: float
    realized_pnl: float
    trade_time: datetime
    notes: str | None
