"""Smoke tests: imports resolve and interfaces behave without network calls."""

import csv
from pathlib import Path
from unittest.mock import MagicMock

from ai_agent.agent import AIAgent
from ai_agent.data_sources import CSVSource, TextSource
from ai_agent.llm.base import LLMMessage, LLMProvider, LLMResponse
from ai_agent.tasks.listing import OptimizedListing
from ai_agent.tasks.seo import SEOArticle


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, text: str):
        self.text = text
        self.calls: list[list[LLMMessage]] = []

    def complete(self, messages, *, temperature=0.7, max_tokens=2048, **kwargs):
        self.calls.append(list(messages))
        return LLMResponse(text=self.text, model="fake")


def test_text_source_load():
    src = TextSource(content="hello")
    assert src.load() == "hello"


def test_csv_source_load(tmp_path: Path):
    path = tmp_path / "data.csv"
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["a", "b"])
        writer.writerow([1, 2])
    text = CSVSource(path).load()
    assert "a" in text and "b" in text


def test_seo_article_parsing():
    raw = (
        "# Great Title\n\n"
        "META DESCRIPTION: A compelling meta description.\n"
        "SLUG: great-title\n"
        "KEYWORDS: a, b, c\n\n"
        "## Intro\nBody."
    )
    art = SEOArticle(raw=raw)
    assert art.title() == "Great Title"
    assert art.slug == "great-title"
    assert art.meta_description == "A compelling meta description."
    assert art.keywords == ["a", "b", "c"]


def test_optimized_listing_from_json():
    text = """{
      "title": "T",
      "meta_title": "MT",
      "meta_description": "MD",
      "short_description": "SD",
      "description_html": "<p>x</p>",
      "bullet_points": ["b1"],
      "tags": ["t1"]
    }"""
    listing = OptimizedListing.from_json(text)
    assert listing.title == "T"
    assert listing.bullet_points == ["b1"]


def test_agent_write_seo_article_passes_sources_to_llm():
    llm = FakeLLM(
        "# Title\n\nMETA DESCRIPTION: x\nSLUG: t\nKEYWORDS: a\n\n## I\nbody"
    )
    agent = AIAgent(llm=llm)
    agent.register_source(TextSource(content="CONTEXT_BLOB"), name="ctx")

    article = agent.write_seo_article(
        topic="t",
        primary_keyword="kw",
        use_sources=["ctx"],
    )
    assert article.title() == "Title"
    user_prompt = llm.calls[0][-1].content
    assert "CONTEXT_BLOB" in user_prompt
    assert "kw" in user_prompt


def test_agent_apply_listing_routes_to_shopify():
    llm = FakeLLM("")
    agent = AIAgent(llm=llm)
    shopify = MagicMock()
    shopify.name = "shopify"
    shopify.update_product_seo.return_value = {"ok": True}
    agent.register_platform("shop", shopify)

    listing = OptimizedListing(
        title="T",
        meta_title="MT",
        meta_description="MD",
        short_description="SD",
        description_html="<p/>",
        bullet_points=[],
        tags=[],
    )
    agent.apply_listing("shop", 1, listing)
    shopify.update_product_seo.assert_called_once_with(
        1,
        title="T",
        body_html="<p/>",
        meta_title="MT",
        meta_description="MD",
    )
