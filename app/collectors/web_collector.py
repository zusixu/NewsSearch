"""
app/collectors/web_collector.py — Public web / RSS+Atom collector.

Supports two content-collection patterns:
  * RSS / Atom feed parsing  (stdlib xml.etree.ElementTree)
  * Static HTML extraction   (stdlib html.parser — headings + text blocks)

Sources are fully configurable via the ``sources`` constructor argument; no
specific URLs are hardcoded.  The first batch source catalogue is a documented
follow-up decision tracked in source-collection-context.md.

Source config dict keys
-----------------------
url       (str, required)  — URL to fetch.
type      (str, required)  — ``"rss"`` (also handles Atom) or ``"html"``.
provider  (str, required)  — Short label used in ``item.provider``.
timeout   (int, optional)  — Per-source request timeout in seconds.

RawDocument schema produced by this collector
---------------------------------------------
``metadata`` is always empty (``{}``); all fields map directly onto the
:class:`~app.collectors.raw_document.RawDocument` core schema.

Partial-failure policy
----------------------
Each source is fetched independently.  Failures for one source are appended
to ``CollectResult.errors``; collection continues for the remaining sources.
The run is considered failed only when no items are collected at all.
"""

from __future__ import annotations

import datetime
import html as _html_mod
import re
import time as _time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any, Callable

from app.collectors.base import (
    BaseCollector,
    CollectResult,
    CollectorError,
    CollectorUnavailableError,
    RunContext,
)
from app.collectors.collection_cache import CollectionCache
from app.collectors.raw_document import RawDocument
from app.collectors.retry import with_retry

_SOURCE_ID = "web"
_DEFAULT_TIMEOUT = 15  # seconds
_USER_AGENT = "Mozilla/5.0 (compatible; mm-collector/1.0)"

# ---------------------------------------------------------------------------
# Date-parsing helpers
# ---------------------------------------------------------------------------

_RFC_2822_MONTHS: dict[str, int] = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_RFC_2822_RE = re.compile(r"(?:\w+,\s*)?(\d{1,2})\s+(\w{3})\s+(\d{4})")


def _parse_rfc2822_date(s: str) -> str | None:
    """Parse an RFC-2822 pubDate string to ISO-8601 date, or return None."""
    m = _RFC_2822_RE.search(s)
    if not m:
        return None
    day, mon_abbr, year = m.groups()
    month = _RFC_2822_MONTHS.get(mon_abbr)
    if month is None:
        return None
    try:
        return datetime.date(int(year), month, int(day)).isoformat()
    except ValueError:
        return None


def _parse_iso_date(s: str) -> str | None:
    """Extract the date portion from an ISO-8601 datetime string."""
    if not s:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s.strip())
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Text-cleaning helpers
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text)


def _clean(text: str | None) -> str:
    """Unescape HTML entities, strip markup, and collapse whitespace."""
    if not text:
        return ""
    text = _html_mod.unescape(text)
    text = _strip_tags(text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# RSS / Atom feed parser
# ---------------------------------------------------------------------------

_ATOM_NS = "http://www.w3.org/2005/Atom"
_CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"


def parse_feed(
    content: str,
    provider: str,
    fallback_date: datetime.date,
) -> list[RawDocument]:
    """Parse an RSS 2.0 or Atom feed string into normalised RawDocument records.

    Returns an empty list when the content cannot be parsed; no exception
    is raised so the caller can decide how to handle an empty result.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    items: list[RawDocument] = []

    # ── RSS 2.0 ──────────────────────────────────────────────────────────
    channel = root.find("channel")
    if channel is not None:
        for el in channel.findall("item"):
            title = _clean(el.findtext("title"))
            link = (el.findtext("link") or "").strip() or None
            desc = _clean(el.findtext("description"))
            encoded = el.findtext(f"{{{_CONTENT_NS}}}encoded")
            body = _clean(encoded) if encoded else (desc or None)
            pub_raw = el.findtext("pubDate") or ""
            date_str = _parse_rfc2822_date(pub_raw) or fallback_date.isoformat()
            if not title and not body:
                continue
            items.append(RawDocument(
                source=_SOURCE_ID,
                provider=provider,
                title=title,
                content=body,
                url=link,
                date=date_str,
            ))
        return items

    # ── Atom ─────────────────────────────────────────────────────────────
    root_tag = root.tag
    is_atom = root_tag == f"{{{_ATOM_NS}}}feed" or root_tag == "feed"
    if is_atom:
        ns = _ATOM_NS if root_tag.startswith("{") else ""

        def _q(name: str) -> str:
            return f"{{{ns}}}{name}" if ns else name

        for entry in root.findall(_q("entry")):
            title = _clean(entry.findtext(_q("title")))
            link_el = entry.find(_q("link"))
            link = link_el.get("href") if link_el is not None else None
            summary_text = entry.findtext(_q("summary")) or entry.findtext(_q("content"))
            body = _clean(summary_text) or None
            pub_raw = (
                entry.findtext(_q("published")) or entry.findtext(_q("updated")) or ""
            )
            date_str = _parse_iso_date(pub_raw) or fallback_date.isoformat()
            if not title and not body:
                continue
            items.append(RawDocument(
                source=_SOURCE_ID,
                provider=provider,
                title=title,
                content=body,
                url=link,
                date=date_str,
            ))

    return items


# ---------------------------------------------------------------------------
# Static HTML extractor
# ---------------------------------------------------------------------------

class _HeadingExtractor(HTMLParser):
    """HTML parser that turns each heading (h1–h3) into a content item.

    Strategy: every <h1>/<h2>/<h3> element opens a new "item"; the text
    that follows (up to the next heading or end of document) becomes the
    item's content.  Tags in _SKIP_TAGS (script, style, nav, footer, head)
    are ignored together with their children.

    This pattern works well for news-listing and announcement pages that
    are structured as a sequence of titled sections.
    """

    _SKIP_TAGS = frozenset({"script", "style", "nav", "footer", "head"})
    _HEADING_TAGS = frozenset({"h1", "h2", "h3"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._items: list[tuple[str, str]] = []
        self._skip_depth = 0
        self._in_heading = False
        self._heading_buf: list[str] = []
        self._current_heading = ""
        self._body_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self._skip_depth:
            self._skip_depth += 1
            return
        if tag in self._SKIP_TAGS:
            self._skip_depth = 1
            return
        if tag in self._HEADING_TAGS:
            self._flush_current()
            self._in_heading = True
            self._heading_buf = []

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in self._HEADING_TAGS and self._in_heading:
            self._in_heading = False
            self._current_heading = " ".join(self._heading_buf).strip()
            self._heading_buf = []
            self._body_buf = []

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        # Void/self-closing elements carry no text; skip entirely.
        pass

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_heading:
            self._heading_buf.append(text)
        elif self._current_heading:
            self._body_buf.append(text)

    def _flush_current(self) -> None:
        if self._current_heading:
            self._items.append(
                (self._current_heading, " ".join(self._body_buf).strip())
            )
            self._current_heading = ""
            self._body_buf = []

    def close(self) -> None:
        self._flush_current()
        super().close()

    @property
    def items(self) -> list[tuple[str, str]]:
        return list(self._items)


def parse_html(
    content: str,
    provider: str,
    url: str | None,
    fallback_date: datetime.date,
) -> list[RawDocument]:
    """Extract heading-anchored items from a static HTML page.

    Returns a list of normalised :class:`~app.collectors.raw_document.RawDocument`
    instances with the same schema as :func:`parse_feed`.
    Returns an empty list when no headings are found.
    """
    extractor = _HeadingExtractor()
    try:
        extractor.feed(content)
        extractor.close()
    except Exception:  # noqa: BLE001
        return []

    result: list[RawDocument] = []
    for heading, body in extractor.items:
        result.append(RawDocument(
            source=_SOURCE_ID,
            provider=provider,
            title=heading,
            content=body or None,
            url=url,
            date=fallback_date.isoformat(),
        ))
    return result


# ---------------------------------------------------------------------------
# HTTP fetch helper (thin urllib wrapper; tested via mock)
# ---------------------------------------------------------------------------

def fetch_url(url: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Fetch *url* and return the decoded response body.

    Raises:
        CollectorUnavailableError: for any network or HTTP error.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise CollectorUnavailableError(
            f"HTTP {exc.code} fetching {url!r}",
            source_id=_SOURCE_ID,
        ) from exc
    except urllib.error.URLError as exc:
        raise CollectorUnavailableError(
            f"Network error fetching {url!r}: {exc.reason}",
            source_id=_SOURCE_ID,
        ) from exc
    except OSError as exc:
        raise CollectorUnavailableError(
            f"OS error fetching {url!r}: {exc}",
            source_id=_SOURCE_ID,
        ) from exc


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class WebCollector(BaseCollector):
    """Collector for public web sources: RSS/Atom feeds and static HTML pages.

    Sources are passed as a list of dicts at construction time; nothing is
    hardcoded.  This makes the collector usable with any source catalogue.

    The first batch source catalogue is a follow-up decision documented in
    ``dev/source-collection/source-collection-context.md``.

    Example usage::

        collector = WebCollector(sources=[
            {"url": "https://example.com/rss.xml", "type": "rss", "provider": "example"},
            {"url": "https://example.com/news",    "type": "html", "provider": "example_news"},
        ])
        result = collector.collect(RunContext.for_today())

    Args:
        sources: List of source configuration dicts.  Each dict must have
                 ``url``, ``type`` (``"rss"`` or ``"html"``), and
                 ``provider`` keys.  An optional ``timeout`` key overrides
                 the per-source request timeout.
        timeout: Default request timeout in seconds (used when a source
                 dict does not specify its own ``timeout``).
        cache:   Optional :class:`~app.collectors.collection_cache.CollectionCache`
                 instance.  When provided, each source is looked up by its
                 ``provider`` key before making any network call.  On a cache
                 miss the source is fetched normally and the result is written
                 back.  Cache key per source: ``"{provider}"`` under
                 ``data/raw/web/{date}/``.
    """

    source_id = _SOURCE_ID

    def __init__(
        self,
        sources: list[dict[str, Any]] | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        cache: CollectionCache | None = None,
        max_attempts: int = 3,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._sources: list[dict[str, Any]] = sources or []
        self._timeout = timeout
        self._cache = cache
        self._max_attempts = max_attempts
        self._sleeper: Callable[[float], None] = (
            sleeper if sleeper is not None else _time.sleep
        )

    def collect(self, ctx: RunContext) -> CollectResult:
        """Collect items from all configured sources.

        When ``ctx.override`` specifies ``web_sources``, those sources
        replace ``self._sources`` for this run only (the instance is not
        mutated).

        For each source, checks the cache first (keyed by ``provider``).
        On a cache hit the network fetch for that source is skipped.  On a
        miss the source is fetched normally and the result is written back
        to cache.

        Per-source failures are recorded in ``CollectResult.errors`` without
        stopping other sources.
        """
        items: list[RawDocument] = []
        errors: list[CollectorError] = []
        source_counts: dict[str, int] = {}

        # Use override web sources if provided, otherwise constructor sources
        active_sources = self._sources
        if ctx.override and ctx.override.sources.web_sources:
            active_sources = [ws.to_dict() for ws in ctx.override.sources.web_sources]

        for src in active_sources:
            url: str = src.get("url", "")
            src_type: str = src.get("type", "rss").lower()
            provider: str = src.get("provider", url)
            per_timeout: int = int(src.get("timeout", self._timeout))

            # ── Cache read (per provider) ─────────────────────────────
            if self._cache is not None:
                cached = self._cache.get(self.source_id, ctx.target_date, provider)
                if cached is not None:
                    items.extend(cached)
                    source_counts[provider] = len(cached)
                    continue

            # ── Live fetch ────────────────────────────────────────────
            try:
                fetched = with_retry(
                    lambda u=url, st=src_type, p=provider, t=per_timeout: self._collect_one(
                        url=u,
                        src_type=st,
                        provider=p,
                        target_date=ctx.target_date,
                        timeout=t,
                    ),
                    max_attempts=self._max_attempts,
                    sleeper=self._sleeper,
                )
                items.extend(fetched)
                source_counts[provider] = len(fetched)
                # ── Cache write ───────────────────────────────────────
                if self._cache is not None:
                    self._cache.put(self.source_id, ctx.target_date, provider, fetched)
            except CollectorError as exc:
                errors.append(exc)
                source_counts[provider] = 0
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    CollectorUnavailableError(
                        f"[{provider}] unexpected error: {exc}",
                        source_id=self.source_id,
                    )
                )
                source_counts[provider] = 0

        return CollectResult(
            source_id=self.source_id,
            target_date=ctx.target_date,
            items=items,
            errors=errors,
            metadata={"source_counts": source_counts},
        )

    def _collect_one(
        self,
        url: str,
        src_type: str,
        provider: str,
        target_date: datetime.date,
        timeout: int,
    ) -> list[RawDocument]:
        """Fetch and parse a single source; return normalised RawDocument records."""
        if not url:
            raise CollectorUnavailableError(
                f"[{provider}] source entry has no url",
                source_id=self.source_id,
            )
        content = fetch_url(url, timeout=timeout)
        if src_type == "html":
            return parse_html(content, provider=provider, url=url, fallback_date=target_date)
        # Default: treat as RSS/Atom
        return parse_feed(content, provider=provider, fallback_date=target_date)

    def is_enabled(self, sources_config: Any) -> bool:
        """Return True unless ``sources_config.web`` is explicitly False."""
        return bool(getattr(sources_config, "web", True))
