from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class StrategyMetadata:
    name: str
    description: str
    default_parameters: dict[str, Any] = field(default_factory=dict)
    experimental: bool = False


class BaseStrategy(ABC):
    metadata = StrategyMetadata(name="base", description="Base strategy", default_parameters={})

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        merged = dict(self.metadata.default_parameters)
        if parameters:
            merged.update(parameters)
        self.params = merged

    @abstractmethod
    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """Return a DataFrame with at least signal, entry, exit columns."""

    def should_enter(self, row: pd.Series, has_position: bool) -> bool:
        return bool(row.get("entry", False)) and not has_position

    def should_exit(self, row: pd.Series, has_position: bool) -> bool:
        return bool(row.get("exit", False)) and has_position

    def stop_loss_pct(self) -> float:
        return float(self.params.get("stop_loss_pct", 0.02))

    def take_profit_pct(self) -> float:
        return float(self.params.get("take_profit_pct", 0.04))

    def position_size(
        self,
        cash_balance: float,
        price: float,
        risk_fraction: float,
        max_notional_fraction: float,
    ) -> float:
        if cash_balance <= 0 or price <= 0:
            return 0.0
        risk_budget = cash_balance * risk_fraction
        stop_distance = max(price * self.stop_loss_pct(), price * 0.0025)
        qty_by_risk = risk_budget / stop_distance
        qty_by_notional = (cash_balance * max_notional_fraction) / price
        quantity = min(qty_by_risk, qty_by_notional)
        return round(max(quantity, 0.0), 8)

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "name": cls.metadata.name,
            "description": cls.metadata.description,
            "experimental": cls.metadata.experimental,
            "parameters": cls.metadata.default_parameters,
        }
