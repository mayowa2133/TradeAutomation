from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.position import PnLSummary
from app.schemas.trade import TradeRead
from app.services.portfolio_service import PortfolioService

router = APIRouter(tags=["trades"])


@router.get("/trades", response_model=list[TradeRead])
def list_trades(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> list[TradeRead]:
    service = PortfolioService(db=db, settings=settings)
    return [TradeRead.model_validate(trade) for trade in service.get_trades()]


@router.get("/pnl/summary", response_model=PnLSummary)
def pnl_summary(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> PnLSummary:
    service = PortfolioService(db=db, settings=settings)
    return PnLSummary(**service.pnl_summary())
