"""Ahrefs API v3 client (subset used for competitor + keyword audit).

Requires an Ahrefs subscription with API access and a Bearer token from
https://ahrefs.com/api/.
"""

from __future__ import annotations

import requests


BASE_URL = "https://api.ahrefs.com/v3"


class AhrefsClient:
    def __init__(self, api_token: str, timeout: int = 30):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_token}",
                "Accept": "application/json",
            }
        )
        self.timeout = timeout

    def _get(self, path: str, **params) -> dict:
        resp = self.session.get(f"{BASE_URL}/{path.lstrip('/')}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # -- keywords --

    def keyword_overview(self, keyword: str, country: str = "us") -> dict:
        """Volume, difficulty, CPC, SERP features for a seed keyword."""
        return self._get(
            "keywords-explorer/overview",
            keywords=keyword, country=country,
        )

    def keyword_ideas(self, seed: str, country: str = "us", limit: int = 50) -> list[dict]:
        data = self._get(
            "keywords-explorer/matching-terms",
            keywords=seed, country=country, limit=limit,
            select="keyword,volume,difficulty,cpc,intents",
        )
        return data.get("keywords", data.get("data", []))

    # -- site / competitors --

    def site_overview(self, target: str, mode: str = "domain") -> dict:
        return self._get(
            "site-explorer/overview",
            target=target, mode=mode,
        )

    def top_pages(self, target: str, country: str = "us", limit: int = 50) -> list[dict]:
        data = self._get(
            "site-explorer/top-pages",
            target=target, country=country, limit=limit,
            select="url,traffic,value,top_keyword,top_keyword_volume",
        )
        return data.get("pages", data.get("data", []))

    def organic_competitors(self, target: str, country: str = "us", limit: int = 20) -> list[dict]:
        data = self._get(
            "site-explorer/organic-competitors",
            target=target, country=country, limit=limit,
            select="domain,common_keywords,dr,organic_traffic",
        )
        return data.get("competitors", data.get("data", []))

    def content_gap(self, target: str, competitors: list[str], country: str = "us", limit: int = 100) -> list[dict]:
        data = self._get(
            "site-explorer/content-gap",
            target=target,
            competitors=",".join(competitors),
            country=country,
            limit=limit,
            select="keyword,volume,difficulty,competitor_positions",
        )
        return data.get("keywords", data.get("data", []))
