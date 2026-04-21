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

## Audit pipeline

The **Audit** tab runs a full SEO audit → plan → execute loop:

1. **Crawl site** – WordPress REST or generic sitemap. Gathers URL, title, word
   count, outbound links.
2. **Google Search Console** – service-account JSON → top queries + top pages
   (28 days by default). Endpoints: `/api/audit/gsc/query`, `/api/audit/gsc/sites`.
3. **Ahrefs (optional)** – organic competitors + content gap + keyword ideas.
   Endpoints: `/api/audit/ahrefs/*`.
4. **Keyword audit** – `/api/audit/run` feeds everything to the LLM and
   returns structured JSON: quick wins, content gaps, cannibalization,
   competitor insights.
5. **Content plan** – `/api/audit/plan` turns the audit into a prioritised
   list of articles (new / update / consolidate), saved to
   `audit_storage.content_plan`.
6. **Execute** – `/api/audit/plan/execute` generates a single plan item and
   optionally auto-publishes to WordPress. Updates status per item.
7. **Ranking tracker** – `/api/audit/ranking/snapshot` pulls GSC for the given
   keywords and appends a row per run; `/api/audit/ranking?keyword=...` returns
   the time series. Schedule via Railway cron / n8n / Zapier.

All endpoints accept service-account JSON + Ahrefs token in the request body
so no secrets need to live in env.

## Admin UI

A lightweight SPA (Tailwind + Alpine.js, no build step) is bundled in
`static/` and served at `/`. It provides:

- **Status** – live view of LLM + platform env config
- **SEO Article** – form-driven article generation, one-click publish to WordPress
- **Listing Optimizer** – fetch a Shopify/WooCommerce product by ID, rewrite,
  push the result back
- **Data Analysis** – upload a CSV, run a SQL query, or paste raw text, then ask
  a natural-language question
- **Settings** – per-browser overrides for LLM and platform credentials
  (saved in `localStorage`, sent per-request)

Open `http://localhost:8000/` after starting the service.

## Running as a service

The module also ships with a FastAPI entrypoint (`main.py`) so it can be
deployed directly to Railway/Fly/Render. Select the LLM with the
`LLM_PROVIDER` env var (`claude` | `openai` | `gemini`).

```bash
LLM_PROVIDER=claude ANTHROPIC_API_KEY=sk-ant-... \
  uvicorn main:app --host 0.0.0.0 --port 8000
```

Endpoints (under `/api`):

- `GET /api/status` – liveness + LLM/platform env check
- `POST /api/seo-article` – `{topic, primary_keyword, ..., llm?}`
- `POST /api/optimize-listing` – `{current_title, current_description, ..., llm?}`
- `POST /api/analyze` – `{question, sources:[{type:"csv",path:"..."}, ...], llm?}`
- `POST /api/analyze-upload` – multipart form with CSV file + question
- `POST /api/shopify/product`, `/api/shopify/apply-listing`
- `POST /api/woocommerce/product`, `/api/woocommerce/apply-listing`
- `POST /api/wordpress/publish`
- `POST /api/platforms/test` – validate credentials

Every task endpoint accepts an optional `llm` object
(`{provider, model, api_key}`) to override the server-side env for that single
request. Interactive docs: `/api/docs`.

`railpack.json` and `Procfile` are included so Railway/Heroku-style platforms
can build and start the service out of the box.

### Deploying to Railway

1. Create a service from this repo.
2. In the service's **Variables** tab, set at minimum:
   - `LLM_PROVIDER` = `claude` (or `openai` / `gemini`)
   - Matching key: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY`
3. (Optional) Add platform credentials only if you use them: `SHOPIFY_*`,
   `WORDPRESS_*`, `WOOCOMMERCE_*`, `DATABASE_URL`.
4. Railway injects `$PORT` automatically — the start command in `railpack.json`
   already binds to it.
5. Hit `/health` to verify `llm_configured: true`.

## Environment variables

See `.env.example`. The module reads credentials from environment variables by
default, but every constructor also accepts explicit parameters so you can plug
in your own secret manager.
