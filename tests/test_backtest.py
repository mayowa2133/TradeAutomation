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
