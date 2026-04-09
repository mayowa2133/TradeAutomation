from __future__ import annotations

import pandas as pd

from app.strategies.base import BaseStrategy, StrategyMetadata
from app.utils.indicators import ema, rsi


class RSIMeanReversionStrategy(BaseStrategy):
    metadata = StrategyMetadata(
        name="rsi_mean_reversion",
        description="Long-only RSI mean reversion with trend confirmation.",
        default_parameters={
            "rsi_window": 14,
            "oversold": 30,
            "exit_rsi": 55,
            "trend_window": 50,
            "stop_loss_pct": 0.012,
            "take_profit_pct": 0.025,
        },
    )

    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        df = market_data.copy()
        df["rsi"] = rsi(df["close"], int(self.params["rsi_window"]))
        df["trend_ema"] = ema(df["close"], int(self.params["trend_window"]))
        entry = (df["rsi"] <= float(self.params["oversold"])) & (df["close"] >= df["trend_ema"])
        exit_signal = (df["rsi"] >= float(self.params["exit_rsi"])) | (df["close"] < df["trend_ema"])
        df["signal"] = entry.astype(int)
        df["entry"] = entry.fillna(False)
        df["exit"] = exit_signal.fillna(False)
        df["confidence"] = ((50 - df["rsi"]).abs() / 50).clip(lower=0.0, upper=1.0)
        return df
