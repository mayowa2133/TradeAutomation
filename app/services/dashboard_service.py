from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import PositionStatus, TradeAction
from app.db.models.event_log import EventLog
from app.db.models.llm_decision import LLMDecision
from app.db.models.news_article import NewsArticle
from app.db.models.position import Position
from app.services.market_depth_service import MarketDepthService
from app.services.optimizer_service import OptimizerService
from app.services.portfolio_service import PortfolioService
from app.services.risk_service import RiskService
from app.services.strategy_registry import StrategyRegistry


class DashboardService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.portfolio_service = PortfolioService(db=db, settings=settings)
        self.risk_service = RiskService(db=db, settings=settings)
        self.market_depth_service = MarketDepthService(db=db)
        self.optimizer_service = OptimizerService(db=db, settings=settings)
        self.registry = StrategyRegistry()

    def _as_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _isoformat(self, value: datetime | None) -> str | None:
        normalized = self._as_utc(value)
        return normalized.isoformat() if normalized else None

    def _worker_status(self) -> dict:
        job_event_types = ("worker_job_success", "worker_job_error", "worker_started", "worker_stopped")
        latest_success = (
            self.db.query(EventLog)
            .filter(EventLog.event_type == "worker_job_success")
            .order_by(desc(EventLog.created_at))
            .first()
        )
        latest_error = (
            self.db.query(EventLog)
            .filter(EventLog.event_type == "worker_job_error")
            .order_by(desc(EventLog.created_at))
            .first()
        )
        latest_event = (
            self.db.query(EventLog)
            .filter(EventLog.event_type.in_(job_event_types))
            .order_by(desc(EventLog.created_at))
            .first()
        )
        recent_errors = (
            self.db.query(EventLog)
            .filter(EventLog.event_type == "worker_job_error")
            .order_by(desc(EventLog.created_at))
            .limit(5)
            .all()
        )
        now = datetime.now(timezone.utc)
        stale_after_seconds = max(
            self.settings.signal_evaluation_seconds * 3,
            self.settings.market_refresh_seconds * 2,
            180,
        )
        latest_success_at = self._as_utc(latest_success.created_at if latest_success else None)
        latest_error_at = self._as_utc(latest_error.created_at if latest_error else None)
        if latest_error_at and (latest_success_at is None or latest_error_at > latest_success_at):
            status = "error"
        elif latest_success_at is None:
            status = "unknown"
        elif (now - latest_success_at).total_seconds() > stale_after_seconds:
            status = "stale"
        else:
            status = "healthy"

        return {
            "status": status,
            "last_success_at": self._isoformat(latest_success_at),
            "last_error_at": self._isoformat(latest_error_at),
            "last_event_type": latest_event.event_type if latest_event else None,
            "last_event_message": latest_event.message if latest_event else None,
            "stale_after_seconds": stale_after_seconds,
            "recent_errors": [
                {
                    "job_name": error.payload.get("job_name") if error.payload else None,
                    "message": error.message,
                    "error": error.payload.get("error") if error.payload else None,
                    "created_at": self._isoformat(error.created_at),
                }
                for error in recent_errors
            ],
        }

    def _position_attribution(self) -> list[dict]:
        positions = (
            self.db.query(Position)
            .filter(Position.mode == self.settings.trading_mode)
            .order_by(desc(Position.opened_at))
            .limit(20)
            .all()
        )
        rows: list[dict] = []
        for position in positions:
            entry_trades = [trade for trade in position.trades if trade.action == TradeAction.ENTRY]
            exit_trades = [trade for trade in position.trades if trade.action == TradeAction.EXIT]
            entry_fees = sum(trade.fee_paid for trade in entry_trades)
            exit_fees = sum(trade.fee_paid for trade in exit_trades)
            entry_notional = sum(trade.notional for trade in entry_trades) or position.entry_notional
            entry_quantity = sum(abs(trade.quantity) for trade in entry_trades)
            exit_quantity = sum(abs(trade.quantity) for trade in exit_trades)
            exit_notional = sum(trade.notional for trade in exit_trades)
            realized_pnl = sum(trade.realized_pnl for trade in exit_trades)
            net_pnl = realized_pnl + position.unrealized_pnl
            display_quantity = position.quantity
            if position.status == PositionStatus.CLOSED:
                display_quantity = entry_quantity or exit_quantity or position.quantity
            opened_at = self._as_utc(position.opened_at)
            closed_at = self._as_utc(position.closed_at)
            hold_seconds = (
                (closed_at or datetime.now(timezone.utc)) - opened_at
            ).total_seconds() if opened_at else None
            rows.append(
                {
                    "position_id": position.id,
                    "strategy_name": position.strategy_name,
                    "symbol": position.symbol,
                    "side": position.side.value,
                    "status": position.status.value,
                    "opened_at": self._isoformat(opened_at),
                    "closed_at": self._isoformat(closed_at),
                    "hold_seconds": hold_seconds,
                    "entry_notional": entry_notional,
                    "exit_notional": exit_notional,
                    "quantity": display_quantity,
                    "entry_quantity": entry_quantity,
                    "exit_quantity": exit_quantity,
                    "current_quantity": position.quantity,
                    "realized_pnl": realized_pnl,
                    "unrealized_pnl": position.unrealized_pnl,
                    "net_pnl": net_pnl,
                    "total_fees": entry_fees + exit_fees,
                    "funding_cost": position.funding_cost,
                    "exit_reason": position.exit_reason,
                    "win": net_pnl > 0 if position.status == PositionStatus.CLOSED else None,
                }
            )
        return rows

    def summary(self) -> dict:
        pnl = self.portfolio_service.pnl_summary()
        latest_optimizer = self.optimizer_service.latest_run()
        recent_news = self.db.query(NewsArticle).order_by(NewsArticle.ingested_at.desc()).limit(5).all()
        recent_decisions = self.db.query(LLMDecision).order_by(LLMDecision.created_at.desc()).limit(5).all()
        recent_events = (
            self.db.query(EventLog)
            .filter(EventLog.event_type != "worker_job_success")
            .order_by(EventLog.created_at.desc())
            .limit(10)
            .all()
        )
        return {
            "portfolio": pnl,
            "risk": self.risk_service.get_state(),
            "strategies": self.registry.list_strategies(self.db),
            "worker_status": self._worker_status(),
            "position_attribution": self._position_attribution(),
            "stream_status": [
                {
                    "stream_name": item["stream_name"],
                    "symbol": item["symbol"],
                    "status": item["status"],
                    "last_message_at": item["last_message_at"].isoformat() if item["last_message_at"] else None,
                    "error_message": item["error_message"],
                }
                for item in self.market_depth_service.stream_status_payloads(
                    stale_after_seconds=self.settings.stream_stale_after_seconds,
                    symbols=set(self.settings.symbol_allowlist_list),
                )
            ],
            "optimizer": latest_optimizer.allocations if latest_optimizer else None,
            "news": [
                {
                    "title": article.title,
                    "source": article.source,
                    "published_at": article.published_at.isoformat() if article.published_at else None,
                    "symbols": article.symbols,
                }
                for article in recent_news
            ],
            "llm_decisions": [
                {
                    "symbol": decision.symbol,
                    "accepted": decision.accepted,
                    "confidence": decision.confidence,
                    "reason": decision.reason,
                    "created_at": decision.created_at.isoformat(),
                }
                for decision in recent_decisions
            ],
            "recent_events": [
                {
                    "event_type": event.event_type,
                    "message": event.message,
                    "created_at": event.created_at.isoformat(),
                }
                for event in recent_events
            ],
        }
