from __future__ import annotations

from dataclasses import dataclass

import ccxt
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import InstrumentType, MarginMode, PositionSide
from app.core.exceptions import TradingError
from app.db.models.instrument import Instrument
from app.utils.precision import enforce_min_notional, round_to_increment


@dataclass(slots=True)
class NormalizedOrder:
    instrument: Instrument
    quantity: float
    limit_price: float | None
    leverage: float


class InstrumentService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def _precision_to_step(self, value: float | int | None) -> float:
        if value is None:
            return 0.0
        numeric = float(value)
        if numeric <= 0:
            return 0.0
        if numeric >= 1 and numeric.is_integer():
            return 10 ** (-int(numeric))
        return numeric

    def _spot_exchange_name(self) -> str:
        return self.settings.exchange_name

    def _perp_exchange_name(self) -> str:
        return self.settings.derivatives_exchange_name

    def get_instrument(self, symbol: str, instrument_type: InstrumentType) -> Instrument | None:
        exchange_name = (
            self._perp_exchange_name() if instrument_type == InstrumentType.PERPETUAL else self._spot_exchange_name()
        )
        return (
            self.db.query(Instrument)
            .filter(
                Instrument.exchange == exchange_name,
                Instrument.symbol == symbol,
                Instrument.instrument_type == instrument_type,
            )
            .one_or_none()
        )

    def ensure_spot_instrument(self, symbol: str) -> Instrument:
        existing = self.get_instrument(symbol, InstrumentType.SPOT)
        if existing is not None:
            return existing
        if "/" not in symbol:
            raise TradingError(f"Unsupported spot symbol format: {symbol}")
        base_asset, quote_asset = symbol.split("/", 1)
        instrument = Instrument(
            exchange=self._spot_exchange_name(),
            symbol=symbol,
            exchange_symbol=symbol,
            instrument_type=InstrumentType.SPOT,
            margin_mode=MarginMode.CASH,
            base_asset=base_asset,
            quote_asset=quote_asset,
            settle_asset=quote_asset,
            contract_size=1.0,
            tick_size=0.0,
            lot_size=0.0,
            min_notional=0.0,
            max_leverage=1.0,
            maintenance_margin_rate=0.0,
            raw={},
        )
        self.db.add(instrument)
        self.db.commit()
        self.db.refresh(instrument)
        return instrument

    def sync_perpetual_instruments(self, symbols: list[str] | None = None) -> list[Instrument]:
        client = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
        markets = client.load_markets()
        allowed = set(symbols or [])
        synced: list[Instrument] = []
        for market in markets.values():
            if not market.get("swap") or not market.get("linear"):
                continue
            exchange_symbol = market["symbol"]
            display_symbol = exchange_symbol.split(":")[0]
            if allowed and display_symbol not in allowed:
                continue
            existing = (
                self.db.query(Instrument)
                .filter(
                    Instrument.exchange == self._perp_exchange_name(),
                    Instrument.symbol == display_symbol,
                    Instrument.instrument_type == InstrumentType.PERPETUAL,
                )
                .one_or_none()
            )
            values = {
                "exchange": self._perp_exchange_name(),
                "symbol": display_symbol,
                "exchange_symbol": exchange_symbol,
                "instrument_type": InstrumentType.PERPETUAL,
                "margin_mode": MarginMode.ISOLATED,
                "base_asset": market["base"],
                "quote_asset": market["quote"],
                "settle_asset": market.get("settle"),
                "contract_size": float(market.get("contractSize") or 1.0),
                "tick_size": self._precision_to_step((market.get("precision") or {}).get("price")),
                "lot_size": self._precision_to_step((market.get("precision") or {}).get("amount")),
                "min_notional": float(((market.get("limits") or {}).get("cost") or {}).get("min") or 0.0),
                "max_leverage": float(
                    (market.get("limits") or {}).get("leverage", {}).get("max")
                    or self.settings.max_leverage
                ),
                "maintenance_margin_rate": float(market.get("maintenanceMarginRate") or 0.0),
                "active": bool(market.get("active", True)),
                "raw": market,
            }
            if existing is None:
                instrument = Instrument(**values)
                self.db.add(instrument)
                synced.append(instrument)
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
                synced.append(existing)
        self.db.commit()
        return synced

    def ensure_instrument(self, symbol: str, instrument_type: InstrumentType) -> Instrument:
        if instrument_type == InstrumentType.SPOT:
            return self.ensure_spot_instrument(symbol)
        instrument = self.get_instrument(symbol, instrument_type)
        if instrument is None:
            self.sync_perpetual_instruments([symbol])
            instrument = self.get_instrument(symbol, instrument_type)
        if instrument is None:
            raise TradingError(f"Unable to resolve instrument metadata for {symbol} ({instrument_type.value}).")
        return instrument

    def normalize_order(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        quantity: float,
        limit_price: float | None,
        reference_price: float,
        leverage: float,
    ) -> NormalizedOrder:
        instrument = self.ensure_instrument(symbol, instrument_type)
        normalized_qty = round_to_increment(quantity, instrument.lot_size) if instrument.lot_size else quantity
        normalized_price = (
            round_to_increment(limit_price, instrument.tick_size)
            if limit_price is not None and instrument.tick_size
            else limit_price
        )
        effective_price = normalized_price or reference_price
        effective_leverage = min(leverage, instrument.max_leverage or leverage, self.settings.max_leverage)
        if normalized_qty <= 0:
            raise TradingError("Normalized quantity is zero after applying broker precision rules.")
        if instrument.min_notional and not enforce_min_notional(
            normalized_qty, effective_price, instrument.min_notional
        ):
            raise TradingError("Order notional is below the broker minimum.")
        return NormalizedOrder(
            instrument=instrument,
            quantity=normalized_qty,
            limit_price=normalized_price,
            leverage=effective_leverage,
        )

    def estimate_liquidation_price(
        self,
        entry_price: float,
        position_side: PositionSide,
        leverage: float,
        maintenance_margin_rate: float,
    ) -> float:
        leverage = max(leverage, 1.0)
        maintenance_margin_rate = max(maintenance_margin_rate, self.settings.default_maintenance_margin_pct)
        if position_side == PositionSide.LONG:
            return max(entry_price * (1 - (1 / leverage) + maintenance_margin_rate), 0.0)
        return entry_price * (1 + (1 / leverage) - maintenance_margin_rate)

    def raw_symbol_for_bybit(self, symbol: str) -> str:
        instrument = self.ensure_instrument(symbol, InstrumentType.PERPETUAL)
        raw_id = instrument.raw.get("id") if instrument.raw else None
        return str(raw_id or instrument.exchange_symbol).replace("/", "").replace(":USDT", "")
