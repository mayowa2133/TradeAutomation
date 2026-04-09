from app.core.enums import OrderStatus, OrderType
from app.services.execution_service import ExecutionService
from app.services.strategy_registry import StrategyRegistry


def test_execution_service_places_paper_entry(db_session, settings):
    service = ExecutionService(db=db_session, settings=settings, registry=StrategyRegistry())
    order = service.submit_entry_order(
        strategy_name="ema_crossover",
        symbol="BTC/USDT",
        reference_price=100.0,
    )
    assert order.status == OrderStatus.FILLED
    positions = service.portfolio_service.get_open_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "BTC/USDT"


def test_paper_limit_order_can_be_canceled(db_session, settings):
    service = ExecutionService(db=db_session, settings=settings, registry=StrategyRegistry())
    order = service.submit_entry_order(
        strategy_name="ema_crossover",
        symbol="BTC/USDT",
        reference_price=100.0,
        order_type=OrderType.LIMIT,
        limit_price=99.0,
    )
    assert order.status == OrderStatus.NEW
    canceled = service.cancel_order(order.id)
    assert canceled.status == OrderStatus.CANCELED
