from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.optimizer_run import OptimizerRun
from app.services.data_service import DataService
from app.services.portfolio_service import PortfolioService


class OptimizerService:
    def __init__(self, db: Session, settings: Settings, data_service: DataService | None = None) -> None:
        self.db = db
        self.settings = settings
        self.data_service = data_service or DataService(db=db, settings=settings)
        self.portfolio_service = PortfolioService(db=db, settings=settings)

    def _build_returns(self, symbols: list[str], timeframe: str, limit: int) -> pd.DataFrame:
        frames: list[pd.Series] = []
        for symbol in symbols:
            data = self.data_service.get_historical_data(symbol=symbol, timeframe=timeframe, limit=limit)
            if data.empty:
                continue
            returns = data["close"].pct_change().rename(symbol)
            frames.append(returns)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1).dropna()

    def run_optimizer(
        self,
        symbols: list[str],
        timeframe: str = "5m",
        signal_strengths: dict[str, float] | None = None,
    ) -> OptimizerRun:
        signal_strengths = signal_strengths or {symbol: 1.0 for symbol in symbols}
        portfolio = self.portfolio_service.recalculate_state()
        returns = self._build_returns(symbols, timeframe, self.settings.optimizer_lookback_periods)
        if returns.empty:
            weights = {symbol: round(1.0 / len(symbols), 4) for symbol in symbols} if symbols else {}
            metrics = {"reason": "insufficient_data", "annualized_volatility": {}, "correlation_penalty": {}}
        else:
            covariance = returns.cov().fillna(0.0)
            vol = returns.std(ddof=0).replace(0, np.nan).fillna(returns.std(ddof=0).mean() or 1.0)
            correlation = returns.corr().fillna(0.0)
            raw_scores: dict[str, float] = {}
            penalties: dict[str, float] = {}
            for symbol in returns.columns:
                mean_abs_corr = correlation.loc[symbol].drop(symbol).abs().mean() if len(correlation.columns) > 1 else 0.0
                penalties[symbol] = 1.0 / (1.0 + float(mean_abs_corr or 0.0))
                raw_scores[symbol] = float(signal_strengths.get(symbol, 1.0)) * penalties[symbol] / float(vol[symbol])
            total_score = sum(max(score, 0.0) for score in raw_scores.values()) or 1.0
            unclipped = {symbol: max(score, 0.0) / total_score for symbol, score in raw_scores.items()}
            weights = {
                symbol: min(weight, self.settings.optimizer_max_weight) for symbol, weight in unclipped.items()
            }
            positive = {symbol: weight for symbol, weight in weights.items() if weight > 0}
            weight_sum = sum(positive.values()) or 1.0
            weights = {symbol: round(weight / weight_sum, 4) for symbol, weight in positive.items()}
            metrics = {
                "annualized_volatility": {
                    symbol: round(float(vol[symbol]) * math.sqrt(len(returns)), 6) for symbol in vol.index
                },
                "correlation_penalty": {symbol: round(value, 6) for symbol, value in penalties.items()},
                "covariance": covariance.round(8).to_dict(),
            }

        deployable_equity = max(portfolio.last_equity * self.settings.max_position_notional_pct, 0.0)
        target_notional = {symbol: round(weight * deployable_equity, 2) for symbol, weight in weights.items()}
        allocations = {
            "weights": weights,
            "target_notional": target_notional,
            "deployable_equity": round(deployable_equity, 2),
        }

        run = OptimizerRun(
            name="volatility_risk_budget",
            status="completed",
            inputs={
                "symbols": symbols,
                "timeframe": timeframe,
                "signal_strengths": signal_strengths,
                "lookback_periods": self.settings.optimizer_lookback_periods,
            },
            allocations=allocations,
            metrics=metrics,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def latest_run(self) -> OptimizerRun | None:
        return self.db.query(OptimizerRun).order_by(OptimizerRun.created_at.desc()).first()
