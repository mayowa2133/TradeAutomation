from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import Settings
from app.workers.jobs import (
    evaluate_signals_job,
    llm_review_job,
    optimizer_job,
    refresh_market_data_job,
    refresh_news_job,
)


def create_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        refresh_market_data_job,
        "interval",
        seconds=settings.market_refresh_seconds,
        id="refresh_market_data",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    scheduler.add_job(
        evaluate_signals_job,
        "interval",
        seconds=settings.signal_evaluation_seconds,
        id="evaluate_signals",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    if settings.news_ingestion_enabled:
        scheduler.add_job(
            refresh_news_job,
            "interval",
            seconds=settings.news_refresh_seconds,
            id="refresh_news",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
    if settings.optimizer_enabled:
        scheduler.add_job(
            optimizer_job,
            "interval",
            seconds=settings.optimizer_refresh_seconds,
            id="run_optimizer",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
    if settings.llm_autonomy_paper:
        scheduler.add_job(
            llm_review_job,
            "interval",
            seconds=max(settings.signal_evaluation_seconds, 120),
            id="llm_review",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
    return scheduler
