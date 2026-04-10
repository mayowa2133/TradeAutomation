from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    refresh_targets = [
        (symbol, timeframe)
        for symbol in settings.symbol_allowlist_list
        for timeframe in settings.default_timeframes_list
    ]
    now = datetime.now(timezone.utc)
    refresh_interval = max(settings.market_refresh_seconds, 1)
    stagger_step_seconds = max(refresh_interval // max(len(refresh_targets), 1), 1)
    for index, (symbol, timeframe) in enumerate(refresh_targets):
        scheduler.add_job(
            refresh_market_data_job,
            "interval",
            seconds=refresh_interval,
            id=f"refresh_market_data:{symbol}:{timeframe}",
            args=[symbol, timeframe, 300],
            next_run_time=now + timedelta(seconds=index * stagger_step_seconds),
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
    scheduler.add_job(
        evaluate_signals_job,
        "interval",
        seconds=settings.signal_evaluation_seconds,
        id="evaluate_signals",
        next_run_time=now + timedelta(seconds=min(max(stagger_step_seconds, 1), 5)),
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
