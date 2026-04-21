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
        "TITLE: Great Title\n"
        "META_DESCRIPTION: A compelling meta description.\n"
        "SLUG: great-title\n"
        "KEYWORDS: a, b, c\n"
        "---\n"
        "<article><h1>Great Title</h1><p>Body.</p></article>"
    )
    art = SEOArticle.parse(raw)
    assert art.title == "Great Title"
    assert art.slug == "great-title"
    assert art.meta_description == "A compelling meta description."
    assert art.keywords == ["a", "b", "c"]
    assert art.body_html.startswith("<article>")


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
        "TITLE: Title\nMETA_DESCRIPTION: x\nSLUG: t\nKEYWORDS: a\n---\n<article><h1>Title</h1></article>"
    )
    agent = AIAgent(llm=llm)
    agent.register_source(TextSource(content="CONTEXT_BLOB"), name="ctx")

    article = agent.write_seo_article(
        topic="t",
        primary_keyword="kw",
        use_sources=["ctx"],
        related_articles=[{"title": "Existing", "url": "https://x.com/post", "excerpt": "old"}],
    )
    assert article.title == "Title"
    user_prompt = llm.calls[0][-1].content
    assert "CONTEXT_BLOB" in user_prompt
    assert "kw" in user_prompt
    assert "https://x.com/post" in user_prompt


def test_history_store_roundtrip(tmp_path: Path):
    from ai_agent.history import HistoryStore

    store = HistoryStore(url=f"sqlite:///{tmp_path}/h.db")
    art_id = store.save(
        topic="t", title="My Article", slug="my-article",
        primary_keyword="pour over", keywords=["a", "b"],
        meta_description="m", body_html="<article/>", body_raw="raw",
        llm_provider="claude", llm_model="x",
    )
    assert art_id
    got = store.get(art_id)
    assert got["title"] == "My Article"
    assert store.list(limit=10)[0]["id"] == art_id

    store.add_publication(art_id, {"platform": "wp", "id": 99, "url": "https://u", "status": "draft"})
    got = store.get(art_id)
    assert got["published_to"][0]["platform"] == "wp"
    assert got["published_to"][0]["at"]

    sim = store.find_similar("pour over")
    assert sim and sim[0]["id"] == art_id

    assert store.delete(art_id) is True
    assert store.get(art_id) is None


def test_audit_storage_plan_and_ranking_roundtrip(tmp_path: Path):
    from ai_agent.audit.storage import AuditStorage

    store = AuditStorage(url=f"sqlite:///{tmp_path}/audit.db")
    plan_id = store.save_plan(
        site="example.com",
        timeframe="next 30 days",
        items=[
            {"priority": 1, "title": "Post A", "primary_keyword": "a"},
            {"priority": 2, "title": "Post B", "primary_keyword": "b"},
        ],
    )
    plan = store.get_plan(plan_id)
    assert plan["item_count"] == 2
    assert len(plan["statuses"]) == 2

    store.update_item_status(plan_id, 0, status="published",
                             article_id="art-1", published_url="https://u/1")
    plan = store.get_plan(plan_id)
    assert plan["statuses"][0]["status"] == "published"
    assert plan["statuses"][0]["article_id"] == "art-1"

    n = store.add_ranking(
        site="example.com",
        rows=[
            {"query": "pour over", "position": 12.3, "clicks": 5, "impressions": 120, "ctr": 0.04},
            {"query": "v60", "position": 4.1, "clicks": 8, "impressions": 90, "ctr": 0.09},
        ],
    )
    assert n == 2
    hist = store.ranking_history("pour over")
    assert hist and hist[0]["position"] == 12.3
    latest = store.latest_rankings("example.com")
    assert len(latest) == 2


def test_audit_report_parse_handles_json_with_noise():
    from ai_agent.audit.keyword_audit import AuditReport

    noisy = (
        "Here is the audit report:\n```json\n"
        '{"summary":"s","quick_wins":[{"query":"kw","current_position":12.3,'
        '"url":"u","impressions":100,"clicks":3,"action":"a","expected_impact":"medium"}],'
        '"content_gaps":[],"cannibalization":[],"competitor_insights":[]}'
        "\n```"
    )
    r = AuditReport.from_llm(noisy)
    assert r.summary == "s"
    assert r.quick_wins[0].query == "kw"


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
