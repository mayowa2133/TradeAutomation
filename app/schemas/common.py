from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    trading_mode: str
    live_trading_enabled: bool


class MessageResponse(BaseModel):
    message: str
