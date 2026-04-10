from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.core.enums import InstrumentType, MarginMode, OrderStatus, PositionSide
from app.db.models.instrument import Instrument
from app.schemas.backtest import BacktestResponse
from app.services.backtest_service import BacktestService
from app.services.instrument_service import InstrumentService
from app.services.market_depth_service import MarketDepthService
from app.services.news_service import NewsItem, NewsService
from app.services.optimizer_service import OptimizerService
from app.services.execution_service import ExecutionService
from app.services.risk_service import RiskService
from app.services.strategy_registry import StrategyRegistry


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
