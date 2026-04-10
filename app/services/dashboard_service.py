from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.event_log import EventLog
from app.db.models.llm_decision import LLMDecision
from app.db.models.news_article import NewsArticle
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

    def summary(self) -> dict:
        pnl = self.portfolio_service.pnl_summary()
        latest_optimizer = self.optimizer_service.latest_run()
        recent_news = self.db.query(NewsArticle).order_by(NewsArticle.ingested_at.desc()).limit(5).all()
        recent_decisions = self.db.query(LLMDecision).order_by(LLMDecision.created_at.desc()).limit(5).all()
        recent_events = self.db.query(EventLog).order_by(EventLog.created_at.desc()).limit(10).all()
        return {
            "portfolio": pnl,
            "risk": self.risk_service.get_state(),
            "strategies": self.registry.list_strategies(self.db),
            "stream_status": [
                {
                    "stream_name": item.stream_name,
                    "symbol": item.symbol,
                    "status": item.status.value,
                    "last_message_at": item.last_message_at.isoformat() if item.last_message_at else None,
                    "error_message": item.error_message,
                }
                for item in self.market_depth_service.list_stream_status()
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
