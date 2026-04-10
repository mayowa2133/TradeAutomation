from __future__ import annotations

from typing import Any

import ccxt

from app.core.config import Settings
from app.core.enums import OrderStatus
from app.core.exceptions import ConfigurationError, ExchangeAdapterError
from app.exchanges.base import ExchangeAdapter, ExecutionReport, OrderRequest
from app.utils.fees import calculate_fee


class BybitPerpExchange(ExchangeAdapter):
    def __init__(self, settings: Settings, allow_private: bool = False) -> None:
        self.settings = settings
        self.allow_private = allow_private
        config: dict[str, Any] = {"enableRateLimit": True, "options": {"defaultType": "swap"}}
        if allow_private:
            settings.require_live_derivatives_ready()
            config.update(
                {
                    "apiKey": settings.derivatives_api_key,
                    "secret": settings.derivatives_api_secret,
                }
            )
        self.client = ccxt.bybit(config)

    def _require_private(self) -> None:
        if not self.allow_private:
            raise ExchangeAdapterError("Private Bybit operations are disabled in the current mode.")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[list[float]]:
        return self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit, params={"category": "linear"})

    def place_order(self, request: OrderRequest) -> ExecutionReport:
        self._require_private()
        params: dict[str, Any] = {"category": "linear", "reduceOnly": request.reduce_only}
        if request.post_only:
            params["timeInForce"] = "PostOnly"
        order = self.client.create_order(
            request.exchange_symbol,
            request.order_type.value,
            request.side.value,
            request.quantity,
            request.limit_price if request.order_type.value == "limit" else None,
            params=params,
        )
        filled_qty = float(order.get("filled") or 0.0)
        remaining = max(request.quantity - filled_qty, 0.0)
        fill_price = float(order.get("average") or order.get("price") or request.reference_price)
        fee_paid = calculate_fee(fill_price * filled_qty, self.settings.default_fee_bps)
        if filled_qty > 0 and remaining > 0:
            status = OrderStatus.PARTIALLY_FILLED
        elif str(order.get("status") or "").lower() in {"closed", "filled"} or remaining == 0:
            status = OrderStatus.FILLED
        else:
            status = OrderStatus.NEW
        return ExecutionReport(
            client_order_id=str(order.get("clientOrderId") or order.get("id")),
            exchange_order_id=str(order.get("id")),
            status=status,
            side=request.side,
            order_type=request.order_type,
            requested_quantity=request.quantity,
            filled_quantity=filled_qty,
            remaining_quantity=remaining,
            fill_price=fill_price if filled_qty else None,
            fee_paid=fee_paid,
            slippage_bps=0.0,
            notes=f"Live Bybit perpetual {request.order_type.value} order.",
        )

    def cancel_order(self, client_order_id: str) -> bool:
        self._require_private()
        self.client.cancel_order(client_order_id, params={"category": "linear"})
        return True

    def fetch_balance(self) -> dict[str, Any]:
        self._require_private()
        return self.client.fetch_balance(params={"type": "swap"})

    def fetch_open_orders(self) -> list[dict[str, Any]]:
        self._require_private()
        return self.client.fetch_open_orders(params={"category": "linear"})
