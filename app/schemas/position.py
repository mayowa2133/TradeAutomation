from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import InstrumentType, MarginMode, PositionSide, PositionStatus, TradingMode


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_name: str
    symbol: str
    instrument_type: InstrumentType
    margin_mode: MarginMode
    side: PositionSide
    mode: TradingMode
    status: PositionStatus
    quantity: float
    leverage: float
    avg_entry_price: float
    current_price: float
    entry_notional: float
    collateral: float
    unrealized_pnl: float
    realized_pnl: float
    stop_loss_price: float | None
    take_profit_price: float | None
    liquidation_price: float | None
    maintenance_margin_rate: float
    funding_cost: float
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
    margin_used: float
    gross_exposure: float
    net_exposure: float
