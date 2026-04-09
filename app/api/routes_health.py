from __future__ import annotations

import redis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.common import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def healthcheck(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> HealthResponse:
    database = "ok"
    redis_state = "unavailable"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    try:
        client = redis.from_url(settings.redis_url)
        client.ping()
        redis_state = "ok"
    except Exception:
        redis_state = "unavailable"
    status = "ok" if database == "ok" else "degraded"
    return HealthResponse(
        status=status,
        database=database,
        redis=redis_state,
        trading_mode=settings.trading_mode.value,
        live_trading_enabled=settings.live_trading_enabled,
    )
