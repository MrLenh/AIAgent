import json
import re
from dataclasses import dataclass

from ai_agent.llm.base import LLMProvider


LISTING_SYSTEM_PROMPT = """You optimize e-commerce product listings for search
and conversion. Apply SEO best practices, compelling copy, and clear benefit
statements.

Respond with a JSON object only (no markdown fences) with these keys:
{
  "title": "<=70 chars, includes primary keyword, benefit-driven",
  "meta_title": "<=60 chars",
  "meta_description": "<=160 chars, includes primary keyword and CTA",
  "short_description": "2-3 sentences summarizing key benefits",
  "description_html": "Rich HTML with <h2>, <ul>, and <p> tags covering benefits, features, specs, and FAQ",
  "bullet_points": ["5-7 benefit-led bullet points"],
  "tags": ["8-15 relevant keyword tags"]
}
"""


@dataclass
class OptimizedListing:
    title: str
    meta_title: str
    meta_description: str
    short_description: str
    description_html: str
    bullet_points: list[str]
    tags: list[str]

    @classmethod
    def from_json(cls, text: str) -> "OptimizedListing":
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("LLM response did not contain a JSON object")
        data = json.loads(match.group(0))
        return cls(
            title=data.get("title", ""),
            meta_title=data.get("meta_title", ""),
            meta_description=data.get("meta_description", ""),
            short_description=data.get("short_description", ""),
            description_html=data.get("description_html", ""),
            bullet_points=data.get("bullet_points", []),
            tags=data.get("tags", []),
        )


class ListingOptimizerTask:
    """Rewrite a product listing for SEO and conversion."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def run(
        self,
        *,
        current_title: str,
        current_description: str = "",
        product_attributes: dict | None = None,
        primary_keyword: str | None = None,
        target_audience: str = "online shoppers",
    ) -> OptimizedListing:
        attributes_text = (
            "\n".join(f"- {k}: {v}" for k, v in (product_attributes or {}).items())
            or "(none provided)"
        )
        user_prompt = (
            f"Current title: {current_title}\n"
            f"Current description: {current_description or '(empty)'}\n"
            f"Primary keyword: {primary_keyword or '(derive from product)'}\n"
            f"Target audience: {target_audience}\n"
            f"Product attributes:\n{attributes_text}\n"
        )
        resp = self.llm.prompt(
            user_prompt,
            system=LISTING_SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=2048,
        )
        return OptimizedListing.from_json(resp.text)
