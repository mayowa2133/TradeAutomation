from app.core.config import Settings, get_settings
from app.services.strategy_registry import StrategyRegistry


def get_app_settings() -> Settings:
    return get_settings()


def get_strategy_registry() -> StrategyRegistry:
    return StrategyRegistry()
