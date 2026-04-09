from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import PositionStatus
from app.db.models.position import Position
from app.services.portfolio_service import PortfolioService


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    reason: str


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
            self.db.query(func.coalesce(func.sum(Position.realized_pnl), 0.0))
            .filter(
                Position.mode == self.settings.trading_mode,
                Position.status == PositionStatus.CLOSED,
                Position.closed_at.is_not(None),
                Position.closed_at >= start_of_day,
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

    def get_state(self) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        portfolio = self.portfolio_service.recalculate_state()
        daily_limit = self.settings.paper_starting_balance * self.settings.max_daily_loss_pct
        peak = portfolio.peak_equity if portfolio.peak_equity > 0 else 1.0
        drawdown = max((portfolio.peak_equity - portfolio.last_equity) / peak, 0.0)
        return {
            "kill_switch": self.settings.kill_switch,
            "live_trading_enabled": self.settings.live_trading_enabled,
            "open_positions": len(self.portfolio_service.get_open_positions()),
            "max_concurrent_positions": self.settings.max_concurrent_positions,
            "daily_realized_pnl": self._daily_realized_pnl(now),
            "daily_loss_limit": -daily_limit,
            "drawdown_pct": drawdown,
            "drawdown_limit_pct": self.settings.max_drawdown_pct,
            "blocked_symbols": self.blocked_symbols(now),
        }

    def evaluate_entry(
        self,
        *,
        symbol: str,
        quantity: float,
        price: float,
        stop_loss_pct: float,
        spread_bps: float = 0.0,
        slippage_bps: float = 0.0,
        now: datetime | None = None,
    ) -> RiskDecision:
        now = now or datetime.now(timezone.utc)
        portfolio = self.portfolio_service.recalculate_state({symbol: price})
        notional = quantity * price
        estimated_loss = notional * stop_loss_pct
        daily_realized = self._daily_realized_pnl(now)
        daily_limit = self.settings.paper_starting_balance * self.settings.max_daily_loss_pct
        peak = portfolio.peak_equity if portfolio.peak_equity > 0 else 1.0
        drawdown = max((portfolio.peak_equity - portfolio.last_equity) / peak, 0.0)

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
        if len(self.portfolio_service.get_open_positions()) >= self.settings.max_concurrent_positions:
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
        if notional > portfolio.cash_balance * self.settings.max_position_notional_pct:
            return RiskDecision(False, "Notional exceeds the configured position cap.")
        if notional > portfolio.cash_balance:
            return RiskDecision(False, "Insufficient cash for the proposed entry.")
        return RiskDecision(True, "approved")
