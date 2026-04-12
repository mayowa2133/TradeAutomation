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
            "min_breakout_strength_pct": 0.0,
            "stop_loss_pct": 0.015,
            "take_profit_pct": 0.035,
        },
    )

    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        df = market_data.copy()
        lookback = int(self.params["lookback"])
        exit_lookback = int(self.params["exit_lookback"])
        buffer_pct = float(self.params["buffer_pct"])
        min_breakout_strength_pct = float(self.params.get("min_breakout_strength_pct", 0.0))
        df["rolling_high"] = rolling_high(df["high"], lookback).shift(1)
        df["rolling_low"] = rolling_low(df["low"], lookback).shift(1)
        df["exit_high"] = rolling_high(df["high"], exit_lookback).shift(1)
        df["exit_low"] = rolling_low(df["low"], exit_lookback).shift(1)
        breakout_level = df["rolling_high"] * (1 + buffer_pct)
        breakdown_level = df["rolling_low"] * (1 - buffer_pct)
        breakout_strength = ((df["close"] - breakout_level) / df["close"]).clip(lower=0.0).fillna(0.0)
        breakdown_strength = ((breakdown_level - df["close"]) / df["close"]).clip(lower=0.0).fillna(0.0)
        long_entry = (df["close"] > breakout_level) & (breakout_strength >= min_breakout_strength_pct)
        short_entry = (df["close"] < breakdown_level) & (breakdown_strength >= min_breakout_strength_pct)
        long_exit = (df["close"] < df["exit_low"]).fillna(False)
        short_exit = (df["close"] > df["exit_high"]).fillna(False)
        df["signal"] = 0
        df.loc[long_entry, "signal"] = 1
        df.loc[short_entry, "signal"] = -1
        df["entry_long"] = long_entry.fillna(False)
        df["entry_short"] = short_entry.fillna(False)
        df["entry"] = (df["entry_long"] | df["entry_short"]).fillna(False)
        df["exit_long"] = long_exit
        df["exit_short"] = short_exit
        df["exit"] = ((df["exit_long"] | df["exit_short"]) & ~df["entry"]).fillna(False)
        df["confidence"] = 0.0
        df.loc[df["signal"] == 1, "confidence"] = breakout_strength[df["signal"] == 1]
        df.loc[df["signal"] == -1, "confidence"] = breakdown_strength[df["signal"] == -1]
        return df
