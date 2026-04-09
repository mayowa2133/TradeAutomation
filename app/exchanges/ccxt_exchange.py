from __future__ import annotations

from typing import Any

import ccxt

from app.core.config import Settings
from app.core.enums import OrderSide, OrderStatus, OrderType
from app.core.exceptions import ConfigurationError, ExchangeAdapterError
from app.exchanges.base import ExchangeAdapter, ExecutionReport
from app.utils.fees import calculate_fee


class CCXTExchange(ExchangeAdapter):
    def __init__(self, settings: Settings, allow_private: bool = False) -> None:
        self.settings = settings
        self.allow_private = allow_private
        exchange_cls = getattr(ccxt, settings.exchange_name, None)
        if exchange_cls is None:
            raise ConfigurationError(f"Unsupported CCXT exchange: {settings.exchange_name}")
        config: dict[str, Any] = {"enableRateLimit": True}
        if allow_private:
            settings.require_live_trading_ready()
            config.update(
                {
                    "apiKey": settings.exchange_api_key,
                    "secret": settings.exchange_api_secret,
                }
            )
            if settings.exchange_api_password:
                config["password"] = settings.exchange_api_password
        self.client = exchange_cls(config)

    def _require_private(self) -> None:
        if not self.allow_private:
            raise ExchangeAdapterError("Private CCXT operations are disabled in the current mode.")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[list[float]]:
        return self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def place_market_order(
        self, symbol: str, side: OrderSide, quantity: float, reference_price: float
    ) -> ExecutionReport:
        self._require_private()
        order = self.client.create_order(symbol, "market", side.value, quantity)
        fill_price = float(order.get("average") or order.get("price") or reference_price)
        filled_qty = float(order.get("filled") or quantity)
        fee_paid = calculate_fee(fill_price * filled_qty, self.settings.default_fee_bps)
        return ExecutionReport(
            client_order_id=str(order.get("clientOrderId") or order.get("id")),
            exchange_order_id=str(order.get("id")),
            status=OrderStatus.FILLED if order.get("status") == "closed" else OrderStatus.NEW,
            side=side,
            order_type=OrderType.MARKET,
            filled_quantity=filled_qty,
            fill_price=fill_price,
            fee_paid=fee_paid,
            slippage_bps=0.0,
            notes=f"Live CCXT market order on {self.settings.exchange_name}.",
        )

    def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        limit_price: float,
        reference_price: float,
    ) -> ExecutionReport:
        self._require_private()
        order = self.client.create_order(symbol, "limit", side.value, quantity, limit_price)
        status = OrderStatus.NEW if order.get("status") == "open" else OrderStatus.FILLED
        filled_qty = float(order.get("filled") or 0.0)
        fee_paid = calculate_fee(limit_price * filled_qty, self.settings.default_fee_bps)
        return ExecutionReport(
            client_order_id=str(order.get("clientOrderId") or order.get("id")),
            exchange_order_id=str(order.get("id")),
            status=status,
            side=side,
            order_type=OrderType.LIMIT,
            filled_quantity=filled_qty,
            fill_price=float(order.get("average") or limit_price) if filled_qty else None,
            fee_paid=fee_paid,
            slippage_bps=0.0,
            notes=f"Live CCXT limit order on {self.settings.exchange_name}.",
        )

    def cancel_order(self, client_order_id: str) -> bool:
        self._require_private()
        self.client.cancel_order(client_order_id)
        return True

    def fetch_balance(self) -> dict[str, Any]:
        self._require_private()
        return self.client.fetch_balance()

    def fetch_open_orders(self) -> list[dict[str, Any]]:
        self._require_private()
        return self.client.fetch_open_orders()
