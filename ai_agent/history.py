"""Persistent store for generated articles.

Uses SQLAlchemy so the backend can be SQLite (default, file-based) or any
supported engine via ``HISTORY_DB_URL``. Each row captures enough context to
re-publish, reference for internal links, or deduplicate against.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base


Base = declarative_base()


class ArticleHistory(Base):
    __tablename__ = "article_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    topic = Column(String, default="")
    title = Column(String, default="")
    slug = Column(String, default="")
    primary_keyword = Column(String, default="")
    keywords = Column(JSON, default=list)
    meta_description = Column(Text, default="")
    body_html = Column(Text, default="")
    body_raw = Column(Text, default="")

    llm_provider = Column(String, default="")
    llm_model = Column(String, default="")

    related_seen = Column(JSON, default=list)
    external_links = Column(JSON, default=list)
    published_to = Column(JSON, default=list)


def _default_url() -> str:
    url = os.getenv("HISTORY_DB_URL")
    if url:
        return url
    default = Path(os.getenv("HISTORY_DB_PATH", "./data/history.db")).resolve()
    default.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{default}"


class HistoryStore:
    def __init__(self, url: str | None = None):
        self.url = url or _default_url()
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        self.engine = create_engine(self.url, connect_args=connect_args, future=True)
        Base.metadata.create_all(self.engine)

    # -- writes --------------------------------------------------------------

    def save(self, **fields) -> str:
        with Session(self.engine) as s:
            art = ArticleHistory(**fields)
            s.add(art)
            s.commit()
            return art.id

    def add_publication(self, article_id: str, entry: dict[str, Any]) -> None:
        with Session(self.engine) as s:
            art = s.get(ArticleHistory, article_id)
            if not art:
                return
            pubs = list(art.published_to or [])
            entry = {**entry, "at": datetime.now(timezone.utc).isoformat()}
            pubs.append(entry)
            art.published_to = pubs
            s.commit()

    def delete(self, article_id: str) -> bool:
        with Session(self.engine) as s:
            art = s.get(ArticleHistory, article_id)
            if not art:
                return False
            s.delete(art)
            s.commit()
            return True

    # -- reads ---------------------------------------------------------------

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with Session(self.engine) as s:
            rows = (
                s.query(ArticleHistory)
                .order_by(ArticleHistory.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get(self, article_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as s:
            art = s.get(ArticleHistory, article_id)
            return self._to_dict(art) if art else None

    def find_similar(self, keyword: str, limit: int = 5) -> list[dict[str, Any]]:
        if not keyword:
            return []
        with Session(self.engine) as s:
            rows = (
                s.query(ArticleHistory)
                .filter(ArticleHistory.primary_keyword.ilike(f"%{keyword}%"))
                .order_by(ArticleHistory.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._to_dict(r) for r in rows]

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _to_dict(a: ArticleHistory) -> dict[str, Any]:
        return {
            "id": a.id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "topic": a.topic,
            "title": a.title,
            "slug": a.slug,
            "primary_keyword": a.primary_keyword,
            "keywords": list(a.keywords or []),
            "meta_description": a.meta_description,
            "body_html": a.body_html,
            "body_raw": a.body_raw,
            "llm_provider": a.llm_provider,
            "llm_model": a.llm_model,
            "related_seen": list(a.related_seen or []),
            "external_links": list(a.external_links or []),
            "published_to": list(a.published_to or []),
        }
