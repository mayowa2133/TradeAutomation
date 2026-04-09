from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_strategy_registry
from app.db.models.strategy_config import StrategyConfigModel
from app.db.session import get_db
from app.schemas.strategy import StrategyToggleRequest, StrategyToggleResponse
from app.services.strategy_registry import StrategyRegistry

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("/{name}/toggle", response_model=StrategyToggleResponse)
def toggle_strategy(
    name: str,
    request: StrategyToggleRequest,
    db: Session = Depends(get_db),
    registry: StrategyRegistry = Depends(get_strategy_registry),
) -> StrategyToggleResponse:
    try:
        config = registry.get_db_config(db, name)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    config.enabled = request.enabled
    db.add(config)
    db.commit()
    db.refresh(config)
    return StrategyToggleResponse(name=config.name, enabled=config.enabled, updated_at=config.updated_at)
