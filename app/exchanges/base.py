from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.enums import OrderSide, OrderStatus, OrderType


@dataclass(slots=True)
class ExecutionReport:
    client_order_id: str
    status: OrderStatus
    side: OrderSide
    order_type: OrderType
    filled_quantity: float
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
    def place_market_order(
        self, symbol: str, side: OrderSide, quantity: float, reference_price: float
    ) -> ExecutionReport:
        raise NotImplementedError

    @abstractmethod
    def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        limit_price: float,
        reference_price: float,
    ) -> ExecutionReport:
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
