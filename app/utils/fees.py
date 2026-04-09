from __future__ import annotations

from app.core.enums import OrderSide


def bps_to_fraction(bps: float) -> float:
    return bps / 10_000.0


def calculate_fee(notional: float, fee_bps: float) -> float:
    return max(notional * bps_to_fraction(fee_bps), 0.0)


def apply_slippage(price: float, side: OrderSide, slippage_bps: float) -> float:
    fraction = bps_to_fraction(slippage_bps)
    if side == OrderSide.BUY:
        return price * (1 + fraction)
    return price * (1 - fraction)
