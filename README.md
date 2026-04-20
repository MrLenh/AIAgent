# AI Agent Module

A pluggable AI Agent that:

- Connects to multiple LLM providers (**OpenAI**, **Anthropic Claude**, **Google Gemini**) behind a uniform interface.
- Loads context data from **text**, **CSV**, or **SQL databases** (PostgreSQL, MySQL, SQLite, ...) to ground LLM responses.
- Publishes or updates content on public platforms (**Shopify**, **WordPress**, **WooCommerce**) via token/authentication.
- Ships with built-in tasks: **SEO article generation**, **product listing optimization**, and **natural-language data analysis**.

## Install

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in your API keys
```

## Quick start

```python
from ai_agent import AIAgent, ClaudeProvider, CSVSource, WordPressClient

agent = AIAgent(llm=ClaudeProvider(model="claude-sonnet-4-6"))

# 1. Connect data
agent.register_source(CSVSource("data/keywords.csv"), name="keywords")

# 2. Connect a publishing platform
agent.register_platform(
    "wp",
    WordPressClient(
        base_url="https://example.com",
        username="admin",
        app_password="xxxx xxxx xxxx xxxx",
    ),
)

# 3. Ask the agent to do work
article = agent.write_seo_article(
    topic="Best pour-over coffee drippers in 2026",
    primary_keyword="pour over coffee dripper",
    use_sources=["keywords"],
)
agent.publish_article("wp", article, status="draft")
```

## Architecture

```
ai_agent/
├── agent.py                # AIAgent orchestrator
├── llm/                    # LLMProvider interface + OpenAI/Claude/Gemini impls
├── data_sources/           # DataSource interface + Text/CSV/Database impls
├── platforms/              # PlatformClient interface + Shopify/WP/Woo impls
└── tasks/                  # SEO, Listing, Analysis tasks
```

Every layer is swappable: add a new LLM by subclassing `LLMProvider`, a new data
feed by subclassing `DataSource`, a new destination by subclassing
`PlatformClient`.

## LLM providers

| Provider | Class | Auth |
|----------|-------|------|
| OpenAI | `OpenAIProvider` | `OPENAI_API_KEY` |
| Anthropic Claude | `ClaudeProvider` (prompt caching on by default) | `ANTHROPIC_API_KEY` |
| Google Gemini | `GeminiProvider` | `GEMINI_API_KEY` |

```python
from ai_agent import OpenAIProvider, ClaudeProvider, GeminiProvider

llm = ClaudeProvider(model="claude-opus-4-7")       # most capable
llm = ClaudeProvider(model="claude-haiku-4-5-20251001")  # fastest
llm = OpenAIProvider(model="gpt-4o")
llm = GeminiProvider(model="gemini-1.5-pro")
```

## Data sources

```python
from ai_agent import TextSource, CSVSource, DatabaseSource

TextSource(path="brief.md")
CSVSource("sales.csv", max_rows=500)
DatabaseSource(
    url="postgresql://user:pass@host:5432/db",
    query="SELECT * FROM products WHERE active = :active",
    params={"active": True},
)
```

All sources implement `.load() -> str`, producing a prompt-ready markdown blob.

## Platforms

### Shopify (Admin REST API)
```python
from ai_agent import ShopifyClient

shop = ShopifyClient(shop="my-store.myshopify.com", access_token="shpat_...")
products = shop.list_products(limit=50)
shop.update_product_seo(product_id, meta_title="...", meta_description="...")
```

### WordPress (Application Password or JWT)
```python
from ai_agent import WordPressClient

wp = WordPressClient(
    base_url="https://example.com",
    username="admin",
    app_password="xxxx xxxx xxxx xxxx",
)
wp.create_post(title="...", content="...", status="draft")
```

### WooCommerce (Consumer Key/Secret)
```python
from ai_agent import WooCommerceClient

woo = WooCommerceClient(
    base_url="https://example.com",
    consumer_key="ck_...",
    consumer_secret="cs_...",
)
woo.update_product_seo(product_id, name="...", description="...")
```

## Built-in tasks

| Task | Method | Output |
|------|--------|--------|
| SEO article | `agent.write_seo_article(...)` | `SEOArticle` (title, slug, meta, body) |
| Listing optimization | `agent.optimize_listing(...)` | `OptimizedListing` (title, meta, HTML, bullets, tags) |
| Data analysis | `agent.analyze(question, use_sources=[...])` | Markdown report |

## Examples

See `examples/`:

- `seo_article.py` — generate an article with Claude and draft it to WordPress.
- `analyze_csv.py` — analyze a CSV using GPT-4o.
- `optimize_shopify.py` — rewrite a Shopify product listing using Gemini.
- `sql_to_seo.py` — pull live SQL data and turn it into an SEO article.

## Running as a service

The module also ships with a FastAPI entrypoint (`main.py`) so it can be
deployed directly to Railway/Fly/Render. Select the LLM with the
`LLM_PROVIDER` env var (`claude` | `openai` | `gemini`).

```bash
LLM_PROVIDER=claude ANTHROPIC_API_KEY=sk-ant-... \
  uvicorn main:app --host 0.0.0.0 --port 8000
```

Endpoints:

- `GET /health` – liveness + LLM-config check
- `POST /seo-article` – `{topic, primary_keyword, ...}`
- `POST /optimize-listing` – `{current_title, current_description, ...}`
- `POST /analyze` – `{question, sources:[{type:"csv",path:"..."}, ...]}`

`railpack.json` and `Procfile` are included so Railway/Heroku-style platforms
can build and start the service out of the box.

## Environment variables

See `.env.example`. The module reads credentials from environment variables by
default, but every constructor also accepts explicit parameters so you can plug
in your own secret manager.
