from ai_agent.data_sources.base import DataSource
from ai_agent.llm.base import LLMProvider
from ai_agent.platforms.base import PlatformClient
from ai_agent.tasks.analysis import DataAnalysisTask
from ai_agent.tasks.listing import ListingOptimizerTask, OptimizedListing
from ai_agent.tasks.seo import SEOArticle, SEOArticleTask


class AIAgent:
    """Orchestrates an LLM, data sources, and publishing platforms.

    Example:
        agent = AIAgent(llm=ClaudeProvider())
        agent.register_source(CSVSource("sales.csv"))
        agent.register_platform("shop", ShopifyClient(...))

        article = agent.write_seo_article(
            topic="How to brew pour-over coffee",
            primary_keyword="pour over coffee",
        )
        agent.publish_article("wp", article)
    """

    def __init__(self, llm: LLMProvider):
        self.llm = llm
        self.sources: dict[str, DataSource] = {}
        self.platforms: dict[str, PlatformClient] = {}

    # --- Registration -------------------------------------------------------

    def register_source(self, source: DataSource, name: str | None = None) -> None:
        key = name or source.name
        self.sources[key] = source

    def register_platform(self, name: str, client: PlatformClient) -> None:
        self.platforms[name] = client

    def _collect_sources(self, names: list[str] | None) -> list[DataSource]:
        if names is None:
            return list(self.sources.values())
        return [self.sources[n] for n in names]

    # --- Tasks --------------------------------------------------------------

    def write_seo_article(
        self,
        topic: str,
        *,
        primary_keyword: str,
        secondary_keywords: list[str] | None = None,
        audience: str = "general readers",
        word_count: int = 1200,
        tone: str = "informative and friendly",
        use_sources: list[str] | None = None,
    ) -> SEOArticle:
        task = SEOArticleTask(self.llm)
        return task.run(
            topic,
            primary_keyword=primary_keyword,
            secondary_keywords=secondary_keywords,
            audience=audience,
            word_count=word_count,
            tone=tone,
            sources=self._collect_sources(use_sources),
        )

    def optimize_listing(
        self,
        *,
        current_title: str,
        current_description: str = "",
        product_attributes: dict | None = None,
        primary_keyword: str | None = None,
        target_audience: str = "online shoppers",
    ) -> OptimizedListing:
        task = ListingOptimizerTask(self.llm)
        return task.run(
            current_title=current_title,
            current_description=current_description,
            product_attributes=product_attributes,
            primary_keyword=primary_keyword,
            target_audience=target_audience,
        )

    def analyze(self, question: str, use_sources: list[str] | None = None) -> str:
        task = DataAnalysisTask(self.llm)
        return task.run(question, self._collect_sources(use_sources))

    # --- Publishing ---------------------------------------------------------

    def publish_article(
        self,
        platform_name: str,
        article: SEOArticle,
        *,
        status: str = "draft",
    ) -> dict:
        platform = self.platforms[platform_name]
        # WordPress
        if hasattr(platform, "create_post"):
            return platform.create_post(
                title=article.title(),
                content=article.raw,
                excerpt=article.meta_description,
                status=status,
            )
        raise TypeError(f"Platform '{platform_name}' does not support article publishing")

    def apply_listing(
        self,
        platform_name: str,
        product_id: int,
        listing: OptimizedListing,
    ) -> dict:
        platform = self.platforms[platform_name]
        if platform.name == "shopify":
            return platform.update_product_seo(
                product_id,
                title=listing.title,
                body_html=listing.description_html,
                meta_title=listing.meta_title,
                meta_description=listing.meta_description,
            )
        if platform.name == "woocommerce":
            return platform.update_product_seo(
                product_id,
                name=listing.title,
                description=listing.description_html,
                short_description=listing.short_description,
                meta_data=[
                    {"key": "_yoast_wpseo_title", "value": listing.meta_title},
                    {"key": "_yoast_wpseo_metadesc", "value": listing.meta_description},
                ],
            )
        raise TypeError(f"Platform '{platform_name}' does not support product updates")
