from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import InstrumentType, OrderSide
from app.db.session import Base


class MarketTick(Base):
    __tablename__ = "market_ticks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    instrument_type: Mapped[InstrumentType] = mapped_column(
        Enum(InstrumentType), default=InstrumentType.SPOT, index=True
    )
    trade_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide))
    price: Mapped[float] = mapped_column(Float)
    size: Mapped[float] = mapped_column(Float)
    tick_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
