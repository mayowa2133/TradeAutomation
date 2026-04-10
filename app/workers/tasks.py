from __future__ import annotations

from app.core.config import get_settings
from app.core.enums import InstrumentType
from app.core.exceptions import RiskCheckFailed
from app.core.logging import get_logger
from app.db.session import get_session_factory, init_db
from app.services.data_service import DataService
from app.services.decision_engine import DecisionEngineService
from app.services.execution_service import ExecutionService
from app.services.news_service import NewsService
from app.services.optimizer_service import OptimizerService
from app.services.strategy_registry import StrategyRegistry

logger = get_logger(__name__)


def refresh_symbol_timeframe(symbol: str, timeframe: str, limit: int = 300) -> None:
    settings = get_settings()
    init_db()
    instrument_type = InstrumentType.PERPETUAL if settings.enable_derivatives else InstrumentType.SPOT
    with get_session_factory()() as db:
        DataService(db=db, settings=settings).get_historical_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            instrument_type=instrument_type,
            refresh=True,
        )
        logger.info(
            "Refreshed market data",
            extra={
                "event_type": "market_data_refresh",
                "symbol": symbol,
                "instrument_type": instrument_type.value,
            },
        )


def evaluate_enabled_strategy(strategy_name: str, symbol: str, timeframe: str, limit: int = 300) -> None:
    settings = get_settings()
    init_db()
    instrument_type = InstrumentType.PERPETUAL if settings.enable_derivatives else InstrumentType.SPOT
    with get_session_factory()() as db:
        registry = StrategyRegistry()
        config = registry.get_db_config(db, strategy_name)
        if not config.enabled:
            return
        try:
            result = ExecutionService(db=db, settings=settings, registry=registry).evaluate_strategy(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                instrument_type=instrument_type,
            )
        except RiskCheckFailed as exc:
            logger.warning(
                "Strategy evaluation blocked by risk controls",
                extra={
                    "event_type": "strategy_eval_blocked",
                    "strategy_name": strategy_name,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "instrument_type": instrument_type.value,
                    "mode": settings.trading_mode.value,
                    "reason": str(exc),
                },
            )
            return
        logger.info(
            "Evaluated strategy",
            extra={
                "event_type": "strategy_eval",
                "strategy_name": strategy_name,
                "symbol": symbol,
                "instrument_type": instrument_type.value,
                "mode": settings.trading_mode.value,
            },
        )
        logger.debug("Strategy result: %s", result)


def ingest_news() -> None:
    settings = get_settings()
    init_db()
    if not settings.news_ingestion_enabled:
        return
    with get_session_factory()() as db:
        count = len(NewsService(db=db, settings=settings).ingest())
        logger.info("Ingested news", extra={"event_type": "news_ingest", "count": count})


def run_optimizer() -> None:
    settings = get_settings()
    init_db()
    if not settings.optimizer_enabled:
        return
    with get_session_factory()() as db:
        run = OptimizerService(db=db, settings=settings).run_optimizer(settings.symbol_allowlist_list)
        logger.info(
            "Optimizer run completed",
            extra={"event_type": "optimizer_run", "optimizer_run_id": run.id},
        )


def review_with_llm(symbol: str, timeframe: str = "5m") -> None:
    settings = get_settings()
    init_db()
    if not settings.llm_autonomy_paper:
        return
    with get_session_factory()() as db:
        decision = DecisionEngineService(db=db, settings=settings).maybe_execute_paper_decision(
            symbol=symbol,
            timeframe=timeframe,
        )
        logger.info(
            "LLM review completed",
            extra={
                "event_type": "llm_review",
                "symbol": symbol,
                "accepted": decision.accepted,
            },
        )
