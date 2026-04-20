"""HTTP entrypoint for the AI Agent module.

Exposes the agent's core tasks over REST so the module can be deployed as a
service (Railway, Fly.io, Render, etc.). The LLM provider is selected via the
``LLM_PROVIDER`` env var (``claude``, ``openai``, or ``gemini``).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ai_agent import AIAgent, ClaudeProvider, GeminiProvider, OpenAIProvider
from ai_agent.data_sources import CSVSource, DatabaseSource, TextSource
from ai_agent.llm.base import LLMProvider


def _build_llm() -> LLMProvider | None:
    provider = os.getenv("LLM_PROVIDER", "").lower()
    try:
        if provider == "openai":
            return OpenAIProvider(model=os.getenv("OPENAI_MODEL", "gpt-4o"))
        if provider == "gemini":
            return GeminiProvider(model=os.getenv("GEMINI_MODEL", "gemini-1.5-pro"))
        if provider == "claude" or (provider == "" and os.getenv("ANTHROPIC_API_KEY")):
            return ClaudeProvider(model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"))
    except ValueError:
        return None
    return None


app = FastAPI(title="AI Agent", version="0.1.0")


def _require_agent() -> AIAgent:
    llm = _build_llm()
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No LLM provider configured. Set LLM_PROVIDER and the matching "
                "API key (ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY)."
            ),
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


@app.get("/")
def root() -> dict:
    return {
        "service": "ai-agent",
        "endpoints": ["/health", "/seo-article", "/optimize-listing", "/analyze"],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm_configured": _build_llm() is not None}


class SEORequest(BaseModel):
    topic: str
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    audience: str = "general readers"
    word_count: int = 1200
    tone: str = "informative and friendly"
    sources: list[dict[str, Any]] = Field(default_factory=list)


@app.post("/seo-article")
def seo_article(req: SEORequest) -> dict:
    agent = _require_agent()
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


class ListingRequest(BaseModel):
    current_title: str
    current_description: str = ""
    product_attributes: dict[str, Any] = Field(default_factory=dict)
    primary_keyword: str | None = None
    target_audience: str = "online shoppers"


@app.post("/optimize-listing")
def optimize_listing(req: ListingRequest) -> dict:
    agent = _require_agent()
    listing = agent.optimize_listing(
        current_title=req.current_title,
        current_description=req.current_description,
        product_attributes=req.product_attributes,
        primary_keyword=req.primary_keyword,
        target_audience=req.target_audience,
    )
    return listing.__dict__


class AnalyzeRequest(BaseModel):
    question: str
    sources: list[dict[str, Any]]


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    agent = _require_agent()
    for idx, src in enumerate(_build_sources(req.sources)):
        agent.register_source(src, name=f"src_{idx}")
    report = agent.analyze(req.question)
    return {"report": report}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
