from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.news import NewsArticleRead
from app.services.news_service import NewsService

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=list[NewsArticleRead])
def list_news(
    refresh: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> list[NewsArticleRead]:
    service = NewsService(db=db, settings=settings)
    if refresh:
        service.ingest()
    return [NewsArticleRead.model_validate(item, from_attributes=True) for item in service.list_articles(limit=limit)]
