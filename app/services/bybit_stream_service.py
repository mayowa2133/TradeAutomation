from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import websockets
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import InstrumentType, StreamHealth
from app.db.session import get_session_factory
from app.services.data_service import DataService
from app.services.instrument_service import InstrumentService
from app.services.market_depth_service import MarketDepthService


class BybitStreamService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def stream_name(self) -> str:
        return "bybit_public_linear"

    def _mark_symbols(
        self,
        *,
        db: Session,
        symbols: list[str],
        status: StreamHealth,
        metadata: dict[str, Any] | None = None,
        error_message: str | None = None,
        touch_message: bool = False,
    ) -> None:
        market_depth = MarketDepthService(db=db)
        for symbol in symbols:
            market_depth.update_stream_status(
                stream_name=self.stream_name,
                symbol=symbol,
                status=status,
                metadata=metadata,
                error_message=error_message,
                touch_message=touch_message,
            )

    async def _subscribe(self, websocket, symbols: list[str], db: Session) -> list[str]:
        instrument_service = InstrumentService(db=db, settings=self.settings)
        topics: list[str] = []
        for symbol in symbols:
            raw_symbol = instrument_service.raw_symbol_for_bybit(symbol)
            topics.extend(
                [
                    f"orderbook.50.{raw_symbol}",
                    f"publicTrade.{raw_symbol}",
                    f"tickers.{raw_symbol}",
                ]
            )
        await websocket.send(json.dumps({"op": "subscribe", "args": topics}))
        return topics

    async def _handle_control_message(self, payload: dict[str, Any], symbols: list[str], db: Session) -> bool:
        op = str(payload.get("op") or "")
        if op == "subscribe":
            if payload.get("success") is False:
                raise RuntimeError(f"Bybit websocket subscription failed: {payload.get('ret_msg') or payload}")
            self._mark_symbols(
                db=db,
                symbols=symbols,
                status=StreamHealth.CONNECTING,
                metadata={
                    "phase": "subscribed",
                    "ret_msg": str(payload.get("ret_msg") or "ok"),
                },
                error_message=None,
            )
            return True
        if op == "pong":
            self._mark_symbols(
                db=db,
                symbols=symbols,
                status=StreamHealth.CONNECTING,
                metadata={"phase": "pong"},
                error_message=None,
            )
            return True
        if payload.get("success") is False and op:
            raise RuntimeError(f"Bybit websocket control error: {payload.get('ret_msg') or payload}")
        return False

    async def _handle_message(self, payload: dict[str, Any], db: Session) -> None:
        topic = str(payload.get("topic") or "")
        data = payload.get("data")
        if not topic or data is None:
            return
        market_depth = MarketDepthService(db=db)
        if topic.startswith("orderbook."):
            raw_symbol = topic.split(".")[-1]
            symbol = raw_symbol.replace("USDT", "/USDT")
            bids = [[float(price), float(size)] for price, size in data.get("b", [])[:25]]
            asks = [[float(price), float(size)] for price, size in data.get("a", [])[:25]]
            market_depth.persist_orderbook(
                exchange=self.settings.derivatives_exchange_name,
                symbol=symbol,
                instrument_type=InstrumentType.PERPETUAL,
                bids=bids,
                asks=asks,
                sequence=int(data.get("seq")) if data.get("seq") else None,
            )
            market_depth.update_stream_status(
                stream_name=self.stream_name,
                symbol=symbol,
                status=StreamHealth.HEALTHY,
                metadata={"topic": topic, "type": str(payload.get("type") or "snapshot")},
                touch_message=True,
            )
        elif topic.startswith("publicTrade."):
            raw_symbol = topic.split(".")[-1]
            symbol = raw_symbol.replace("USDT", "/USDT")
            trades = data if isinstance(data, list) else [data]
            for trade in trades[:10]:
                market_depth.persist_tick(
                    exchange=self.settings.derivatives_exchange_name,
                    symbol=symbol,
                    instrument_type=InstrumentType.PERPETUAL,
                    trade_id=str(trade.get("i")) if trade.get("i") else None,
                    side=str(trade.get("S", "buy")).lower(),
                    price=float(trade.get("p")),
                    size=float(trade.get("v")),
                    tick_time=datetime.fromtimestamp(int(trade.get("T")) / 1000, tz=timezone.utc),
                )
            market_depth.update_stream_status(
                stream_name=self.stream_name,
                symbol=symbol,
                status=StreamHealth.HEALTHY,
                metadata={"topic": topic, "type": "trade"},
                touch_message=True,
            )
        elif topic.startswith("tickers."):
            raw_symbol = topic.split(".")[-1]
            symbol = raw_symbol.replace("USDT", "/USDT")
            market_depth.persist_quote(
                exchange=self.settings.derivatives_exchange_name,
                symbol=symbol,
                instrument_type=InstrumentType.PERPETUAL,
                best_bid=float(data.get("bid1Price") or 0.0),
                best_ask=float(data.get("ask1Price") or 0.0),
                bid_size=float(data.get("bid1Size") or 0.0),
                ask_size=float(data.get("ask1Size") or 0.0),
                last_price=float(data.get("lastPrice") or 0.0),
                mark_price=float(data.get("markPrice") or 0.0),
                index_price=float(data.get("indexPrice") or 0.0),
                funding_rate=float(data.get("fundingRate")) if data.get("fundingRate") is not None else None,
            )
            if data.get("fundingRate") is not None:
                market_depth.persist_funding_rate(
                    exchange=self.settings.derivatives_exchange_name,
                    symbol=symbol,
                    funding_rate=float(data.get("fundingRate")),
                    mark_price=float(data.get("markPrice") or 0.0),
                    index_price=float(data.get("indexPrice") or 0.0),
                )
            market_depth.update_stream_status(
                stream_name=self.stream_name,
                symbol=symbol,
                status=StreamHealth.HEALTHY,
                metadata={"topic": topic, "type": "ticker"},
                touch_message=True,
            )

    async def run(self, symbols: list[str] | None = None) -> None:
        target_symbols = symbols or self.settings.symbol_allowlist_list
        retry_delay = 2
        attempt = 0
        while True:
            attempt += 1
            with get_session_factory()() as db:
                self._mark_symbols(
                    db=db,
                    symbols=target_symbols,
                    status=StreamHealth.CONNECTING,
                    metadata={"phase": "connecting", "attempt": attempt},
                    error_message=None,
                )
            try:
                async with websockets.connect(
                    self.settings.bybit_ws_public_url,
                    ping_interval=20,
                    ping_timeout=20,
                    open_timeout=max(10, min(self.settings.stream_message_timeout_seconds, 30)),
                    close_timeout=5,
                ) as ws:
                    with get_session_factory()() as db:
                        InstrumentService(db=db, settings=self.settings).sync_perpetual_instruments(target_symbols)
                        topics = await self._subscribe(ws, target_symbols, db)
                        self._mark_symbols(
                            db=db,
                            symbols=target_symbols,
                            status=StreamHealth.CONNECTING,
                            metadata={"phase": "subscription_sent", "topic_count": len(topics), "attempt": attempt},
                            error_message=None,
                        )
                    with get_session_factory()() as db:
                        data_service = DataService(db=db, settings=self.settings)
                        for symbol in target_symbols:
                            for timeframe in self.settings.default_timeframes_list:
                                data_service.get_historical_data(
                                    symbol=symbol,
                                    timeframe=timeframe,
                                    limit=120,
                                    instrument_type=InstrumentType.PERPETUAL,
                                )
                    retry_delay = 2
                    while True:
                        try:
                            message = await asyncio.wait_for(
                                ws.recv(),
                                timeout=self.settings.stream_message_timeout_seconds,
                            )
                        except asyncio.TimeoutError as exc:
                            raise RuntimeError(
                                f"No websocket payload received in {self.settings.stream_message_timeout_seconds} seconds."
                            ) from exc
                        payload = json.loads(message)
                        if str(payload.get("op") or "") == "ping":
                            await ws.send(json.dumps({"op": "pong"}))
                        with get_session_factory()() as db:
                            if await self._handle_control_message(payload, target_symbols, db):
                                continue
                            await self._handle_message(payload, db)
            except Exception as exc:
                with get_session_factory()() as db:
                    self._mark_symbols(
                        db=db,
                        symbols=target_symbols,
                        status=StreamHealth.DEGRADED,
                        metadata={
                            "phase": "reconnecting",
                            "attempt": attempt,
                            "retry_delay_seconds": retry_delay,
                        },
                        error_message=str(exc),
                    )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
