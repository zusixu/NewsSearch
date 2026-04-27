"""app/normalize/url_dedup.py — URL-based deduplication for NewsItem lists.

Pipeline stage
--------------
list[NewsItem]  →  deduplicate_by_url  →  list[NewsItem]

What this module does
---------------------
1. Canonicalizes each NewsItem URL with conservative, safe transformations:
   - Lowercases scheme and host.
   - Removes URL fragments (#...).
   - Removes default ports (80 for http, 443 for https).
   - Normalizes an empty path to "/", and strips a single trailing slash from
     paths longer than one character (i.e. "/foo/" → "/foo").
   - Sorts query parameters lexicographically for stable comparison.
   - Does NOT drop arbitrary query parameters (e.g. trackers), per spec.

2. Groups NewsItems by canonical URL fingerprint.
   - Items whose url is None are treated as non-duplicates (one group each).
   - First occurrence wins: it becomes the representative item in the output.
   - All raw_refs from later duplicates are appended to the representative's
     raw_refs list (order: representative's refs first, then duplicates in
     encounter order).
   - Missing fields on the representative (None or empty string) may be filled
     from the first duplicate that supplies a non-empty value — only for safe,
     obviously equivalent fields (title, content, published_at, source,
     provider, metadata).
   - Original NewsItem instances are never mutated; merged items are shallow
     copies with an updated raw_refs (and optionally filled fields).
"""

from __future__ import annotations

from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.news_item import NewsItem
from app.normalize._item_merge import merge_news_items

# Default ports that should be dropped from the canonical form.
_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


def canonicalize_url(url: str) -> str:
    """Return a canonical form of *url* suitable for deduplication.

    Transformations applied (conservative — no semantic information is lost):
    - Scheme and host are lower-cased.
    - Fragment is removed.
    - Default port for the scheme is removed.
    - Empty path is normalized to ``"/"``.
    - A trailing slash is stripped from paths longer than ``"/"``
      (e.g. ``"/article/"`` → ``"/article"``).
    - Query parameters are sorted lexicographically.

    Parameters
    ----------
    url:
        Raw URL string to canonicalize.

    Returns
    -------
    str
        Canonical URL string.  If *url* cannot be parsed it is returned
        unchanged.
    """
    try:
        parts: SplitResult = urlsplit(url)
    except Exception:
        return url

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    # Strip default port from netloc.
    if ":" in netloc:
        host, _, port_str = netloc.rpartition(":")
        try:
            port = int(port_str)
            if _DEFAULT_PORTS.get(scheme) == port:
                netloc = host
        except ValueError:
            pass  # not a numeric port — leave netloc as-is

    # Normalize path: empty → "/"; strip trailing slash (unless root).
    path = parts.path
    if not path:
        path = "/"
    elif len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"

    # Sort query parameters for stable comparison.
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))

    # Fragment is intentionally dropped.
    canonical = urlunsplit((scheme, netloc, path, query, ""))
    return canonical


def deduplicate_by_url(items: list[NewsItem]) -> list[NewsItem]:
    """Deduplicate *items* by canonical URL, merging raw_refs on collisions.

    Items with ``url=None`` are never considered duplicates of each other or
    of URL-bearing items — each passes through unchanged.

    Ordering guarantee
    ------------------
    The first occurrence of each canonical URL determines both the
    representative item and its position in the output list.  Subsequent
    duplicates are merged into the representative (their raw_refs are
    appended) but do not affect output order.

    Field filling
    -------------
    If the representative item has a ``None`` or empty-string value for a
    scalar field (``title``, ``content``, ``published_at``, ``source``,
    ``provider``), the value from the first duplicate that provides a
    non-empty value is used.  Metadata dicts are shallow-merged: keys absent
    in the representative are filled from duplicates in encounter order;
    existing keys in the representative are never overwritten.

    Parameters
    ----------
    items:
        Input list of ``NewsItem`` objects, possibly containing duplicates.

    Returns
    -------
    list[NewsItem]
        Deduplicated list preserving first-occurrence order.  No input
        instance is mutated; merged items are new objects (shallow copy with
        updated ``raw_refs`` and optionally filled fields).
    """
    seen: dict[str, int] = {}  # canonical_url → index in `result`
    result: list[NewsItem] = []

    for item in items:
        if item.url is None:
            # No URL — cannot deduplicate; always include as-is.
            result.append(item)
            continue

        key = canonicalize_url(item.url)

        if key not in seen:
            seen[key] = len(result)
            result.append(item)
        else:
            # Merge this duplicate into the existing representative.
            idx = seen[key]
            rep = result[idx]
            result[idx] = _merge(rep, item)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# _merge delegates to the shared merge helper so that URL dedup and text
# dedup always apply identical merge semantics from a single definition.
_merge = merge_news_items
