from dataclasses import dataclass

from ai_agent.data_sources.base import DataSource
from ai_agent.llm.base import LLMProvider


SEO_SYSTEM_PROMPT = """You are an expert SEO content writer.
Produce articles that satisfy search intent, follow E-E-A-T guidelines, and
are formatted for both readers and search engines.

Always return output in this exact format:

# <SEO Title (50-60 chars, includes primary keyword)>

META DESCRIPTION: <150-160 chars, actionable, includes primary keyword>
SLUG: <kebab-case-url-slug>
KEYWORDS: <comma-separated primary and secondary keywords>

## Introduction
<hook paragraph>

## <H2 section 1>
<body>

## <H2 section 2>
<body>

...

## Conclusion
<summary + CTA>
"""


@dataclass
class SEOArticle:
    raw: str

    def title(self) -> str:
        for line in self.raw.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    def meta(self, key: str) -> str:
        prefix = f"{key.upper()}:"
        for line in self.raw.splitlines():
            if line.startswith(prefix):
                return line[len(prefix):].strip()
        return ""

    @property
    def meta_description(self) -> str:
        return self.meta("META DESCRIPTION")

    @property
    def slug(self) -> str:
        return self.meta("SLUG")

    @property
    def keywords(self) -> list[str]:
        raw = self.meta("KEYWORDS")
        return [k.strip() for k in raw.split(",") if k.strip()]


class SEOArticleTask:
    """Generate an SEO-optimized article, optionally grounded in data sources."""

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
    ) -> SEOArticle:
        context_blocks: list[str] = []
        for src in sources or []:
            context_blocks.append(f"### Source {src.describe()}\n{src.load()}")

        user_prompt = (
            f"Topic: {topic}\n"
            f"Primary keyword: {primary_keyword}\n"
            f"Secondary keywords: {', '.join(secondary_keywords or [])}\n"
            f"Target audience: {audience}\n"
            f"Target length: ~{word_count} words\n"
            f"Tone: {tone}\n"
        )
        if context_blocks:
            user_prompt += (
                "\nUse the following reference data when relevant. Do not "
                "fabricate numbers that are not supported by the data.\n\n"
                + "\n\n".join(context_blocks)
            )

        resp = self.llm.prompt(
            user_prompt,
            system=SEO_SYSTEM_PROMPT,
            temperature=0.6,
            max_tokens=4096,
        )
        return SEOArticle(raw=resp.text)
