"""Generate an SEO-optimized article and publish to WordPress as a draft."""

import os

from dotenv import load_dotenv

from ai_agent import AIAgent, ClaudeProvider, WordPressClient

load_dotenv()


def main() -> None:
    agent = AIAgent(llm=ClaudeProvider(model="claude-sonnet-4-6"))
    agent.register_platform(
        "wp",
        WordPressClient(
            base_url=os.environ["WORDPRESS_URL"],
            username=os.environ["WORDPRESS_USERNAME"],
            app_password=os.environ["WORDPRESS_APP_PASSWORD"],
        ),
    )

    article = agent.write_seo_article(
        topic="How to choose the right pour-over coffee dripper",
        primary_keyword="pour over coffee dripper",
        secondary_keywords=["V60", "Kalita Wave", "Chemex", "coffee brewing"],
        audience="home coffee enthusiasts",
        word_count=1400,
    )

    print("Title:", article.title)
    print("Slug:", article.slug)
    print("Meta:", article.meta_description)

    published = agent.publish_article("wp", article, status="draft")
    print("Draft URL:", published.get("link"))


if __name__ == "__main__":
    main()
