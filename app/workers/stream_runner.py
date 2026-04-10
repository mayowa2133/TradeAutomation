from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import init_db
from app.services.bybit_stream_service import BybitStreamService

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    init_db()
    if not settings.stream_worker_enabled:
        logger.warning("Stream worker is disabled by configuration.", extra={"event_type": "stream_worker_disabled"})
        return
    logger.info("Starting Bybit websocket stream worker.", extra={"event_type": "stream_worker_started"})
    asyncio.run(BybitStreamService(settings=settings).run())


if __name__ == "__main__":
    main()
