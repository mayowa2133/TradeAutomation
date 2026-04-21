from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import TradingError
from app.db.models.strategy_config import StrategyConfigModel
from app.strategies.base import BaseStrategy
from app.strategies.breakout import BreakoutStrategy
from app.strategies.ema_crossover import EMACrossoverStrategy
from app.strategies.ml_filter import MLFilterStrategy
from app.strategies.rsi_mean_reversion import RSIMeanReversionStrategy


class StrategyRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, type[BaseStrategy]] = {
            EMACrossoverStrategy.metadata.name: EMACrossoverStrategy,
            RSIMeanReversionStrategy.metadata.name: RSIMeanReversionStrategy,
            BreakoutStrategy.metadata.name: BreakoutStrategy,
            MLFilterStrategy.metadata.name: MLFilterStrategy,
        }

    def names(self) -> list[str]:
        return sorted(self._registry.keys())

    def sync_configs(self, db: Session) -> None:
        existing = {
            row.name: row for row in db.query(StrategyConfigModel).filter(StrategyConfigModel.name.in_(self.names()))
        }
        for name, strategy_cls in self._registry.items():
            if name not in existing:
                metadata = strategy_cls.describe()
                db.add(
                    StrategyConfigModel(
                        name=name,
                        enabled=True,
                        description=metadata["description"],
                        parameters=metadata["parameters"],
                        experimental=metadata["experimental"],
                    )
                )
        db.commit()

    def get_db_config(self, db: Session, name: str) -> StrategyConfigModel:
        self.sync_configs(db)
        config = db.query(StrategyConfigModel).filter(StrategyConfigModel.name == name).one_or_none()
        if config is None:
            raise TradingError(f"Unknown strategy: {name}")
        return config

    def list_strategies(self, db: Session) -> list[dict[str, Any]]:
        self.sync_configs(db)
        results = []
        for config in db.query(StrategyConfigModel).order_by(StrategyConfigModel.name.asc()).all():
            results.append(
                {
                    "name": config.name,
                    "description": config.description,
                    "experimental": config.experimental,
                    "enabled": config.enabled,
                    "parameters": config.parameters,
                }
            )
        return results

    def create_strategy(
        self,
        name: str,
        db: Session | None = None,
        overrides: dict[str, Any] | None = None,
        symbol: str | None = None,
    ) -> BaseStrategy:
        strategy_cls = self._registry.get(name)
        if strategy_cls is None:
            raise TradingError(f"Unknown strategy: {name}")
        parameters: dict[str, Any] = {}
        if db is not None:
            config = self.get_db_config(db, name)
            parameters.update(config.parameters)
            symbol_overrides = parameters.get("symbol_overrides")
            if symbol and isinstance(symbol_overrides, dict):
                symbol_parameters = symbol_overrides.get(symbol)
                if isinstance(symbol_parameters, dict):
                    parameters.update(symbol_parameters)
        if overrides:
            parameters.update(overrides)
        return strategy_cls(parameters=parameters)
