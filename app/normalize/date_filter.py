"""
app/normalize/date_filter.py — date-range filtering for NewsItem.

Pipeline stage
--------------
list[NewsItem]  →  filter_by_date_range / filter_last_n_days  →  list[NewsItem]

Goal
----
Remove items whose ``published_at`` falls outside a configurable date window.
By default only items from the last 7 days (inclusive) are retained.

This stage should run **after** time normalization (so dates are guaranteed to
be in ``YYYY-MM-DD`` format) and **before** deduplication or credibility
grading (to avoid wasting cycles on old items).

Non-mutation guarantee
----------------------
Input ``NewsItem`` instances are never modified; items that pass the filter
are returned as-is (same object references).

Items with empty or unparseable ``published_at`` are dropped silently.
"""

from __future__ import annotations

import datetime
import copy
from typing import Any

from app.models.news_item import NewsItem

_METADATA_KEY = "date_filter"


def filter_by_date_range(
    items: list[NewsItem],
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[NewsItem]:
    """Filter items to only those published within [start_date, end_date].

    Parameters
    ----------
    items:
        List of ``NewsItem`` objects.  May be empty.
    start_date:
        Inclusive lower bound.
    end_date:
        Inclusive upper bound.

    Returns
    -------
    list[NewsItem]
        Items whose ``published_at`` falls within the date range.
        Items with empty or unparseable dates are dropped.
    """
    filtered: list[NewsItem] = []
    for item in items:
        if not item.published_at:
            continue
        try:
            item_date = datetime.date.fromisoformat(item.published_at)
        except (ValueError, TypeError):
            continue
        if start_date <= item_date <= end_date:
            new_metadata = copy.copy(item.metadata)
            new_metadata[_METADATA_KEY] = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "kept": True,
            }
            filtered.append(NewsItem(
                title=item.title,
                content=item.content,
                url=item.url,
                published_at=item.published_at,
                source=item.source,
                provider=item.provider,
                raw_refs=list(item.raw_refs),
                metadata=new_metadata,
            ))
    return filtered


def filter_last_n_days(
    items: list[NewsItem],
    n: int = 7,
    today: datetime.date | None = None,
) -> list[NewsItem]:
    """Filter items to only those published in the last *n* days (inclusive).

    Parameters
    ----------
    items:
        List of ``NewsItem`` objects.  May be empty.
    n:
        Number of days to look back.  Must be >= 1.  Default: 7.
    today:
        Override for "today's" date (useful for testing).  Defaults to
        ``datetime.date.today()``.

    Returns
    -------
    list[NewsItem]
        Items whose ``published_at`` is within [today - n + 1, today].
    """
    if n < 1:
        raise ValueError(f"n must be >= 1; got {n}")
    ref_date = today if today is not None else datetime.date.today()
    start_date = ref_date - datetime.timedelta(days=n - 1)
    return filter_by_date_range(items, start_date, ref_date)
