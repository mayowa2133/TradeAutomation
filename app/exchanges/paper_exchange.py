from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.core.enums import OrderSide, OrderStatus, OrderType
from app.exchanges.base import ExchangeAdapter, ExecutionReport
from app.utils.fees import apply_slippage, calculate_fee


class PaperExchange(ExchangeAdapter):
    def __init__(self, fee_bps: float, slippage_bps: float) -> None:
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self._open_orders: dict[str, dict[str, Any]] = {}

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[list[float]]:
        raise NotImplementedError("Paper exchange does not fetch market data directly.")

    def place_market_order(
        self, symbol: str, side: OrderSide, quantity: float, reference_price: float
    ) -> ExecutionReport:
        client_order_id = str(uuid4())
        fill_price = apply_slippage(reference_price, side=side, slippage_bps=self.slippage_bps)
        notional = fill_price * quantity
        fee_paid = calculate_fee(notional, self.fee_bps)
        return ExecutionReport(
            client_order_id=client_order_id,
            status=OrderStatus.FILLED,
            side=side,
            order_type=OrderType.MARKET,
            filled_quantity=quantity,
            fill_price=fill_price,
            fee_paid=fee_paid,
            slippage_bps=self.slippage_bps,
            notes=f"Paper-filled {symbol} market order.",
        )

    def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        limit_price: float,
        reference_price: float,
    ) -> ExecutionReport:
        client_order_id = str(uuid4())
        crosses_market = (side == OrderSide.BUY and limit_price >= reference_price) or (
            side == OrderSide.SELL and limit_price <= reference_price
        )
        if crosses_market:
            notional = limit_price * quantity
            fee_paid = calculate_fee(notional, self.fee_bps)
            return ExecutionReport(
                client_order_id=client_order_id,
                status=OrderStatus.FILLED,
                side=side,
                order_type=OrderType.LIMIT,
                filled_quantity=quantity,
                fill_price=limit_price,
                fee_paid=fee_paid,
                slippage_bps=0.0,
                notes=f"Paper-filled {symbol} limit order immediately.",
            )
        self._open_orders[client_order_id] = {
            "symbol": symbol,
            "side": side.value,
            "quantity": quantity,
            "limit_price": limit_price,
            "status": OrderStatus.NEW.value,
        }
        return ExecutionReport(
            client_order_id=client_order_id,
            status=OrderStatus.NEW,
            side=side,
            order_type=OrderType.LIMIT,
            filled_quantity=0.0,
            fill_price=None,
            fee_paid=0.0,
            slippage_bps=0.0,
            notes=f"Paper-submitted resting {symbol} limit order.",
        )

    def cancel_order(self, client_order_id: str) -> bool:
        return self._open_orders.pop(client_order_id, None) is not None

    def fetch_balance(self) -> dict[str, Any]:
        return {"status": "simulated"}

    def fetch_open_orders(self) -> list[dict[str, Any]]:
        return [{"client_order_id": key, **value} for key, value in self._open_orders.items()]
