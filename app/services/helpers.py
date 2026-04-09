from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models.event_log import EventLog


def record_event(
    db: Session,
    level: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> EventLog:
    event = EventLog(level=level, event_type=event_type, message=message, payload=payload or {})
    db.add(event)
    return event
