"""HTTP entrypoint for the AI Agent module.

Serves an admin SPA at ``/`` and a REST API under ``/api``. The LLM provider
is selected via the ``LLM_PROVIDER`` env var (``claude`` / ``openai`` /
``gemini``) but requests may override it by sending an ``llm`` object.

Platform credentials are sent per-request so the UI can target different
stores/sites without redeploying.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ai_agent import (
    AIAgent,
    AuditStorage,
    BlogCrawler,
    ClaudeProvider,
    ContentPlanTask,
    GeminiProvider,
    GSCClient,
    HistoryStore,
    KeywordAuditTask,
    OpenAIProvider,
    ShopifyClient,
    WooCommerceClient,
    WordPressClient,
)
from ai_agent.audit.ahrefs import AhrefsClient
from ai_agent.audit.keyword_audit import AuditReport
from ai_agent.data_sources import CSVSource, DatabaseSource, TextSource
from ai_agent.llm.base import LLMProvider
from ai_agent.tasks.listing import OptimizedListing


history_store = HistoryStore()
audit_storage = AuditStorage()


BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ai_agent")


# ---------------------------------------------------------------------------
# LLM + source builders
# ---------------------------------------------------------------------------


class LLMConfig(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


def _build_llm(override: LLMConfig | None = None, *, raise_errors: bool = False) -> LLMProvider | None:
    provider = (override.provider if override and override.provider else os.getenv("LLM_PROVIDER", "")).lower()
    model = override.model if override and override.model else None
    api_key = override.api_key if override and override.api_key else None

    try:
        if provider == "openai":
            return OpenAIProvider(
                api_key=api_key, model=model or os.getenv("OPENAI_MODEL", "gpt-4o")
            )
        if provider == "gemini":
            return GeminiProvider(
                api_key=api_key, model=model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            )
        if provider == "claude" or (provider == "" and os.getenv("ANTHROPIC_API_KEY")):
            return ClaudeProvider(
                api_key=api_key, model=model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
            )
    except Exception as exc:
        logger.exception("LLM init failed for provider=%s", provider)
        if raise_errors:
            raise HTTPException(
                status_code=503,
                detail=f"LLM init failed ({provider}): {type(exc).__name__}: {exc}",
            )
        return None
    return None


def _require_agent(override: LLMConfig | None = None) -> AIAgent:
    llm = _build_llm(override, raise_errors=True)
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail="No LLM provider configured. Set LLM_PROVIDER + API key, or send an `llm` override.",
        )
    return AIAgent(llm=llm)


def _build_sources(specs: list[dict[str, Any]] | None):
    out = []
    for spec in specs or []:
        kind = spec.get("type")
        if kind == "text":
            out.append(TextSource(content=spec.get("content"), path=spec.get("path")))
        elif kind == "csv":
            out.append(CSVSource(spec["path"], max_rows=spec.get("max_rows", 200)))
        elif kind == "database":
            out.append(
                DatabaseSource(
                    url=spec["url"],
                    query=spec["query"],
                    params=spec.get("params"),
                    max_rows=spec.get("max_rows", 200),
                )
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown source type: {kind}")
    return out


# ---------------------------------------------------------------------------
# App + static
# ---------------------------------------------------------------------------

app = FastAPI(title="AI Agent", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error("Unhandled %s at %s\n%s", type(exc).__name__, request.url.path, tb)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"service": "ai-agent", "ui": "not installed", "api": "/api"}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class LLMTestRequest(BaseModel):
    llm: LLMConfig | None = None


class GeminiListReq(BaseModel):
    api_key: str | None = None


@app.post("/api/gemini/models")
def gemini_models(req: GeminiListReq) -> dict:
    """List Gemini models that support generateContent for the given key."""
    import google.generativeai as genai

    key = req.api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY not set and no api_key provided")
    genai.configure(api_key=key)
    models = []
    for m in genai.list_models():
        if "generateContent" in getattr(m, "supported_generation_methods", []):
            models.append({
                "name": m.name.replace("models/", ""),
                "display_name": getattr(m, "display_name", ""),
                "input_token_limit": getattr(m, "input_token_limit", 0),
                "output_token_limit": getattr(m, "output_token_limit", 0),
            })
    return {"models": models}


@app.post("/api/llm-test")
def llm_test(req: LLMTestRequest) -> dict:
    """Send a trivial prompt to verify the LLM works end-to-end."""
    llm = _build_llm(req.llm, raise_errors=True)
    if llm is None:
        raise HTTPException(status_code=503, detail="No LLM provider configured")
    # 1024 tokens covers Gemini 2.5 thinking overhead + short reply.
    resp = llm.prompt("Reply with the single word: OK", max_tokens=1024, temperature=0)
    return {
        "ok": True,
        "provider": llm.name,
        "model": getattr(llm, "model", ""),
        "text": resp.text.strip()[:100],
        "usage": resp.usage,
    }


@app.get("/api/status")
def status() -> dict:
    env = {
        "llm_provider": os.getenv("LLM_PROVIDER", ""),
        "has_anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "has_openai": bool(os.getenv("OPENAI_API_KEY")),
        "has_gemini": bool(os.getenv("GEMINI_API_KEY")),
        "has_shopify": bool(os.getenv("SHOPIFY_SHOP") and os.getenv("SHOPIFY_ACCESS_TOKEN")),
        "has_wordpress": bool(os.getenv("WORDPRESS_URL") and os.getenv("WORDPRESS_APP_PASSWORD")),
        "has_woocommerce": bool(
            os.getenv("WOOCOMMERCE_URL") and os.getenv("WOOCOMMERCE_CONSUMER_KEY")
        ),
        "has_database": bool(os.getenv("DATABASE_URL")),
    }
    return {
        "status": "ok",
        "llm_configured": _build_llm() is not None,
        "env": env,
    }


# Back-compat alias
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm_configured": _build_llm() is not None}


# ---------------------------------------------------------------------------
# SEO Article
# ---------------------------------------------------------------------------


class PublishSpec(BaseModel):
    platform: str  # "wordpress" | "shopify"
    status: str = "draft"
    creds: dict[str, Any] | None = None  # override env


class InternalLinkSpec(BaseModel):
    source: str = "none"  # "wordpress" | "shopify" | "history" | "none"
    creds: dict[str, Any] | None = None
    limit: int = 5


class SEORequest(BaseModel):
    topic: str
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    audience: str = "general readers"
    word_count: int = 1200
    tone: str = "informative and friendly"
    sources: list[dict[str, Any]] = Field(default_factory=list)

    internal_links: InternalLinkSpec | None = None
    external_links: list[str] = Field(default_factory=list)
    check_duplicates: bool = True

    publish: PublishSpec | None = None
    save_history: bool = True

    llm: LLMConfig | None = None


def _fetch_related(spec: InternalLinkSpec, keyword: str) -> list[dict]:
    if not spec or spec.source == "none":
        return []
    try:
        if spec.source == "wordpress":
            creds = spec.creds or {
                "base_url": os.getenv("WORDPRESS_URL", ""),
                "username": os.getenv("WORDPRESS_USERNAME", ""),
                "app_password": os.getenv("WORDPRESS_APP_PASSWORD", ""),
            }
            return WordPressClient(**creds).search_posts(keyword, per_page=spec.limit)
        if spec.source == "shopify":
            creds = spec.creds or {
                "shop": os.getenv("SHOPIFY_SHOP", ""),
                "access_token": os.getenv("SHOPIFY_ACCESS_TOKEN", ""),
            }
            return ShopifyClient(**creds).search_articles(keyword, limit=spec.limit)
        if spec.source == "history":
            rows = history_store.find_similar(keyword, limit=spec.limit)
            return [
                {
                    "title": r["title"],
                    "url": f"/history/{r['id']}",
                    "excerpt": r["meta_description"],
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("Related lookup failed (%s): %s", spec.source, exc)
    return []


def _auto_publish(article, publish: PublishSpec) -> dict:
    if publish.platform in ("wordpress", "wp"):
        creds = publish.creds or {
            "base_url": os.getenv("WORDPRESS_URL", ""),
            "username": os.getenv("WORDPRESS_USERNAME", ""),
            "app_password": os.getenv("WORDPRESS_APP_PASSWORD", ""),
        }
        post = WordPressClient(**creds).create_post(
            title=article.title,
            content=article.body_html,
            excerpt=article.meta_description,
            status=publish.status,
        )
        return {
            "platform": "wordpress",
            "id": post.get("id"),
            "url": post.get("link"),
            "status": post.get("status"),
        }
    raise HTTPException(400, f"Unsupported publish platform: {publish.platform}")


@app.post("/api/seo-article")
def seo_article(req: SEORequest) -> dict:
    agent = _require_agent(req.llm)
    llm = agent.llm

    # 1. Look for related articles to link to (and to flag duplicates).
    related = _fetch_related(req.internal_links, req.primary_keyword) if req.internal_links else []
    duplicates: list[dict] = []
    if req.check_duplicates and related:
        key = req.primary_keyword.lower().strip()
        duplicates = [r for r in related if key and key in (r.get("title") or "").lower()]

    # 2. Grounding sources.
    for idx, src in enumerate(_build_sources(req.sources)):
        agent.register_source(src, name=f"src_{idx}")

    # 3. Generate.
    article = agent.write_seo_article(
        topic=req.topic,
        primary_keyword=req.primary_keyword,
        secondary_keywords=req.secondary_keywords,
        audience=req.audience,
        word_count=req.word_count,
        tone=req.tone,
        related_articles=related,
        external_references=req.external_links,
    )

    # 4. Persist history.
    history_id = None
    if req.save_history:
        history_id = history_store.save(
            topic=req.topic,
            title=article.title,
            slug=article.slug,
            primary_keyword=req.primary_keyword,
            keywords=article.keywords,
            meta_description=article.meta_description,
            body_html=article.body_html,
            body_raw=article.raw,
            llm_provider=llm.name,
            llm_model=getattr(llm, "model", ""),
            related_seen=[{"title": r["title"], "url": r["url"]} for r in related],
            external_links=list(req.external_links),
        )

    # 5. Optional auto-publish.
    published = None
    if req.publish:
        published = _auto_publish(article, req.publish)
        if history_id:
            history_store.add_publication(history_id, published)

    return {
        "history_id": history_id,
        "title": article.title,
        "slug": article.slug,
        "meta_description": article.meta_description,
        "keywords": article.keywords,
        "body_html": article.body_html,
        "raw": article.raw,
        "related": related,
        "duplicates": duplicates,
        "published": published,
    }


# ---------------------------------------------------------------------------
# Listing Optimizer
# ---------------------------------------------------------------------------


class ListingRequest(BaseModel):
    current_title: str
    current_description: str = ""
    product_attributes: dict[str, Any] = Field(default_factory=dict)
    primary_keyword: str | None = None
    target_audience: str = "online shoppers"
    llm: LLMConfig | None = None


@app.post("/api/optimize-listing")
def optimize_listing(req: ListingRequest) -> dict:
    agent = _require_agent(req.llm)
    listing = agent.optimize_listing(
        current_title=req.current_title,
        current_description=req.current_description,
        product_attributes=req.product_attributes,
        primary_keyword=req.primary_keyword,
        target_audience=req.target_audience,
    )
    return listing.__dict__


# ---------------------------------------------------------------------------
# Data Analysis
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    question: str
    sources: list[dict[str, Any]]
    llm: LLMConfig | None = None


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    agent = _require_agent(req.llm)
    for idx, src in enumerate(_build_sources(req.sources)):
        agent.register_source(src, name=f"src_{idx}")
    report = agent.analyze(req.question)
    return {"report": report}


@app.post("/api/analyze-upload")
async def analyze_upload(
    question: str = Form(...),
    file: UploadFile = File(...),
    provider: str | None = Form(None),
    model: str | None = Form(None),
    api_key: str | None = Form(None),
) -> dict:
    override = LLMConfig(provider=provider, model=model, api_key=api_key) if provider else None
    agent = _require_agent(override)

    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "Upload must be UTF-8 CSV")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(400, "CSV is empty")

    preview = "\n".join([",".join(r) for r in rows[:200]])
    agent.register_source(TextSource(content=f"CSV upload '{file.filename}':\n{preview}"), name="upload")
    report = agent.analyze(question)
    return {"report": report, "rows": len(rows) - 1, "columns": rows[0]}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@app.get("/api/history")
def history_list(limit: int = 100) -> dict:
    rows = history_store.list(limit=limit)
    # Strip heavy body fields from the list view.
    return {
        "items": [
            {k: v for k, v in r.items() if k not in ("body_html", "body_raw")}
            for r in rows
        ]
    }


@app.get("/api/history/{article_id}")
def history_get(article_id: str) -> dict:
    row = history_store.get(article_id)
    if not row:
        raise HTTPException(404, "Not found")
    return row


@app.delete("/api/history/{article_id}")
def history_delete(article_id: str) -> dict:
    ok = history_store.delete(article_id)
    if not ok:
        raise HTTPException(404, "Not found")
    return {"ok": True}


class HistoryPublishReq(BaseModel):
    platform: str
    status: str = "draft"
    creds: dict[str, Any] | None = None


@app.post("/api/history/{article_id}/publish")
def history_publish(article_id: str, req: HistoryPublishReq) -> dict:
    row = history_store.get(article_id)
    if not row:
        raise HTTPException(404, "Not found")

    class _Article:
        title = row["title"]
        body_html = row["body_html"]
        meta_description = row["meta_description"]

    pub = _auto_publish(_Article(), PublishSpec(platform=req.platform, status=req.status, creds=req.creds))
    history_store.add_publication(article_id, pub)
    return pub


# ---------------------------------------------------------------------------
# Platform passthroughs
# ---------------------------------------------------------------------------


class ShopifyCreds(BaseModel):
    shop: str
    access_token: str


class ShopifyFetch(ShopifyCreds):
    product_id: int


class ShopifyApply(ShopifyCreds):
    product_id: int
    listing: dict[str, Any]


@app.post("/api/shopify/product")
def shopify_product(req: ShopifyFetch) -> dict:
    client = ShopifyClient(shop=req.shop, access_token=req.access_token)
    return client.get_product(req.product_id)


@app.post("/api/shopify/apply-listing")
def shopify_apply(req: ShopifyApply) -> dict:
    client = ShopifyClient(shop=req.shop, access_token=req.access_token)
    listing = OptimizedListing(**{k: req.listing.get(k) for k in OptimizedListing.__dataclass_fields__})
    return client.update_product_seo(
        req.product_id,
        title=listing.title,
        body_html=listing.description_html,
        meta_title=listing.meta_title,
        meta_description=listing.meta_description,
    )


class WPCreds(BaseModel):
    base_url: str
    username: str
    app_password: str


class WPPublish(WPCreds):
    title: str
    content: str
    excerpt: str = ""
    status: str = "draft"


@app.post("/api/wordpress/publish")
def wordpress_publish(req: WPPublish) -> dict:
    client = WordPressClient(
        base_url=req.base_url, username=req.username, app_password=req.app_password
    )
    return client.create_post(
        title=req.title, content=req.content, excerpt=req.excerpt, status=req.status
    )


class WooCreds(BaseModel):
    base_url: str
    consumer_key: str
    consumer_secret: str


class WooFetch(WooCreds):
    product_id: int


class WooApply(WooCreds):
    product_id: int
    listing: dict[str, Any]


@app.post("/api/woocommerce/product")
def woo_product(req: WooFetch) -> dict:
    client = WooCommerceClient(
        base_url=req.base_url,
        consumer_key=req.consumer_key,
        consumer_secret=req.consumer_secret,
    )
    return client.get_product(req.product_id)


@app.post("/api/woocommerce/apply-listing")
def woo_apply(req: WooApply) -> dict:
    client = WooCommerceClient(
        base_url=req.base_url,
        consumer_key=req.consumer_key,
        consumer_secret=req.consumer_secret,
    )
    listing = OptimizedListing(**{k: req.listing.get(k) for k in OptimizedListing.__dataclass_fields__})
    return client.update_product_seo(
        req.product_id,
        name=listing.title,
        description=listing.description_html,
        short_description=listing.short_description,
        meta_data=[
            {"key": "_yoast_wpseo_title", "value": listing.meta_title},
            {"key": "_yoast_wpseo_metadesc", "value": listing.meta_description},
        ],
    )


class PlatformTest(BaseModel):
    platform: str
    creds: dict[str, Any]


@app.post("/api/platforms/test")
def platform_test(req: PlatformTest) -> dict:
    try:
        if req.platform == "shopify":
            ShopifyClient(**req.creds).list_products(limit=1)
        elif req.platform == "wordpress":
            WordPressClient(**req.creds).list_posts(per_page=1)
        elif req.platform == "woocommerce":
            WooCommerceClient(**req.creds).list_products(per_page=1)
        else:
            raise HTTPException(400, f"Unknown platform: {req.platform}")
    except HTTPException:
        raise
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class WPCredsOpt(BaseModel):
    base_url: str | None = None
    username: str | None = None
    app_password: str | None = None


class CrawlRequest(BaseModel):
    source: str = "wordpress"  # "wordpress" | "sitemap"
    base_url: str | None = None
    wp: WPCredsOpt | None = None
    limit: int = 100


def _wp_client_from(creds: WPCredsOpt | None) -> WordPressClient:
    c = creds or WPCredsOpt()
    return WordPressClient(
        base_url=c.base_url or os.getenv("WORDPRESS_URL", ""),
        username=c.username or os.getenv("WORDPRESS_USERNAME", ""),
        app_password=c.app_password or os.getenv("WORDPRESS_APP_PASSWORD", ""),
    )


@app.post("/api/audit/crawl")
def audit_crawl(req: CrawlRequest) -> dict:
    if req.source == "wordpress":
        crawler = BlogCrawler(wp=_wp_client_from(req.wp))
    else:
        if not req.base_url:
            raise HTTPException(400, "base_url required for sitemap crawl")
        crawler = BlogCrawler(base_url=req.base_url)
    posts = crawler.crawl(limit=req.limit)
    return {
        "count": len(posts),
        "posts": [
            {
                "url": p.url, "title": p.title, "slug": p.slug,
                "published": p.published, "word_count": p.word_count,
                "excerpt": p.excerpt[:240],
            }
            for p in posts
        ],
    }


class GSCRequest(BaseModel):
    site_url: str
    service_account_json: dict[str, Any] | str
    days: int = 28
    row_limit: int = 500
    dimensions: list[str] = Field(default_factory=lambda: ["query"])


@app.post("/api/audit/gsc/query")
def audit_gsc_query(req: GSCRequest) -> dict:
    gsc = GSCClient(req.site_url, req.service_account_json)
    start, end = gsc._window(req.days)
    rows = gsc.query(start, end, req.dimensions, row_limit=req.row_limit)
    return {"rows": rows, "start": start, "end": end}


@app.post("/api/audit/gsc/sites")
def audit_gsc_sites(req: GSCRequest) -> dict:
    gsc = GSCClient(req.site_url, req.service_account_json)
    return {"sites": gsc.list_sites()}


class AhrefsRequest(BaseModel):
    api_token: str
    target: str | None = None
    seed: str | None = None
    country: str = "us"
    competitors: list[str] = Field(default_factory=list)
    limit: int = 50


@app.post("/api/audit/ahrefs/competitors")
def audit_ahrefs_competitors(req: AhrefsRequest) -> dict:
    if not req.target:
        raise HTTPException(400, "target required")
    return {"competitors": AhrefsClient(req.api_token).organic_competitors(req.target, req.country, req.limit)}


@app.post("/api/audit/ahrefs/content-gap")
def audit_ahrefs_gap(req: AhrefsRequest) -> dict:
    if not req.target or not req.competitors:
        raise HTTPException(400, "target and competitors required")
    return {"keywords": AhrefsClient(req.api_token).content_gap(req.target, req.competitors, req.country, req.limit)}


@app.post("/api/audit/ahrefs/keyword-ideas")
def audit_ahrefs_ideas(req: AhrefsRequest) -> dict:
    if not req.seed:
        raise HTTPException(400, "seed required")
    return {"keywords": AhrefsClient(req.api_token).keyword_ideas(req.seed, req.country, req.limit)}


class RunAuditRequest(BaseModel):
    blog_posts: list[dict[str, Any]] = Field(default_factory=list)
    gsc_queries: list[dict[str, Any]] = Field(default_factory=list)
    gsc_pages: list[dict[str, Any]] = Field(default_factory=list)
    competitor_keywords: list[dict[str, Any]] = Field(default_factory=list)
    competitors: list[dict[str, Any]] = Field(default_factory=list)
    llm: LLMConfig | None = None


@app.post("/api/audit/run")
def audit_run(req: RunAuditRequest) -> dict:
    agent = _require_agent(req.llm)
    report = KeywordAuditTask(agent.llm).run(
        blog_posts=req.blog_posts,
        gsc_queries=req.gsc_queries,
        gsc_pages=req.gsc_pages,
        competitor_keywords=req.competitor_keywords,
        competitors=req.competitors,
    )
    return report.to_dict()


class PlanRequest(BaseModel):
    audit: dict[str, Any]
    timeframe: str = "next 30 days"
    inventory_urls: list[str] = Field(default_factory=list)
    max_items: int = 12
    site: str = ""
    save: bool = True
    llm: LLMConfig | None = None


@app.post("/api/audit/plan")
def audit_plan(req: PlanRequest) -> dict:
    agent = _require_agent(req.llm)
    audit_obj = AuditReport.from_llm(req.audit.get("raw") or "") if req.audit.get("raw") else req.audit
    plan = ContentPlanTask(agent.llm).run(
        audit_obj,
        timeframe=req.timeframe,
        inventory_urls=req.inventory_urls,
        max_items=req.max_items,
    )
    plan_id = None
    if req.save:
        plan_id = audit_storage.save_plan(
            site=req.site,
            timeframe=plan.timeframe or req.timeframe,
            items=[i for i in plan.to_dict()["items"]],
            summary=req.audit.get("summary", ""),
        )
    result = plan.to_dict()
    result["plan_id"] = plan_id
    return result


@app.get("/api/audit/plans")
def audit_list_plans(limit: int = 50) -> dict:
    return {"items": audit_storage.list_plans(limit=limit)}


@app.get("/api/audit/plans/{plan_id}")
def audit_get_plan(plan_id: str) -> dict:
    plan = audit_storage.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Not found")
    return plan


@app.delete("/api/audit/plans/{plan_id}")
def audit_delete_plan(plan_id: str) -> dict:
    if not audit_storage.delete_plan(plan_id):
        raise HTTPException(404, "Not found")
    return {"ok": True}


class ExecutePlanItem(BaseModel):
    plan_id: str
    item_index: int
    publish: PublishSpec | None = None
    internal_links: InternalLinkSpec | None = None
    llm: LLMConfig | None = None


@app.post("/api/audit/plan/execute")
def audit_execute_item(req: ExecutePlanItem) -> dict:
    plan = audit_storage.get_plan(req.plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    items = plan.get("items") or []
    if req.item_index < 0 or req.item_index >= len(items):
        raise HTTPException(400, "item_index out of range")
    item = items[req.item_index]

    seo_req = SEORequest(
        topic=item.get("title", ""),
        primary_keyword=item.get("primary_keyword", ""),
        secondary_keywords=item.get("secondary_keywords", []) or [],
        audience=item.get("target_audience", "general readers"),
        word_count=item.get("word_count", 1200) or 1200,
        tone="informative and friendly",
        internal_links=req.internal_links,
        external_links=[],
        check_duplicates=True,
        publish=req.publish,
        save_history=True,
        llm=req.llm,
    )
    try:
        result = seo_article(seo_req)
        audit_storage.update_item_status(
            req.plan_id,
            req.item_index,
            status="published" if result.get("published") else "generated",
            article_id=result.get("history_id") or "",
            published_url=(result.get("published") or {}).get("url", ""),
        )
        return {"ok": True, "result": result}
    except HTTPException:
        raise
    except Exception as exc:
        audit_storage.update_item_status(
            req.plan_id, req.item_index, status="failed", notes=str(exc)[:500]
        )
        raise


class RankingSnapshotReq(BaseModel):
    site: str
    service_account_json: dict[str, Any] | str
    keywords: list[str] = Field(default_factory=list)
    days: int = 7


@app.post("/api/audit/ranking/snapshot")
def audit_ranking_snapshot(req: RankingSnapshotReq) -> dict:
    gsc = GSCClient(req.site, req.service_account_json)
    rows = (
        gsc.positions_for_keywords(req.keywords, days=req.days)
        if req.keywords
        else gsc.top_queries(days=req.days, row_limit=200)
    )
    n = audit_storage.add_ranking(site=req.site, rows=rows, source="gsc")
    return {"saved": n, "rows": rows[:50]}


@app.get("/api/audit/ranking")
def audit_ranking_query(keyword: str, site: str | None = None, days: int = 90) -> dict:
    return {
        "keyword": keyword,
        "site": site,
        "history": audit_storage.ranking_history(keyword, site=site, days=days),
    }


@app.get("/api/audit/ranking/latest")
def audit_ranking_latest(site: str, limit: int = 200) -> dict:
    return {"items": audit_storage.latest_rankings(site=site, limit=limit)}


# ---------------------------------------------------------------------------
# Back-compat aliases (old paths)
# ---------------------------------------------------------------------------


@app.post("/seo-article", include_in_schema=False)
def _seo_legacy(req: SEORequest):
    return seo_article(req)


@app.post("/optimize-listing", include_in_schema=False)
def _listing_legacy(req: ListingRequest):
    return optimize_listing(req)


@app.post("/analyze", include_in_schema=False)
def _analyze_legacy(req: AnalyzeRequest):
    return analyze(req)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
