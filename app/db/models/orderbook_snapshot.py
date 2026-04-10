from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import InstrumentType
from app.db.session import Base


class OrderBookSnapshot(Base):
    __tablename__ = "orderbook_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    instrument_type: Mapped[InstrumentType] = mapped_column(
        Enum(InstrumentType), default=InstrumentType.SPOT, index=True
    )
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depth: Mapped[int] = mapped_column(Integer, default=50)
    bids: Mapped[list] = mapped_column(JSON, default=list)
    asks: Mapped[list] = mapped_column(JSON, default=list)
    mid_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
