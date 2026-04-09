from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import TradingMode


class StrategyDescriptor(BaseModel):
    name: str
    description: str
    experimental: bool = False
    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class StrategyToggleRequest(BaseModel):
    enabled: bool


class StrategyToggleResponse(BaseModel):
    name: str
    enabled: bool
    updated_at: datetime


class ConfigResponse(BaseModel):
    settings: dict[str, Any]
    trading_mode: TradingMode
    live_trading_enabled: bool


class PaperTradingStatus(BaseModel):
    mode: TradingMode
    live_trading_enabled: bool
    scheduler_enabled: bool
    cash_balance: float
    equity: float
    open_positions: int


class RiskStateResponse(BaseModel):
    kill_switch: bool
    live_trading_enabled: bool
    open_positions: int
    max_concurrent_positions: int
    daily_realized_pnl: float
    daily_loss_limit: float
    drawdown_pct: float
    drawdown_limit_pct: float
    blocked_symbols: list[str]


class EventLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    event_type: str
    message: str
    payload: dict[str, Any]
    created_at: datetime
