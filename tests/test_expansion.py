from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.core.enums import InstrumentType, MarginMode, OrderStatus, PositionSide, PositionStatus
from app.db.models.instrument import Instrument
from app.db.models.position import Position
from app.db.models.trade import Trade
from app.schemas.backtest import BacktestResponse
from app.services.backtest_service import BacktestService
from app.services.data_service import DataService
from app.services.instrument_service import InstrumentService
from app.services.market_depth_service import MarketDepthService
from app.services.news_service import NewsItem, NewsService
from app.services.optimizer_service import OptimizerService
from app.services.execution_service import ExecutionService
from app.services.risk_service import RiskService
from app.services.strategy_registry import StrategyRegistry
from app.core.exceptions import RiskCheckFailed
from app.workers.tasks import evaluate_enabled_strategy


def seed_perpetual_instrument(db_session) -> Instrument:
    instrument = Instrument(
        exchange="bybit",
        symbol="BTC/USDT",
        exchange_symbol="BTC/USDT:USDT",
        instrument_type=InstrumentType.PERPETUAL,
        margin_mode=MarginMode.ISOLATED,
        base_asset="BTC",
        quote_asset="USDT",
        settle_asset="USDT",
        contract_size=1.0,
        tick_size=0.5,
        lot_size=0.001,
        min_notional=10.0,
        max_leverage=10.0,
        maintenance_margin_rate=0.005,
        active=True,
        raw={"id": "BTCUSDT"},
    )
    db_session.add(instrument)
    db_session.commit()
    db_session.refresh(instrument)
    return instrument


def test_precision_rounding_and_min_notional(db_session, settings):
    seed_perpetual_instrument(db_session)
    service = InstrumentService(db=db_session, settings=settings)
    normalized = service.normalize_order(
        symbol="BTC/USDT",
        instrument_type=InstrumentType.PERPETUAL,
        quantity=0.1049,
        limit_price=100.74,
        reference_price=100.74,
        leverage=7.0,
    )
    assert normalized.quantity == 0.104
    assert normalized.limit_price == 100.5
    assert normalized.leverage == 5.0


def test_derivatives_liquidation_buffer_guard(db_session, settings):
    service = RiskService(db=db_session, settings=settings)
    decision = service.evaluate_entry(
        symbol="BTC/USDT",
        quantity=0.5,
        price=100.0,
        stop_loss_pct=0.01,
        instrument_type=InstrumentType.PERPETUAL,
        leverage=5.0,
        position_side=PositionSide.LONG,
        liquidation_price=99.0,
    )
    assert decision.allowed is False
    assert "Liquidation distance" in decision.reason


def test_perpetual_short_paper_trade_updates_positions(db_session, settings):
    seed_perpetual_instrument(db_session)
    service = ExecutionService(db=db_session, settings=settings, registry=StrategyRegistry())
    order = service.manual_order(
        symbol="BTC/USDT",
        instrument_type=InstrumentType.PERPETUAL,
        position_side=PositionSide.SHORT,
        quantity=0.2,
        reference_price=100.0,
        leverage=2.0,
    )
    assert order.status == OrderStatus.FILLED
    position = service.portfolio_service.get_open_positions()[0]
    assert position.side == PositionSide.SHORT
    assert position.collateral > 0


def test_strategy_instances_are_isolated_by_timeframe(db_session, settings):
    seed_perpetual_instrument(db_session)
    service = ExecutionService(db=db_session, settings=settings, registry=StrategyRegistry())

    first = service.submit_entry_order(
        strategy_name="ema_crossover",
        strategy_instance_name="ema_crossover@1m",
        symbol="BTC/USDT",
        reference_price=100.0,
        instrument_type=InstrumentType.PERPETUAL,
        margin_mode=MarginMode.ISOLATED,
        leverage=2.0,
        position_side=PositionSide.LONG,
        quantity=0.2,
    )
    second = service.submit_entry_order(
        strategy_name="ema_crossover",
        strategy_instance_name="ema_crossover@5m",
        symbol="BTC/USDT",
        reference_price=101.0,
        instrument_type=InstrumentType.PERPETUAL,
        margin_mode=MarginMode.ISOLATED,
        leverage=2.0,
        position_side=PositionSide.LONG,
        quantity=0.2,
    )

    positions = service.portfolio_service.get_open_positions()
    assert first.status == OrderStatus.FILLED
    assert second.status == OrderStatus.FILLED
    assert len(positions) == 2
    assert {position.strategy_name for position in positions} == {"ema_crossover@1m", "ema_crossover@5m"}


def test_strategy_evaluation_only_acts_once_per_bar(db_session, settings):
    seed_perpetual_instrument(db_session)
    registry = StrategyRegistry()
    config = registry.get_db_config(db_session, "breakout")
    config.parameters = {
        "lookback": 3,
        "exit_lookback": 2,
        "buffer_pct": 0.0,
        "stop_loss_pct": 0.01,
        "take_profit_pct": 0.015,
    }
    db_session.add(config)
    db_session.commit()

    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=5, freq="1min")
    frame = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 106.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 105.5],
            "volume": [10.0, 10.0, 10.0, 10.0, 10.0],
        },
        index=timestamps,
    )
    DataService(db=db_session, settings=settings).store_synthetic_data(
        "BTC/USDT",
        "1m",
        frame,
        instrument_type=InstrumentType.PERPETUAL,
    )

    service = ExecutionService(db=db_session, settings=settings, registry=registry)
    first = service.evaluate_strategy(
        strategy_name="breakout",
        symbol="BTC/USDT",
        timeframe="1m",
        limit=5,
        instrument_type=InstrumentType.PERPETUAL,
    )
    second = service.evaluate_strategy(
        strategy_name="breakout",
        symbol="BTC/USDT",
        timeframe="1m",
        limit=5,
        instrument_type=InstrumentType.PERPETUAL,
    )

    assert first["action"] == "entry"
    assert second["reason"] == "bar_already_processed"
    assert len(service.portfolio_service.get_open_positions()) == 1
    assert db_session.query(Trade).count() == 1


def test_strategy_evaluation_waits_for_bar_close(db_session, settings):
    seed_perpetual_instrument(db_session)
    registry = StrategyRegistry()
    config = registry.get_db_config(db_session, "breakout")
    config.parameters = {
        "lookback": 3,
        "exit_lookback": 2,
        "buffer_pct": 0.0,
        "stop_loss_pct": 0.01,
        "take_profit_pct": 0.015,
    }
    db_session.add(config)
    db_session.commit()

    timestamps = pd.date_range("2024-01-01T00:01:00Z", periods=5, freq="1min")
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 100.0, 100.0, 100.0, 106.0],
            "low": [99.5, 99.5, 99.5, 99.5, 99.5],
            "close": [100.0, 100.0, 100.0, 100.0, 105.0],
            "volume": [10.0, 10.0, 10.0, 10.0, 10.0],
        },
        index=timestamps,
    )
    DataService(db=db_session, settings=settings).store_synthetic_data(
        "BTC/USDT",
        "1m",
        frame,
        instrument_type=InstrumentType.PERPETUAL,
    )

    service = ExecutionService(db=db_session, settings=settings, registry=registry)
    before_close = service.evaluate_strategy(
        strategy_name="breakout",
        symbol="BTC/USDT",
        timeframe="1m",
        limit=5,
        instrument_type=InstrumentType.PERPETUAL,
        now=datetime(2024, 1, 1, 0, 5, 30, tzinfo=timezone.utc),
    )
    assert before_close["action"] == "flat"
    assert db_session.query(Trade).count() == 0

    after_close = service.evaluate_strategy(
        strategy_name="breakout",
        symbol="BTC/USDT",
        timeframe="1m",
        limit=5,
        instrument_type=InstrumentType.PERPETUAL,
        now=datetime(2024, 1, 1, 0, 6, 1, tzinfo=timezone.utc),
    )

    assert after_close["action"] == "entry"


def test_strategy_exit_cooldown_blocks_reentry(db_session, settings):
    seed_perpetual_instrument(db_session)
    registry = StrategyRegistry()
    config = registry.get_db_config(db_session, "breakout")
    config.parameters = {
        "lookback": 3,
        "exit_lookback": 2,
        "buffer_pct": 0.0,
        "stop_loss_pct": 0.01,
        "take_profit_pct": 0.015,
    }
    db_session.add(config)
    db_session.commit()

    timestamps = pd.date_range("2024-01-01T00:01:00Z", periods=5, freq="1min")
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 100.0, 100.0, 100.0, 106.0],
            "low": [99.5, 99.5, 99.5, 99.5, 99.5],
            "close": [100.0, 100.0, 100.0, 100.0, 105.0],
            "volume": [10.0, 10.0, 10.0, 10.0, 10.0],
        },
        index=timestamps,
    )
    DataService(db=db_session, settings=settings).store_synthetic_data(
        "BTC/USDT",
        "1m",
        frame,
        instrument_type=InstrumentType.PERPETUAL,
    )

    db_session.add(
        Position(
            strategy_name="breakout@1m",
            symbol="BTC/USDT",
            instrument_type=InstrumentType.PERPETUAL,
            margin_mode=MarginMode.ISOLATED,
            side=PositionSide.LONG,
            mode=settings.trading_mode,
            status=PositionStatus.CLOSED,
            quantity=0.5,
            leverage=2.0,
            avg_entry_price=100.0,
            current_price=100.0,
            entry_notional=50.0,
            collateral=25.0,
            unrealized_pnl=0.0,
            realized_pnl=-5.0,
            stop_loss_price=99.0,
            take_profit_price=101.0,
            liquidation_price=50.0,
            maintenance_margin_rate=0.005,
            funding_cost=0.0,
            exit_reason="strategy_exit",
            opened_at=datetime(2024, 1, 1, 0, 4, 0, tzinfo=timezone.utc),
            closed_at=datetime(2024, 1, 1, 0, 5, 30, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    service = ExecutionService(db=db_session, settings=settings, registry=registry)
    result = service.evaluate_strategy(
        strategy_name="breakout",
        symbol="BTC/USDT",
        timeframe="1m",
        limit=5,
        instrument_type=InstrumentType.PERPETUAL,
        now=datetime(2024, 1, 1, 0, 6, 1, tzinfo=timezone.utc),
    )

    assert result["action"] == "flat"
    assert result["reason"] == "strategy_cooldown_active"


def test_worker_risk_rejections_do_not_fail_scheduler(db_session, monkeypatch):
    class RaisingExecutionService:
        def __init__(self, *args, **kwargs):
            pass

        def evaluate_strategy(self, **kwargs):
            raise RiskCheckFailed("Daily loss limit breached.")

    monkeypatch.setattr("app.workers.tasks.ExecutionService", RaisingExecutionService)

    evaluate_enabled_strategy(
        strategy_name="breakout",
        symbol="BTC/USDT",
        timeframe="1m",
        limit=5,
    )


def test_optimizer_outputs_target_notionals(db_session, settings, synthetic_market_data):
    data = synthetic_market_data.copy()
    from app.services.data_service import DataService

    data_service = DataService(db=db_session, settings=settings)
    data_service.store_synthetic_data("BTC/USDT", "5m", data)
    data_service.store_synthetic_data("ETH/USDT", "5m", data * [1, 1, 1, 1.01, 1])
    optimizer = OptimizerService(db=db_session, settings=settings, data_service=data_service)
    run = optimizer.run_optimizer(["BTC/USDT", "ETH/USDT"])
    weights = run.allocations["weights"]
    assert 0.0 < sum(weights.values()) <= 1.01
    assert "target_notional" in run.allocations


def test_refresh_historical_data_bypasses_stale_db(db_session, settings):
    data_service = DataService(db=db_session, settings=settings)
    stale_index = pd.date_range("2024-01-01T00:00:00Z", periods=5, freq="1min")
    stale_frame = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [10.0] * 5,
        },
        index=stale_index,
    )
    data_service.store_synthetic_data("BTC/USDT", "1m", stale_frame)

    fresh_index = pd.date_range("2024-01-01T00:05:00Z", periods=5, freq="1min")
    fresh_frame = pd.DataFrame(
        {
            "open": [105.0, 106.0, 107.0, 108.0, 109.0],
            "high": [106.0, 107.0, 108.0, 109.0, 110.0],
            "low": [104.0, 105.0, 106.0, 107.0, 108.0],
            "close": [105.5, 106.5, 107.5, 108.5, 109.5],
            "volume": [12.0] * 5,
        },
        index=fresh_index,
    )

    def fake_fetch_from_exchange(*args, **kwargs):
        data_service.persist_ohlcv(
            symbol="BTC/USDT",
            timeframe="1m",
            frame=fresh_frame,
            instrument_type=InstrumentType.SPOT,
        )
        return fresh_frame

    data_service.fetch_from_exchange = fake_fetch_from_exchange  # type: ignore[method-assign]

    refreshed = data_service.get_historical_data("BTC/USDT", "1m", limit=5, refresh=True)
    assert refreshed.index.max() == fresh_index.max()
    assert float(refreshed.iloc[-1]["close"]) == 109.5


def test_news_service_ingests_articles(db_session, settings):
    class StaticProvider:
        def fetch(self, _feed_urls):
            return [
                NewsItem(
                    source="Example Feed",
                    title="Bitcoin rally extends",
                    summary="BTC traders react to macro headlines.",
                    url="https://example.com/btc-rally",
                    published_at=datetime.now(timezone.utc),
                    symbols=["BTC/USDT"],
                )
            ]

    service = NewsService(db=db_session, settings=settings, provider=StaticProvider())
    articles = service.ingest()
    assert len(articles) == 1
    assert articles[0].symbols == ["BTC/USDT"]


def test_dashboard_and_market_endpoints(client, db_session, settings):
    depth = MarketDepthService(db=db_session)
    depth.persist_orderbook(
        exchange=settings.derivatives_exchange_name,
        symbol="BTC/USDT",
        instrument_type=InstrumentType.PERPETUAL,
        bids=[[100.0, 1.0], [99.5, 2.0]],
        asks=[[100.5, 1.2], [101.0, 1.8]],
    )

    market_response = client.get(
        "/api/v1/market/depth",
        params={"symbol": "BTC/USDT", "instrument_type": "perpetual"},
    )
    dashboard_response = client.get("/api/v1/dashboard/summary")

    assert market_response.status_code == 200
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["portfolio"]["currency"] == "USDT"


def test_perpetual_backtest_runs(db_session, settings, synthetic_market_data):
    service = BacktestService(settings=settings, registry=StrategyRegistry(), db=db_session)
    result = service.run_backtest(
        strategy_name="ema_crossover",
        symbol="BTC/USDT",
        timeframe="5m",
        market_data=synthetic_market_data,
        instrument_type=InstrumentType.PERPETUAL,
        margin_mode=MarginMode.ISOLATED,
        leverage=2.0,
        persist_run=False,
    )
    assert isinstance(result, BacktestResponse)
    assert result.instrument_type == InstrumentType.PERPETUAL
    assert result.execution_model == "candle"
