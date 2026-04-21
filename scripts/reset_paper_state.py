from __future__ import annotations

import argparse

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.enums import TradingMode
from app.db.models.event_log import EventLog
from app.db.models.order import Order
from app.db.models.portfolio_state import PortfolioState
from app.db.models.position import Position
from app.db.models.stream_status import StreamStatus
from app.db.models.trade import Trade
from app.db.session import get_session_factory, init_db
from app.services.portfolio_service import PortfolioService


def reset_paper_state(*, yes: bool) -> dict[str, int]:
    settings = get_settings()
    if settings.trading_mode != TradingMode.PAPER:
        raise RuntimeError("Paper-state reset is only allowed when TRADING_MODE=paper.")
    if not yes:
        raise RuntimeError("Refusing to reset paper state without --yes.")

    init_db()
    with get_session_factory()() as db:
        trades_deleted = db.execute(delete(Trade).where(Trade.mode == TradingMode.PAPER)).rowcount or 0
        orders_deleted = db.execute(delete(Order).where(Order.mode == TradingMode.PAPER)).rowcount or 0
        positions_deleted = db.execute(delete(Position).where(Position.mode == TradingMode.PAPER)).rowcount or 0
        event_logs_deleted = db.execute(delete(EventLog)).rowcount or 0
        allowed_symbols = settings.symbol_allowlist_list
        stream_status_deleted = 0
        if allowed_symbols:
            stream_status_deleted = (
                db.execute(
                    delete(StreamStatus).where(StreamStatus.symbol.not_in(allowed_symbols))
                ).rowcount
                or 0
            )
        portfolio_states_deleted = db.execute(
            delete(PortfolioState).where(PortfolioState.mode == TradingMode.PAPER)
        ).rowcount or 0
        db.commit()
        PortfolioService(db=db, settings=settings).get_or_create_state()
        db.commit()
    return {
        "trades_deleted": trades_deleted,
        "orders_deleted": orders_deleted,
        "positions_deleted": positions_deleted,
        "event_logs_deleted": event_logs_deleted,
        "stream_status_deleted": stream_status_deleted,
        "portfolio_states_deleted": portfolio_states_deleted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the paper-trading runtime state for a fresh demo run.")
    parser.add_argument("--yes", action="store_true", help="Confirm the destructive reset.")
    args = parser.parse_args()
    summary = reset_paper_state(yes=args.yes)
    print(
        "Reset paper state: "
        f"trades={summary['trades_deleted']}, "
        f"orders={summary['orders_deleted']}, "
        f"positions={summary['positions_deleted']}, "
        f"event_logs={summary['event_logs_deleted']}, "
        f"stream_status={summary['stream_status_deleted']}, "
        f"portfolio_states={summary['portfolio_states_deleted']}"
    )


if __name__ == "__main__":
    main()
