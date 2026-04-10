from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic
from openai import OpenAI

from app.core.config import Settings


@dataclass(slots=True)
class StructuredDecision:
    summary: str
    thesis: str
    action: str
    symbol: str
    position_side: str
    confidence: float
    invalidation: str
    leverage: float


class BaseLLMHooks(ABC):
    @abstractmethod
    def summarize_market_news(self, context: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def generate_trade_decision(self, prompt: str, symbol: str) -> StructuredDecision | None:
        raise NotImplementedError


class DisabledLLMService(BaseLLMHooks):
    def summarize_market_news(self, context: str) -> str | None:
        return None

    def generate_trade_decision(self, prompt: str, symbol: str) -> StructuredDecision | None:
        return None


class OpenAILLMService(BaseLLMHooks):
    def __init__(self, settings: Settings) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model

    def summarize_market_news(self, context: str) -> str | None:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Summarize the market news in 4 sentences max."},
                {"role": "user", "content": context},
            ],
        )
        return response.choices[0].message.content

    def generate_trade_decision(self, prompt: str, symbol: str) -> StructuredDecision | None:
        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return strict JSON with keys: summary, thesis, action, symbol, position_side, "
                        "confidence, invalidation, leverage. Use action in {enter, exit, hold}."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        payload.setdefault("symbol", symbol)
        return StructuredDecision(**payload)


class ClaudeLLMService(BaseLLMHooks):
    def __init__(self, settings: Settings) -> None:
        self.client = Anthropic(api_key=settings.claude_api_key)
        self.model = settings.llm_anthropic_model

    def summarize_market_news(self, context: str) -> str | None:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            system="Summarize the market news in 4 sentences max.",
            messages=[{"role": "user", "content": context}],
        )
        text = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        return "\n".join(text) if text else None

    def generate_trade_decision(self, prompt: str, symbol: str) -> StructuredDecision | None:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            system=(
                "Return strict JSON with keys: summary, thesis, action, symbol, position_side, "
                "confidence, invalidation, leverage. Use action in {enter, exit, hold}."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        payload: dict[str, Any] = json.loads(text or "{}")
        payload.setdefault("symbol", symbol)
        return StructuredDecision(**payload)


def get_llm_service(settings: Settings) -> BaseLLMHooks:
    if not settings.llm_features_enabled:
        return DisabledLLMService()
    if settings.llm_provider.lower() == "claude" and settings.claude_api_key:
        return ClaudeLLMService(settings)
    if settings.openai_api_key:
        return OpenAILLMService(settings)
    return DisabledLLMService()
