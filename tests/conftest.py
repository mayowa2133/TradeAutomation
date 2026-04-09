from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

TEST_DB_PATH = Path("data/test.db")
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["REDIS_URL"] = "redis://localhost:6390/0"
os.environ["TRADING_MODE"] = "paper"
os.environ["ENABLE_LIVE_TRADING"] = "false"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["EXCHANGE_NAME"] = "kraken"

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_session_factory, init_db, reset_db_state  # noqa: E402
from app.main import app  # noqa: E402
from app.services.portfolio_service import PortfolioService  # noqa: E402
from app.services.strategy_registry import StrategyRegistry  # noqa: E402

get_settings.cache_clear()
reset_db_state()
init_db()


@pytest.fixture()
def settings():
    return get_settings()


@pytest.fixture(autouse=True)
def clean_db(settings):
    with get_session_factory()() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
        StrategyRegistry().sync_configs(db)
        PortfolioService(db=db, settings=settings).get_or_create_state()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session():
    with get_session_factory()() as db:
        yield db


@pytest.fixture()
def synthetic_market_data() -> pd.DataFrame:
    periods = 180
    index = pd.date_range("2024-01-01", periods=periods, freq="5min", tz="UTC")
    base = pd.Series(range(periods), index=index, dtype=float)
    trend = 100 + (base * 0.4)
    oscillation = ((base % 12) - 6) * 0.3
    close = trend + oscillation
    frame = pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.6,
            "low": close - 0.6,
            "close": close,
            "volume": 1000 + (base % 15) * 25,
        },
        index=index,
    )
    return frame
