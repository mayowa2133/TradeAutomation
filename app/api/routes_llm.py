from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.models.llm_decision import LLMDecision
from app.db.session import get_db
from app.schemas.llm import LLMDecisionRead, LLMDecisionRequest
from app.services.decision_engine import DecisionEngineService

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/decisions", response_model=list[LLMDecisionRead])
def list_llm_decisions(limit: int = 50, db: Session = Depends(get_db)) -> list[LLMDecisionRead]:
    rows = db.query(LLMDecision).order_by(LLMDecision.created_at.desc()).limit(limit).all()
    return [LLMDecisionRead.model_validate(item, from_attributes=True) for item in rows]


@router.post("/decisions", response_model=LLMDecisionRead)
def review_symbol_with_llm(
    request: LLMDecisionRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> LLMDecisionRead:
    try:
        decision = DecisionEngineService(db=db, settings=settings).review_symbol(
            symbol=request.symbol,
            timeframe=request.timeframe,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LLMDecisionRead.model_validate(decision, from_attributes=True)
