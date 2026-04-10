from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

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

    async def _subscribe(self, websocket, symbols: list[str], db: Session) -> None:
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

    async def _handle_message(self, payload: dict, db: Session) -> None:
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
                stream_name="bybit_public_linear",
                symbol=symbol,
                status=StreamHealth.HEALTHY,
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

    async def run(self, symbols: list[str] | None = None) -> None:
        target_symbols = symbols or self.settings.symbol_allowlist_list
        retry_delay = 2
        while True:
            try:
                async with websockets.connect(self.settings.bybit_ws_public_url, ping_interval=20, ping_timeout=20) as ws:
                    with get_session_factory()() as db:
                        InstrumentService(db=db, settings=self.settings).sync_perpetual_instruments(target_symbols)
                        await self._subscribe(ws, target_symbols, db)
                        for symbol in target_symbols:
                            MarketDepthService(db=db).update_stream_status(
                                stream_name="bybit_public_linear",
                                symbol=symbol,
                                status=StreamHealth.CONNECTING,
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
                        message = await ws.recv()
                        payload = json.loads(message)
                        with get_session_factory()() as db:
                            await self._handle_message(payload, db)
            except Exception as exc:
                with get_session_factory()() as db:
                    depth_service = MarketDepthService(db=db)
                    for symbol in target_symbols:
                        depth_service.update_stream_status(
                            stream_name="bybit_public_linear",
                            symbol=symbol,
                            status=StreamHealth.DEGRADED,
                            error_message=str(exc),
                        )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
