from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.core.enums import InstrumentType, MarginMode, OrderSide, OrderStatus, OrderType
from app.exchanges.base import ExchangeAdapter, ExecutionReport, OrderRequest
from app.utils.fees import apply_slippage, calculate_fee
from app.utils.orderbook import simulate_limit_fill, simulate_market_fill


class PaperExchange(ExchangeAdapter):
    def __init__(self, fee_bps: float, slippage_bps: float) -> None:
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self._open_orders: dict[str, dict[str, Any]] = {}

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[list[float]]:
        raise NotImplementedError("Paper exchange does not fetch market data directly.")

    def _build_report(
        self,
        request: OrderRequest,
        *,
        status: OrderStatus,
        filled_quantity: float,
        remaining_quantity: float,
        fill_price: float | None,
        fee_paid: float,
        slippage_bps: float,
        notes: str,
    ) -> ExecutionReport:
        client_order_id = str(uuid4())
        return ExecutionReport(
            client_order_id=client_order_id,
            status=status,
            side=request.side,
            order_type=request.order_type,
            requested_quantity=request.quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            fill_price=fill_price,
            fee_paid=fee_paid,
            slippage_bps=slippage_bps,
            notes=notes,
        )

    def place_order(self, request: OrderRequest) -> ExecutionReport:
        if request.execution_model == "depth" and request.depth_snapshot is None and not request.allow_candle_fallback:
            return self._build_report(
                request,
                status=OrderStatus.REJECTED,
                filled_quantity=0.0,
                remaining_quantity=request.quantity,
                fill_price=None,
                fee_paid=0.0,
                slippage_bps=0.0,
                notes="Depth execution requested without an order-book snapshot.",
            )

        if request.depth_snapshot:
            bids = request.depth_snapshot.get("bids", [])
            asks = request.depth_snapshot.get("asks", [])
            if request.order_type == OrderType.MARKET:
                fill = simulate_market_fill(request.side, request.quantity, bids, asks)
            else:
                fill = simulate_limit_fill(
                    request.side,
                    request.quantity,
                    request.limit_price or request.reference_price,
                    bids,
                    asks,
                )
            if fill.status in {OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED}:
                fee_paid = calculate_fee(fill.notional, self.fee_bps)
                report = self._build_report(
                    request,
                    status=fill.status,
                    filled_quantity=fill.filled_quantity,
                    remaining_quantity=fill.remaining_quantity,
                    fill_price=fill.average_price,
                    fee_paid=fee_paid,
                    slippage_bps=0.0,
                    notes=f"Paper {request.instrument_type.value} order filled from depth.",
                )
                if fill.remaining_quantity > 0 and request.order_type == OrderType.LIMIT:
                    self._open_orders[report.client_order_id] = {
                        "symbol": request.symbol,
                        "side": request.side.value,
                        "quantity": fill.remaining_quantity,
                        "limit_price": request.limit_price,
                        "status": OrderStatus.NEW.value,
                    }
                return report
            if request.order_type == OrderType.LIMIT:
                report = self._build_report(
                    request,
                    status=OrderStatus.NEW,
                    filled_quantity=0.0,
                    remaining_quantity=request.quantity,
                    fill_price=None,
                    fee_paid=0.0,
                    slippage_bps=0.0,
                    notes=f"Paper-submitted resting {request.symbol} limit order.",
                )
                self._open_orders[report.client_order_id] = {
                    "symbol": request.symbol,
                    "side": request.side.value,
                    "quantity": request.quantity,
                    "limit_price": request.limit_price,
                    "status": OrderStatus.NEW.value,
                }
                return report

        fill_price = apply_slippage(
            request.limit_price if request.order_type == OrderType.LIMIT and request.limit_price else request.reference_price,
            side=request.side,
            slippage_bps=self.slippage_bps if request.order_type == OrderType.MARKET else 0.0,
        )
        notional = fill_price * request.quantity if fill_price is not None else 0.0
        fee_paid = calculate_fee(notional, self.fee_bps) if fill_price is not None else 0.0
        if request.order_type == OrderType.LIMIT and request.limit_price is not None:
            crosses_market = (request.side == OrderSide.BUY and request.limit_price >= request.reference_price) or (
                request.side == OrderSide.SELL and request.limit_price <= request.reference_price
            )
            if not crosses_market:
                report = self._build_report(
                    request,
                    status=OrderStatus.NEW,
                    filled_quantity=0.0,
                    remaining_quantity=request.quantity,
                    fill_price=None,
                    fee_paid=0.0,
                    slippage_bps=0.0,
                    notes=f"Paper-submitted resting {request.symbol} limit order.",
                )
                self._open_orders[report.client_order_id] = {
                    "symbol": request.symbol,
                    "side": request.side.value,
                    "quantity": request.quantity,
                    "limit_price": request.limit_price,
                    "status": OrderStatus.NEW.value,
                }
                return report

        return self._build_report(
            request,
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            remaining_quantity=0.0,
            fill_price=fill_price,
            fee_paid=fee_paid,
            slippage_bps=self.slippage_bps if request.order_type == OrderType.MARKET else 0.0,
            notes=f"Paper-filled {request.instrument_type.value} {request.order_type.value} order.",
        )

    def cancel_order(self, client_order_id: str) -> bool:
        return self._open_orders.pop(client_order_id, None) is not None

    def fetch_balance(self) -> dict[str, Any]:
        return {"status": "simulated"}

    def fetch_open_orders(self) -> list[dict[str, Any]]:
        return [{"client_order_id": key, **value} for key, value in self._open_orders.items()]
