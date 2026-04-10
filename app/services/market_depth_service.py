from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.enums import InstrumentType, OrderSide, StreamHealth
from app.db.models.funding_rate import FundingRate
from app.db.models.market_tick import MarketTick
from app.db.models.orderbook_snapshot import OrderBookSnapshot
from app.db.models.quote_snapshot import QuoteSnapshot
from app.db.models.stream_status import StreamStatus


class MarketDepthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def persist_orderbook(
        self,
        *,
        exchange: str,
        symbol: str,
        instrument_type: InstrumentType,
        bids: list[list[float]],
        asks: list[list[float]],
        sequence: int | None = None,
        snapshot_time: datetime | None = None,
    ) -> OrderBookSnapshot:
        snapshot_time = snapshot_time or datetime.now(timezone.utc)
        top_bid = float(bids[0][0]) if bids else 0.0
        top_ask = float(asks[0][0]) if asks else 0.0
        mid_price = ((top_bid + top_ask) / 2.0) if top_bid and top_ask else None
        snapshot = OrderBookSnapshot(
            exchange=exchange,
            symbol=symbol,
            instrument_type=instrument_type,
            sequence=sequence,
            depth=min(len(bids), len(asks)),
            bids=bids,
            asks=asks,
            mid_price=mid_price,
            snapshot_time=snapshot_time,
        )
        self.db.add(snapshot)
        self.db.flush()
        if bids and asks:
            self.persist_quote(
                exchange=exchange,
                symbol=symbol,
                instrument_type=instrument_type,
                best_bid=top_bid,
                best_ask=top_ask,
                bid_size=float(bids[0][1]),
                ask_size=float(asks[0][1]),
                snapshot_time=snapshot_time,
            )
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def persist_quote(
        self,
        *,
        exchange: str,
        symbol: str,
        instrument_type: InstrumentType,
        best_bid: float,
        best_ask: float,
        bid_size: float,
        ask_size: float,
        last_price: float | None = None,
        mark_price: float | None = None,
        index_price: float | None = None,
        funding_rate: float | None = None,
        snapshot_time: datetime | None = None,
    ) -> QuoteSnapshot:
        snapshot_time = snapshot_time or datetime.now(timezone.utc)
        mid = ((best_bid + best_ask) / 2.0) if best_bid and best_ask else None
        spread_bps = (((best_ask - best_bid) / mid) * 10_000.0) if mid else 0.0
        quote = QuoteSnapshot(
            exchange=exchange,
            symbol=symbol,
            instrument_type=instrument_type,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_size=bid_size,
            ask_size=ask_size,
            last_price=last_price,
            mark_price=mark_price,
            index_price=index_price,
            funding_rate=funding_rate,
            spread_bps=spread_bps,
            snapshot_time=snapshot_time,
        )
        self.db.add(quote)
        self.db.commit()
        self.db.refresh(quote)
        return quote

    def persist_tick(
        self,
        *,
        exchange: str,
        symbol: str,
        instrument_type: InstrumentType,
        trade_id: str | None,
        side: str,
        price: float,
        size: float,
        tick_time: datetime | None = None,
    ) -> MarketTick:
        tick = MarketTick(
            exchange=exchange,
            symbol=symbol,
            instrument_type=instrument_type,
            trade_id=trade_id,
            side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
            price=price,
            size=size,
            tick_time=tick_time or datetime.now(timezone.utc),
        )
        self.db.add(tick)
        self.db.commit()
        self.db.refresh(tick)
        return tick

    def persist_funding_rate(
        self,
        *,
        exchange: str,
        symbol: str,
        funding_rate: float,
        mark_price: float | None = None,
        index_price: float | None = None,
        next_funding_time: datetime | None = None,
    ) -> FundingRate:
        record = FundingRate(
            exchange=exchange,
            symbol=symbol,
            instrument_type=InstrumentType.PERPETUAL,
            funding_rate=funding_rate,
            mark_price=mark_price,
            index_price=index_price,
            next_funding_time=next_funding_time,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def latest_orderbook(self, symbol: str, instrument_type: InstrumentType) -> OrderBookSnapshot | None:
        return (
            self.db.query(OrderBookSnapshot)
            .filter(
                OrderBookSnapshot.symbol == symbol,
                OrderBookSnapshot.instrument_type == instrument_type,
            )
            .order_by(OrderBookSnapshot.snapshot_time.desc())
            .first()
        )

    def latest_quote(self, symbol: str, instrument_type: InstrumentType) -> QuoteSnapshot | None:
        return (
            self.db.query(QuoteSnapshot)
            .filter(
                QuoteSnapshot.symbol == symbol,
                QuoteSnapshot.instrument_type == instrument_type,
            )
            .order_by(QuoteSnapshot.snapshot_time.desc())
            .first()
        )

    def latest_funding_rate(self, symbol: str) -> FundingRate | None:
        return (
            self.db.query(FundingRate)
            .filter(FundingRate.symbol == symbol)
            .order_by(FundingRate.observed_at.desc())
            .first()
        )

    def list_stream_status(self) -> list[StreamStatus]:
        return self.db.query(StreamStatus).order_by(StreamStatus.stream_name.asc(), StreamStatus.symbol.asc()).all()

    def update_stream_status(
        self,
        *,
        stream_name: str,
        symbol: str,
        status: StreamHealth,
        metadata: dict | None = None,
        error_message: str | None = None,
        touch_message: bool = False,
    ) -> StreamStatus:
        record = (
            self.db.query(StreamStatus)
            .filter(StreamStatus.stream_name == stream_name, StreamStatus.symbol == symbol)
            .one_or_none()
        )
        now = datetime.now(timezone.utc)
        if record is None:
            record = StreamStatus(stream_name=stream_name, symbol=symbol, status=status)
            self.db.add(record)
        record.status = status
        record.stream_metadata = metadata or record.stream_metadata or {}
        record.error_message = error_message
        record.last_heartbeat_at = now
        if touch_message:
            record.last_message_at = now
        self.db.commit()
        self.db.refresh(record)
        return record
