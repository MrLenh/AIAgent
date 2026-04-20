import requests
from requests.auth import HTTPBasicAuth

from ai_agent.platforms.base import PlatformClient


class WordPressClient(PlatformClient):
    """WordPress REST API client.

    Uses Application Passwords (recommended) or a JWT token. Create an
    application password under Users -> Profile -> Application Passwords.
    """

    name = "wordpress"

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        app_password: str | None = None,
        jwt_token: str | None = None,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        if jwt_token:
            self.session.headers["Authorization"] = f"Bearer {jwt_token}"
        elif username and app_password:
            self.session.auth = HTTPBasicAuth(username, app_password)
        else:
            raise ValueError("Provide either jwt_token or username + app_password")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/wp-json/wp/v2/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs):
        resp = self.session.request(method, self._url(path), timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # --- Posts --------------------------------------------------------------

    def list_posts(self, per_page: int = 20, **params) -> list[dict]:
        return self._request("GET", "posts", params={"per_page": per_page, **params})

    def get_post(self, post_id: int) -> dict:
        return self._request("GET", f"posts/{post_id}")

    def create_post(
        self,
        *,
        title: str,
        content: str,
        status: str = "draft",
        excerpt: str | None = None,
        categories: list[int] | None = None,
        tags: list[int] | None = None,
        meta: dict | None = None,
    ) -> dict:
        payload: dict = {"title": title, "content": content, "status": status}
        if excerpt:
            payload["excerpt"] = excerpt
        if categories:
            payload["categories"] = categories
        if tags:
            payload["tags"] = tags
        if meta:
            payload["meta"] = meta
        return self._request("POST", "posts", json=payload)

    def update_post(self, post_id: int, updates: dict) -> dict:
        return self._request("POST", f"posts/{post_id}", json=updates)
