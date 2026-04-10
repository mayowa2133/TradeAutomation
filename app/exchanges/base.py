from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.enums import (
    DecisionSource,
    InstrumentType,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
)


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    exchange_symbol: str
    instrument_type: InstrumentType
    margin_mode: MarginMode
    position_side: PositionSide
    side: OrderSide
    order_type: OrderType
    quantity: float
    reference_price: float
    limit_price: float | None = None
    leverage: float = 1.0
    reduce_only: bool = False
    post_only: bool = False
    decision_source: DecisionSource = DecisionSource.STRATEGY
    tick_size: float | None = None
    lot_size: float | None = None
    min_notional: float | None = None
    depth_snapshot: dict[str, list[list[float]]] | None = None
    execution_model: str = "candle"
    allow_candle_fallback: bool = True


@dataclass(slots=True)
class ExecutionReport:
    client_order_id: str
    status: OrderStatus
    side: OrderSide
    order_type: OrderType
    requested_quantity: float
    filled_quantity: float
    remaining_quantity: float
    fill_price: float | None
    fee_paid: float
    slippage_bps: float
    exchange_order_id: str | None = None
    notes: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExchangeAdapter(ABC):
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, request: OrderRequest) -> ExecutionReport:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch_balance(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_open_orders(self) -> list[dict[str, Any]]:
        raise NotImplementedError
