from __future__ import annotations

import pandas as pd

from app.strategies.base import BaseStrategy, StrategyMetadata
from app.utils.indicators import ema


class EMACrossoverStrategy(BaseStrategy):
    metadata = StrategyMetadata(
        name="ema_crossover",
        description="Long-only EMA crossover momentum strategy.",
        default_parameters={
            "fast_window": 9,
            "slow_window": 21,
            "stop_loss_pct": 0.015,
            "take_profit_pct": 0.03,
        },
    )

    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        df = market_data.copy()
        fast = int(self.params["fast_window"])
        slow = int(self.params["slow_window"])
        df["ema_fast"] = ema(df["close"], fast)
        df["ema_slow"] = ema(df["close"], slow)
        df["signal"] = 0
        bullish_cross = (df["ema_fast"] > df["ema_slow"]) & (
            df["ema_fast"].shift(1) <= df["ema_slow"].shift(1)
        )
        bearish_cross = (df["ema_fast"] < df["ema_slow"]) & (
            df["ema_fast"].shift(1) >= df["ema_slow"].shift(1)
        )
        df.loc[bullish_cross, "signal"] = 1
        df["entry"] = bullish_cross.fillna(False)
        df["exit"] = bearish_cross.fillna(False)
        df["confidence"] = ((df["ema_fast"] - df["ema_slow"]).abs() / df["close"]).fillna(0.0)
        return df
