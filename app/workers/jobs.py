from __future__ import annotations

from app.core.config import get_settings
from app.workers.tasks import (
    evaluate_enabled_strategy,
    ingest_news,
    refresh_symbol_timeframe,
    review_with_llm,
    run_optimizer,
)


def refresh_market_data_job() -> None:
    settings = get_settings()
    for symbol in settings.symbol_allowlist_list:
        for timeframe in settings.default_timeframes_list:
            refresh_symbol_timeframe(symbol=symbol, timeframe=timeframe, limit=300)


def evaluate_signals_job() -> None:
    settings = get_settings()
    for strategy_name in ["ema_crossover", "rsi_mean_reversion", "breakout", "ml_filter"]:
        for symbol in settings.symbol_allowlist_list:
            for timeframe in settings.default_timeframes_list:
                evaluate_enabled_strategy(
                    strategy_name=strategy_name,
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=300,
                )


def refresh_news_job() -> None:
    ingest_news()


def optimizer_job() -> None:
    run_optimizer()


def llm_review_job() -> None:
    settings = get_settings()
    for symbol in settings.symbol_allowlist_list:
        review_with_llm(symbol=symbol, timeframe="5m")
