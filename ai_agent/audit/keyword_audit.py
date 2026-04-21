"""Keyword audit: fold site content + GSC + (optional) Ahrefs data into an LLM
prompt that returns a structured JSON report with quick wins, content gaps,
and cannibalization issues.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from ai_agent.llm.base import LLMProvider


AUDIT_SYSTEM_PROMPT = """You are a senior SEO analyst. Audit the site using the
provided on-site content, Google Search Console data, and (if present)
competitor/keyword data. Return STRICT JSON only — no prose outside the JSON,
no markdown fences.

Schema:
{
  "summary": "<3-5 sentence executive summary>",
  "quick_wins": [
    {
      "query": "<kw>",
      "current_position": <float>,
      "url": "<ranking page>",
      "impressions": <int>,
      "clicks": <int>,
      "action": "<specific action: expand, internal link, fix title, etc.>",
      "expected_impact": "<low|medium|high>"
    }
  ],
  "content_gaps": [
    {
      "topic": "<missing topic>",
      "suggested_primary_keyword": "<kw>",
      "related_queries": ["<kw1>", "<kw2>"],
      "rationale": "<why this fills a gap>",
      "difficulty": "<low|medium|high>"
    }
  ],
  "cannibalization": [
    {
      "query": "<kw>",
      "urls": ["<url1>", "<url2>"],
      "recommendation": "<consolidate / re-target / redirect>"
    }
  ],
  "competitor_insights": [
    {
      "competitor": "<domain>",
      "winning_topics": ["<topic1>", "<topic2>"],
      "takeaway": "<what we should do>"
    }
  ]
}

Rules:
- Derive quick_wins ONLY from queries with position between 5 and 30 AND
  impressions > a meaningful threshold. Include up to 10.
- Mark cannibalization when multiple site URLs appear for the same query
  above position 30.
- Never fabricate URLs or numbers — only use values present in the input.
- If competitor data is absent, return competitor_insights as [].
"""


@dataclass
class QuickWin:
    query: str
    current_position: float
    url: str
    impressions: int = 0
    clicks: int = 0
    action: str = ""
    expected_impact: str = "medium"


@dataclass
class ContentGap:
    topic: str
    suggested_primary_keyword: str
    related_queries: list[str] = field(default_factory=list)
    rationale: str = ""
    difficulty: str = "medium"


@dataclass
class Cannibalization:
    query: str
    urls: list[str]
    recommendation: str = ""


@dataclass
class CompetitorInsight:
    competitor: str
    winning_topics: list[str]
    takeaway: str = ""


@dataclass
class AuditReport:
    summary: str = ""
    quick_wins: list[QuickWin] = field(default_factory=list)
    content_gaps: list[ContentGap] = field(default_factory=list)
    cannibalization: list[Cannibalization] = field(default_factory=list)
    competitor_insights: list[CompetitorInsight] = field(default_factory=list)
    raw: str = ""

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "quick_wins": [asdict(q) for q in self.quick_wins],
            "content_gaps": [asdict(g) for g in self.content_gaps],
            "cannibalization": [asdict(c) for c in self.cannibalization],
            "competitor_insights": [asdict(c) for c in self.competitor_insights],
            "raw": self.raw,
        }

    @classmethod
    def from_llm(cls, text: str) -> "AuditReport":
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return cls(summary="(no JSON returned)", raw=text)
        data = json.loads(match.group(0))
        return cls(
            summary=data.get("summary", ""),
            quick_wins=[QuickWin(**q) for q in data.get("quick_wins", [])],
            content_gaps=[ContentGap(**g) for g in data.get("content_gaps", [])],
            cannibalization=[Cannibalization(**c) for c in data.get("cannibalization", [])],
            competitor_insights=[CompetitorInsight(**c) for c in data.get("competitor_insights", [])],
            raw=text,
        )


class KeywordAuditTask:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def run(
        self,
        *,
        blog_posts: list[dict],
        gsc_queries: list[dict] | None = None,
        gsc_pages: list[dict] | None = None,
        competitor_keywords: list[dict] | None = None,
        competitors: list[dict] | None = None,
    ) -> AuditReport:
        parts: list[str] = []

        if blog_posts:
            rows = [
                f"- {p.get('url', '')} | {p.get('title', '')} | {p.get('word_count', 0)} words"
                for p in blog_posts[:100]
            ]
            parts.append("ON-SITE POSTS:\n" + "\n".join(rows))

        if gsc_queries:
            # Trim to top 150 by impressions
            top = sorted(gsc_queries, key=lambda r: r.get("impressions", 0), reverse=True)[:150]
            rows = [
                f"- {r.get('query', '')} | pos={r.get('position', 0):.1f} | imp={r.get('impressions', 0)} | clicks={r.get('clicks', 0)} | ctr={r.get('ctr', 0):.2%}"
                for r in top
            ]
            parts.append("GSC QUERIES (28d):\n" + "\n".join(rows))

        if gsc_pages:
            top = sorted(gsc_pages, key=lambda r: r.get("impressions", 0), reverse=True)[:100]
            rows = [
                f"- {r.get('page', '')} | imp={r.get('impressions', 0)} | clicks={r.get('clicks', 0)} | pos={r.get('position', 0):.1f}"
                for r in top
            ]
            parts.append("GSC PAGES (28d):\n" + "\n".join(rows))

        if competitor_keywords:
            rows = [
                f"- {k.get('keyword', '')} | vol={k.get('volume', 0)} | diff={k.get('difficulty', 0)}"
                for k in competitor_keywords[:100]
            ]
            parts.append("COMPETITOR KEYWORD GAP (Ahrefs):\n" + "\n".join(rows))

        if competitors:
            rows = [
                f"- {c.get('domain', '')} | dr={c.get('dr', 0)} | common_kw={c.get('common_keywords', 0)}"
                for c in competitors[:20]
            ]
            parts.append("ORGANIC COMPETITORS:\n" + "\n".join(rows))

        user_prompt = "\n\n".join(parts) or "(no data)"
        resp = self.llm.prompt(
            user_prompt,
            system=AUDIT_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=6000,
        )
        return AuditReport.from_llm(resp.text)
