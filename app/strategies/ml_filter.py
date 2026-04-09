from __future__ import annotations

import pandas as pd

from app.ml.predict import predict_probabilities
from app.strategies.base import BaseStrategy, StrategyMetadata
from app.utils.indicators import ema


class MLFilterStrategy(BaseStrategy):
    metadata = StrategyMetadata(
        name="ml_filter",
        description="Experimental long-only strategy that filters trend signals with a lightweight ML model.",
        default_parameters={
            "model_name": "direction_filter",
            "probability_threshold": 0.56,
            "fast_window": 8,
            "slow_window": 21,
            "stop_loss_pct": 0.015,
            "take_profit_pct": 0.03,
        },
        experimental=True,
    )

    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        df = market_data.copy()
        df["ema_fast"] = ema(df["close"], int(self.params["fast_window"]))
        df["ema_slow"] = ema(df["close"], int(self.params["slow_window"]))
        df["ml_probability"] = 0.5
        try:
            probabilities = predict_probabilities(df, model_name=str(self.params["model_name"]))
            if not probabilities.empty:
                df.loc[probabilities.index, "ml_probability"] = probabilities
        except FileNotFoundError:
            pass
        trend_ok = (df["close"] > df["ema_fast"]) & (df["ema_fast"] > df["ema_slow"])
        entry = trend_ok & (df["ml_probability"] >= float(self.params["probability_threshold"]))
        exit_signal = (df["ml_probability"] <= 0.48) | (df["close"] < df["ema_fast"])
        df["signal"] = entry.astype(int)
        df["entry"] = entry.fillna(False)
        df["exit"] = exit_signal.fillna(False)
        df["confidence"] = df["ml_probability"].fillna(0.5)
        return df
