from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models.event_log import EventLog
from app.db.session import get_db
from app.schemas.strategy import EventLogRead

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/recent", response_model=list[EventLogRead])
def recent_events(
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[EventLogRead]:
    rows = db.query(EventLog).order_by(EventLog.created_at.desc()).limit(limit).all()
    return [EventLogRead.model_validate(row) for row in rows]
