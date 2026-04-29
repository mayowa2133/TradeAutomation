from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DashboardEventRead(BaseModel):
    event_type: str
    message: str
    created_at: datetime


class DashboardSummaryRead(BaseModel):
    portfolio: dict[str, Any]
    risk: dict[str, Any]
    strategies: list[dict[str, Any]]
    worker_status: dict[str, Any]
    position_attribution: list[dict[str, Any]]
    stream_status: list[dict[str, Any]]
    optimizer: dict[str, Any] | None
    news: list[dict[str, Any]]
    llm_decisions: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]
