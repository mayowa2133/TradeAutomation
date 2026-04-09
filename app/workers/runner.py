from __future__ import annotations

import signal
import sys
import time

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import init_db
from app.services.scheduler_service import create_scheduler
from app.services.strategy_registry import StrategyRegistry
from app.services.portfolio_service import PortfolioService
from app.db.session import get_session_factory

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    init_db()
    with get_session_factory()() as db:
        StrategyRegistry().sync_configs(db)
        PortfolioService(db=db, settings=settings).get_or_create_state()
    scheduler = create_scheduler(settings)
    scheduler.start()
    logger.info("Scheduler worker started.", extra={"event_type": "worker_started"})

    def _shutdown(*_) -> None:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler worker stopped.", extra={"event_type": "worker_stopped"})
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
