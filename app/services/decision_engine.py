from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import DecisionSource, InstrumentType, MarginMode, OrderType, PositionSide
from app.db.models.llm_decision import LLMDecision
from app.services.data_service import DataService
from app.services.execution_service import ExecutionService
from app.services.helpers import record_event
from app.services.llm_service import StructuredDecision, get_llm_service
from app.services.market_depth_service import MarketDepthService
from app.services.news_service import NewsService
from app.services.strategy_registry import StrategyRegistry


class DecisionEngineService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.news_service = NewsService(db=db, settings=settings)
        self.data_service = DataService(db=db, settings=settings)
        self.market_depth_service = MarketDepthService(db=db)
        self.registry = StrategyRegistry()

    def _build_prompt(self, symbol: str, timeframe: str) -> tuple[str, list[dict]]:
        news = self.news_service.list_articles(limit=10)
        market = self.data_service.get_historical_data(symbol=symbol, timeframe=timeframe, limit=120)
        latest_close = float(market["close"].iloc[-1]) if not market.empty else None
        quote = self.market_depth_service.latest_quote(symbol, InstrumentType.PERPETUAL) or self.market_depth_service.latest_quote(
            symbol, InstrumentType.SPOT
        )
        context = {
            "symbol": symbol,
            "timeframe": timeframe,
            "latest_close": latest_close,
            "quote": {
                "best_bid": quote.best_bid,
                "best_ask": quote.best_ask,
                "spread_bps": quote.spread_bps,
                "funding_rate": quote.funding_rate,
            }
            if quote
            else None,
            "news": [
                {"title": article.title, "summary": article.summary, "symbols": article.symbols}
                for article in news[:6]
            ],
        }
        prompt = (
            "Review the market and news context. If there is no clear action, return hold with low confidence. "
            "Never imply guaranteed returns. Use isolated leverage only and keep leverage conservative.\n\n"
            f"{context}"
        )
        return prompt, context["news"]

    def review_symbol(self, symbol: str, timeframe: str = "5m") -> LLMDecision:
        llm = get_llm_service(self.settings)
        prompt, news_context = self._build_prompt(symbol=symbol, timeframe=timeframe)
        structured = llm.generate_trade_decision(prompt, symbol=symbol)
        accepted = False
        reason = "LLM disabled or no decision."
        output: dict = {}
        if structured is not None:
            accepted = structured.action in {"enter", "exit"} and structured.confidence >= 0.55
            reason = structured.thesis
            output = structured.__dict__
        decision = LLMDecision(
            provider=self.settings.llm_provider,
            model=self.settings.llm_model if self.settings.llm_provider == "openai" else self.settings.llm_anthropic_model,
            mode=self.settings.trading_mode,
            decision_source=DecisionSource.LLM,
            symbol=symbol,
            position_side=PositionSide(output.get("position_side", "long")) if output.get("position_side") else None,
            confidence=float(output.get("confidence") or 0.0),
            accepted=accepted,
            reason=reason,
            prompt=prompt,
            context_payload={"news": news_context},
            structured_output=output,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(decision)
        record_event(
            self.db,
            "INFO",
            "llm_decision",
            f"LLM reviewed {symbol}.",
            {"decision_id": decision.id, "accepted": decision.accepted},
        )
        self.db.commit()
        return decision

    def maybe_execute_paper_decision(self, symbol: str, timeframe: str = "5m") -> LLMDecision:
        decision = self.review_symbol(symbol=symbol, timeframe=timeframe)
        if (
            not self.settings.llm_autonomy_paper
            or self.settings.trading_mode.value != "paper"
            or not decision.accepted
        ):
            return decision
        output = decision.structured_output
        if output.get("action") != "enter":
            return decision
        position_side = PositionSide(output.get("position_side", "long"))
        latest = self.data_service.get_historical_data(symbol=symbol, timeframe=timeframe, limit=2)
        price = float(latest["close"].iloc[-1])
        ExecutionService(db=self.db, settings=self.settings, registry=self.registry).submit_entry_order(
            strategy_name="llm_autonomy",
            symbol=symbol,
            reference_price=price,
            order_type=OrderType.MARKET,
            instrument_type=InstrumentType.PERPETUAL,
            margin_mode=MarginMode.ISOLATED,
            leverage=float(output.get("leverage") or self.settings.default_leverage),
            position_side=position_side,
            decision_source=DecisionSource.LLM,
        )
        return decision
