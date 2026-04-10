from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.core.enums import InstrumentType
from app.db.models.instrument import Instrument
from app.db.session import get_db
from app.schemas.instrument import InstrumentRead
from app.services.instrument_service import InstrumentService

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("", response_model=list[InstrumentRead])
def list_instruments(
    instrument_type: InstrumentType | None = None,
    sync: bool = False,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> list[InstrumentRead]:
    service = InstrumentService(db=db, settings=settings)
    if sync and (instrument_type in {None, InstrumentType.PERPETUAL}):
        service.sync_perpetual_instruments(settings.symbol_allowlist_list)
    query = db.query(Instrument).order_by(Instrument.exchange.asc(), Instrument.symbol.asc())
    if instrument_type is not None:
        query = query.filter(Instrument.instrument_type == instrument_type)
    return [InstrumentRead.model_validate(item) for item in query.all()]
