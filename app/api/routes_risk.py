from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.strategy import RiskStateResponse
from app.services.risk_service import RiskService

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/state", response_model=RiskStateResponse)
def risk_state(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> RiskStateResponse:
    service = RiskService(db=db, settings=settings)
    return RiskStateResponse(**service.get_state())
