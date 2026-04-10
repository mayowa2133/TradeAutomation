from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NewsArticleRead(BaseModel):
    id: int
    source: str
    title: str
    summary: str | None
    url: str
    symbols: list[str]
    sentiment_score: float | None
    published_at: datetime | None
    ingested_at: datetime
