from __future__ import annotations

from app.core.config import get_settings
from app.core.enums import InstrumentType, PositionStatus
from app.core.exceptions import RiskCheckFailed
from app.core.logging import get_logger
from app.db.models.position import Position
from app.db.session import get_session_factory, init_db
from app.services.data_service import DataService
from app.services.decision_engine import DecisionEngineService
from app.services.execution_service import ExecutionService
from app.services.news_service import NewsService
from app.services.optimizer_service import OptimizerService
from app.services.strategy_registry import StrategyRegistry

logger = get_logger(__name__)


def _parse_strategy_instance_name(strategy_instance_name: str) -> tuple[str, str]:
    if "@" not in strategy_instance_name:
        return strategy_instance_name, "15m"
    strategy_name, timeframe = strategy_instance_name.rsplit("@", 1)
    return strategy_name, timeframe


def rank_entry_candidates(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    def sort_key(candidate: dict[str, object]) -> tuple[float, str, str, str]:
        confidence = float(candidate.get("confidence") or 0.0)
        return (-confidence, str(candidate.get("symbol") or ""), str(candidate.get("timeframe") or ""), str(candidate.get("strategy_name") or ""))

    return sorted(candidates, key=sort_key)


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


def evaluate_signals_with_ranking() -> None:
    settings = get_settings()
    init_db()
    instrument_type = InstrumentType.PERPETUAL if settings.enable_derivatives else InstrumentType.SPOT
    with get_session_factory()() as db:
        registry = StrategyRegistry()
        registry.sync_configs(db)
        service = ExecutionService(db=db, settings=settings, registry=registry)
        open_positions = (
            db.query(Position)
            .filter(
                Position.mode == settings.trading_mode,
                Position.status == PositionStatus.OPEN,
            )
            .order_by(Position.opened_at.asc())
            .all()
        )

        open_position_keys = {
            (position.strategy_name, position.symbol, position.instrument_type) for position in open_positions
        }

        for position in open_positions:
            strategy_name, timeframe = _parse_strategy_instance_name(position.strategy_name)
            if strategy_name not in registry.names():
                continue
            try:
                result = service.evaluate_strategy(
                    strategy_name=strategy_name,
                    symbol=position.symbol,
                    timeframe=timeframe,
                    limit=300,
                    instrument_type=position.instrument_type,
                )
            except RiskCheckFailed as exc:
                logger.warning(
                    "Open-position evaluation blocked by risk controls",
                    extra={
                        "event_type": "strategy_eval_blocked",
                        "strategy_name": strategy_name,
                        "symbol": position.symbol,
                        "timeframe": timeframe,
                        "instrument_type": position.instrument_type.value,
                        "mode": settings.trading_mode.value,
                        "reason": str(exc),
                    },
                )
                continue
            logger.info(
                "Evaluated strategy",
                extra={
                    "event_type": "strategy_eval",
                    "strategy_name": strategy_name,
                    "symbol": position.symbol,
                    "instrument_type": position.instrument_type.value,
                    "mode": settings.trading_mode.value,
                    "evaluation": result.get("action"),
                },
            )

        current_open_positions = service.portfolio_service.get_open_positions()
        free_slots = max(settings.max_concurrent_positions - len(current_open_positions), 0)
        if free_slots <= 0:
            return

        candidates: list[dict[str, object]] = []
        for strategy_name in registry.names():
            config = registry.get_db_config(db, strategy_name)
            if not config.enabled:
                continue
            for symbol in settings.symbol_allowlist_list:
                for timeframe in settings.default_timeframes_list:
                    if (f"{strategy_name}@{timeframe}", symbol, instrument_type) in open_position_keys:
                        continue
                    candidate = service.preview_strategy_candidate(
                        strategy_name=strategy_name,
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=300,
                        instrument_type=instrument_type,
                    )
                    if candidate.get("action") == "entry":
                        candidates.append(candidate)

        for candidate in rank_entry_candidates(candidates)[:free_slots]:
            strategy_name = str(candidate["strategy_name"])
            symbol = str(candidate["symbol"])
            timeframe = str(candidate["timeframe"])
            try:
                result = service.evaluate_strategy(
                    strategy_name=strategy_name,
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=300,
                    instrument_type=instrument_type,
                )
            except RiskCheckFailed as exc:
                logger.warning(
                    "Ranked entry blocked by risk controls",
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
                continue
            logger.info(
                "Ranked strategy candidate executed",
                extra={
                    "event_type": "strategy_eval",
                    "strategy_name": strategy_name,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "instrument_type": instrument_type.value,
                    "mode": settings.trading_mode.value,
                    "confidence": candidate.get("confidence", 0.0),
                    "evaluation": result.get("action"),
                },
            )


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
