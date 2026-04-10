from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import InstrumentType, MarginMode
from app.db.session import Base


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("exchange", "symbol", "instrument_type", name="uq_instruments_exchange_symbol_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange_symbol: Mapped[str] = mapped_column(String(64), index=True)
    instrument_type: Mapped[InstrumentType] = mapped_column(Enum(InstrumentType), index=True)
    margin_mode: Mapped[MarginMode] = mapped_column(Enum(MarginMode), default=MarginMode.CASH)
    base_asset: Mapped[str] = mapped_column(String(16))
    quote_asset: Mapped[str] = mapped_column(String(16))
    settle_asset: Mapped[str | None] = mapped_column(String(16), nullable=True)
    contract_size: Mapped[float] = mapped_column(Float, default=1.0)
    tick_size: Mapped[float] = mapped_column(Float, default=0.0)
    lot_size: Mapped[float] = mapped_column(Float, default=0.0)
    min_notional: Mapped[float] = mapped_column(Float, default=0.0)
    max_leverage: Mapped[float] = mapped_column(Float, default=1.0)
    maintenance_margin_rate: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
