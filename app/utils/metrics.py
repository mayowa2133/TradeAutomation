from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd


def compute_max_drawdown(equity_curve: Sequence[float]) -> float:
    if not equity_curve:
        return 0.0
    series = pd.Series(equity_curve, dtype=float)
    peak = series.cummax()
    drawdown = (series - peak) / peak.replace(0, np.nan)
    return abs(float(drawdown.min() or 0.0))


def compute_sharpe_like(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    series = pd.Series(returns, dtype=float)
    std = float(series.std(ddof=0))
    if math.isclose(std, 0.0):
        return 0.0
    return float((series.mean() / std) * math.sqrt(len(series)))


def compute_win_rate(pnls: Sequence[float]) -> float:
    if not pnls:
        return 0.0
    wins = sum(1 for pnl in pnls if pnl > 0)
    return wins / len(pnls)
