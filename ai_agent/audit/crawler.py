"""Crawl a blog's own articles so the audit can reason about what's on-site."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests

from ai_agent.platforms.wordpress import WordPressClient


@dataclass
class CrawledPost:
    url: str
    title: str
    slug: str = ""
    published: str = ""
    excerpt: str = ""
    content_text: str = ""
    word_count: int = 0
    links_out: list[str] = field(default_factory=list)


def _strip_html(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def _count_words(text: str) -> int:
    return len(text.split())


def _extract_links(html: str, base: str) -> list[str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        out.append(urljoin(base, a["href"]))
    return out


class BlogCrawler:
    """Collect posts either via WordPress REST API or a generic sitemap."""

    def __init__(
        self,
        *,
        wp: WordPressClient | None = None,
        base_url: str | None = None,
        timeout: int = 20,
    ):
        self.wp = wp
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout

    def crawl(self, limit: int = 100) -> list[CrawledPost]:
        if self.wp is not None:
            return self._crawl_wp(limit)
        if self.base_url:
            return self._crawl_sitemap(limit)
        raise ValueError("BlogCrawler requires either a WordPressClient or base_url")

    # --- WordPress ----------------------------------------------------------

    def _crawl_wp(self, limit: int) -> list[CrawledPost]:
        out: list[CrawledPost] = []
        page = 1
        per_page = min(limit, 100)
        while len(out) < limit:
            batch = self.wp.list_posts(
                per_page=per_page,
                page=page,
                _fields="id,link,slug,date,title,excerpt,content",
            )
            if not batch:
                break
            for p in batch:
                html = (p.get("content") or {}).get("rendered", "")
                text = _strip_html(html)
                out.append(
                    CrawledPost(
                        url=p.get("link", ""),
                        title=_strip_html((p.get("title") or {}).get("rendered", "")),
                        slug=p.get("slug", ""),
                        published=p.get("date", ""),
                        excerpt=_strip_html((p.get("excerpt") or {}).get("rendered", "")),
                        content_text=text,
                        word_count=_count_words(text),
                        links_out=_extract_links(html, p.get("link", "")),
                    )
                )
                if len(out) >= limit:
                    break
            if len(batch) < per_page:
                break
            page += 1
        return out

    # --- Generic sitemap ----------------------------------------------------

    def _crawl_sitemap(self, limit: int) -> list[CrawledPost]:
        urls = list(self._discover_urls())[:limit]
        out: list[CrawledPost] = []
        for url in urls:
            try:
                out.append(self._fetch_page(url))
            except Exception:
                continue
        return out

    def _discover_urls(self) -> Iterable[str]:
        from xml.etree import ElementTree as ET

        for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
            try:
                resp = requests.get(self.base_url + path, timeout=self.timeout)
                if resp.status_code != 200 or "<" not in resp.text:
                    continue
                root = ET.fromstring(resp.text)
                for loc in root.iter():
                    if loc.tag.endswith("}loc") or loc.tag == "loc":
                        url = (loc.text or "").strip()
                        if url:
                            # Nested sitemap
                            if url.endswith(".xml"):
                                yield from self._read_sub_sitemap(url)
                            else:
                                yield url
                return
            except Exception:
                continue

    def _read_sub_sitemap(self, url: str):
        from xml.etree import ElementTree as ET

        try:
            resp = requests.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                return
            root = ET.fromstring(resp.text)
            for loc in root.iter():
                if loc.tag.endswith("}loc") or loc.tag == "loc":
                    t = (loc.text or "").strip()
                    if t and not t.endswith(".xml"):
                        yield t
        except Exception:
            return

    def _fetch_page(self, url: str) -> CrawledPost:
        from bs4 import BeautifulSoup

        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        title = (soup.title.string if soup.title else "") or ""
        body = soup.find("article") or soup.find("main") or soup.body or soup
        text = _strip_html(str(body))
        slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        return CrawledPost(
            url=url,
            title=title.strip(),
            slug=slug,
            content_text=text,
            word_count=_count_words(text),
            links_out=_extract_links(resp.text, url),
        )
