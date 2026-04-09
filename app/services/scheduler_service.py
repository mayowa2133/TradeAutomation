from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import Settings
from app.workers.jobs import evaluate_signals_job, refresh_market_data_job


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
    return scheduler
