from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str = "5m"
    limit: int = Field(default=300, ge=100, le=5000)
    fee_bps: float | None = None
    slippage_bps: float | None = None
    use_cached_data_only: bool = False
    persist_run: bool = True


class BacktestTrade(BaseModel):
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    fees: float
    exit_reason: str


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float


class BacktestResponse(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
    total_trades: int
    win_rate: float
    total_return_pct: float
    sharpe_like: float
    max_drawdown_pct: float
    fees_paid: float
    ending_balance: float
