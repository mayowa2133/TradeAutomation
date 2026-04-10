from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.dashboard import DashboardSummaryRead
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryRead)
def dashboard_summary(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> DashboardSummaryRead:
    summary = DashboardService(db=db, settings=settings).summary()
    return DashboardSummaryRead(**summary)
