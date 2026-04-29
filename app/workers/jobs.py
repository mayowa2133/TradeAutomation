from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory, init_db
from app.services.helpers import record_event
from app.workers.tasks import (
    evaluate_signals_with_ranking,
    ingest_news,
    refresh_symbol_timeframe,
    review_with_llm,
    run_optimizer,
)

logger = get_logger(__name__)


def _record_worker_event(
    *,
    event_type: str,
    level: str,
    job_name: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        init_db()
        with get_session_factory()() as db:
            record_event(
                db,
                level,
                event_type,
                message,
                {"job_name": job_name, **(payload or {})},
            )
            db.commit()
    except Exception:
        logger.warning("Unable to persist worker event.", extra={"event_type": "worker_event_persist_failed"})


def _run_worker_job(job_name: str, callback: Callable[..., None], *args: Any, **kwargs: Any) -> None:
    try:
        callback(*args, **kwargs)
    except Exception as exc:
        _record_worker_event(
            event_type="worker_job_error",
            level="ERROR",
            job_name=job_name,
            message=f"{job_name} failed: {exc}",
            payload={
                "exception_type": exc.__class__.__name__,
                "error": str(exc),
                "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:],
            },
        )
        raise
    _record_worker_event(
        event_type="worker_job_success",
        level="INFO",
        job_name=job_name,
        message=f"{job_name} completed successfully.",
    )


def refresh_market_data_job(symbol: str, timeframe: str, limit: int = 300) -> None:
    _run_worker_job(
        "refresh_market_data",
        refresh_symbol_timeframe,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


def evaluate_signals_job() -> None:
    _run_worker_job("evaluate_signals", evaluate_signals_with_ranking)


def refresh_news_job() -> None:
    _run_worker_job("refresh_news", ingest_news)


def optimizer_job() -> None:
    _run_worker_job("run_optimizer", run_optimizer)


def llm_review_job() -> None:
    settings = get_settings()
    for symbol in settings.symbol_allowlist_list:
        _run_worker_job("llm_review", review_with_llm, symbol=symbol, timeframe="5m")
