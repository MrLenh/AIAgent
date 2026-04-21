"""Google Search Console client.

Auth: service account JSON. Grant the service-account email access to the
property (Search Console → Settings → Users and permissions → Add user).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class GSCClient:
    def __init__(self, site_url: str, service_account_json: str | dict):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = (
            json.loads(service_account_json)
            if isinstance(service_account_json, str)
            else service_account_json
        )
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        self.service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        self.site_url = site_url

    # -- sites --

    def list_sites(self) -> list[dict]:
        data = self.service.sites().list().execute()
        return data.get("siteEntry", [])

    # -- search analytics --

    def query(
        self,
        start_date: str,
        end_date: str,
        dimensions: list[str] | None = None,
        filters: list[dict] | None = None,
        row_limit: int = 1000,
    ) -> list[dict]:
        body: dict[str, Any] = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions or ["query"],
            "rowLimit": row_limit,
        }
        if filters:
            body["dimensionFilterGroups"] = [{"filters": filters}]
        data = (
            self.service.searchanalytics()
            .query(siteUrl=self.site_url, body=body)
            .execute()
        )
        rows = []
        for r in data.get("rows", []):
            entry = {
                "clicks": r.get("clicks", 0),
                "impressions": r.get("impressions", 0),
                "ctr": r.get("ctr", 0.0),
                "position": r.get("position", 0.0),
            }
            for i, dim in enumerate(body["dimensions"]):
                entry[dim] = r["keys"][i]
            rows.append(entry)
        return rows

    def _window(self, days: int) -> tuple[str, str]:
        end = date.today()
        start = end - timedelta(days=days)
        return start.isoformat(), end.isoformat()

    def top_queries(self, days: int = 28, row_limit: int = 500) -> list[dict]:
        start, end = self._window(days)
        return self.query(start, end, ["query"], row_limit=row_limit)

    def top_pages(self, days: int = 28, row_limit: int = 500) -> list[dict]:
        start, end = self._window(days)
        return self.query(start, end, ["page"], row_limit=row_limit)

    def pages_for_query(self, q: str, days: int = 28) -> list[dict]:
        start, end = self._window(days)
        return self.query(
            start, end, ["page"],
            filters=[{"dimension": "query", "operator": "equals", "expression": q}],
            row_limit=50,
        )

    def positions_for_keywords(self, keywords: list[str], days: int = 28) -> list[dict]:
        """One row per keyword with aggregated position/clicks/impressions."""
        start, end = self._window(days)
        out = []
        for kw in keywords:
            rows = self.query(
                start, end, ["query"],
                filters=[{"dimension": "query", "operator": "equals", "expression": kw}],
                row_limit=1,
            )
            if rows:
                out.append(rows[0])
            else:
                out.append({"query": kw, "position": None, "clicks": 0, "impressions": 0, "ctr": 0})
        return out
