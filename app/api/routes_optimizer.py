from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.optimizer import OptimizerRunRead, OptimizerRunRequest
from app.services.optimizer_service import OptimizerService

router = APIRouter(prefix="/optimizer", tags=["optimizer"])


@router.post("/run", response_model=OptimizerRunRead)
def run_optimizer(
    request: OptimizerRunRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> OptimizerRunRead:
    service = OptimizerService(db=db, settings=settings)
    try:
        run = service.run_optimizer(
            symbols=request.symbols,
            timeframe=request.timeframe,
            signal_strengths=request.signal_strengths,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OptimizerRunRead.model_validate(run, from_attributes=True)


@router.get("/latest", response_model=OptimizerRunRead | None)
def latest_optimizer(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> OptimizerRunRead | None:
    service = OptimizerService(db=db, settings=settings)
    run = service.latest_run()
    return OptimizerRunRead.model_validate(run, from_attributes=True) if run else None
