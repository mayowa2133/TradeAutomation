from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.strategy import PaperTradingStatus
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/paper", tags=["paper"])


@router.get("/status", response_model=PaperTradingStatus)
def paper_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> PaperTradingStatus:
    service = PortfolioService(db=db, settings=settings)
    summary = service.pnl_summary()
    return PaperTradingStatus(
        mode=settings.trading_mode,
        live_trading_enabled=settings.live_trading_enabled,
        scheduler_enabled=settings.scheduler_enabled,
        cash_balance=summary["cash_balance"],
        equity=summary["equity"],
        open_positions=len(service.get_open_positions()),
    )
