from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.core.enums import InstrumentType
from app.db.session import get_db
from app.schemas.market import OrderBookSnapshotRead, StreamStatusRead
from app.services.market_depth_service import MarketDepthService

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/depth", response_model=OrderBookSnapshotRead)
def latest_depth(
    symbol: str,
    instrument_type: InstrumentType = InstrumentType.PERPETUAL,
    db: Session = Depends(get_db),
) -> OrderBookSnapshotRead:
    service = MarketDepthService(db=db)
    snapshot = service.latest_orderbook(symbol, instrument_type)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No order-book snapshot available.")
    return OrderBookSnapshotRead.model_validate(snapshot, from_attributes=True)


@router.get("/stream-status", response_model=list[StreamStatusRead])
def stream_status(db: Session = Depends(get_db)) -> list[StreamStatusRead]:
    service = MarketDepthService(db=db)
    return [StreamStatusRead.model_validate(item, from_attributes=True) for item in service.list_stream_status()]
