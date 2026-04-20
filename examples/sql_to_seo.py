"""Pull data from a SQL DB, then use it as grounding for an SEO article."""

import os

from dotenv import load_dotenv

from ai_agent import AIAgent, ClaudeProvider, DatabaseSource

load_dotenv()


def main() -> None:
    agent = AIAgent(llm=ClaudeProvider())
    agent.register_source(
        DatabaseSource(
            url=os.environ["DATABASE_URL"],
            query=(
                "SELECT category, SUM(revenue) AS revenue, COUNT(*) AS orders "
                "FROM sales WHERE order_date >= :start GROUP BY category "
                "ORDER BY revenue DESC"
            ),
            params={"start": "2026-01-01"},
        ),
        name="q1_sales",
    )

    article = agent.write_seo_article(
        topic="Top-performing product categories in Q1 2026",
        primary_keyword="Q1 2026 bestselling products",
        secondary_keywords=["product trends", "ecommerce insights"],
        audience="ecommerce merchandisers",
        word_count=1000,
        use_sources=["q1_sales"],
    )
    print(article.raw)


if __name__ == "__main__":
    main()
