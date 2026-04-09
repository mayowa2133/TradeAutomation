from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import PositionStatus, TradeAction
from app.db.models.order import Order
from app.db.models.portfolio_state import PortfolioState
from app.db.models.position import Position
from app.db.models.trade import Trade


class PortfolioService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def get_or_create_state(self) -> PortfolioState:
        state = (
            self.db.query(PortfolioState)
            .filter(PortfolioState.mode == self.settings.trading_mode)
            .one_or_none()
        )
        if state is None:
            starting_balance = float(self.settings.paper_starting_balance)
            state = PortfolioState(
                mode=self.settings.trading_mode,
                currency=self.settings.default_quote_currency,
                starting_balance=starting_balance,
                cash_balance=starting_balance,
                last_equity=starting_balance,
                peak_equity=starting_balance,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
            )
            self.db.add(state)
            self.db.commit()
            self.db.refresh(state)
        return state

    def get_open_positions(self) -> list[Position]:
        return (
            self.db.query(Position)
            .filter(
                Position.mode == self.settings.trading_mode,
                Position.status == PositionStatus.OPEN,
            )
            .order_by(Position.opened_at.asc())
            .all()
        )

    def get_orders(self, limit: int = 100) -> list[Order]:
        return (
            self.db.query(Order)
            .filter(Order.mode == self.settings.trading_mode)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_trades(self, limit: int = 100) -> list[Trade]:
        return (
            self.db.query(Trade)
            .filter(Trade.mode == self.settings.trading_mode)
            .order_by(Trade.trade_time.desc())
            .limit(limit)
            .all()
        )

    def recalculate_state(self, latest_prices: dict[str, float] | None = None) -> PortfolioState:
        latest_prices = latest_prices or {}
        state = self.get_or_create_state()

        entry_trades = (
            self.db.query(Trade)
            .filter(Trade.mode == self.settings.trading_mode, Trade.action == TradeAction.ENTRY)
            .all()
        )
        exit_trades = (
            self.db.query(Trade)
            .filter(Trade.mode == self.settings.trading_mode, Trade.action == TradeAction.EXIT)
            .all()
        )

        cash_balance = state.starting_balance
        cash_balance -= sum(trade.notional + trade.fee_paid for trade in entry_trades)
        cash_balance += sum(trade.notional - trade.fee_paid for trade in exit_trades)

        open_positions = self.get_open_positions()
        market_value = 0.0
        unrealized_pnl = 0.0
        for position in open_positions:
            last_price = float(latest_prices.get(position.symbol, position.current_price or position.avg_entry_price))
            position.current_price = last_price
            position.unrealized_pnl = (last_price - position.avg_entry_price) * position.quantity
            market_value += last_price * position.quantity
            unrealized_pnl += position.unrealized_pnl

        realized_pnl = (
            self.db.query(func.coalesce(func.sum(Position.realized_pnl), 0.0))
            .filter(
                Position.mode == self.settings.trading_mode,
                Position.status == PositionStatus.CLOSED,
            )
            .scalar()
            or 0.0
        )

        equity = cash_balance + market_value
        state.cash_balance = float(cash_balance)
        state.realized_pnl = float(realized_pnl)
        state.unrealized_pnl = float(unrealized_pnl)
        state.last_equity = float(equity)
        state.peak_equity = max(float(state.peak_equity), float(equity))
        state.updated_at = datetime.now(timezone.utc)
        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)
        return state

    def pnl_summary(self) -> dict[str, float | str]:
        state = self.recalculate_state()
        peak = state.peak_equity if state.peak_equity > 0 else 1.0
        drawdown_pct = max((peak - state.last_equity) / peak, 0.0)
        return {
            "currency": state.currency,
            "starting_balance": state.starting_balance,
            "cash_balance": state.cash_balance,
            "realized_pnl": state.realized_pnl,
            "unrealized_pnl": state.unrealized_pnl,
            "equity": state.last_equity,
            "peak_equity": state.peak_equity,
            "drawdown_pct": drawdown_pct,
        }
