from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.position import PositionRead
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=list[PositionRead])
def list_positions(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> list[PositionRead]:
    service = PortfolioService(db=db, settings=settings)
    return [PositionRead.model_validate(position) for position in service.get_open_positions()]
