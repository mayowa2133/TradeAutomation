from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import InstrumentType, PositionSide, PositionStatus
from app.db.models.order import Order
from app.db.models.portfolio_state import PortfolioState
from app.db.models.position import Position
from app.db.models.trade import Trade


def _direction(side: PositionSide) -> float:
    return -1.0 if side == PositionSide.SHORT else 1.0


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
                margin_used=0.0,
                gross_exposure=0.0,
                net_exposure=0.0,
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

    def get_position(
        self,
        *,
        strategy_name: str,
        symbol: str,
        instrument_type: InstrumentType,
    ) -> Position | None:
        return (
            self.db.query(Position)
            .filter(
                Position.mode == self.settings.trading_mode,
                Position.strategy_name == strategy_name,
                Position.symbol == symbol,
                Position.instrument_type == instrument_type,
                Position.status == PositionStatus.OPEN,
            )
            .one_or_none()
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

    def _trade_cash_balance(self) -> float:
        cash_flow = (
            self.db.query(func.coalesce(func.sum(Trade.cash_flow), 0.0))
            .filter(Trade.mode == self.settings.trading_mode)
            .scalar()
            or 0.0
        )
        return float(self.get_or_create_state().starting_balance + cash_flow)

    def _realized_pnl(self) -> float:
        realized = (
            self.db.query(func.coalesce(func.sum(Trade.realized_pnl), 0.0))
            .filter(Trade.mode == self.settings.trading_mode)
            .scalar()
            or 0.0
        )
        return float(realized)

    def recalculate_state(self, latest_prices: dict[str, float] | None = None) -> PortfolioState:
        latest_prices = latest_prices or {}
        state = self.get_or_create_state()

        cash_balance = self._trade_cash_balance()
        open_positions = self.get_open_positions()

        equity_contribution = 0.0
        unrealized_pnl = 0.0
        margin_used = 0.0
        gross_exposure = 0.0
        net_exposure = 0.0

        for position in open_positions:
            last_price = float(latest_prices.get(position.symbol, position.current_price or position.avg_entry_price))
            direction = _direction(position.side)
            notional = position.quantity * last_price
            pnl = direction * (last_price - position.avg_entry_price) * position.quantity

            position.current_price = last_price
            position.unrealized_pnl = pnl
            unrealized_pnl += pnl
            gross_exposure += abs(notional)
            net_exposure += direction * notional

            if position.instrument_type == InstrumentType.SPOT and position.side == PositionSide.LONG:
                equity_contribution += position.quantity * last_price
            else:
                margin_used += position.collateral
                equity_contribution += position.collateral + pnl

        equity = cash_balance + equity_contribution
        state.cash_balance = float(cash_balance)
        state.realized_pnl = self._realized_pnl()
        state.unrealized_pnl = float(unrealized_pnl)
        state.margin_used = float(margin_used)
        state.gross_exposure = float(gross_exposure)
        state.net_exposure = float(net_exposure)
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
            "margin_used": state.margin_used,
            "gross_exposure": state.gross_exposure,
            "net_exposure": state.net_exposure,
        }
