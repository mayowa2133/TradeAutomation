from __future__ import annotations

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes_backtest import router as backtest_router
from app.api.routes_config import router as config_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_events import router as events_router
from app.api.routes_health import router as health_router
from app.api.routes_instruments import router as instruments_router
from app.api.routes_llm import router as llm_router
from app.api.routes_market import router as market_router
from app.api.routes_news import router as news_router
from app.api.routes_optimizer import router as optimizer_router
from app.api.routes_orders import router as orders_router
from app.api.routes_paper import router as paper_router
from app.api.routes_positions import router as positions_router
from app.api.routes_risk import router as risk_router
from app.api.routes_strategies import router as strategies_router
from app.api.routes_trades import router as trades_router
from app.core.config import get_settings
from app.core.enums import InstrumentType
from app.core.exceptions import ConfigurationError, RiskCheckFailed, TradingError
from app.core.logging import configure_logging, get_logger
from app.db.models.event_log import EventLog
from app.db.session import get_session_factory, init_db
from app.services.dashboard_service import DashboardService
from app.services.market_depth_service import MarketDepthService
from app.services.portfolio_service import PortfolioService
from app.services.scheduler_service import create_scheduler
from app.services.strategy_registry import StrategyRegistry

settings = get_settings()
logger = get_logger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Safety-first crypto trading automation platform with paper trading defaults.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [
    health_router,
    config_router,
    strategies_router,
    backtest_router,
    paper_router,
    positions_router,
    orders_router,
    trades_router,
    risk_router,
    events_router,
    instruments_router,
    market_router,
    optimizer_router,
    news_router,
    llm_router,
    dashboard_router,
]:
    app.include_router(router, prefix=settings.api_prefix)


@app.exception_handler(TradingError)
async def trading_error_handler(_, exc: TradingError) -> JSONResponse:
    status = 403 if isinstance(exc, RiskCheckFailed) else 400
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(_, exc: ConfigurationError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/")
def root() -> dict[str, str | bool]:
    return {
        "name": settings.app_name,
        "mode": settings.trading_mode.value,
        "live_trading_enabled": settings.live_trading_enabled,
    }


@app.on_event("startup")
def startup_event() -> None:
    configure_logging(settings)
    if settings.live_trading_enabled and settings.llm_autonomy_live:
        raise ConfigurationError("LLM-triggered live trading is disabled by design and cannot be enabled.")
    if settings.auto_create_tables:
        init_db()
    with get_session_factory()() as db:
        StrategyRegistry().sync_configs(db)
        PortfolioService(db=db, settings=settings).get_or_create_state()
    if settings.live_trading_enabled:
        logger.warning(
            "Live trading is enabled. Verify credentials, venue routing, and kill-switch state.",
            extra={"event_type": "live_trading_enabled"},
        )
    if settings.scheduler_enabled:
        scheduler = create_scheduler(settings)
        scheduler.start()
        app.state.scheduler = scheduler


@app.on_event("shutdown")
def shutdown_event() -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.shutdown(wait=False)


@app.websocket("/ws/events")
async def event_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    last_id = 0
    try:
        while True:
            with get_session_factory()() as db:
                rows = (
                    db.query(EventLog)
                    .filter(EventLog.id > last_id)
                    .order_by(EventLog.id.asc())
                    .limit(25)
                    .all()
                )
            for row in rows:
                last_id = max(last_id, row.id)
                await websocket.send_json(
                    {
                        "id": row.id,
                        "level": row.level,
                        "event_type": row.event_type,
                        "message": row.message,
                        "payload": row.payload,
                        "created_at": row.created_at.isoformat(),
                    }
                )
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/market")
async def market_stream(
    websocket: WebSocket,
    symbol: str = "BTC/USDT",
    instrument_type: InstrumentType = InstrumentType.PERPETUAL,
) -> None:
    await websocket.accept()
    try:
        while True:
            with get_session_factory()() as db:
                depth_service = MarketDepthService(db=db)
                quote = depth_service.latest_quote(symbol, instrument_type)
                orderbook = depth_service.latest_orderbook(symbol, instrument_type)
                stream_rows = [
                    item
                    for item in depth_service.list_stream_status()
                    if item.symbol == symbol
                ]
            await websocket.send_json(
                {
                    "symbol": symbol,
                    "instrument_type": instrument_type.value,
                    "quote": {
                        "best_bid": quote.best_bid,
                        "best_ask": quote.best_ask,
                        "last_price": quote.last_price,
                        "mark_price": quote.mark_price,
                        "funding_rate": quote.funding_rate,
                        "spread_bps": quote.spread_bps,
                        "snapshot_time": quote.snapshot_time.isoformat(),
                    }
                    if quote
                    else None,
                    "orderbook": {
                        "bids": orderbook.bids,
                        "asks": orderbook.asks,
                        "mid_price": orderbook.mid_price,
                        "snapshot_time": orderbook.snapshot_time.isoformat(),
                    }
                    if orderbook
                    else None,
                    "stream_status": [
                        {
                            "stream_name": row.stream_name,
                            "status": row.status.value,
                            "error_message": row.error_message,
                            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
                        }
                        for row in stream_rows
                    ],
                }
            )
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/execution")
async def execution_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            with get_session_factory()() as db:
                portfolio = PortfolioService(db=db, settings=settings)
                orders = portfolio.get_orders(limit=15)
                positions = portfolio.get_open_positions()
                trades = portfolio.get_trades(limit=15)
            await websocket.send_json(
                {
                    "positions": [
                        {
                            "id": position.id,
                            "symbol": position.symbol,
                            "instrument_type": position.instrument_type.value,
                            "side": position.side.value,
                            "quantity": position.quantity,
                            "entry_price": position.avg_entry_price,
                            "current_price": position.current_price,
                            "unrealized_pnl": position.unrealized_pnl,
                            "leverage": position.leverage,
                        }
                        for position in positions
                    ],
                    "orders": [
                        {
                            "id": order.id,
                            "symbol": order.symbol,
                            "instrument_type": order.instrument_type.value,
                            "status": order.status.value,
                            "side": order.side.value,
                            "position_side": order.position_side.value,
                            "quantity": order.quantity,
                            "filled_quantity": order.filled_quantity,
                            "fill_price": order.fill_price,
                            "created_at": order.created_at.isoformat(),
                        }
                        for order in orders
                    ],
                    "trades": [
                        {
                            "id": trade.id,
                            "symbol": trade.symbol,
                            "action": trade.action.value,
                            "position_side": trade.position_side.value,
                            "quantity": trade.quantity,
                            "price": trade.price,
                            "realized_pnl": trade.realized_pnl,
                            "trade_time": trade.trade_time.isoformat(),
                        }
                        for trade in trades
                    ],
                }
            )
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/system")
async def system_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            with get_session_factory()() as db:
                payload = DashboardService(db=db, settings=settings).summary()
            await websocket.send_json(payload)
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        return
