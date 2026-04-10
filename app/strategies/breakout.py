from __future__ import annotations

import pandas as pd

from app.strategies.base import BaseStrategy, StrategyMetadata
from app.utils.indicators import rolling_high, rolling_low


class BreakoutStrategy(BaseStrategy):
    metadata = StrategyMetadata(
        name="breakout",
        description="Bidirectional channel breakout strategy with rolling breakout and breakdown entries.",
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
        breakdown_level = df["rolling_low"] * (1 - buffer_pct)
        long_entry = df["close"] > breakout_level
        short_entry = df["close"] < breakdown_level
        exit_signal = (df["close"] < df["rolling_low"]) | (df["close"] > df["rolling_high"])
        df["signal"] = 0
        df.loc[long_entry, "signal"] = 1
        df.loc[short_entry, "signal"] = -1
        df["entry"] = (long_entry | short_entry).fillna(False)
        df["exit"] = exit_signal.fillna(False)
        breakout_distance = ((df["close"] - breakout_level).abs() / df["close"]).fillna(0.0)
        breakdown_distance = ((breakdown_level - df["close"]).abs() / df["close"]).fillna(0.0)
        df["confidence"] = breakout_distance.where(df["signal"] >= 0, breakdown_distance).clip(lower=0.0)
        return df
