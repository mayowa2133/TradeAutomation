from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import PositionSide, TradingMode


class LLMDecisionRequest(BaseModel):
    symbol: str
    timeframe: str = "5m"


class LLMDecisionRead(BaseModel):
    id: int
    provider: str
    model: str
    mode: TradingMode
    symbol: str | None
    position_side: PositionSide | None
    confidence: float = Field(ge=0.0, le=1.0)
    accepted: bool
    reason: str | None
    prompt: str
    context_payload: dict
    structured_output: dict
    created_at: datetime
