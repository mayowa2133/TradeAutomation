from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DecisionSource, PositionSide, TradingMode
from app.db.session import Base


class LLMDecision(Base):
    __tablename__ = "llm_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(128))
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode), default=TradingMode.PAPER, index=True)
    decision_source: Mapped[DecisionSource] = mapped_column(
        Enum(DecisionSource), default=DecisionSource.LLM, index=True
    )
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    position_side: Mapped[PositionSide | None] = mapped_column(Enum(PositionSide), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    context_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    structured_output: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
