from __future__ import annotations

import pandas as pd

from app.utils.indicators import ema, rsi, zscore


FEATURE_COLUMNS = [
    "return_1",
    "return_3",
    "range_pct",
    "ema_spread",
    "rsi_14",
    "volatility_10",
    "volume_zscore_20",
]


def engineer_features(market_data: pd.DataFrame) -> pd.DataFrame:
    df = market_data.copy()
    df["return_1"] = df["close"].pct_change(1)
    df["return_3"] = df["close"].pct_change(3)
    df["range_pct"] = (df["high"] - df["low"]) / df["close"]
    df["ema_fast"] = ema(df["close"], 8)
    df["ema_slow"] = ema(df["close"], 21)
    df["ema_spread"] = (df["ema_fast"] - df["ema_slow"]) / df["close"]
    df["rsi_14"] = rsi(df["close"], 14)
    df["volatility_10"] = df["return_1"].rolling(window=10, min_periods=10).std().fillna(0.0)
    df["volume_zscore_20"] = zscore(df["volume"], 20)
    return df


def build_training_frame(market_data: pd.DataFrame, horizon: int = 3) -> pd.DataFrame:
    df = engineer_features(market_data)
    df["future_return"] = df["close"].shift(-horizon) / df["close"] - 1
    df["target"] = (df["future_return"] > 0).astype(int)
    return df.dropna().copy()
