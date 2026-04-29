from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import (
    DecisionSource,
    InstrumentType,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    PositionStatus,
    TradeAction,
)
from app.core.exceptions import RiskCheckFailed, TradingError
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.trade import Trade
from app.exchanges.base import ExchangeAdapter, ExecutionReport, OrderRequest
from app.exchanges.bybit_perp_exchange import BybitPerpExchange
from app.exchanges.ccxt_exchange import CCXTExchange
from app.exchanges.paper_exchange import PaperExchange
from app.services.data_service import DataService
from app.services.helpers import record_event
from app.services.instrument_service import InstrumentService, NormalizedOrder
from app.services.market_depth_service import MarketDepthService
from app.services.portfolio_service import PortfolioService
from app.services.risk_service import RiskService
from app.services.strategy_registry import StrategyRegistry
from app.utils.timeframes import timeframe_to_minutes

_paper_exchange_singleton: PaperExchange | None = None


def _get_paper_exchange(settings: Settings) -> PaperExchange:
    global _paper_exchange_singleton
    if _paper_exchange_singleton is None:
        _paper_exchange_singleton = PaperExchange(
            fee_bps=settings.default_fee_bps,
            slippage_bps=settings.default_slippage_bps,
        )
    return _paper_exchange_singleton


def _entry_side(position_side: PositionSide) -> OrderSide:
    return OrderSide.SELL if position_side == PositionSide.SHORT else OrderSide.BUY


def _exit_side(position_side: PositionSide) -> OrderSide:
    return OrderSide.BUY if position_side == PositionSide.SHORT else OrderSide.SELL


def _direction(position_side: PositionSide) -> float:
    return -1.0 if position_side == PositionSide.SHORT else 1.0


class ExecutionService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        registry: StrategyRegistry | None = None,
        data_service: DataService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.registry = registry or StrategyRegistry()
        self.data_service = data_service or DataService(db=db, settings=settings)
        self.portfolio_service = PortfolioService(db=db, settings=settings)
        self.risk_service = RiskService(db=db, settings=settings)
        self.instrument_service = InstrumentService(db=db, settings=settings)
        self.market_depth_service = MarketDepthService(db=db)

    def _exchange(self, instrument_type: InstrumentType) -> ExchangeAdapter:
        if self.settings.live_trading_enabled:
            if instrument_type == InstrumentType.PERPETUAL:
                return BybitPerpExchange(settings=self.settings, allow_private=True)
            return CCXTExchange(settings=self.settings, allow_private=True)
        return _get_paper_exchange(self.settings)

    def _exchange_name(self, instrument_type: InstrumentType) -> str:
        return (
            self.settings.derivatives_exchange_name
            if instrument_type == InstrumentType.PERPETUAL
            else self.settings.exchange_name
        )

    def _build_depth_snapshot(
        self,
        *,
        symbol: str,
        instrument_type: InstrumentType,
        supplied_snapshot: dict[str, list[list[float]]] | None,
    ) -> dict[str, list[list[float]]] | None:
        if supplied_snapshot is not None:
            return supplied_snapshot
        latest = self.market_depth_service.latest_orderbook(symbol, instrument_type)
        if latest is None:
            return None
        return {"bids": latest.bids, "asks": latest.asks}

    def _derive_spread_bps(self, symbol: str, instrument_type: InstrumentType, fallback: float = 0.0) -> float:
        latest_quote = self.market_depth_service.latest_quote(symbol, instrument_type)
        if latest_quote is None:
            return fallback
        return float(latest_quote.spread_bps)

    def _persist_order(
        self,
        *,
        strategy_name: str | None,
        request: OrderRequest,
        normalized: NormalizedOrder,
        report: ExecutionReport,
    ) -> Order:
        order = Order(
            client_order_id=report.client_order_id,
            exchange_order_id=report.exchange_order_id,
            strategy_name=strategy_name,
            symbol=request.symbol,
            instrument_type=request.instrument_type,
            margin_mode=request.margin_mode,
            position_side=request.position_side,
            source=request.decision_source,
            side=request.side,
            order_type=request.order_type,
            status=report.status,
            mode=self.settings.trading_mode,
            quantity=request.quantity,
            filled_quantity=report.filled_quantity,
            remaining_quantity=report.remaining_quantity,
            limit_price=request.limit_price,
            fill_price=report.fill_price,
            fee_paid=report.fee_paid,
            slippage_bps=report.slippage_bps,
            leverage=normalized.leverage,
            reduce_only=request.reduce_only,
            post_only=request.post_only,
            tick_size=normalized.instrument.tick_size,
            lot_size=normalized.instrument.lot_size,
            min_notional=normalized.instrument.min_notional,
            liquidation_price=None,
            funding_cost=0.0,
            exchange_name=self._exchange_name(request.instrument_type),
            notes=report.notes,
        )
        self.db.add(order)
        self.db.flush()
        return order

    def _latest_strategy_order(
        self,
        *,
        strategy_name: str,
        symbol: str,
        instrument_type: InstrumentType,
    ) -> Order | None:
        return (
            self.db.query(Order)
            .filter(
                Order.strategy_name == strategy_name,
                Order.symbol == symbol,
                Order.instrument_type == instrument_type,
            )
            .order_by(Order.created_at.desc())
            .first()
        )

    def _bar_already_processed(
        self,
        *,
        strategy_name: str,
        symbol: str,
        instrument_type: InstrumentType,
        bar_timestamp: pd.Timestamp | datetime,
    ) -> bool:
        latest_order = self._latest_strategy_order(
            strategy_name=strategy_name,
            symbol=symbol,
            instrument_type=instrument_type,
        )
        if latest_order is None:
            return False
        if isinstance(bar_timestamp, pd.Timestamp):
            bar_datetime = bar_timestamp.to_pydatetime()
        else:
            bar_datetime = bar_timestamp
        order_datetime = latest_order.created_at
        if order_datetime.tzinfo is None:
            order_datetime = order_datetime.replace(tzinfo=timezone.utc)
        if bar_datetime.tzinfo is None:
            bar_datetime = bar_datetime.replace(tzinfo=timezone.utc)
        return order_datetime >= bar_datetime

    def _normalize_timestamp(self, value: pd.Timestamp | datetime) -> datetime:
        if isinstance(value, pd.Timestamp):
            normalized = value.to_pydatetime()
        else:
            normalized = value
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=timezone.utc)
        return normalized

    def _selected_signal_row(
        self,
        *,
        signal_frame: pd.DataFrame,
        timeframe: str,
        now: datetime,
    ) -> tuple[pd.Timestamp | datetime | None, pd.Series | None, str]:
        latest_timestamp = signal_frame.index[-1]
        latest_row = signal_frame.iloc[-1]
        if not self.settings.evaluate_on_bar_close_only:
            return latest_timestamp, latest_row, "latest_bar"

        bar_minutes = timeframe_to_minutes(timeframe)
        latest_close_at = self._normalize_timestamp(latest_timestamp) + timedelta(minutes=bar_minutes)
        if latest_close_at <= now:
            return latest_timestamp, latest_row, "latest_closed_bar"
        if len(signal_frame) < 2:
            return None, None, "awaiting_bar_close"

        previous_timestamp = signal_frame.index[-2]
        previous_row = signal_frame.iloc[-2]
        previous_close_at = self._normalize_timestamp(previous_timestamp) + timedelta(minutes=bar_minutes)
        if previous_close_at > now:
            return None, None, "awaiting_bar_close"
        return previous_timestamp, previous_row, "previous_closed_bar"

    def _strategy_cooldown_until(
        self,
        *,
        strategy_name: str,
        symbol: str,
        instrument_type: InstrumentType,
        timeframe: str,
        now: datetime,
    ) -> datetime | None:
        latest_closed_position = self.portfolio_service.get_latest_closed_position(
            strategy_name=strategy_name,
            symbol=symbol,
            instrument_type=instrument_type,
        )
        if latest_closed_position is None or latest_closed_position.closed_at is None:
            return None
        if latest_closed_position.exit_reason == "manual_exit":
            return None
        cooldown_minutes = max(self.settings.strategy_exit_cooldown_minutes, timeframe_to_minutes(timeframe))
        cooldown_until = self._normalize_timestamp(latest_closed_position.closed_at) + timedelta(
            minutes=cooldown_minutes
        )
        if cooldown_until > now:
            return cooldown_until
        return None

    def _strategy_instance_timeframe(self, strategy_instance_name: str) -> str | None:
        if "@" not in strategy_instance_name:
            return None
        return strategy_instance_name.rsplit("@", 1)[-1]

    def preview_strategy_candidate(
        self,
        *,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        limit: int = 300,
        instrument_type: InstrumentType | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        now = now or datetime.now(timezone.utc)
        instrument_type = instrument_type or (
            InstrumentType.PERPETUAL if self.settings.enable_derivatives else InstrumentType.SPOT
        )
        strategy_instance_name = f"{strategy_name}@{timeframe}"
        strategy = self.registry.create_strategy(strategy_name, db=self.db, symbol=symbol)
        frame = self.data_service.get_historical_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            instrument_type=instrument_type,
        )
        if frame.empty:
            return {"action": "no_data", "strategy_name": strategy_name, "symbol": symbol, "timeframe": timeframe}

        signal_frame = strategy.generate_signals(frame)
        selected_bar_timestamp, selected_row, selection_reason = self._selected_signal_row(
            signal_frame=signal_frame,
            timeframe=timeframe,
            now=now,
        )
        latest_price = float(signal_frame.iloc[-1]["close"])
        if selected_bar_timestamp is None or selected_row is None:
            return {
                "action": "flat",
                "reason": selection_reason,
                "strategy_name": strategy_name,
                "strategy_instance_name": strategy_instance_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "instrument_type": instrument_type.value,
                "confidence": 0.0,
            }

        if self._bar_already_processed(
            strategy_name=strategy_instance_name,
            symbol=symbol,
            instrument_type=instrument_type,
            bar_timestamp=selected_bar_timestamp,
        ):
            return {
                "action": "flat",
                "reason": "bar_already_processed",
                "strategy_name": strategy_name,
                "strategy_instance_name": strategy_instance_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "instrument_type": instrument_type.value,
                "confidence": 0.0,
            }

        open_position = self.portfolio_service.get_position(
            strategy_name=strategy_instance_name,
            symbol=symbol,
            instrument_type=instrument_type,
        )
        if open_position is not None:
            return {
                "action": "occupied",
                "reason": "position_open",
                "strategy_name": strategy_name,
                "strategy_instance_name": strategy_instance_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "instrument_type": instrument_type.value,
                "confidence": float(selected_row.get("confidence", 0.0) or 0.0),
                "latest_price": latest_price,
                "position_side": open_position.side.value,
            }

        cooldown_until = self._strategy_cooldown_until(
            strategy_name=strategy_instance_name,
            symbol=symbol,
            instrument_type=instrument_type,
            timeframe=timeframe,
            now=now,
        )
        if cooldown_until is not None:
            return {
                "action": "flat",
                "reason": "strategy_cooldown_active",
                "cooldown_until": cooldown_until.isoformat(),
                "strategy_name": strategy_name,
                "strategy_instance_name": strategy_instance_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "instrument_type": instrument_type.value,
                "confidence": 0.0,
            }

        if not strategy.should_enter(selected_row, has_position=False):
            return {
                "action": "flat",
                "reason": "no_entry_signal",
                "strategy_name": strategy_name,
                "strategy_instance_name": strategy_instance_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "instrument_type": instrument_type.value,
                "confidence": float(selected_row.get("confidence", 0.0) or 0.0),
            }

        signal_side = strategy.desired_position_side(selected_row)
        if instrument_type == InstrumentType.SPOT and signal_side == PositionSide.SHORT:
            return {
                "action": "flat",
                "reason": "spot_short_disabled",
                "strategy_name": strategy_name,
                "strategy_instance_name": strategy_instance_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "instrument_type": instrument_type.value,
                "confidence": 0.0,
            }

        confidence = float(selected_row.get("confidence", 0.0) or 0.0)
        return {
            "action": "entry",
            "reason": "entry_signal",
            "strategy_name": strategy_name,
            "strategy_instance_name": strategy_instance_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "instrument_type": instrument_type.value,
            "bar_timestamp": selected_bar_timestamp.isoformat() if selected_bar_timestamp is not None else None,
            "side": signal_side.value,
            "confidence": confidence,
            "signal": int(selected_row.get("signal", 0) or 0),
            "latest_price": latest_price,
        }

    def _reject_order(
        self,
        *,
        strategy_name: str | None,
        symbol: str,
        instrument_type: InstrumentType,
        margin_mode: MarginMode,
        position_side: PositionSide,
        side: OrderSide,
        reason: str,
        source: DecisionSource,
    ) -> None:
        order = Order(
            strategy_name=strategy_name,
            symbol=symbol,
            instrument_type=instrument_type,
            margin_mode=margin_mode,
            position_side=position_side,
            source=source,
            side=side,
            order_type=OrderType.MARKET,
            status=OrderStatus.REJECTED,
            mode=self.settings.trading_mode,
            quantity=0.0,
            filled_quantity=0.0,
            remaining_quantity=0.0,
            leverage=1.0,
            exchange_name=self._exchange_name(instrument_type),
            notes=reason,
        )
        self.db.add(order)
        record_event(
            self.db,
            "WARNING",
            "risk_rejection",
            reason,
            {"strategy_name": strategy_name, "symbol": symbol, "instrument_type": instrument_type.value},
        )
        self.db.commit()

    def _position_stop_price(self, side: PositionSide, entry_price: float, stop_loss_pct: float) -> float:
        if side == PositionSide.SHORT:
            return entry_price * (1 + stop_loss_pct)
        return entry_price * (1 - stop_loss_pct)

    def _position_take_profit_price(self, side: PositionSide, entry_price: float, take_profit_pct: float) -> float:
        if side == PositionSide.SHORT:
            return entry_price * (1 - take_profit_pct)
        return entry_price * (1 + take_profit_pct)

    def _entry_cash_flow(
        self,
        *,
        instrument_type: InstrumentType,
        position_side: PositionSide,
        notional: float,
        fee_paid: float,
        collateral: float,
    ) -> float:
        if instrument_type == InstrumentType.SPOT and position_side == PositionSide.LONG:
            return -(notional + fee_paid)
        return -(collateral + fee_paid)

    def _exit_cash_flow(
        self,
        *,
        instrument_type: InstrumentType,
        position_side: PositionSide,
        exit_notional: float,
        gross_pnl: float,
        fee_paid: float,
        collateral_release: float,
        funding_alloc: float,
    ) -> float:
        if instrument_type == InstrumentType.SPOT and position_side == PositionSide.LONG:
            return exit_notional - fee_paid
        return collateral_release + gross_pnl - fee_paid - funding_alloc

    def _record_entry_fill(
        self,
        *,
        strategy_name: str | None,
        normalized: NormalizedOrder,
        order: Order,
        report: ExecutionReport,
        position_side: PositionSide,
        stop_loss_pct: float,
        take_profit_pct: float,
        decision_source: DecisionSource,
    ) -> Position:
        if report.fill_price is None or report.filled_quantity <= 0:
            raise TradingError("Cannot create a position from an unfilled order.")

        entry_notional = report.fill_price * report.filled_quantity
        collateral = (
            entry_notional / max(normalized.leverage, 1.0)
            if normalized.instrument.instrument_type == InstrumentType.PERPETUAL
            else 0.0
        )
        liquidation_price = (
            self.instrument_service.estimate_liquidation_price(
                entry_price=report.fill_price,
                position_side=position_side,
                leverage=normalized.leverage,
                maintenance_margin_rate=normalized.instrument.maintenance_margin_rate,
            )
            if normalized.instrument.instrument_type == InstrumentType.PERPETUAL
            else None
        )
        position = Position(
            strategy_name=strategy_name or "manual",
            symbol=order.symbol,
            instrument_type=normalized.instrument.instrument_type,
            margin_mode=order.margin_mode,
            side=position_side,
            mode=self.settings.trading_mode,
            status=PositionStatus.OPEN,
            quantity=report.filled_quantity,
            leverage=normalized.leverage,
            avg_entry_price=report.fill_price,
            current_price=report.fill_price,
            entry_notional=entry_notional,
            collateral=collateral,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            stop_loss_price=self._position_stop_price(position_side, report.fill_price, stop_loss_pct),
            take_profit_price=self._position_take_profit_price(position_side, report.fill_price, take_profit_pct),
            liquidation_price=liquidation_price,
            maintenance_margin_rate=normalized.instrument.maintenance_margin_rate,
            funding_cost=0.0,
        )
        self.db.add(position)
        self.db.flush()
        order.liquidation_price = liquidation_price
        entry_side = _entry_side(position_side)
        self.db.add(
            Trade(
                order_id=order.id,
                position_id=position.id,
                strategy_name=strategy_name,
                symbol=order.symbol,
                instrument_type=normalized.instrument.instrument_type,
                margin_mode=order.margin_mode,
                position_side=position_side,
                source=decision_source,
                side=entry_side,
                action=TradeAction.ENTRY,
                mode=self.settings.trading_mode,
                leverage=normalized.leverage,
                price=report.fill_price,
                quantity=report.filled_quantity,
                notional=entry_notional,
                fee_paid=report.fee_paid,
                funding_cost=0.0,
                realized_pnl=0.0,
                cash_flow=self._entry_cash_flow(
                    instrument_type=normalized.instrument.instrument_type,
                    position_side=position_side,
                    notional=entry_notional,
                    fee_paid=report.fee_paid,
                    collateral=collateral,
                ),
                notes="entry_fill",
            )
        )
        return position

    def submit_entry_order(
        self,
        *,
        strategy_name: str | None,
        strategy_instance_name: str | None = None,
        symbol: str,
        reference_price: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        margin_mode: MarginMode | None = None,
        leverage: float | None = None,
        position_side: PositionSide = PositionSide.LONG,
        decision_source: DecisionSource = DecisionSource.STRATEGY,
        quantity: float | None = None,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        spread_bps: float | None = None,
        slippage_bps: float | None = None,
        depth_snapshot: dict[str, list[list[float]]] | None = None,
        execution_model: str | None = None,
        allow_candle_fallback: bool = True,
    ) -> Order:
        selected_margin_mode = (
            margin_mode
            if margin_mode is not None
            else (MarginMode.ISOLATED if instrument_type == InstrumentType.PERPETUAL else MarginMode.CASH)
        )
        stored_strategy_name = strategy_instance_name or strategy_name or "manual"
        selected_leverage = 1.0 if instrument_type == InstrumentType.SPOT else float(leverage or self.settings.default_leverage)
        execution_model = execution_model or self.settings.default_execution_model
        existing_position = self.portfolio_service.get_position(
            strategy_name=stored_strategy_name,
            symbol=symbol,
            instrument_type=instrument_type,
        )
        if existing_position is not None:
            raise TradingError(f"Open position already exists for {stored_strategy_name} on {symbol}.")

        strategy = None
        if strategy_name and strategy_name in self.registry.names():
            strategy = self.registry.create_strategy(strategy_name, db=self.db, symbol=symbol)

        portfolio = self.portfolio_service.recalculate_state({symbol: reference_price})
        stop_loss_pct = stop_loss_pct if stop_loss_pct is not None else (strategy.stop_loss_pct() if strategy else 0.015)
        take_profit_pct = (
            take_profit_pct if take_profit_pct is not None else (strategy.take_profit_pct() if strategy else 0.03)
        )

        if quantity is None:
            if strategy is not None:
                quantity = strategy.position_size(
                    cash_balance=portfolio.last_equity,
                    price=reference_price,
                    risk_fraction=self.settings.max_risk_per_trade,
                    max_notional_fraction=self.settings.max_position_notional_pct,
                    leverage=selected_leverage,
                )
            else:
                quantity = round(
                    max(
                        (portfolio.last_equity * self.settings.max_position_notional_pct * max(selected_leverage, 1.0))
                        / max(reference_price, 1.0),
                        0.0,
                    ),
                    8,
                )
        if quantity <= 0:
            raise RiskCheckFailed("Calculated order quantity is zero.")

        normalized = self.instrument_service.normalize_order(
            symbol=symbol,
            instrument_type=instrument_type,
            quantity=quantity,
            limit_price=limit_price,
            reference_price=reference_price,
            leverage=selected_leverage,
        )
        funding_record = (
            self.market_depth_service.latest_funding_rate(symbol)
            if instrument_type == InstrumentType.PERPETUAL
            else None
        )
        liquidation_price = (
            self.instrument_service.estimate_liquidation_price(
                entry_price=normalized.limit_price or reference_price,
                position_side=position_side,
                leverage=normalized.leverage,
                maintenance_margin_rate=normalized.instrument.maintenance_margin_rate,
            )
            if instrument_type == InstrumentType.PERPETUAL
            else None
        )
        spread_bps = (
            float(spread_bps)
            if spread_bps is not None
            else self._derive_spread_bps(symbol, instrument_type, fallback=0.0)
        )
        slippage_bps = (
            float(slippage_bps)
            if slippage_bps is not None
            else self.settings.default_slippage_bps
        )
        risk = self.risk_service.evaluate_entry(
            symbol=symbol,
            quantity=normalized.quantity,
            price=normalized.limit_price or reference_price,
            stop_loss_pct=stop_loss_pct,
            instrument_type=instrument_type,
            leverage=normalized.leverage,
            position_side=position_side,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
            funding_rate=funding_record.funding_rate if funding_record else None,
            liquidation_price=liquidation_price,
        )
        entry_side = _entry_side(position_side)
        if not risk.allowed:
            self._reject_order(
                strategy_name=stored_strategy_name,
                symbol=symbol,
                instrument_type=instrument_type,
                margin_mode=selected_margin_mode,
                position_side=position_side,
                side=entry_side,
                reason=risk.reason,
                source=decision_source,
            )
            raise RiskCheckFailed(risk.reason)

        request = OrderRequest(
            symbol=symbol,
            exchange_symbol=normalized.instrument.exchange_symbol,
            instrument_type=instrument_type,
            margin_mode=selected_margin_mode,
            position_side=position_side,
            side=entry_side,
            order_type=order_type,
            quantity=normalized.quantity,
            reference_price=reference_price,
            limit_price=normalized.limit_price,
            leverage=normalized.leverage,
            reduce_only=False,
            post_only=order_type == OrderType.LIMIT and execution_model == "depth",
            decision_source=decision_source,
            tick_size=normalized.instrument.tick_size,
            lot_size=normalized.instrument.lot_size,
            min_notional=normalized.instrument.min_notional,
            depth_snapshot=self._build_depth_snapshot(
                symbol=symbol,
                instrument_type=instrument_type,
                supplied_snapshot=depth_snapshot,
            ),
            execution_model=execution_model,
            allow_candle_fallback=allow_candle_fallback,
        )
        report = self._exchange(instrument_type).place_order(request)
        order = self._persist_order(
            strategy_name=stored_strategy_name,
            request=request,
            normalized=normalized,
            report=report,
        )

        if report.filled_quantity > 0 and report.fill_price is not None:
            position = self._record_entry_fill(
                strategy_name=stored_strategy_name,
                normalized=normalized,
                order=order,
                report=report,
                position_side=position_side,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                decision_source=decision_source,
            )
            record_event(
                self.db,
                "INFO",
                "order_filled",
                f"Opened {position.side.value.lower()} {symbol} position.",
                {
                    "order_id": order.id,
                    "position_id": position.id,
                    "strategy_name": stored_strategy_name,
                    "symbol": symbol,
                    "instrument_type": instrument_type.value,
                },
            )
        else:
            record_event(
                self.db,
                "INFO",
                "order_open",
                f"Submitted resting order for {symbol}.",
                {"order_id": order.id, "strategy_name": stored_strategy_name, "symbol": symbol},
            )
        self.db.commit()
        self.portfolio_service.recalculate_state({symbol: report.fill_price or reference_price})
        self.db.refresh(order)
        return order

    def close_position(
        self,
        position: Position,
        reference_price: float,
        exit_reason: str,
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        depth_snapshot: dict[str, list[list[float]]] | None = None,
        execution_model: str | None = None,
        allow_candle_fallback: bool = True,
    ) -> Order:
        if position.status != PositionStatus.OPEN:
            raise TradingError(f"Position {position.id} is not open.")

        normalized = self.instrument_service.normalize_order(
            symbol=position.symbol,
            instrument_type=position.instrument_type,
            quantity=position.quantity,
            limit_price=limit_price,
            reference_price=reference_price,
            leverage=position.leverage,
        )
        request = OrderRequest(
            symbol=position.symbol,
            exchange_symbol=normalized.instrument.exchange_symbol,
            instrument_type=position.instrument_type,
            margin_mode=position.margin_mode,
            position_side=position.side,
            side=_exit_side(position.side),
            order_type=order_type,
            quantity=normalized.quantity,
            reference_price=reference_price,
            limit_price=normalized.limit_price,
            leverage=position.leverage,
            reduce_only=True,
            post_only=False,
            decision_source=DecisionSource.RISK if exit_reason in {"stop_loss", "liquidation"} else DecisionSource.STRATEGY,
            tick_size=normalized.instrument.tick_size,
            lot_size=normalized.instrument.lot_size,
            min_notional=normalized.instrument.min_notional,
            depth_snapshot=self._build_depth_snapshot(
                symbol=position.symbol,
                instrument_type=position.instrument_type,
                supplied_snapshot=depth_snapshot,
            ),
            execution_model=execution_model or self.settings.default_execution_model,
            allow_candle_fallback=allow_candle_fallback,
        )
        report = self._exchange(position.instrument_type).place_order(request)
        order = self._persist_order(
            strategy_name=position.strategy_name,
            request=request,
            normalized=normalized,
            report=report,
        )

        if report.filled_quantity <= 0 or report.fill_price is None:
            record_event(
                self.db,
                "WARNING",
                "position_close_pending",
                f"Close order for position {position.id} is not filled.",
                {"position_id": position.id, "order_id": order.id},
            )
            self.db.commit()
            self.db.refresh(order)
            return order

        original_quantity = position.quantity
        close_quantity = min(report.filled_quantity, original_quantity)
        remaining_quantity = max(original_quantity - close_quantity, 0.0)
        direction = _direction(position.side)
        gross_pnl = direction * (report.fill_price - position.avg_entry_price) * close_quantity
        entry_trades = [trade for trade in position.trades if trade.action == TradeAction.ENTRY]
        entry_fee_total = sum(trade.fee_paid for trade in entry_trades)
        entry_quantity_total = sum(trade.quantity for trade in entry_trades)
        entry_fee_alloc = entry_fee_total * (close_quantity / entry_quantity_total) if entry_quantity_total else 0.0
        funding_alloc = position.funding_cost * (close_quantity / original_quantity) if original_quantity else 0.0
        collateral_release = position.collateral * (close_quantity / original_quantity) if original_quantity else 0.0
        realized_pnl = gross_pnl - entry_fee_alloc - report.fee_paid - funding_alloc
        exit_notional = report.fill_price * close_quantity

        position.quantity = remaining_quantity
        position.current_price = report.fill_price
        position.realized_pnl += realized_pnl
        position.entry_notional = position.avg_entry_price * remaining_quantity
        position.collateral = max(position.collateral - collateral_release, 0.0)
        position.funding_cost = max(position.funding_cost - funding_alloc, 0.0)

        if remaining_quantity <= 1e-12:
            position.status = PositionStatus.CLOSED
            position.unrealized_pnl = 0.0
            position.exit_reason = exit_reason
            position.closed_at = datetime.now(timezone.utc)
            position.quantity = 0.0
        else:
            position.unrealized_pnl = direction * (position.current_price - position.avg_entry_price) * remaining_quantity

        self.db.add(position)
        self.db.add(
            Trade(
                order_id=order.id,
                position_id=position.id,
                strategy_name=position.strategy_name,
                symbol=position.symbol,
                instrument_type=position.instrument_type,
                margin_mode=position.margin_mode,
                position_side=position.side,
                source=request.decision_source,
                side=request.side,
                action=TradeAction.EXIT,
                mode=self.settings.trading_mode,
                leverage=position.leverage,
                price=report.fill_price,
                quantity=close_quantity,
                notional=exit_notional,
                fee_paid=report.fee_paid,
                funding_cost=funding_alloc,
                realized_pnl=realized_pnl,
                cash_flow=self._exit_cash_flow(
                    instrument_type=position.instrument_type,
                    position_side=position.side,
                    exit_notional=exit_notional,
                    gross_pnl=gross_pnl,
                    fee_paid=report.fee_paid,
                    collateral_release=collateral_release,
                    funding_alloc=funding_alloc,
                ),
                notes=exit_reason,
            )
        )
        record_event(
            self.db,
            "INFO",
            "position_closed" if position.status == PositionStatus.CLOSED else "position_reduced",
            f"Processed exit for position {position.id} on {position.symbol}.",
            {
                "position_id": position.id,
                "order_id": order.id,
                "exit_reason": exit_reason,
                "remaining_quantity": remaining_quantity,
            },
        )
        self.db.commit()
        self.portfolio_service.recalculate_state({position.symbol: report.fill_price})
        self.db.refresh(order)
        return order

    def close_position_by_id(self, position_id: int, reference_price: float | None = None, reason: str = "manual_exit") -> Order:
        position = self.db.query(Position).filter(Position.id == position_id).one_or_none()
        if position is None:
            raise TradingError(f"Unknown position id {position_id}.")
        return self.close_position(
            position=position,
            reference_price=reference_price or position.current_price or position.avg_entry_price,
            exit_reason=reason,
        )

    def cancel_order(self, order_id: int) -> Order:
        order = self.db.query(Order).filter(Order.id == order_id).one()
        if order.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
            raise TradingError(f"Order {order_id} is not cancelable.")
        canceled = self._exchange(order.instrument_type).cancel_order(order.exchange_order_id or order.client_order_id)
        if not canceled:
            raise TradingError(f"Adapter could not cancel order {order_id}.")
        order.status = OrderStatus.CANCELED
        record_event(
            self.db,
            "INFO",
            "order_canceled",
            f"Canceled order {order_id}.",
            {"order_id": order_id},
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def evaluate_strategy(
        self,
        *,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        limit: int = 300,
        instrument_type: InstrumentType | None = None,
        execution_model: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        now = now or datetime.now(timezone.utc)
        instrument_type = instrument_type or (
            InstrumentType.PERPETUAL if self.settings.enable_derivatives else InstrumentType.SPOT
        )
        strategy_instance_name = f"{strategy_name}@{timeframe}"
        strategy = self.registry.create_strategy(strategy_name, db=self.db, symbol=symbol)
        frame = self.data_service.get_historical_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            instrument_type=instrument_type,
        )
        if frame.empty:
            return {"action": "no_data", "strategy_name": strategy_name, "symbol": symbol}
        signal_frame = strategy.generate_signals(frame)
        latest_market = signal_frame.iloc[-1]
        latest_price = float(latest_market["close"])
        selected_bar_timestamp, selected_row, selection_reason = self._selected_signal_row(
            signal_frame=signal_frame,
            timeframe=timeframe,
            now=now,
        )
        open_position = self.portfolio_service.get_position(
            strategy_name=strategy_instance_name,
            symbol=symbol,
            instrument_type=instrument_type,
        )
        if selected_bar_timestamp is None or selected_row is None:
            self.portfolio_service.recalculate_state({symbol: latest_price})
            return {
                "action": "hold" if open_position is not None else "flat",
                "reason": selection_reason,
                "strategy_name": strategy_name,
                "symbol": symbol,
            }
        if self._bar_already_processed(
            strategy_name=strategy_instance_name,
            symbol=symbol,
            instrument_type=instrument_type,
            bar_timestamp=selected_bar_timestamp,
        ):
            self.portfolio_service.recalculate_state({symbol: latest_price})
            return {
                "action": "hold" if open_position is not None else "flat",
                "reason": "bar_already_processed",
                "strategy_name": strategy_name,
                "symbol": symbol,
            }

        if open_position is not None:
            self.portfolio_service.recalculate_state({symbol: latest_price})
            if open_position.liquidation_price:
                if (
                    open_position.side == PositionSide.LONG
                    and float(selected_row["low"]) <= open_position.liquidation_price
                ):
                    self.close_position(open_position, open_position.liquidation_price, "liquidation")
                    return {"action": "exit", "reason": "liquidation", "strategy_name": strategy_name}
                if (
                    open_position.side == PositionSide.SHORT
                    and float(selected_row["high"]) >= open_position.liquidation_price
                ):
                    self.close_position(open_position, open_position.liquidation_price, "liquidation")
                    return {"action": "exit", "reason": "liquidation", "strategy_name": strategy_name}
            if open_position.stop_loss_price:
                if open_position.side == PositionSide.LONG and float(selected_row["low"]) <= open_position.stop_loss_price:
                    self.close_position(open_position, open_position.stop_loss_price, "stop_loss")
                    return {"action": "exit", "reason": "stop_loss", "strategy_name": strategy_name}
                if open_position.side == PositionSide.SHORT and float(selected_row["high"]) >= open_position.stop_loss_price:
                    self.close_position(open_position, open_position.stop_loss_price, "stop_loss")
                    return {"action": "exit", "reason": "stop_loss", "strategy_name": strategy_name}
            if open_position.take_profit_price:
                if (
                    open_position.side == PositionSide.LONG
                    and float(selected_row["high"]) >= open_position.take_profit_price
                ):
                    self.close_position(open_position, open_position.take_profit_price, "take_profit")
                    return {"action": "exit", "reason": "take_profit", "strategy_name": strategy_name}
                if (
                    open_position.side == PositionSide.SHORT
                    and float(selected_row["low"]) <= open_position.take_profit_price
                ):
                    self.close_position(open_position, open_position.take_profit_price, "take_profit")
                    return {"action": "exit", "reason": "take_profit", "strategy_name": strategy_name}
            signal_side = strategy.desired_position_side(selected_row)
            opposite_signal = bool(selected_row.get("entry", False)) and signal_side != open_position.side
            if strategy.should_exit(selected_row, has_position=True, position_side=open_position.side) or opposite_signal:
                self.close_position(open_position, float(selected_row["close"]), "strategy_exit")
                return {"action": "exit", "reason": "strategy_exit", "strategy_name": strategy_name}
            return {"action": "hold", "strategy_name": strategy_name, "symbol": symbol}

        cooldown_until = self._strategy_cooldown_until(
            strategy_name=strategy_instance_name,
            symbol=symbol,
            instrument_type=instrument_type,
            timeframe=timeframe,
            now=now,
        )
        if cooldown_until is not None:
            return {
                "action": "flat",
                "reason": "strategy_cooldown_active",
                "cooldown_until": cooldown_until.isoformat(),
                "strategy_name": strategy_name,
                "symbol": symbol,
            }

        if strategy.should_enter(selected_row, has_position=False):
            signal_side = strategy.desired_position_side(selected_row)
            if instrument_type == InstrumentType.SPOT and signal_side == PositionSide.SHORT:
                return {"action": "flat", "reason": "spot_short_disabled", "strategy_name": strategy_name}
            order = self.submit_entry_order(
                strategy_name=strategy_name,
                strategy_instance_name=strategy_instance_name,
                symbol=symbol,
                reference_price=float(selected_row["close"]),
                instrument_type=instrument_type,
                margin_mode=MarginMode.ISOLATED if instrument_type == InstrumentType.PERPETUAL else MarginMode.CASH,
                leverage=self.settings.default_leverage if instrument_type == InstrumentType.PERPETUAL else 1.0,
                position_side=signal_side,
                decision_source=DecisionSource.STRATEGY,
                stop_loss_pct=strategy.stop_loss_pct(),
                take_profit_pct=strategy.take_profit_pct(),
                execution_model=execution_model or self.settings.default_execution_model,
            )
            return {"action": "entry", "order_id": order.id, "strategy_name": strategy_name, "side": signal_side.value}

        return {"action": "flat", "strategy_name": strategy_name, "symbol": symbol}

    def manual_order(
        self,
        *,
        symbol: str,
        instrument_type: InstrumentType,
        position_side: PositionSide,
        quantity: float,
        reference_price: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        leverage: float | None = None,
    ) -> Order:
        return self.submit_entry_order(
            strategy_name="manual",
            symbol=symbol,
            reference_price=reference_price,
            order_type=order_type,
            limit_price=limit_price,
            instrument_type=instrument_type,
            margin_mode=MarginMode.ISOLATED if instrument_type == InstrumentType.PERPETUAL else MarginMode.CASH,
            leverage=leverage,
            position_side=position_side,
            decision_source=DecisionSource.MANUAL,
            quantity=quantity,
        )
