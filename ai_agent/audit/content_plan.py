"""Turn an AuditReport into a prioritised content plan ready to execute."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from ai_agent.audit.keyword_audit import AuditReport
from ai_agent.llm.base import LLMProvider


PLAN_SYSTEM_PROMPT = """You are a content strategist. Given the audit report
and (optionally) current inventory, produce a prioritised content plan for the
specified timeframe. Return STRICT JSON — no markdown fences.

Schema:
{
  "timeframe": "<string>",
  "items": [
    {
      "priority": <1-5, 1=highest>,
      "action": "<new | update | consolidate>",
      "title": "<SEO-optimised working title>",
      "primary_keyword": "<kw>",
      "secondary_keywords": ["<kw1>", "<kw2>"],
      "target_audience": "<audience>",
      "word_count": <int>,
      "brief": "<2-3 sentence brief that the writer should follow>",
      "internal_link_candidates": ["<url1>", "<url2>"],
      "expected_impact": "<short value statement>",
      "target_url": "<existing URL if action=update/consolidate, else empty>"
    }
  ]
}

Rules:
- Prioritise quick wins from the audit first (priority 1-2).
- Cover content gaps in priority 2-4.
- Do not propose more items than can realistically be produced in the
  timeframe — budget ~1-2 items per week.
- Each item must cite internal_link_candidates pulled from the site's existing
  URLs in the audit.
- Never invent URLs.
"""


@dataclass
class PlanItem:
    priority: int = 3
    action: str = "new"
    title: str = ""
    primary_keyword: str = ""
    secondary_keywords: list[str] = field(default_factory=list)
    target_audience: str = "general readers"
    word_count: int = 1200
    brief: str = ""
    internal_link_candidates: list[str] = field(default_factory=list)
    expected_impact: str = ""
    target_url: str = ""


@dataclass
class ContentPlan:
    timeframe: str = ""
    items: list[PlanItem] = field(default_factory=list)
    raw: str = ""

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "items": [asdict(i) for i in self.items],
            "raw": self.raw,
        }

    @classmethod
    def from_llm(cls, text: str) -> "ContentPlan":
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return cls(raw=text)
        data = json.loads(match.group(0))
        return cls(
            timeframe=data.get("timeframe", ""),
            items=[PlanItem(**i) for i in data.get("items", [])],
            raw=text,
        )


class ContentPlanTask:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def run(
        self,
        audit: AuditReport | dict,
        *,
        timeframe: str = "next 30 days",
        inventory_urls: list[str] | None = None,
        max_items: int = 12,
    ) -> ContentPlan:
        audit_dict = audit.to_dict() if isinstance(audit, AuditReport) else audit

        parts = [
            f"Timeframe: {timeframe}",
            f"Max items: {max_items}",
            "Audit report:\n```json\n" + json.dumps(audit_dict, ensure_ascii=False)[:15000] + "\n```",
        ]
        if inventory_urls:
            parts.append("Existing URLs (use for internal_link_candidates):\n" + "\n".join(inventory_urls[:200]))

        resp = self.llm.prompt(
            "\n\n".join(parts),
            system=PLAN_SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=6000,
        )
        plan = ContentPlan.from_llm(resp.text)
        plan.items = plan.items[:max_items]
        return plan
