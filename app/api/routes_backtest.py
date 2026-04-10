from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_strategy_registry
from app.core.config import Settings
from app.core.enums import InstrumentType
from app.db.session import get_db
from app.schemas.backtest import BacktestRequest, BacktestResponse
from app.services.backtest_service import BacktestService
from app.services.data_service import DataService
from app.services.strategy_registry import StrategyRegistry

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("/run", response_model=BacktestResponse)
def run_backtest(
    request: BacktestRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    registry: StrategyRegistry = Depends(get_strategy_registry),
) -> BacktestResponse:
    data_service = DataService(db=db, settings=settings)
    try:
        data = data_service.get_historical_data(
            symbol=request.symbol,
            timeframe=request.timeframe,
            limit=request.limit,
            instrument_type=request.instrument_type,
            use_cached_only=request.use_cached_data_only,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data.empty:
        raise HTTPException(status_code=400, detail="No market data available for the request.")
    service = BacktestService(settings=settings, registry=registry, db=db)
    return service.run_backtest(
        strategy_name=request.strategy_name,
        symbol=request.symbol,
        timeframe=request.timeframe,
        market_data=data,
        instrument_type=request.instrument_type,
        margin_mode=request.margin_mode,
        leverage=request.leverage,
        execution_model=request.execution_model,
        allow_candle_fallback=request.allow_candle_fallback,
        persist_run=request.persist_run,
        fee_bps=request.fee_bps,
        slippage_bps=request.slippage_bps,
    )
