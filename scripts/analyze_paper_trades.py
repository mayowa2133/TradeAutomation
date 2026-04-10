from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.exc import SQLAlchemyError

from app.core.enums import PositionStatus, TradeAction, TradingMode
from app.db.models.position import Position
from app.db.models.trade import Trade
from app.db.session import get_session_factory, init_db


@dataclass
class StrategyBucket:
    closed_positions: int = 0
    wins: int = 0
    losses: int = 0
    total_realized_pnl: float = 0.0
    total_fees: float = 0.0
    hold_seconds: list[float] = field(default_factory=list)


def build_diagnosis(
    *,
    total_closed_positions: int,
    total_realized_pnl: float,
    total_fees: float,
    average_hold_seconds: float,
    overall_win_rate: float,
) -> list[str]:
    diagnosis: list[str] = []
    if total_closed_positions == 0:
        return [
            "No closed paper positions were found. Run the worker long enough to generate exits, or point DATABASE_URL at the active runtime database."
        ]
    if total_realized_pnl < 0:
        diagnosis.append(
            "Paper trading is currently net negative; treat the active configuration as a demo/runtime profile, not a validated trading profile."
        )
    if total_fees > max(abs(total_realized_pnl), 1.0) * 0.5:
        diagnosis.append(
            "Fee drag is materially large relative to realized PnL. Current turnover is high enough that costs are dominating weak directional edge."
        )
    if 0 < average_hold_seconds < 600:
        diagnosis.append(
            "Average holding time is very short. That usually means the strategy is competing against spread, slippage, and fees instead of harvesting larger moves."
        )
    if overall_win_rate < 0.45:
        diagnosis.append(
            "Win rate is weak in the current sample. Improvements should focus on selectivity and turnover reduction before adding any AI overlay."
        )
    if not diagnosis:
        diagnosis.append(
            "No dominant failure mode stood out from this sample. Review symbol-level results and cost assumptions before changing strategy logic."
        )
    return diagnosis


def summarize_paper_trades() -> dict[str, object]:
    init_db()
    with get_session_factory()() as db:
        exit_trades = (
            db.query(Trade)
            .filter(
                Trade.mode == TradingMode.PAPER,
                Trade.action == TradeAction.EXIT,
            )
            .order_by(Trade.trade_time.asc())
            .all()
        )
        all_trades = db.query(Trade).filter(Trade.mode == TradingMode.PAPER).all()
        closed_positions = (
            db.query(Position)
            .filter(
                Position.mode == TradingMode.PAPER,
                Position.status == PositionStatus.CLOSED,
            )
            .order_by(Position.closed_at.asc())
            .all()
        )

    buckets: dict[tuple[str, str], StrategyBucket] = defaultdict(StrategyBucket)
    for position in closed_positions:
        key = (position.strategy_name, position.symbol)
        bucket = buckets[key]
        bucket.closed_positions += 1
        bucket.total_realized_pnl += position.realized_pnl
        if position.realized_pnl >= 0:
            bucket.wins += 1
        else:
            bucket.losses += 1
        if position.closed_at is not None:
            bucket.hold_seconds.append((position.closed_at - position.opened_at).total_seconds())

    for trade in all_trades:
        key = (trade.strategy_name or "manual_or_system", trade.symbol)
        buckets[key].total_fees += trade.fee_paid

    total_realized_pnl = sum(bucket.total_realized_pnl for bucket in buckets.values())
    total_fees = sum(bucket.total_fees for bucket in buckets.values())
    total_closed_positions = sum(bucket.closed_positions for bucket in buckets.values())
    total_wins = sum(bucket.wins for bucket in buckets.values())
    total_losses = sum(bucket.losses for bucket in buckets.values())
    hold_samples = [value for bucket in buckets.values() for value in bucket.hold_seconds]
    average_hold_seconds = (
        sum(hold_samples) / len(hold_samples) if hold_samples else 0.0
    )
    overall_win_rate = total_wins / total_closed_positions if total_closed_positions else 0.0

    strategy_summaries = []
    for (strategy_name, symbol), bucket in sorted(
        buckets.items(),
        key=lambda item: item[1].total_realized_pnl,
        reverse=True,
    ):
        avg_hold_seconds = (
            sum(bucket.hold_seconds) / len(bucket.hold_seconds) if bucket.hold_seconds else 0.0
        )
        avg_realized_pnl = (
            bucket.total_realized_pnl / bucket.closed_positions if bucket.closed_positions else 0.0
        )
        strategy_summaries.append(
            {
                "strategy_name": strategy_name,
                "symbol": symbol,
                "closed_positions": bucket.closed_positions,
                "wins": bucket.wins,
                "losses": bucket.losses,
                "win_rate": round(bucket.wins / bucket.closed_positions, 4)
                if bucket.closed_positions
                else 0.0,
                "avg_hold_seconds": round(avg_hold_seconds, 2),
                "avg_realized_pnl": round(avg_realized_pnl, 4),
                "total_realized_pnl": round(bucket.total_realized_pnl, 4),
                "total_fees": round(bucket.total_fees, 4),
                "fee_to_pnl_ratio": round(
                    bucket.total_fees / max(abs(bucket.total_realized_pnl), 1.0),
                    4,
                ),
            }
        )

    return {
        "mode": TradingMode.PAPER.value,
        "total_closed_positions": total_closed_positions,
        "wins": total_wins,
        "losses": total_losses,
        "overall_win_rate": round(overall_win_rate, 4),
        "average_hold_seconds": round(average_hold_seconds, 2),
        "total_exit_fees": round(sum(trade.fee_paid for trade in exit_trades), 4),
        "total_realized_pnl": round(total_realized_pnl, 4),
        "total_fees": round(total_fees, 4),
        "strategy_summaries": strategy_summaries,
        "diagnosis": build_diagnosis(
            total_closed_positions=total_closed_positions,
            total_realized_pnl=total_realized_pnl,
            total_fees=total_fees,
            average_hold_seconds=average_hold_seconds,
            overall_win_rate=overall_win_rate,
        ),
    }


def main() -> None:
    try:
        print(json.dumps(summarize_paper_trades(), indent=2))
    except SQLAlchemyError as exc:
        raise SystemExit(
            "Unable to analyze paper trades. Verify DATABASE_URL points to a reachable runtime database."
        ) from exc


if __name__ == "__main__":
    main()
