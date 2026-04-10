from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.core.exceptions import TradingError
from app.db.session import get_db
from app.schemas.common import MessageResponse
from app.schemas.position import PositionRead
from app.services.execution_service import ExecutionService
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=list[PositionRead])
def list_positions(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> list[PositionRead]:
    service = PortfolioService(db=db, settings=settings)
    return [PositionRead.model_validate(position) for position in service.get_open_positions()]


@router.post("/{position_id}/close", response_model=MessageResponse)
def close_position(
    position_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> MessageResponse:
    service = ExecutionService(db=db, settings=settings)
    try:
        service.close_position_by_id(position_id)
    except TradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(message=f"Close submitted for position {position_id}.")
