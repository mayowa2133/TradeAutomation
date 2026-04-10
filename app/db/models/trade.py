from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    DecisionSource,
    InstrumentType,
    MarginMode,
    OrderSide,
    PositionSide,
    TradeAction,
    TradingMode,
)
from app.db.session import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True, index=True)
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
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide))
    action: Mapped[TradeAction] = mapped_column(Enum(TradeAction))
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode), default=TradingMode.PAPER, index=True)
    leverage: Mapped[float] = mapped_column(Float, default=1.0)
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    notional: Mapped[float] = mapped_column(Float)
    fee_paid: Mapped[float] = mapped_column(Float, default=0.0)
    funding_cost: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    cash_flow: Mapped[float] = mapped_column(Float, default=0.0)
    trade_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    order = relationship("Order", back_populates="trades")
    position = relationship("Position", back_populates="trades")
