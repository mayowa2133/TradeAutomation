from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.core.exceptions import TradingError
from app.db.session import get_db
from app.schemas.order import ManualOrderRequest, OrderCancelResponse, OrderRead
from app.services.execution_service import ExecutionService
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderRead])
def list_orders(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> list[OrderRead]:
    service = PortfolioService(db=db, settings=settings)
    return [OrderRead.model_validate(order) for order in service.get_orders()]


@router.post("/manual", response_model=OrderRead)
def submit_manual_order(
    request: ManualOrderRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> OrderRead:
    service = ExecutionService(db=db, settings=settings)
    try:
        order = service.manual_order(
            symbol=request.symbol,
            instrument_type=request.instrument_type,
            position_side=request.position_side,
            quantity=request.quantity,
            reference_price=request.reference_price,
            order_type=request.order_type,
            limit_price=request.limit_price,
            leverage=request.leverage,
        )
    except TradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrderRead.model_validate(order)


@router.post("/{order_id}/cancel", response_model=OrderCancelResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> OrderCancelResponse:
    service = ExecutionService(db=db, settings=settings)
    try:
        order = service.cancel_order(order_id)
    except TradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrderCancelResponse(order_id=order.id, status=order.status, message="Order canceled.")
