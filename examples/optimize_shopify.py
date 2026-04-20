"""Fetch a Shopify product, rewrite its listing for SEO, and push the result back."""

import os

from dotenv import load_dotenv

from ai_agent import AIAgent, GeminiProvider, ShopifyClient

load_dotenv()


def main() -> None:
    shopify = ShopifyClient(
        shop=os.environ["SHOPIFY_SHOP"],
        access_token=os.environ["SHOPIFY_ACCESS_TOKEN"],
    )
    agent = AIAgent(llm=GeminiProvider(model="gemini-1.5-pro"))
    agent.register_platform("shop", shopify)

    product_id = 1234567890
    product = shopify.get_product(product_id)

    listing = agent.optimize_listing(
        current_title=product["title"],
        current_description=product.get("body_html", ""),
        product_attributes={
            "type": product.get("product_type", ""),
            "vendor": product.get("vendor", ""),
            "tags": product.get("tags", ""),
        },
        primary_keyword="organic green tea",
        target_audience="wellness-focused shoppers",
    )

    result = agent.apply_listing("shop", product_id, listing)
    print("Updated:", result.get("title"))


if __name__ == "__main__":
    main()
