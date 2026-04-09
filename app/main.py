from __future__ import annotations

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes_backtest import router as backtest_router
from app.api.routes_config import router as config_router
from app.api.routes_events import router as events_router
from app.api.routes_health import router as health_router
from app.api.routes_orders import router as orders_router
from app.api.routes_paper import router as paper_router
from app.api.routes_positions import router as positions_router
from app.api.routes_risk import router as risk_router
from app.api.routes_strategies import router as strategies_router
from app.api.routes_trades import router as trades_router
from app.core.config import get_settings
from app.core.exceptions import ConfigurationError, RiskCheckFailed, TradingError
from app.core.logging import configure_logging, get_logger
from app.db.models.event_log import EventLog
from app.db.session import get_session_factory, init_db
from app.services.portfolio_service import PortfolioService
from app.services.scheduler_service import create_scheduler
from app.services.strategy_registry import StrategyRegistry

settings = get_settings()
logger = get_logger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Safety-first crypto trading automation MVP",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(config_router, prefix=settings.api_prefix)
app.include_router(strategies_router, prefix=settings.api_prefix)
app.include_router(backtest_router, prefix=settings.api_prefix)
app.include_router(paper_router, prefix=settings.api_prefix)
app.include_router(positions_router, prefix=settings.api_prefix)
app.include_router(orders_router, prefix=settings.api_prefix)
app.include_router(trades_router, prefix=settings.api_prefix)
app.include_router(risk_router, prefix=settings.api_prefix)
app.include_router(events_router, prefix=settings.api_prefix)


@app.exception_handler(TradingError)
async def trading_error_handler(_, exc: TradingError) -> JSONResponse:
    status = 403 if isinstance(exc, RiskCheckFailed) else 400
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(_, exc: ConfigurationError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "mode": settings.trading_mode.value}


@app.on_event("startup")
def startup_event() -> None:
    configure_logging(settings)
    if settings.auto_create_tables:
        init_db()
    with get_session_factory()() as db:
        StrategyRegistry().sync_configs(db)
        PortfolioService(db=db, settings=settings).get_or_create_state()
    if settings.live_trading_enabled:
        logger.warning("Live trading is enabled.", extra={"event_type": "live_trading_enabled"})
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
