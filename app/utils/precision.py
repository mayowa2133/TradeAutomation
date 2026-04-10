from __future__ import annotations

from decimal import Decimal, ROUND_DOWN


def quantize_down(value: float, step: float) -> float:
    if step <= 0:
        return float(value)
    quant = Decimal(str(step))
    normalized = Decimal(str(value)).quantize(quant, rounding=ROUND_DOWN)
    return float(normalized)


def round_to_increment(value: float, increment: float) -> float:
    if increment <= 0:
        return float(value)
    value_dec = Decimal(str(value))
    inc_dec = Decimal(str(increment))
    rounded = (value_dec // inc_dec) * inc_dec
    return float(rounded)


def enforce_min_notional(quantity: float, price: float, min_notional: float) -> bool:
    return (quantity * price) >= min_notional
