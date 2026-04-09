from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import Settings


class BaseLLMHooks(ABC):
    @abstractmethod
    def summarize_market_news(self, context: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def explain_signal(self, strategy_name: str, context: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def generate_trade_rationale(self, context: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def review_anomaly(self, context: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def build_daily_summary(self, context: str) -> str | None:
        raise NotImplementedError


class DisabledLLMService(BaseLLMHooks):
    def summarize_market_news(self, context: str) -> str | None:
        return None

    def explain_signal(self, strategy_name: str, context: str) -> str | None:
        return None

    def generate_trade_rationale(self, context: str) -> str | None:
        return None

    def review_anomaly(self, context: str) -> str | None:
        return None

    def build_daily_summary(self, context: str) -> str | None:
        return None


def get_llm_service(settings: Settings) -> BaseLLMHooks:
    if not settings.llm_features_enabled:
        return DisabledLLMService()
    return DisabledLLMService()
