from __future__ import annotations

from dataclasses import dataclass, field

from ai_agent.data_sources.base import DataSource
from ai_agent.llm.base import LLMProvider


SEO_SYSTEM_PROMPT = """You are an expert SEO content writer. Produce articles
that satisfy search intent, follow E-E-A-T guidelines, and are formatted for
both readers and search engines.

Return output EXACTLY in this format (metadata block, a line with three
hyphens, then an HTML article):

TITLE: <SEO title, 50-60 chars, includes the primary keyword>
META_DESCRIPTION: <150-160 chars, actionable, includes the primary keyword>
SLUG: <kebab-case-url-slug>
KEYWORDS: <primary, secondary1, secondary2, ...>
---
<article>
  <header>
    <h1><!-- primary keyword in the H1 --></h1>
    <p class="lede"><!-- 1-2 sentence hook that also contains the primary keyword --></p>
  </header>
  <nav class="toc" aria-label="Table of contents">
    <ol>
      <li><a href="#section-1">Section 1</a></li>
      <!-- more entries -->
    </ol>
  </nav>
  <section id="section-1">
    <h2>Section 1</h2>
    <p>...</p>
  </section>
  <!-- more sections -->
  <section class="faq" id="faq">
    <h2>Frequently Asked Questions</h2>
    <details>
      <summary>Q1?</summary>
      <p>A1</p>
    </details>
    <!-- 3-5 Q&A pairs -->
  </section>
</article>

<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "<title>",
  "description": "<meta description>",
  "keywords": "<comma-separated keywords>",
  "articleBody": "<plain-text first paragraph>"
}
</script>

Rules:
- Use semantic HTML5 (article, header, nav, section, details, figure).
- The primary keyword MUST appear in the H1 and the first paragraph.
- Use H2/H3 for section/subsection hierarchy. Never skip heading levels.
- Use <ul>/<ol>/<table> where it genuinely helps scannability.
- For external links, use <a href="..." rel="noopener" target="_blank">.
- For internal links, use relative or same-origin URLs and descriptive anchor
  text. NEVER make up URLs — only use URLs from the "Related articles" block
  below. If none are provided, skip internal links.
- If an "External references" block is provided, cite those URLs naturally in
  the body as authoritative sources.
- End the article with a FAQ section (3-5 entries) using <details>/<summary>.
- Append a valid JSON-LD Article schema as the LAST element.
- Do NOT wrap the HTML in markdown fences. Output the metadata block, the
  separator ---, then the HTML, nothing else.
"""


@dataclass
class SEOArticle:
    raw: str
    title: str = ""
    slug: str = ""
    meta_description: str = ""
    keywords: list[str] = field(default_factory=list)
    body_html: str = ""

    @classmethod
    def parse(cls, text: str) -> "SEOArticle":
        lines = text.splitlines()
        sep = None
        for i, line in enumerate(lines):
            if line.strip() == "---":
                sep = i
                break

        meta_block = lines[:sep] if sep is not None else []
        body = "\n".join(lines[sep + 1:]).strip() if sep is not None else text.strip()

        meta: dict[str, str] = {}
        for line in meta_block:
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip().upper()] = v.strip()

        keywords_raw = meta.get("KEYWORDS", "")
        return cls(
            raw=text,
            title=meta.get("TITLE", ""),
            slug=meta.get("SLUG", ""),
            meta_description=meta.get("META_DESCRIPTION", "") or meta.get("META DESCRIPTION", ""),
            keywords=[k.strip() for k in keywords_raw.split(",") if k.strip()],
            body_html=body,
        )


class SEOArticleTask:
    """Generate an SEO-optimized HTML article, optionally grounded in data
    sources and linking to a provided list of related (internal) articles and
    external references."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def run(
        self,
        topic: str,
        *,
        primary_keyword: str,
        secondary_keywords: list[str] | None = None,
        audience: str = "general readers",
        word_count: int = 1200,
        tone: str = "informative and friendly",
        sources: list[DataSource] | None = None,
        related_articles: list[dict] | None = None,
        external_references: list[str] | None = None,
    ) -> SEOArticle:
        parts: list[str] = [
            f"Topic: {topic}",
            f"Primary keyword: {primary_keyword}",
            f"Secondary keywords: {', '.join(secondary_keywords or []) or '(none)'}",
            f"Target audience: {audience}",
            f"Target length: ~{word_count} words",
            f"Tone: {tone}",
        ]

        if related_articles:
            bullets = "\n".join(
                f"- [{r.get('title', '')}]({r.get('url', '')}) — {self._clean(r.get('excerpt', ''))[:200]}"
                for r in related_articles
                if r.get("url")
            )
            parts.append(
                "Related articles (use 2-5 of these as internal links with "
                "descriptive anchor text, only if genuinely relevant):\n"
                + bullets
            )

        if external_references:
            bullets = "\n".join(f"- {url}" for url in external_references if url)
            parts.append(
                "External references (cite as authoritative sources where it "
                "strengthens a claim; use rel=\"noopener\"):\n" + bullets
            )

        if sources:
            ctx = "\n\n".join(f"### {s.describe()}\n{s.load()}" for s in sources)
            parts.append(
                "Use the following reference data when relevant. Do not "
                "fabricate numbers that the data does not support.\n\n" + ctx
            )

        user_prompt = "\n\n".join(parts)

        resp = self.llm.prompt(
            user_prompt,
            system=SEO_SYSTEM_PROMPT,
            temperature=0.6,
            max_tokens=8192,
        )
        return SEOArticle.parse(resp.text)

    @staticmethod
    def _clean(html: str) -> str:
        import re

        return re.sub(r"<[^>]+>", "", html).strip()
