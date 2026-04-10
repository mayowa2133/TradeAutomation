from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import feedparser
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.news_article import NewsArticle


@dataclass(slots=True)
class NewsItem:
    source: str
    title: str
    summary: str | None
    url: str
    published_at: datetime | None
    symbols: list[str]


class RSSNewsProvider:
    SYMBOL_KEYWORDS = {
        "BTC": "BTC/USDT",
        "BITCOIN": "BTC/USDT",
        "ETH": "ETH/USDT",
        "ETHEREUM": "ETH/USDT",
        "SOL": "SOL/USDT",
        "SOLANA": "SOL/USDT",
    }

    def fetch(self, feed_urls: list[str]) -> list[NewsItem]:
        items: list[NewsItem] = []
        for url in feed_urls:
            parsed = feedparser.parse(url)
            source = parsed.feed.get("title") or urlparse(url).netloc
            for entry in parsed.entries:
                text_blob = f"{entry.get('title', '')} {entry.get('summary', '')}".upper()
                symbols = sorted(
                    {
                        symbol
                        for keyword, symbol in self.SYMBOL_KEYWORDS.items()
                        if keyword in text_blob
                    }
                )
                published_at = None
                if entry.get("published"):
                    try:
                        published_at = parsedate_to_datetime(entry["published"]).astimezone(timezone.utc)
                    except Exception:
                        published_at = None
                items.append(
                    NewsItem(
                        source=source,
                        title=entry.get("title", "Untitled"),
                        summary=entry.get("summary"),
                        url=entry.get("link", ""),
                        published_at=published_at,
                        symbols=symbols,
                    )
                )
        return items


class NewsService:
    def __init__(self, db: Session, settings: Settings, provider: RSSNewsProvider | None = None) -> None:
        self.db = db
        self.settings = settings
        self.provider = provider or RSSNewsProvider()

    def ingest(self) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for item in self.provider.fetch(self.settings.news_rss_feed_list):
            if not item.url:
                continue
            existing = self.db.query(NewsArticle).filter(NewsArticle.url == item.url).one_or_none()
            if existing is not None:
                articles.append(existing)
                continue
            article = NewsArticle(
                source=item.source,
                title=item.title,
                summary=item.summary,
                url=item.url,
                symbols=item.symbols,
                published_at=item.published_at,
                ingested_at=datetime.now(timezone.utc),
            )
            self.db.add(article)
            articles.append(article)
        self.db.commit()
        return articles

    def list_articles(self, limit: int = 100) -> list[NewsArticle]:
        return self.db.query(NewsArticle).order_by(NewsArticle.ingested_at.desc()).limit(limit).all()
