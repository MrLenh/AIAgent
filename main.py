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
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ai_agent import (
    AIAgent,
    ClaudeProvider,
    GeminiProvider,
    OpenAIProvider,
    ShopifyClient,
    WooCommerceClient,
    WordPressClient,
)
from ai_agent.data_sources import CSVSource, DatabaseSource, TextSource
from ai_agent.llm.base import LLMProvider
from ai_agent.tasks.listing import OptimizedListing


BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"


# ---------------------------------------------------------------------------
# LLM + source builders
# ---------------------------------------------------------------------------


class LLMConfig(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


def _build_llm(override: LLMConfig | None = None) -> LLMProvider | None:
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
                api_key=api_key, model=model or os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
            )
        if provider == "claude" or (provider == "" and os.getenv("ANTHROPIC_API_KEY")):
            return ClaudeProvider(
                api_key=api_key, model=model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
            )
    except ValueError:
        return None
    return None


def _require_agent(override: LLMConfig | None = None) -> AIAgent:
    llm = _build_llm(override)
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


class SEORequest(BaseModel):
    topic: str
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    audience: str = "general readers"
    word_count: int = 1200
    tone: str = "informative and friendly"
    sources: list[dict[str, Any]] = Field(default_factory=list)
    llm: LLMConfig | None = None


@app.post("/api/seo-article")
def seo_article(req: SEORequest) -> dict:
    agent = _require_agent(req.llm)
    for idx, src in enumerate(_build_sources(req.sources)):
        agent.register_source(src, name=f"src_{idx}")
    article = agent.write_seo_article(
        topic=req.topic,
        primary_keyword=req.primary_keyword,
        secondary_keywords=req.secondary_keywords,
        audience=req.audience,
        word_count=req.word_count,
        tone=req.tone,
    )
    return {
        "title": article.title(),
        "slug": article.slug,
        "meta_description": article.meta_description,
        "keywords": article.keywords,
        "body": article.raw,
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
