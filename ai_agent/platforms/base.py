from abc import ABC


class PlatformClient(ABC):
    """Base for external platform clients (Shopify, WP, Woo, ...)."""

    name: str = "base"
