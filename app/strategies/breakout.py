from __future__ import annotations

import pandas as pd

from app.strategies.base import BaseStrategy, StrategyMetadata
from app.utils.indicators import rolling_high, rolling_low
from app.utils.timeframes import timeframe_to_pandas_freq


class BreakoutStrategy(BaseStrategy):
    metadata = StrategyMetadata(
        name="breakout",
        description="Bidirectional channel breakout strategy with rolling breakout and breakdown entries.",
        default_parameters={
            "lookback": 20,
            "buffer_pct": 0.001,
            "exit_lookback": 10,
            "min_breakout_strength_pct": 0.0,
            "min_atr_pct": 0.0,
            "min_volume_ratio": 0.0,
            "max_breakout_extension_pct": 0.05,
            "trend_timeframe": "1h",
            "trend_ema_window": 24,
            "trend_margin_pct": 0.0,
            "allow_long": True,
            "allow_short": True,
            "stop_loss_pct": 0.015,
            "take_profit_pct": 0.035,
        },
    )

    def _true_range_pct(self, market_data: pd.DataFrame, window: int) -> pd.Series:
        previous_close = market_data["close"].shift(1)
        true_range = pd.concat(
            [
                market_data["high"] - market_data["low"],
                (market_data["high"] - previous_close).abs(),
                (market_data["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = true_range.rolling(window=window, min_periods=window).mean()
        return (atr / market_data["close"]).fillna(0.0)

    def _volume_ratio(self, market_data: pd.DataFrame, window: int) -> pd.Series:
        volume_ma = market_data["volume"].rolling(window=window, min_periods=window).mean()
        return (market_data["volume"] / volume_ma.replace(0, pd.NA)).fillna(0.0)

    def _higher_timeframe_trend_bias(
        self,
        market_data: pd.DataFrame,
        trend_timeframe: str,
        trend_ema_window: int,
    ) -> pd.Series:
        if market_data.empty:
            return pd.Series(dtype=float, index=market_data.index)
        trend_frame = market_data[["open", "high", "low", "close", "volume"]].resample(
            timeframe_to_pandas_freq(trend_timeframe)
        ).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        if trend_frame.empty:
            return pd.Series(0.0, index=market_data.index)
        trend_frame["trend_ema"] = trend_frame["close"].ewm(span=trend_ema_window, adjust=False).mean()
        trend_frame["trend_bias"] = (
            (trend_frame["close"] - trend_frame["trend_ema"]) / trend_frame["trend_ema"].replace(0, pd.NA)
        ).fillna(0.0)
        completed_bias = trend_frame["trend_bias"].shift(1)
        return completed_bias.reindex(market_data.index, method="ffill").fillna(0.0)

    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        df = market_data.copy()
        lookback = int(self.params["lookback"])
        exit_lookback = int(self.params["exit_lookback"])
        buffer_pct = float(self.params["buffer_pct"])
        min_breakout_strength_pct = float(self.params.get("min_breakout_strength_pct", 0.0))
        min_atr_pct = float(self.params.get("min_atr_pct", 0.0))
        min_volume_ratio = float(self.params.get("min_volume_ratio", 0.0))
        max_breakout_extension_pct = float(self.params.get("max_breakout_extension_pct", 0.02))
        trend_timeframe = str(self.params.get("trend_timeframe", "1h"))
        trend_ema_window = int(self.params.get("trend_ema_window", 24))
        trend_margin_pct = float(self.params.get("trend_margin_pct", 0.0))
        atr_window = int(self.params.get("atr_window", 14))
        volume_window = int(self.params.get("volume_window", max(lookback, 10)))
        allow_long = bool(self.params.get("allow_long", True))
        allow_short = bool(self.params.get("allow_short", True))
        df["rolling_high"] = rolling_high(df["high"], lookback).shift(1)
        df["rolling_low"] = rolling_low(df["low"], lookback).shift(1)
        df["exit_high"] = rolling_high(df["high"], exit_lookback).shift(1)
        df["exit_low"] = rolling_low(df["low"], exit_lookback).shift(1)
        df["atr_pct"] = self._true_range_pct(df, atr_window)
        df["volume_ratio"] = self._volume_ratio(df, volume_window)
        df["trend_bias"] = self._higher_timeframe_trend_bias(df, trend_timeframe, trend_ema_window)
        breakout_level = df["rolling_high"] * (1 + buffer_pct)
        breakdown_level = df["rolling_low"] * (1 - buffer_pct)
        breakout_strength = ((df["close"] - breakout_level) / df["close"]).clip(lower=0.0).fillna(0.0)
        breakdown_strength = ((breakdown_level - df["close"]) / df["close"]).clip(lower=0.0).fillna(0.0)
        long_extension = ((df["close"] - breakout_level) / breakout_level.replace(0, pd.NA)).clip(lower=0.0).fillna(0.0)
        short_extension = ((breakdown_level - df["close"]) / breakdown_level.replace(0, pd.NA)).clip(lower=0.0).fillna(0.0)
        long_trend_ok = df["trend_bias"] >= trend_margin_pct
        short_trend_ok = df["trend_bias"] <= -trend_margin_pct
        atr_ok = df["atr_pct"] >= min_atr_pct
        volume_ok = df["volume_ratio"] >= min_volume_ratio
        long_entry = (
            (df["close"] > breakout_level)
            & (breakout_strength >= min_breakout_strength_pct)
            & (long_extension <= max_breakout_extension_pct)
            & atr_ok
            & volume_ok
            & long_trend_ok
        )
        short_entry = (
            (df["close"] < breakdown_level)
            & (breakdown_strength >= min_breakout_strength_pct)
            & (short_extension <= max_breakout_extension_pct)
            & atr_ok
            & volume_ok
            & short_trend_ok
        )
        if not allow_long:
            long_entry = pd.Series(False, index=df.index)
        if not allow_short:
            short_entry = pd.Series(False, index=df.index)
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
        if (df["signal"] == 1).any():
            long_quality = (
                breakout_strength
                * df["volume_ratio"].clip(lower=0.0, upper=3.0)
                * (1 + df["atr_pct"].clip(lower=0.0, upper=0.1))
                * (1 + df["trend_bias"].clip(lower=0.0, upper=0.1))
            )
            df.loc[df["signal"] == 1, "confidence"] = long_quality[df["signal"] == 1]
        if (df["signal"] == -1).any():
            short_quality = (
                breakdown_strength
                * df["volume_ratio"].clip(lower=0.0, upper=3.0)
                * (1 + df["atr_pct"].clip(lower=0.0, upper=0.1))
                * (1 + (-df["trend_bias"]).clip(lower=0.0, upper=0.1))
            )
            df.loc[df["signal"] == -1, "confidence"] = short_quality[df["signal"] == -1]
        return df
