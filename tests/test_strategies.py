import pandas as pd

from app.core.enums import PositionSide
from app.services.strategy_registry import StrategyRegistry


def test_breakout_side_specific_exit_does_not_conflict_with_long_entry(db_session):
    strategy = StrategyRegistry().create_strategy(
        "breakout",
        db=db_session,
        overrides={
            "lookback": 3,
            "exit_lookback": 2,
            "buffer_pct": 0.0,
            "min_breakout_strength_pct": 0.0,
        },
    )
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 101.5, 102.0, 102.5, 105.0],
            "low": [99.0, 99.2, 99.4, 99.6, 102.0],
            "close": [100.2, 100.7, 101.2, 101.8, 104.5],
            "volume": [10.0, 10.0, 10.0, 10.0, 10.0],
        },
        index=pd.date_range("2024-01-01", periods=5, freq="15min", tz="UTC"),
    )

    result = strategy.generate_signals(frame)
    latest = result.iloc[-1]

    assert bool(latest["entry"]) is True
    assert bool(latest["exit"]) is False
    assert bool(latest["exit_long"]) is False
    assert strategy.should_exit(latest, has_position=True, position_side=PositionSide.LONG) is False


def test_breakout_side_specific_exit_does_not_conflict_with_short_entry(db_session):
    strategy = StrategyRegistry().create_strategy(
        "breakout",
        db=db_session,
        overrides={
            "lookback": 3,
            "exit_lookback": 2,
            "buffer_pct": 0.0,
            "min_breakout_strength_pct": 0.0,
        },
    )
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

    result = strategy.generate_signals(frame)
    latest = result.iloc[-1]

    assert bool(latest["entry"]) is True
    assert bool(latest["exit"]) is False
    assert bool(latest["exit_short"]) is False
    assert strategy.should_exit(latest, has_position=True, position_side=PositionSide.SHORT) is False


def test_breakout_min_strength_filter_blocks_tiny_breakouts(db_session):
    strategy = StrategyRegistry().create_strategy(
        "breakout",
        db=db_session,
        overrides={
            "lookback": 3,
            "exit_lookback": 2,
            "buffer_pct": 0.0,
            "min_breakout_strength_pct": 0.001,
        },
    )
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 101.2, 101.4, 101.6, 101.8],
            "low": [99.0, 99.1, 99.2, 99.3, 99.4],
            "close": [100.0, 100.3, 100.6, 100.9, 101.05],
            "volume": [10.0, 10.0, 10.0, 10.0, 10.0],
        },
        index=pd.date_range("2024-01-01", periods=5, freq="15min", tz="UTC"),
    )

    result = strategy.generate_signals(frame)
    latest = result.iloc[-1]

    assert bool(latest["entry"]) is False
    assert int(latest["signal"]) == 0


def test_breakout_symbol_override_can_disable_btc_shorts(db_session):
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

    strategy = registry.create_strategy("breakout", db=db_session, symbol="BTC/USDT")
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

    result = strategy.generate_signals(frame)
    latest = result.iloc[-1]

    assert bool(latest["entry"]) is False
    assert int(latest["signal"]) == 0


def test_breakout_trend_filter_blocks_countertrend_short(db_session):
    strategy = StrategyRegistry().create_strategy(
        "breakout",
        db=db_session,
        overrides={
            "lookback": 4,
            "exit_lookback": 2,
            "buffer_pct": 0.0,
            "min_breakout_strength_pct": 0.0,
            "min_atr_pct": 0.0,
            "min_volume_ratio": 0.0,
            "max_breakout_extension_pct": 1.0,
            "trend_timeframe": "1h",
            "trend_ema_window": 2,
            "trend_margin_pct": 0.001,
            "allow_short": True,
        },
    )
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 106.0, 105.0, 104.0, 96.5],
            "high": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 106.5, 105.5, 104.5, 97.0],
            "low": [99.5, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 105.5, 104.5, 103.5, 95.5],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 106.0, 105.0, 104.0, 96.0],
            "volume": [100.0] * 12,
        },
        index=pd.date_range("2024-01-01", periods=12, freq="15min", tz="UTC"),
    )

    result = strategy.generate_signals(frame)
    latest = result.iloc[-1]

    assert bool(latest["entry"]) is False
    assert int(latest["signal"]) == 0


def test_breakout_volume_filter_blocks_low_quality_breakouts(db_session):
    strategy = StrategyRegistry().create_strategy(
        "breakout",
        db=db_session,
        overrides={
            "lookback": 3,
            "exit_lookback": 2,
            "buffer_pct": 0.0,
            "min_breakout_strength_pct": 0.0,
            "min_volume_ratio": 1.5,
        },
    )
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 101.5, 102.0, 102.5, 105.0],
            "low": [99.0, 99.2, 99.4, 99.6, 102.0],
            "close": [100.2, 100.7, 101.2, 101.8, 104.5],
            "volume": [10.0, 10.0, 10.0, 10.0, 10.0],
        },
        index=pd.date_range("2024-01-01", periods=5, freq="15min", tz="UTC"),
    )

    result = strategy.generate_signals(frame)
    latest = result.iloc[-1]

    assert bool(latest["entry"]) is False
    assert int(latest["signal"]) == 0


def test_strategies_generate_signals(db_session, synthetic_market_data):
    registry = StrategyRegistry()
    for name in ["ema_crossover", "rsi_mean_reversion", "breakout", "ml_filter"]:
        strategy = registry.create_strategy(name, db=db_session)
        result = strategy.generate_signals(synthetic_market_data)
        assert "entry" in result.columns
        assert "exit" in result.columns
        assert "signal" in result.columns
        assert len(result) == len(synthetic_market_data)
