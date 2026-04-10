from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import InstrumentType, MarginMode, PositionSide


class BacktestRequest(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str = "5m"
    limit: int = Field(default=300, ge=100, le=5000)
    instrument_type: InstrumentType = InstrumentType.SPOT
    margin_mode: MarginMode = MarginMode.CASH
    leverage: float = Field(default=1.0, ge=1.0, le=25.0)
    fee_bps: float | None = None
    slippage_bps: float | None = None
    execution_model: str = "candle"
    allow_candle_fallback: bool = True
    use_cached_data_only: bool = False
    persist_run: bool = True


class BacktestTrade(BaseModel):
    entry_time: datetime
    exit_time: datetime
    instrument_type: InstrumentType
    position_side: PositionSide
    leverage: float
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    fees: float
    funding_paid: float
    exit_reason: str


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float


class BacktestResponse(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str
    instrument_type: InstrumentType
    margin_mode: MarginMode
    execution_model: str
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
    total_trades: int
    win_rate: float
    total_return_pct: float
    sharpe_like: float
    max_drawdown_pct: float
    fees_paid: float
    funding_paid: float
    liquidation_count: int
    ending_balance: float
    ending_equity: float
