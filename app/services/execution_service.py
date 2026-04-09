from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import OrderSide, OrderStatus, OrderType, PositionSide, PositionStatus, TradeAction
from app.core.exceptions import RiskCheckFailed, TradingError
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.trade import Trade
from app.exchanges.base import ExchangeAdapter, ExecutionReport
from app.exchanges.ccxt_exchange import CCXTExchange
from app.exchanges.paper_exchange import PaperExchange
from app.services.data_service import DataService
from app.services.helpers import record_event
from app.services.portfolio_service import PortfolioService
from app.services.risk_service import RiskService
from app.services.strategy_registry import StrategyRegistry

_paper_exchange_singleton: PaperExchange | None = None


def _get_paper_exchange(settings: Settings) -> PaperExchange:
    global _paper_exchange_singleton
    if _paper_exchange_singleton is None:
        _paper_exchange_singleton = PaperExchange(
            fee_bps=settings.default_fee_bps,
            slippage_bps=settings.default_slippage_bps,
        )
    return _paper_exchange_singleton


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

    def _exchange(self) -> ExchangeAdapter:
        if self.settings.live_trading_enabled:
            return CCXTExchange(settings=self.settings, allow_private=True)
        return _get_paper_exchange(self.settings)

    def _persist_order(self, strategy_name: str, symbol: str, report: ExecutionReport) -> Order:
        order = Order(
            client_order_id=report.client_order_id,
            exchange_order_id=report.exchange_order_id,
            strategy_name=strategy_name,
            symbol=symbol,
            side=report.side,
            order_type=report.order_type,
            status=report.status,
            mode=self.settings.trading_mode,
            quantity=report.filled_quantity if report.status == OrderStatus.FILLED else 0.0,
            limit_price=report.fill_price if report.order_type == OrderType.LIMIT else None,
            fill_price=report.fill_price,
            fee_paid=report.fee_paid,
            slippage_bps=report.slippage_bps,
            exchange_name=self.settings.exchange_name,
            notes=report.notes,
        )
        self.db.add(order)
        self.db.flush()
        return order

    def _reject_order(self, strategy_name: str, symbol: str, side: OrderSide, reason: str) -> None:
        order = Order(
            strategy_name=strategy_name,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            status=OrderStatus.REJECTED,
            mode=self.settings.trading_mode,
            quantity=0.0,
            exchange_name=self.settings.exchange_name,
            notes=reason,
        )
        self.db.add(order)
        record_event(
            self.db,
            "WARNING",
            "risk_rejection",
            reason,
            {"strategy_name": strategy_name, "symbol": symbol},
        )
        self.db.commit()

    def submit_entry_order(
        self,
        *,
        strategy_name: str,
        symbol: str,
        reference_price: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        spread_bps: float = 0.0,
        slippage_bps: float | None = None,
    ) -> Order:
        existing_position = (
            self.db.query(Position)
            .filter(
                Position.mode == self.settings.trading_mode,
                Position.strategy_name == strategy_name,
                Position.symbol == symbol,
                Position.status == PositionStatus.OPEN,
            )
            .one_or_none()
        )
        if existing_position is not None:
            raise TradingError(f"Open position already exists for {strategy_name} on {symbol}.")

        strategy = self.registry.create_strategy(strategy_name, db=self.db)
        state = self.portfolio_service.recalculate_state({symbol: reference_price})
        quantity = strategy.position_size(
            cash_balance=state.cash_balance,
            price=reference_price,
            risk_fraction=self.settings.max_risk_per_trade,
            max_notional_fraction=self.settings.max_position_notional_pct,
        )
        if quantity <= 0:
            raise RiskCheckFailed("Calculated order quantity is zero.")

        risk = self.risk_service.evaluate_entry(
            symbol=symbol,
            quantity=quantity,
            price=reference_price,
            stop_loss_pct=strategy.stop_loss_pct(),
            spread_bps=spread_bps,
            slippage_bps=slippage_bps if slippage_bps is not None else self.settings.default_slippage_bps,
        )
        if not risk.allowed:
            self._reject_order(strategy_name, symbol, OrderSide.BUY, risk.reason)
            raise RiskCheckFailed(risk.reason)

        exchange = self._exchange()
        if order_type == OrderType.MARKET:
            report = exchange.place_market_order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                reference_price=reference_price,
            )
        else:
            if limit_price is None:
                raise TradingError("Limit price is required for limit orders.")
            report = exchange.place_limit_order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                limit_price=limit_price,
                reference_price=reference_price,
            )

        order = self._persist_order(strategy_name=strategy_name, symbol=symbol, report=report)
        order.quantity = quantity
        if order_type == OrderType.LIMIT:
            order.limit_price = limit_price

        if report.status == OrderStatus.FILLED and report.fill_price is not None:
            position = Position(
                strategy_name=strategy_name,
                symbol=symbol,
                side=PositionSide.LONG,
                mode=self.settings.trading_mode,
                status=PositionStatus.OPEN,
                quantity=report.filled_quantity,
                avg_entry_price=report.fill_price,
                current_price=report.fill_price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                stop_loss_price=report.fill_price * (1 - strategy.stop_loss_pct()),
                take_profit_price=report.fill_price * (1 + strategy.take_profit_pct()),
            )
            self.db.add(position)
            self.db.flush()
            self.db.add(
                Trade(
                    order_id=order.id,
                    position_id=position.id,
                    strategy_name=strategy_name,
                    symbol=symbol,
                    side=OrderSide.BUY,
                    action=TradeAction.ENTRY,
                    mode=self.settings.trading_mode,
                    price=report.fill_price,
                    quantity=report.filled_quantity,
                    notional=report.fill_price * report.filled_quantity,
                    fee_paid=report.fee_paid,
                    realized_pnl=0.0,
                    notes="entry_fill",
                )
            )
            record_event(
                self.db,
                "INFO",
                "order_filled",
                f"Opened {strategy_name} position on {symbol}.",
                {"order_id": order.id, "symbol": symbol, "strategy_name": strategy_name},
            )
        else:
            record_event(
                self.db,
                "INFO",
                "order_open",
                f"Submitted resting order for {symbol}.",
                {"order_id": order.id, "symbol": symbol, "strategy_name": strategy_name},
            )
        self.db.commit()
        self.portfolio_service.recalculate_state({symbol: report.fill_price or reference_price})
        self.db.refresh(order)
        return order

    def close_position(self, position: Position, reference_price: float, exit_reason: str) -> Order:
        if position.status != PositionStatus.OPEN:
            raise TradingError(f"Position {position.id} is not open.")

        exchange = self._exchange()
        report = exchange.place_market_order(
            symbol=position.symbol,
            side=OrderSide.SELL,
            quantity=position.quantity,
            reference_price=reference_price,
        )
        order = self._persist_order(strategy_name=position.strategy_name, symbol=position.symbol, report=report)
        order.quantity = position.quantity

        if report.status != OrderStatus.FILLED or report.fill_price is None:
            record_event(
                self.db,
                "WARNING",
                "position_close_pending",
                f"Close order for position {position.id} is not filled.",
                {"position_id": position.id, "order_id": order.id},
            )
            self.db.commit()
            return order

        entry_fees = sum(
            trade.fee_paid
            for trade in position.trades
            if trade.action == TradeAction.ENTRY
        )
        gross_pnl = (report.fill_price - position.avg_entry_price) * position.quantity
        net_pnl = gross_pnl - entry_fees - report.fee_paid

        position.current_price = report.fill_price
        position.unrealized_pnl = 0.0
        position.realized_pnl = net_pnl
        position.status = PositionStatus.CLOSED
        position.exit_reason = exit_reason
        position.closed_at = datetime.now(timezone.utc)
        self.db.add(position)
        self.db.add(
            Trade(
                order_id=order.id,
                position_id=position.id,
                strategy_name=position.strategy_name,
                symbol=position.symbol,
                side=OrderSide.SELL,
                action=TradeAction.EXIT,
                mode=self.settings.trading_mode,
                price=report.fill_price,
                quantity=position.quantity,
                notional=report.fill_price * position.quantity,
                fee_paid=report.fee_paid,
                realized_pnl=net_pnl,
                notes=exit_reason,
            )
        )
        record_event(
            self.db,
            "INFO",
            "position_closed",
            f"Closed position {position.id} on {position.symbol}.",
            {"position_id": position.id, "order_id": order.id, "exit_reason": exit_reason},
        )
        self.db.commit()
        self.portfolio_service.recalculate_state({position.symbol: report.fill_price})
        self.db.refresh(order)
        return order

    def cancel_order(self, order_id: int) -> Order:
        order = self.db.query(Order).filter(Order.id == order_id).one()
        if order.status != OrderStatus.NEW:
            raise TradingError(f"Order {order_id} is not cancelable.")
        canceled = self._exchange().cancel_order(order.client_order_id)
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
    ) -> dict[str, object]:
        strategy = self.registry.create_strategy(strategy_name, db=self.db)
        frame = self.data_service.get_historical_data(symbol=symbol, timeframe=timeframe, limit=limit)
        if frame.empty:
            return {"action": "no_data", "strategy_name": strategy_name, "symbol": symbol}
        signal_frame = strategy.generate_signals(frame)
        latest = signal_frame.iloc[-1]
        latest_price = float(latest["close"])
        open_position = (
            self.db.query(Position)
            .filter(
                Position.mode == self.settings.trading_mode,
                Position.strategy_name == strategy_name,
                Position.symbol == symbol,
                Position.status == PositionStatus.OPEN,
            )
            .one_or_none()
        )

        if open_position is not None:
            open_position.current_price = latest_price
            open_position.unrealized_pnl = (latest_price - open_position.avg_entry_price) * open_position.quantity
            self.db.add(open_position)
            self.db.commit()
            if open_position.stop_loss_price and float(latest["low"]) <= open_position.stop_loss_price:
                self.close_position(open_position, open_position.stop_loss_price, "stop_loss")
                return {"action": "exit", "reason": "stop_loss", "strategy_name": strategy_name}
            if open_position.take_profit_price and float(latest["high"]) >= open_position.take_profit_price:
                self.close_position(open_position, open_position.take_profit_price, "take_profit")
                return {"action": "exit", "reason": "take_profit", "strategy_name": strategy_name}
            if strategy.should_exit(latest, has_position=True):
                self.close_position(open_position, latest_price, "strategy_exit")
                return {"action": "exit", "reason": "strategy_exit", "strategy_name": strategy_name}
            self.portfolio_service.recalculate_state({symbol: latest_price})
            return {"action": "hold", "strategy_name": strategy_name, "symbol": symbol}

        if strategy.should_enter(latest, has_position=False):
            order = self.submit_entry_order(
                strategy_name=strategy_name,
                symbol=symbol,
                reference_price=latest_price,
            )
            return {"action": "entry", "order_id": order.id, "strategy_name": strategy_name}

        return {"action": "flat", "strategy_name": strategy_name, "symbol": symbol}
