"""Persistence for audit artefacts: saved plans + ranking snapshots."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base

from ai_agent.history import _default_url


Base = declarative_base()


class ContentPlanRow(Base):
    __tablename__ = "content_plan"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    site = Column(String, default="")
    timeframe = Column(String, default="")
    items = Column(JSON, default=list)  # list of PlanItem dicts
    summary = Column(Text, default="")


class PlanItemStatus(Base):
    __tablename__ = "plan_item_status"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id = Column(String, index=True)
    item_index = Column(Integer)
    status = Column(String, default="pending")  # pending | generated | published | failed
    article_id = Column(String, default="")     # history_store id
    published_url = Column(String, default="")
    notes = Column(Text, default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RankingSnapshot(Base):
    __tablename__ = "ranking_snapshot"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    captured_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    site = Column(String, index=True)
    keyword = Column(String, index=True)
    url = Column(String, default="")
    position = Column(Float, default=0.0)
    clicks = Column(Integer, default=0)
    impressions = Column(Integer, default=0)
    ctr = Column(Float, default=0.0)
    source = Column(String, default="gsc")


class AuditStorage:
    def __init__(self, url: str | None = None):
        self.url = url or _default_url()
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        self.engine = create_engine(self.url, connect_args=connect_args, future=True)
        Base.metadata.create_all(self.engine)

    # -- plans --

    def save_plan(self, *, site: str, timeframe: str, items: list[dict], summary: str = "") -> str:
        with Session(self.engine) as s:
            row = ContentPlanRow(site=site, timeframe=timeframe, items=items, summary=summary)
            s.add(row)
            s.flush()
            for i in range(len(items)):
                s.add(PlanItemStatus(plan_id=row.id, item_index=i, status="pending"))
            s.commit()
            return row.id

    def list_plans(self, limit: int = 50) -> list[dict]:
        with Session(self.engine) as s:
            rows = s.query(ContentPlanRow).order_by(ContentPlanRow.created_at.desc()).limit(limit).all()
            return [self._plan_to_dict(r, include_items=False) for r in rows]

    def get_plan(self, plan_id: str) -> dict | None:
        with Session(self.engine) as s:
            row = s.get(ContentPlanRow, plan_id)
            if not row:
                return None
            plan = self._plan_to_dict(row, include_items=True)
            statuses = (
                s.query(PlanItemStatus)
                .filter(PlanItemStatus.plan_id == plan_id)
                .order_by(PlanItemStatus.item_index)
                .all()
            )
            plan["statuses"] = [
                {
                    "item_index": st.item_index,
                    "status": st.status,
                    "article_id": st.article_id,
                    "published_url": st.published_url,
                    "notes": st.notes,
                    "updated_at": st.updated_at.isoformat() if st.updated_at else None,
                }
                for st in statuses
            ]
            return plan

    def update_item_status(
        self,
        plan_id: str,
        item_index: int,
        *,
        status: str,
        article_id: str = "",
        published_url: str = "",
        notes: str = "",
    ) -> None:
        with Session(self.engine) as s:
            row = (
                s.query(PlanItemStatus)
                .filter(PlanItemStatus.plan_id == plan_id, PlanItemStatus.item_index == item_index)
                .first()
            )
            if not row:
                row = PlanItemStatus(plan_id=plan_id, item_index=item_index)
                s.add(row)
            row.status = status
            if article_id:
                row.article_id = article_id
            if published_url:
                row.published_url = published_url
            if notes:
                row.notes = notes
            row.updated_at = datetime.now(timezone.utc)
            s.commit()

    def delete_plan(self, plan_id: str) -> bool:
        with Session(self.engine) as s:
            row = s.get(ContentPlanRow, plan_id)
            if not row:
                return False
            s.query(PlanItemStatus).filter(PlanItemStatus.plan_id == plan_id).delete()
            s.delete(row)
            s.commit()
            return True

    # -- ranking --

    def add_ranking(self, *, site: str, rows: list[dict], source: str = "gsc") -> int:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as s:
            for r in rows:
                s.add(
                    RankingSnapshot(
                        captured_at=now,
                        site=site,
                        keyword=r.get("query") or r.get("keyword") or "",
                        url=r.get("page") or r.get("url", ""),
                        position=float(r.get("position") or 0.0),
                        clicks=int(r.get("clicks") or 0),
                        impressions=int(r.get("impressions") or 0),
                        ctr=float(r.get("ctr") or 0.0),
                        source=source,
                    )
                )
            s.commit()
        return len(rows)

    def ranking_history(self, keyword: str, site: str | None = None, days: int = 90) -> list[dict]:
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with Session(self.engine) as s:
            q = (
                s.query(RankingSnapshot)
                .filter(RankingSnapshot.keyword == keyword)
                .filter(RankingSnapshot.captured_at >= cutoff)
                .order_by(RankingSnapshot.captured_at.asc())
            )
            if site:
                q = q.filter(RankingSnapshot.site == site)
            return [self._rank_to_dict(r) for r in q.all()]

    def latest_rankings(self, site: str, limit: int = 200) -> list[dict]:
        with Session(self.engine) as s:
            rows = (
                s.query(RankingSnapshot)
                .filter(RankingSnapshot.site == site)
                .order_by(RankingSnapshot.captured_at.desc())
                .limit(limit)
                .all()
            )
            return [self._rank_to_dict(r) for r in rows]

    # -- helpers --

    @staticmethod
    def _plan_to_dict(row: ContentPlanRow, *, include_items: bool) -> dict[str, Any]:
        out = {
            "id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "site": row.site,
            "timeframe": row.timeframe,
            "summary": row.summary,
            "item_count": len(row.items or []),
        }
        if include_items:
            out["items"] = list(row.items or [])
        return out

    @staticmethod
    def _rank_to_dict(r: RankingSnapshot) -> dict[str, Any]:
        return {
            "captured_at": r.captured_at.isoformat() if r.captured_at else None,
            "site": r.site,
            "keyword": r.keyword,
            "url": r.url,
            "position": r.position,
            "clicks": r.clicks,
            "impressions": r.impressions,
            "ctr": r.ctr,
            "source": r.source,
        }
