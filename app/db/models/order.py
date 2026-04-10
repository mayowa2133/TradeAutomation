from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    DecisionSource,
    InstrumentType,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    TradingMode,
)
from app.db.session import Base

if TYPE_CHECKING:
    from app.db.models.trade import Trade


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: str(uuid4()))
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    strategy_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    instrument_type: Mapped[InstrumentType] = mapped_column(
        Enum(InstrumentType), default=InstrumentType.SPOT, index=True
    )
    margin_mode: Mapped[MarginMode] = mapped_column(Enum(MarginMode), default=MarginMode.CASH)
    position_side: Mapped[PositionSide] = mapped_column(Enum(PositionSide), default=PositionSide.LONG)
    source: Mapped[DecisionSource] = mapped_column(
        Enum(DecisionSource), default=DecisionSource.STRATEGY, index=True
    )
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide), index=True)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType))
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.NEW, index=True)
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode), default=TradingMode.PAPER)
    quantity: Mapped[float] = mapped_column(Float)
    filled_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    remaining_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_paid: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=0.0)
    leverage: Mapped[float] = mapped_column(Float, default=1.0)
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    post_only: Mapped[bool] = mapped_column(Boolean, default=False)
    tick_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    lot_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_notional: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidation_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    funding_cost: Mapped[float] = mapped_column(Float, default=0.0)
    exchange_name: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    trades: Mapped[list["Trade"]] = relationship("Trade", back_populates="order")
