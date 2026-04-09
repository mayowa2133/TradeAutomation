from app.services.strategy_registry import StrategyRegistry


def test_strategies_generate_signals(db_session, synthetic_market_data):
    registry = StrategyRegistry()
    for name in ["ema_crossover", "rsi_mean_reversion", "breakout", "ml_filter"]:
        strategy = registry.create_strategy(name, db=db_session)
        result = strategy.generate_signals(synthetic_market_data)
        assert "entry" in result.columns
        assert "exit" in result.columns
        assert "signal" in result.columns
        assert len(result) == len(synthetic_market_data)
