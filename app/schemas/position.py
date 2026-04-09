from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import PositionSide, PositionStatus, TradingMode


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_name: str
    symbol: str
    side: PositionSide
    mode: TradingMode
    status: PositionStatus
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    stop_loss_price: float | None
    take_profit_price: float | None
    exit_reason: str | None
    opened_at: datetime
    closed_at: datetime | None
    updated_at: datetime


class PnLSummary(BaseModel):
    currency: str
    starting_balance: float
    cash_balance: float
    realized_pnl: float
    unrealized_pnl: float
    equity: float
    peak_equity: float
    drawdown_pct: float
