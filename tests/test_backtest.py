import pandas as pd

from app.core.enums import InstrumentType, MarginMode
from app.services.backtest_service import BacktestService
from app.services.strategy_registry import StrategyRegistry


def test_backtest_runs(db_session, settings, synthetic_market_data):
    service = BacktestService(settings=settings, registry=StrategyRegistry(), db=db_session)
    result = service.run_backtest(
        strategy_name="ema_crossover",
        symbol="BTC/USDT",
        timeframe="5m",
        market_data=synthetic_market_data,
        persist_run=True,
    )
    assert result.strategy_name == "ema_crossover"
    assert result.symbol == "BTC/USDT"
    assert result.total_trades >= 1
    assert len(result.equity_curve) == len(synthetic_market_data)


def test_backtest_applies_symbol_specific_btc_short_lockout(db_session, settings):
    registry = StrategyRegistry()
    config = registry.get_db_config(db_session, "breakout")
    config.parameters = {
        "lookback": 3,
        "exit_lookback": 2,
        "buffer_pct": 0.0,
        "min_breakout_strength_pct": 0.0,
        "symbol_overrides": {
            "BTC/USDT": {
                "allow_short": False,
            }
        },
    }
    db_session.add(config)
    db_session.commit()

    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 100.8, 100.6, 100.4, 98.4],
            "low": [99.0, 98.8, 98.6, 98.4, 95.0],
            "close": [99.8, 99.3, 98.9, 98.5, 95.5],
            "volume": [10.0, 10.0, 10.0, 10.0, 10.0],
        },
        index=pd.date_range("2024-01-01", periods=5, freq="15min", tz="UTC"),
    )

    service = BacktestService(settings=settings, registry=registry, db=db_session)
    result = service.run_backtest(
        strategy_name="breakout",
        symbol="BTC/USDT",
        timeframe="15m",
        market_data=frame,
        instrument_type=InstrumentType.PERPETUAL,
        margin_mode=MarginMode.ISOLATED,
        leverage=1.5,
        persist_run=False,
    )

    assert result.total_trades == 0
