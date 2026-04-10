from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import InstrumentType, OrderSide, PositionSide, PositionStatus, TradeAction
from app.db.models.position import Position
from app.db.models.trade import Trade
from app.services.portfolio_service import PortfolioService


def _direction(side: PositionSide) -> float:
    return -1.0 if side == PositionSide.SHORT else 1.0


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


class RiskService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.portfolio_service = PortfolioService(db=db, settings=settings)

    def _in_session(self, now: datetime) -> bool:
        current = now.time()
        start = self.settings.session_start
        end = self.settings.session_end
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end

    def _daily_realized_pnl(self, now: datetime) -> float:
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            self.db.query(func.coalesce(func.sum(Trade.realized_pnl), 0.0))
            .filter(
                Trade.mode == self.settings.trading_mode,
                Trade.trade_time >= start_of_day,
            )
            .scalar()
            or 0.0
        )

    def blocked_symbols(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=self.settings.stop_loss_cooldown_minutes)
        positions = (
            self.db.query(Position)
            .filter(
                Position.mode == self.settings.trading_mode,
                Position.status == PositionStatus.CLOSED,
                Position.exit_reason == "stop_loss",
                Position.closed_at.is_not(None),
                Position.closed_at >= threshold,
            )
            .all()
        )
        return sorted({position.symbol for position in positions})

    def _side_exposure(self, positions: list[Position]) -> tuple[float, float]:
        long_exposure = 0.0
        short_exposure = 0.0
        for position in positions:
            notional = position.quantity * position.current_price
            if position.side == PositionSide.SHORT:
                short_exposure += abs(notional)
            else:
                long_exposure += abs(notional)
        return long_exposure, short_exposure

    def get_state(self) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        portfolio = self.portfolio_service.recalculate_state()
        daily_limit = self.settings.paper_starting_balance * self.settings.max_daily_loss_pct
        peak = portfolio.peak_equity if portfolio.peak_equity > 0 else 1.0
        drawdown = max((portfolio.peak_equity - portfolio.last_equity) / peak, 0.0)
        positions = self.portfolio_service.get_open_positions()
        long_exposure, short_exposure = self._side_exposure(positions)
        return {
            "kill_switch": self.settings.kill_switch,
            "live_trading_enabled": self.settings.live_trading_enabled,
            "open_positions": len(positions),
            "max_concurrent_positions": self.settings.max_concurrent_positions,
            "daily_realized_pnl": self._daily_realized_pnl(now),
            "daily_loss_limit": -daily_limit,
            "drawdown_pct": drawdown,
            "drawdown_limit_pct": self.settings.max_drawdown_pct,
            "blocked_symbols": self.blocked_symbols(now),
            "equity": portfolio.last_equity,
            "cash_balance": portfolio.cash_balance,
            "margin_used": portfolio.margin_used,
            "gross_exposure": portfolio.gross_exposure,
            "net_exposure": portfolio.net_exposure,
            "max_gross_exposure_pct": self.settings.max_gross_exposure_pct,
            "max_net_exposure_pct": self.settings.max_net_exposure_pct,
            "max_side_exposure_pct": self.settings.max_side_exposure_pct,
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
        }

    def evaluate_entry(
        self,
        *,
        symbol: str,
        quantity: float,
        price: float,
        stop_loss_pct: float,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        leverage: float = 1.0,
        position_side: PositionSide = PositionSide.LONG,
        spread_bps: float = 0.0,
        slippage_bps: float = 0.0,
        funding_rate: float | None = None,
        liquidation_price: float | None = None,
        now: datetime | None = None,
    ) -> RiskDecision:
        now = now or datetime.now(timezone.utc)
        portfolio = self.portfolio_service.recalculate_state({symbol: price})
        open_positions = self.portfolio_service.get_open_positions()
        notional = quantity * price
        estimated_loss = notional * stop_loss_pct
        daily_realized = self._daily_realized_pnl(now)
        daily_limit = self.settings.paper_starting_balance * self.settings.max_daily_loss_pct
        peak = portfolio.peak_equity if portfolio.peak_equity > 0 else 1.0
        drawdown = max((portfolio.peak_equity - portfolio.last_equity) / peak, 0.0)
        long_exposure, short_exposure = self._side_exposure(open_positions)
        direction = _direction(position_side)
        proposed_gross = portfolio.gross_exposure + abs(notional)
        proposed_net = portfolio.net_exposure + (direction * notional)

        if quantity <= 0 or price <= 0:
            return RiskDecision(False, "Quantity and price must be positive.")
        if self.settings.kill_switch:
            return RiskDecision(False, "Kill switch is active.")
        if symbol not in self.settings.symbol_allowlist_list:
            return RiskDecision(False, f"Symbol {symbol} is not in the allowlist.")
        if now.weekday() not in self.settings.allowed_weekdays_list:
            return RiskDecision(False, "Trading weekday filter blocked the entry.")
        if not self._in_session(now):
            return RiskDecision(False, "Trading session filter blocked the entry.")
        if spread_bps > self.settings.max_spread_bps:
            return RiskDecision(False, "Spread sanity check failed.")
        if slippage_bps > self.settings.max_slippage_bps:
            return RiskDecision(False, "Slippage sanity check failed.")
        if len(open_positions) >= self.settings.max_concurrent_positions:
            return RiskDecision(False, "Maximum concurrent positions reached.")
        if daily_realized <= -daily_limit:
            return RiskDecision(False, "Daily loss limit breached.")
        if drawdown >= self.settings.max_drawdown_pct:
            return RiskDecision(False, "Drawdown circuit breaker is active.")
        if symbol in self.blocked_symbols(now):
            return RiskDecision(False, f"Symbol {symbol} is in stop-loss cooldown.")
        if portfolio.last_equity <= 0:
            return RiskDecision(False, "Account equity is non-positive.")
        if estimated_loss > portfolio.last_equity * self.settings.max_risk_per_trade:
            return RiskDecision(False, "Estimated trade risk exceeds the per-trade budget.")
        if leverage > self.settings.max_leverage:
            return RiskDecision(False, "Requested leverage exceeds the configured maximum leverage.")
        if instrument_type == InstrumentType.SPOT and position_side == PositionSide.SHORT:
            return RiskDecision(False, "Short entries are only supported for perpetual instruments.")

        if instrument_type == InstrumentType.SPOT:
            if notional > portfolio.cash_balance * self.settings.max_position_notional_pct:
                return RiskDecision(False, "Spot notional exceeds the configured position cap.")
            if notional > portfolio.cash_balance:
                return RiskDecision(False, "Insufficient cash for the proposed spot entry.")
        else:
            collateral_required = notional / max(leverage, 1.0)
            if collateral_required > portfolio.cash_balance:
                return RiskDecision(False, "Insufficient collateral for the proposed perpetual entry.")
            if funding_rate is not None and abs(funding_rate) > self.settings.max_abs_funding_rate:
                return RiskDecision(False, "Funding-rate sanity guard blocked the entry.")
            if liquidation_price is not None:
                liquidation_distance = abs(price - liquidation_price) / price
                if liquidation_distance < self.settings.min_liquidation_buffer_pct:
                    return RiskDecision(False, "Liquidation distance is below the configured safety buffer.")

        if proposed_gross / portfolio.last_equity > self.settings.max_gross_exposure_pct:
            return RiskDecision(False, "Gross exposure cap would be breached.")
        if abs(proposed_net) / portfolio.last_equity > self.settings.max_net_exposure_pct:
            return RiskDecision(False, "Net exposure cap would be breached.")

        proposed_side_exposure = (
            short_exposure + abs(notional) if position_side == PositionSide.SHORT else long_exposure + abs(notional)
        )
        if proposed_side_exposure / portfolio.last_equity > self.settings.max_side_exposure_pct:
            return RiskDecision(False, "Per-side concentration cap would be breached.")

        return RiskDecision(
            True,
            "approved",
            details={
                "notional": notional,
                "estimated_loss": estimated_loss,
                "proposed_gross": proposed_gross,
                "proposed_net": proposed_net,
            },
        )

    def record_funding_charge(
        self,
        *,
        position: Position,
        funding_cost: float,
        note: str = "funding",
    ) -> Trade:
        if not position.trades:
            raise ValueError("Cannot record funding without a position trade history.")
        position.funding_cost += funding_cost
        self.db.add(position)
        trade = Trade(
            order_id=position.trades[-1].order_id,
            position_id=position.id,
            strategy_name=position.strategy_name,
            symbol=position.symbol,
            instrument_type=position.instrument_type,
            margin_mode=position.margin_mode,
            position_side=position.side,
            source=position.trades[-1].source,
            side=OrderSide.SELL if position.side == PositionSide.SHORT else OrderSide.BUY,
            action=TradeAction.FUNDING,
            mode=position.mode,
            leverage=position.leverage,
            price=position.current_price,
            quantity=position.quantity,
            notional=position.current_price * position.quantity,
            fee_paid=0.0,
            funding_cost=funding_cost,
            realized_pnl=-funding_cost,
            cash_flow=-funding_cost,
            notes=note,
        )
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)
        return trade
