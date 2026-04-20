import requests

from ai_agent.platforms.base import PlatformClient


class ShopifyClient(PlatformClient):
    """Shopify Admin REST API client using an Access Token.

    Create a custom app in your Shopify admin to obtain an Admin API access
    token (``shpat_...``).
    """

    name = "shopify"

    def __init__(
        self,
        shop: str,
        access_token: str,
        api_version: str = "2024-10",
        timeout: int = 30,
    ):
        self.shop = shop.replace("https://", "").rstrip("/")
        self.api_version = api_version
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        return f"https://{self.shop}/admin/api/{self.api_version}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs):
        resp = self.session.request(method, self._url(path), timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # --- Products -----------------------------------------------------------

    def list_products(self, limit: int = 50, **params) -> list[dict]:
        data = self._request("GET", "products.json", params={"limit": limit, **params})
        return data.get("products", [])

    def get_product(self, product_id: int) -> dict:
        return self._request("GET", f"products/{product_id}.json").get("product", {})

    def create_product(self, product: dict) -> dict:
        return self._request("POST", "products.json", json={"product": product}).get(
            "product", {}
        )

    def update_product(self, product_id: int, updates: dict) -> dict:
        payload = {"product": {"id": product_id, **updates}}
        return self._request("PUT", f"products/{product_id}.json", json=payload).get(
            "product", {}
        )

    def update_product_seo(
        self,
        product_id: int,
        *,
        title: str | None = None,
        body_html: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
    ) -> dict:
        updates: dict = {}
        if title is not None:
            updates["title"] = title
        if body_html is not None:
            updates["body_html"] = body_html
        if meta_title is not None or meta_description is not None:
            updates["metafields"] = [
                {
                    "namespace": "global",
                    "key": "title_tag",
                    "value": meta_title or "",
                    "type": "single_line_text_field",
                },
                {
                    "namespace": "global",
                    "key": "description_tag",
                    "value": meta_description or "",
                    "type": "single_line_text_field",
                },
            ]
        return self.update_product(product_id, updates)
