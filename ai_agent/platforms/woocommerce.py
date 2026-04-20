import requests

from ai_agent.platforms.base import PlatformClient


class WooCommerceClient(PlatformClient):
    """WooCommerce REST API client using consumer key/secret (HTTP Basic)."""

    name = "woocommerce"

    def __init__(
        self,
        base_url: str,
        consumer_key: str,
        consumer_secret: str,
        version: str = "wc/v3",
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.version = version
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = (consumer_key, consumer_secret)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/wp-json/{self.version}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs):
        resp = self.session.request(method, self._url(path), timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # --- Products -----------------------------------------------------------

    def list_products(self, per_page: int = 20, **params) -> list[dict]:
        return self._request("GET", "products", params={"per_page": per_page, **params})

    def get_product(self, product_id: int) -> dict:
        return self._request("GET", f"products/{product_id}")

    def create_product(self, product: dict) -> dict:
        return self._request("POST", "products", json=product)

    def update_product(self, product_id: int, updates: dict) -> dict:
        return self._request("PUT", f"products/{product_id}", json=updates)

    def update_product_seo(
        self,
        product_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        short_description: str | None = None,
        meta_data: list[dict] | None = None,
    ) -> dict:
        updates: dict = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if short_description is not None:
            updates["short_description"] = short_description
        if meta_data:
            updates["meta_data"] = meta_data
        return self.update_product(product_id, updates)
