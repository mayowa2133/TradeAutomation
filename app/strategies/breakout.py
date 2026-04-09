from __future__ import annotations

import pandas as pd

from app.strategies.base import BaseStrategy, StrategyMetadata
from app.utils.indicators import rolling_high, rolling_low


class BreakoutStrategy(BaseStrategy):
    metadata = StrategyMetadata(
        name="breakout",
        description="Long-only price breakout strategy with rolling channel exit.",
        default_parameters={
            "lookback": 20,
            "buffer_pct": 0.001,
            "exit_lookback": 10,
            "stop_loss_pct": 0.015,
            "take_profit_pct": 0.035,
        },
    )

    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        df = market_data.copy()
        lookback = int(self.params["lookback"])
        exit_lookback = int(self.params["exit_lookback"])
        buffer_pct = float(self.params["buffer_pct"])
        df["rolling_high"] = rolling_high(df["high"], lookback).shift(1)
        df["rolling_low"] = rolling_low(df["low"], exit_lookback).shift(1)
        breakout_level = df["rolling_high"] * (1 + buffer_pct)
        entry = df["close"] > breakout_level
        exit_signal = df["close"] < df["rolling_low"]
        df["signal"] = entry.astype(int)
        df["entry"] = entry.fillna(False)
        df["exit"] = exit_signal.fillna(False)
        df["confidence"] = ((df["close"] - breakout_level) / df["close"]).fillna(0.0).clip(lower=0.0)
        return df
