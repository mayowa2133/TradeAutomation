from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import OrderSide, OrderStatus


@dataclass(slots=True)
class DepthFillResult:
    status: OrderStatus
    filled_quantity: float
    remaining_quantity: float
    average_price: float | None
    notional: float


def _walk_levels(levels: list[list[float]], quantity: float) -> DepthFillResult:
    remaining = quantity
    filled = 0.0
    notional = 0.0
    for price, size in levels:
        if remaining <= 0:
            break
        take = min(float(size), remaining)
        if take <= 0:
            continue
        filled += take
        notional += take * float(price)
        remaining -= take

    average_price = (notional / filled) if filled > 0 else None
    if filled <= 0:
        status = OrderStatus.REJECTED
    elif remaining > 0:
        status = OrderStatus.PARTIALLY_FILLED
    else:
        status = OrderStatus.FILLED
    return DepthFillResult(
        status=status,
        filled_quantity=filled,
        remaining_quantity=max(remaining, 0.0),
        average_price=average_price,
        notional=notional,
    )


def simulate_market_fill(
    side: OrderSide,
    quantity: float,
    bids: list[list[float]],
    asks: list[list[float]],
) -> DepthFillResult:
    book = asks if side == OrderSide.BUY else bids
    return _walk_levels(book, quantity)


def simulate_limit_fill(
    side: OrderSide,
    quantity: float,
    limit_price: float,
    bids: list[list[float]],
    asks: list[list[float]],
) -> DepthFillResult:
    if side == OrderSide.BUY:
        eligible = [level for level in asks if float(level[0]) <= limit_price]
    else:
        eligible = [level for level in bids if float(level[0]) >= limit_price]
    if not eligible:
        return DepthFillResult(
            status=OrderStatus.NEW,
            filled_quantity=0.0,
            remaining_quantity=quantity,
            average_price=None,
            notional=0.0,
        )
    return _walk_levels(eligible, quantity)
