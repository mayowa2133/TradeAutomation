from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OptimizerRunRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    timeframe: str = "5m"
    signal_strengths: dict[str, float] | None = None


class OptimizerRunRead(BaseModel):
    id: int
    name: str
    status: str
    inputs: dict
    allocations: dict
    metrics: dict
    created_at: datetime
