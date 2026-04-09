from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_strategy_registry
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.strategy import ConfigResponse, StrategyDescriptor
from app.services.strategy_registry import StrategyRegistry

router = APIRouter(tags=["config"])


@router.get("/config", response_model=ConfigResponse)
def get_config(settings: Settings = Depends(get_app_settings)) -> ConfigResponse:
    return ConfigResponse(
        settings=settings.masked_config(),
        trading_mode=settings.trading_mode,
        live_trading_enabled=settings.live_trading_enabled,
    )


@router.get("/strategies", response_model=list[StrategyDescriptor])
def list_strategies(
    db: Session = Depends(get_db),
    registry: StrategyRegistry = Depends(get_strategy_registry),
) -> list[StrategyDescriptor]:
    return [StrategyDescriptor(**item) for item in registry.list_strategies(db)]
