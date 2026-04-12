from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import StreamHealth
from app.db.session import Base


class StreamStatus(Base):
    __tablename__ = "stream_status"
    __table_args__ = (UniqueConstraint("stream_name", "symbol", name="uq_stream_status_name_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stream_name: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[StreamHealth] = mapped_column(
        Enum(StreamHealth), default=StreamHealth.DISCONNECTED, index=True
    )
    stream_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
