"""app/normalize/_item_merge.py — shared NewsItem merge helpers (internal).

This module is *private* to ``app.normalize``.  It provides the merge
primitive that all dedup stages reuse so that the logic lives in exactly
one place.

Public surface (within the package)
------------------------------------
``merge_news_items(rep, dup) -> NewsItem``
    Returns a new ``NewsItem`` that combines the representative item *rep*
    with a later duplicate *dup*, following the conservative merge rules
    documented below.

Merge rules
-----------
- ``raw_refs``: *rep*'s refs come first, then *dup*'s.
- Scalar fields (``title``, ``content``, ``published_at``, ``source``,
  ``provider``): *rep*'s value is kept when it is non-None and non-empty;
  otherwise the first non-empty value from *dup* is used.
- ``url``: *rep*'s url is always preserved (the representative owns the URL).
- ``metadata``: shallow merge — *dup*'s dict is used as the base, then
  *rep*'s entries overwrite it, so *rep* always wins on key conflicts.
- Neither *rep* nor *dup* is mutated; the result is always a fresh
  ``NewsItem`` instance.
"""

from __future__ import annotations

import copy

from app.models.news_item import NewsItem


def _fill_if_empty(representative_val: str | None, donor_val: str | None) -> str | None:
    """Return *donor_val* if *representative_val* is ``None`` or empty, else keep it."""
    if not representative_val and donor_val:
        return donor_val
    return representative_val


def merge_news_items(rep: NewsItem, dup: NewsItem) -> NewsItem:
    """Return a new ``NewsItem`` that combines *rep* (representative) and *dup*.

    This is the single authoritative merge implementation used by all dedup
    stages (URL dedup, text-hash dedup, …).

    Parameters
    ----------
    rep:
        The first-occurrence (representative) item.
    dup:
        A later item identified as a duplicate of *rep*.

    Returns
    -------
    NewsItem
        A fresh ``NewsItem`` with merged ``raw_refs``, conservatively filled
        scalar fields, and a shallow-merged ``metadata`` dict.  Neither *rep*
        nor *dup* is modified.
    """
    merged_raw_refs = list(rep.raw_refs) + list(dup.raw_refs)

    title = _fill_if_empty(rep.title, dup.title)
    content = _fill_if_empty(rep.content, dup.content)
    published_at = _fill_if_empty(rep.published_at, dup.published_at)
    source = _fill_if_empty(rep.source, dup.source)
    provider = _fill_if_empty(rep.provider, dup.provider)

    # Shallow-merge metadata: start from dup, then overwrite with rep (rep wins).
    merged_metadata = copy.copy(dup.metadata)
    merged_metadata.update(rep.metadata)

    return NewsItem(
        title=title if title is not None else "",
        content=content,
        url=rep.url,
        published_at=published_at if published_at is not None else "",
        source=source if source is not None else "",
        provider=provider if provider is not None else "",
        raw_refs=merged_raw_refs,
        metadata=merged_metadata,
    )
