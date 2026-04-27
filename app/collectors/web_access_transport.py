"""
app/collectors/web_access_transport.py

WebAccessTransport — bridges the CopilotResearchCollector with real web
search and fetch capabilities, using the web-access CDP proxy for browser-
based operations and direct HTTP for static pages.

Architecture
------------
1. Search phase: executes search queries against DuckDuckGo (via direct HTTP)
   or search engines via CDP proxy for richer results.
2. Fetch phase: retrieves page content via direct HTTP (static) or CDP proxy
   (JavaScript-rendered).
3. Extract phase: parses HTML with BeautifulSoup, extracts title/text/url,
   and returns structured items in ResearchResponse.

CDP proxy integration
---------------------
When the web-access CDP proxy is available at ``localhost:3456``, this
transport can use Chrome's remote-debugging for pages that require
JavaScript rendering or for richer search results.  When the proxy is
unavailable, it falls back to direct HTTP requests.

Usage
-----
::

    from app.collectors.copilot_research_collector import CopilotResearchCollector
    from app.collectors.web_access_transport import WebAccessTransport

    transport = WebAccessTransport()
    collector = CopilotResearchCollector(transport=transport)
"""

from __future__ import annotations

import datetime
import html
import json
import re
import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from app.collectors.copilot_research_collector import (
    ResearchRequest,
    ResearchResponse,
    ResearchTransport,
)

_SOURCE_ID = "copilot_research"

# Default search queries used when no keywords are provided.
_DEFAULT_AI_INVESTMENT_QUERIES = [
    "AI startup funding investment news site:techcrunch.com",
    "artificial intelligence investment VC funding site:reuters.com",
    "AI company acquisition merger site:cnbc.com",
    "AI 人工智能 投融资 新闻 site:36kr.com",
    "artificial intelligence financing round latest",
    "AI investment news today",
]

# User-Agent for HTTP requests
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# CDP Proxy client
# ---------------------------------------------------------------------------


class CDPProxyClient:
    """Minimal HTTP client for the web-access CDP proxy at localhost:3456."""

    def __init__(self, base_url: str = "http://localhost:3456", timeout: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def is_available(self) -> bool:
        """Check whether the CDP proxy is running."""
        try:
            import urllib.request

            req = urllib.request.Request(
                f"{self._base_url}/targets",
                headers={"User-Agent": _USER_AGENT},
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False

    def new_tab(self, url: str) -> str | None:
        """Create a new browser tab and return its target ID."""
        try:
            import urllib.request

            encoded = urllib.parse.quote(url, safe="")
            req = urllib.request.Request(
                f"{self._base_url}/new?url={encoded}",
                headers={"User-Agent": _USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("targetId") or data.get("id")
        except Exception:
            return None

    def eval_js(self, target_id: str, expression: str) -> str | None:
        """Execute JavaScript in a tab and return the unwrapped result.

        The CDP proxy returns ``{"value": "<result>"}`` — this method
        extracts the ``value`` field so callers get the bare JS return.
        """
        try:
            import urllib.request

            req = urllib.request.Request(
                f"{self._base_url}/eval?target={target_id}",
                data=expression.encode("utf-8"),
                headers={"User-Agent": _USER_AGENT, "Content-Type": "text/plain"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                wrapped = json.loads(body)
                return wrapped.get("value", body)
        except Exception:
            return None

    def navigate(self, target_id: str, url: str) -> bool:
        """Navigate an existing tab to a new URL."""
        try:
            import urllib.request

            encoded = urllib.parse.quote(url, safe="")
            req = urllib.request.Request(
                f"{self._base_url}/navigate?target={target_id}&url={encoded}",
                headers={"User-Agent": _USER_AGENT},
            )
            urllib.request.urlopen(req, timeout=self._timeout)
            return True
        except Exception:
            return False

    def close_tab(self, target_id: str) -> None:
        """Close a browser tab."""
        try:
            import urllib.request

            req = urllib.request.Request(
                f"{self._base_url}/close?target={target_id}",
                headers={"User-Agent": _USER_AGENT},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    def get_page_text(self, url: str) -> str | None:
        """Open a URL in a new tab and extract visible text content."""
        target_id = self.new_tab(url)
        if not target_id:
            return None
        try:
            # Wait a moment for the page to load
            time.sleep(2)
            text = self.eval_js(target_id, "document.body.innerText")
            return text
        finally:
            self.close_tab(target_id)

    def search_bing(self, query: str, max_results: int = 10) -> list[dict[str, str]]:
        """Search Bing via CDP browser and extract result links."""
        search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        target_id = self.new_tab(search_url)
        if not target_id:
            return []
        try:
            time.sleep(3)
            # Extract search result links from the Bing results page
            js = """
            (() => {
                const results = [];
                document.querySelectorAll('li.b_algo h2 a, h2 a[href^="http"], .b_title a').forEach(a => {
                    if (a.textContent.trim()) results.push({title: a.textContent.trim(), url: a.href});
                });
                return JSON.stringify(results.slice(0, """ + str(max_results) + """));
            })()
            """
            raw = self.eval_js(target_id, js)
            if raw:
                return json.loads(raw)
            return []
        except Exception:
            return []
        finally:
            self.close_tab(target_id)


# ---------------------------------------------------------------------------
# Static HTTP search and fetch
# ---------------------------------------------------------------------------


def _fetch_html(url: str, timeout: int = 15) -> str | None:
    """Fetch a URL and return its HTML content as a string."""
    try:
        import requests

        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


def _extract_text_from_html(html_content: str) -> str:
    """Extract readable text from HTML content using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "lxml")
        # Remove script/style/nav/footer elements
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return html.unescape(text)[:5000]
    except Exception:
        # Fallback: simple regex-based extraction
        clean = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return html.unescape(clean)[:5000]


def _search_bing(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """Search Bing and extract result links.

    Bing is the primary backend because DuckDuckGo is frequently
    unreachable from mainland China.  Results are requested with
    ``setmkt=en-US`` to favour English-language content.
    """
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    try:
        import requests

        url = (
            f"https://www.bing.com/search"
            f"?q={urllib.parse.quote(query)}"
            f"&setmkt=en-US"
            f"&cc=us"
            f"&setlang=en"
        )
        resp = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.5",
            },
        )
        resp.raise_for_status()

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "lxml")
        # Bing result selectors — try several known patterns
        for selector in [
            "li.b_algo h2 a",       # standard Bing algo result
            "li.b_ans h2 a",        # Bing answer result
            "h2 a[href]",           # generic h2 link
            ".b_title a",           # older Bing
        ]:
            links = soup.select(selector)
            if links:
                for link in links:
                    title = link.get_text(strip=True)
                    href = link.get("href", "").strip()
                    if not title or not href:
                        continue
                    if href.startswith("javascript"):
                        continue
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    results.append({"title": title, "url": href})
                    if len(results) >= max_results:
                        break
            if results:
                break
    except Exception:
        pass
    return results


def _search_bing_news(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """Search Bing News for investment-related articles.

    Uses the Bing News vertical which surfaces recent articles from
    recognised news outlets — more useful for the daily pipeline than
    general web search.
    """
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    try:
        import requests

        url = (
            f"https://www.bing.com/news/search"
            f"?q={urllib.parse.quote(query)}"
            f"&setmkt=en-US"
            f"&cc=us"
            f"&qft=interval%3d%227%22"   # last 7 days
            f"&format=rs"
            f"&count={max_results}"
        )
        resp = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        resp.raise_for_status()

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "lxml")
        # Bing News result cards
        for card in soup.select(".news-card, article, .t_s"):
            link = card.select_one("a[href]")
            if link:
                title = link.get_text(strip=True)
                href = link.get("href", "").strip()
                if title and href and href not in seen_urls:
                    seen_urls.add(href)
                    results.append({"title": title, "url": href})
                    if len(results) >= max_results:
                        break
        # Fallback: generic links in the page
        if not results:
            for a in soup.select("a.title, a[href^='http']"):
                title = a.get_text(strip=True)
                href = a.get("href", "").strip()
                if title and href and href not in seen_urls and len(title) > 10:
                    seen_urls.add(href)
                    results.append({"title": title, "url": href})
                    if len(results) >= max_results:
                        break
    except Exception:
        pass
    return results


def _search_duckduckgo_html(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """Search DuckDuckGo via the HTML (non-JS) interface.

    Deprecated as primary backend — DuckDuckGo is often unreachable from
    mainland China.  Kept as fallback for environments where it works.
    """
    results: list[dict[str, str]] = []
    try:
        import requests

        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(
            url,
            data={"q": query, "kl": "us-en"},
            timeout=15,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "lxml")
        for link in soup.select("a.result__a"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href.startswith("//"):
                href = "https:" + href
            if title and href:
                results.append({"title": title, "url": href})
            if len(results) >= max_results:
                break
    except Exception:
        pass
    return results


def _extract_article_links(html_content: str, base_url: str = "") -> list[str]:
    """Extract article-like links from a category / landing page.

    Returns deduplicated absolute URLs that look like individual article
    pages, filtering out navigation, header, and footer boilerplate.
    """
    links: list[str] = []
    seen: set[str] = set()
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin

        soup = BeautifulSoup(html_content, "lxml")

        # Remove nav/header/footer elements before searching
        for tag in soup(["nav", "header", "footer", "noscript"]):
            tag.decompose()

        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            text = a.get_text(strip=True)

            # Basic filtering
            if not text or len(text) < 20:
                continue
            if not href or href.startswith(("javascript:", "#", "mailto:")):
                continue

            # Resolve relative URLs
            if base_url:
                href = urljoin(base_url, href)
            if not href.startswith("http"):
                continue

            # Skip known non-article paths
            skip_patterns = [
                "/category/", "/tag/", "/author/", "/about", "/contact",
                "/login", "/signup", "/register", "/search", "/page/",
                "/events/", "/podcast", "/video", "/newsletter",
                "/sponsored/", "/brand-studio", "/startup-battlefield",
                "login", "signup", "wikipedia.org",
            ]
            if any(p in href.lower() for p in skip_patterns):
                continue

            # Skip links that are clearly site-chrome (same text on every page)
            chrome_texts = {"logo", "subscribe", "newsletter", "sign in", "sign up"}
            if text.strip().lower() in chrome_texts:
                continue

            if href in seen:
                continue
            seen.add(href)
            links.append(href)
    except Exception:
        pass
    return links


def _extract_title_from_html(html_content: str) -> str:
    """Extract the <title> from HTML."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.DOTALL | re.IGNORECASE)
    if m:
        return html.unescape(m.group(1).strip())
    return ""


# ---------------------------------------------------------------------------
# WebAccessTransport
# ---------------------------------------------------------------------------


@dataclass
class WebAccessTransportConfig:
    """Configuration for :class:`WebAccessTransport`.

    Fields
    ------
    cdp_proxy_url
        Base URL of the web-access CDP proxy (default ``http://localhost:3456``).
    max_search_results
        Maximum search results to process per query (default 10).
    max_pages_to_fetch
        Maximum pages to fetch and extract content from (default 5).
    fetch_timeout
        HTTP fetch timeout in seconds (default 15).
    use_cdp_for_search
        Prefer CDP browser for search when available (richer results).
    use_cdp_for_fetch
        Prefer CDP browser for page fetching (handles JS-rendered pages).
    search_queries
        Custom list of search query strings.  When empty, uses defaults
        merged with keywords from the request.
    direct_sources
        List of URLs to fetch directly without searching.  These are
        high-quality investment news sources that can be scraped directly
        for reliable results regardless of search engine availability.
    """

    cdp_proxy_url: str = "http://localhost:3456"
    max_search_results: int = 10
    max_pages_to_fetch: int = 5
    fetch_timeout: int = 15
    use_cdp_for_search: bool = True
    use_cdp_for_fetch: bool = True
    search_queries: list[str] = field(default_factory=list)
    direct_sources: list[str] = field(default_factory=lambda: [
        "https://techcrunch.com/category/artificial-intelligence/",
        "https://venturebeat.com/category/ai/",
    ])


class WebAccessTransport(ResearchTransport):
    """Concrete :class:`ResearchTransport` that uses direct HTTP + CDP proxy.

    Implements the research pipeline:
    1. Build search queries (from config + request keywords)
    2. Execute searches (DuckDuckGo HTML API ± CDP browser)
    3. Fetch and extract content from result pages
    4. Return structured :class:`ResearchResponse`

    Parameters
    ----------
    config
        Transport configuration; defaults to :class:`WebAccessTransportConfig`.
    """

    def __init__(self, config: WebAccessTransportConfig | None = None) -> None:
        self._config = config or WebAccessTransportConfig()
        self._cdp = CDPProxyClient(
            base_url=self._config.cdp_proxy_url,
            timeout=self._config.fetch_timeout,
        )

    # ------------------------------------------------------------------
    # ResearchTransport implementation
    # ------------------------------------------------------------------

    def execute(self, request: ResearchRequest) -> ResearchResponse:
        """Execute the research request and return collected items.

        Parameters
        ----------
        request
            Research parameters — profile, date, keywords, dry_run flag.

        Returns
        -------
        ResearchResponse
            Collected items and optional error message.
        """
        if request.dry_run:
            return self._dry_run_execute(request)

        items: list[dict[str, Any]] = []
        fetch_errors: list[str] = []
        seen_urls: set[str] = set()

        # 1. Fetch direct sources — category pages yield article links,
        #    individual article pages yield content directly.
        for url in self._config.direct_sources[:5]:
            try:
                html = _fetch_html(url, timeout=self._config.fetch_timeout)
                if not html:
                    fetch_errors.append(f"{url}: no response")
                    continue

                # Category / landing page: extract article links and fetch them
                article_links = _extract_article_links(html, base_url=url)
                if article_links:
                    for link_url in article_links[: self._config.max_pages_to_fetch]:
                        if link_url in seen_urls:
                            continue
                        seen_urls.add(link_url)
                        try:
                            art_html = _fetch_html(link_url, timeout=self._config.fetch_timeout)
                            if art_html:
                                art_title = _extract_title_from_html(art_html)
                                art_text = _extract_text_from_html(art_html)
                                if art_text and art_text.strip():
                                    items.append({
                                        "title": art_title or link_url,
                                        "content": art_text[:3000].strip(),
                                        "url": link_url,
                                        "date": datetime.date.today().isoformat(),
                                        "query": None,
                                    })
                        except Exception:
                            pass
                else:
                    # Single article or non-category page — extract directly
                    if url not in seen_urls:
                        seen_urls.add(url)
                        text = _extract_text_from_html(html)
                        title = _extract_title_from_html(html)
                        if text and text.strip():
                            items.append({
                                "title": title or url,
                                "content": text[:3000].strip(),
                                "url": url,
                                "date": datetime.date.today().isoformat(),
                                "query": None,
                            })
            except Exception as exc:
                fetch_errors.append(f"{url}: {exc}")

        # Cap direct-source items
        items = items[: self._config.max_pages_to_fetch * 2]

        # 2. Search and fetch additional results (only if we need more items)
        if len(items) < self._config.max_pages_to_fetch:
            queries = self._build_queries(request)
            search_results: list[dict[str, str]] = []
            for query in queries[:4]:
                results = self._search(query)
                for r in results:
                    url = (r.get("url") or "").strip()
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        search_results.append(r)
                if len(search_results) >= self._config.max_search_results:
                    break

            for result in search_results[: self._config.max_pages_to_fetch]:
                try:
                    extracted = self._fetch_url(result.get("url", ""), seen_urls)
                    if extracted:
                        items.append(extracted)
                except Exception as exc:
                    fetch_errors.append(f"{result.get('url', '?')}: {exc}")

        # 3. Build response
        error_msg: str | None = None
        if not items:
            if fetch_errors:
                error_msg = f"Fetch errors: {'; '.join(fetch_errors[:5])}"
            else:
                error_msg = "No items collected from any source"

        return ResearchResponse(
            items=items,
            provider="web-access",
            error=error_msg,
        )

    # ------------------------------------------------------------------
    # Internal: search
    # ------------------------------------------------------------------

    def _build_queries(self, request: ResearchRequest) -> list[str]:
        """Build search queries from config and request context."""
        queries: list[str] = []

        # Use custom queries from config if provided
        if self._config.search_queries:
            queries.extend(self._config.search_queries)
        else:
            queries.extend(_DEFAULT_AI_INVESTMENT_QUERIES)

        # Append keyword-driven queries from the request
        if request.search_keywords:
            for kw in request.search_keywords:
                queries.append(f"{kw} AI investment news")

        # Append date-targeted query
        if request.target_date:
            date_str = request.target_date.strftime("%Y-%m-%d")
            queries.append(f"AI investment news {date_str}")

        return queries

    def _search(self, query: str) -> list[dict[str, str]]:
        """Execute a single search query. Returns list of {title, url} dicts.

        Search backends are tried in order:
        1. CDP browser Bing search (richest results, requires CDP proxy)
        2. Direct Bing HTTP scraping (works from mainland China)
        3. Bing News vertical (surfaces recent articles from news outlets)
        4. DuckDuckGo HTML as last resort
        """
        results: list[dict[str, str]] = []

        # Try CDP-based search first if enabled and available
        if self._config.use_cdp_for_search and self._cdp.is_available():
            try:
                results = self._cdp.search_bing(
                    query, max_results=self._config.max_search_results
                )
            except Exception:
                pass

        # Fall back to direct Bing HTTP scraping
        if not results:
            results = _search_bing(
                query, max_results=self._config.max_search_results
            )

        # Try Bing News vertical for investment news
        if not results:
            results = _search_bing_news(
                query, max_results=self._config.max_search_results
            )

        # Last resort: DuckDuckGo HTML
        if not results:
            results = _search_duckduckgo_html(
                query, max_results=self._config.max_search_results
            )

        return results

    # ------------------------------------------------------------------
    # Internal: fetch and extract
    # ------------------------------------------------------------------

    def _fetch_url(
        self, url: str, seen_urls: set[str] | None = None, *, title: str = ""
    ) -> dict[str, Any] | None:
        """Fetch a page URL and extract structured content from it.

        Parameters
        ----------
        url
            Full URL to fetch.
        seen_urls
            Optional set of already-seen URLs (used for dedup).  If *url*
            is already in this set, returns ``None`` immediately.
        title
            Optional title hint from search result.  Used as fallback
            when the page has no usable ``<title>``.

        Returns
        -------
        dict or None
            Structured item with title, content, url, date, query fields.
        """
        url = url.strip()
        if not url:
            return None
        if seen_urls is not None and url in seen_urls:
            return None

        # Try CDP-based fetch for JS-rendered pages
        text: str | None = None
        if self._config.use_cdp_for_fetch and self._cdp.is_available():
            try:
                text = self._cdp.get_page_text(url)
            except Exception:
                pass

        # Fall back to direct HTTP
        if not text:
            html_content = _fetch_html(url, timeout=self._config.fetch_timeout)
            if html_content:
                if not title:
                    title = _extract_title_from_html(html_content)
                text = _extract_text_from_html(html_content)

        if not text or not text.strip():
            return None

        # Truncate content to keep storage reasonable
        content = text[:3000].strip()
        if not title:
            title = content.split("\n")[0][:100] if content else "Untitled"

        return {
            "title": title,
            "content": content,
            "url": url or None,
            "date": datetime.date.today().isoformat(),
            "query": None,
        }

    # ------------------------------------------------------------------
    # Dry-run
    # ------------------------------------------------------------------

    @staticmethod
    def _dry_run_execute(request: ResearchRequest) -> ResearchResponse:
        """Deterministic dummy output for dry-run mode."""
        return ResearchResponse(
            items=[
                {
                    "title": f"Dry-run research result #{i}",
                    "content": f"Dry-run content for research result #{i}: "
                    f"profile={request.prompt_profile}, date={request.target_date.isoformat()}.",
                    "url": f"https://example.com/dry-run-{i}",
                    "date": request.target_date.isoformat(),
                    "query": None,
                }
                for i in range(1, 4)
            ],
            provider="web-access",
        )
