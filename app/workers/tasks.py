from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory, init_db
from app.services.data_service import DataService
from app.services.execution_service import ExecutionService
from app.services.strategy_registry import StrategyRegistry

logger = get_logger(__name__)


def refresh_symbol_timeframe(symbol: str, timeframe: str, limit: int = 300) -> None:
    settings = get_settings()
    init_db()
    with get_session_factory()() as db:
        DataService(db=db, settings=settings).get_historical_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        logger.info(
            "Refreshed market data",
            extra={"event_type": "market_data_refresh", "symbol": symbol},
        )


def evaluate_enabled_strategy(strategy_name: str, symbol: str, timeframe: str, limit: int = 300) -> None:
    settings = get_settings()
    init_db()
    with get_session_factory()() as db:
        registry = StrategyRegistry()
        config = registry.get_db_config(db, strategy_name)
        if not config.enabled:
            return
        result = ExecutionService(db=db, settings=settings, registry=registry).evaluate_strategy(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        logger.info(
            "Evaluated strategy",
            extra={
                "event_type": "strategy_eval",
                "strategy_name": strategy_name,
                "symbol": symbol,
                "mode": settings.trading_mode.value,
            },
        )
        logger.debug("Strategy result: %s", result)
