"""app/normalize/time_norm.py — time normalization for NewsItem.published_at.

Pipeline stage
--------------
list[NewsItem]  →  normalize_time  →  list[NewsItem]

Goal
----
Normalize the ``published_at`` field of every ``NewsItem`` to a stable,
comparable ISO date string (``"YYYY-MM-DD"``).  When normalization succeeds,
the original raw string is replaced with the canonical form.  When all parse
attempts fail, ``published_at`` is set to an empty-string sentinel and the
failure is recorded in ``metadata["time_normalization"]`` so that downstream
stages can detect and act on it.

Supported input formats (attempted in order by ``parse_date_string``)
----------------------------------------------------------------------
1. ISO date or ISO datetime prefix: ``YYYY-MM-DD[…]``
   Handles ``"2025-06-01"``, ``"2025-06-01T10:30:00Z"``,
   ``"2025-06-01 10:30:00+08:00"``, etc.  The time and timezone parts are
   discarded; only the date portion is used.
2. Slash-separated date: ``YYYY/MM/DD[…]``
   Handles ``"2025/06/01"``, ``"2025/6/1"``, ``"2025/06/01 10:30"``, etc.
   Month and day may be one or two digits.
3. Compact 8-digit: ``YYYYMMDD`` (exactly 8 digits, nothing else after strip).
4. RFC-2822 style (e.g. from RSS feeds):
   ``Mon, 01 Jun 2025 10:30:00 +0000`` — delegated to
   :func:`email.utils.parsedate`.
5. Chinese-style: ``YYYY年M月D日[…]``
   Handles ``"2025年6月1日"``, ``"2025年06月01日"``, etc.  Month and day
   may be one or two digits.

Fallback order (autonomous decision — recorded here and in context.md)
----------------------------------------------------------------------
1. Try ``item.published_at``.
2. If that fails, try ``item.raw_refs[0].date``, ``item.raw_refs[1].date``,
   … in list order, stopping at the first parseable value.
3. If every attempt fails, set ``published_at = ""`` (empty-string sentinel)
   and set ``metadata["time_normalization"]["status"]`` to ``"failed"``.

Rationale: ``published_at`` is the normalized field most likely to carry a
clean value because it is copied verbatim from ``RawDocument.date`` by
``NewsItem.from_raw``.  When it fails, the raw documents themselves are the
next-best source because they preserve the original collected strings without
any prior transformation.  Scanning in list order preserves the
representative-first semantics established by the dedup stages.

Audit metadata
--------------
Every output ``NewsItem`` receives a ``metadata["time_normalization"]``
entry with the following structure::

    {
        "status":          "ok" | "fallback" | "failed",
        "original":        "<original published_at value>",
        "normalized":      "<YYYY-MM-DD>" | "",   # "" when status=="failed"
        "fallback_source": None | "raw_refs[N].date",
        "attempts": [
            {"source": "<name>", "value": "<raw string>", "result": "ok" | "parse_failed"},
            ...
        ]
    }

Status values:
- ``"ok"``       — ``item.published_at`` parsed successfully; no fallback needed.
- ``"fallback"`` — ``item.published_at`` failed; a ``raw_refs[*].date`` succeeded.
- ``"failed"``   — all candidates failed; ``published_at`` is set to ``""``.

Non-mutation guarantee
----------------------
Neither ``normalize_item_time`` nor ``normalize_time`` modifies any input
``NewsItem`` or ``RawDocument`` instance.  Every output item is a new
``NewsItem`` with a shallow-copied (then updated) metadata dict.  The
``raw_refs`` list is copied by value; no ``RawDocument`` is modified.

Ordering and count
------------------
``normalize_time`` returns one output item for every input item in the same
order.  This stage is a pure transformation — it does not filter or dedup.

Public API
----------
``parse_date_string(s) -> str | None``
    Parse a single raw date string to ``"YYYY-MM-DD"`` or ``None``.
    Exported for testing and external reuse.

``normalize_item_time(item) -> NewsItem``
    Normalize the time fields of a single ``NewsItem``.
    Returns a new ``NewsItem``; the input is not modified.

``normalize_time(items) -> list[NewsItem]``
    Batch form: normalize ``published_at`` for every item in *items*.
    Preserves order and count.
"""

from __future__ import annotations

import copy
import email.utils
import re
from datetime import datetime
from typing import Any

from app.models.news_item import NewsItem


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_METADATA_KEY = "time_normalization"

# Deterministic sentinel used when all date-parsing attempts fail.
# Chosen as empty string for consistency with the existing field default.
_SENTINEL = ""


# ---------------------------------------------------------------------------
# Public single-string parser
# ---------------------------------------------------------------------------

def parse_date_string(s: str) -> str | None:
    """Parse *s* into a stable ISO date string (``"YYYY-MM-DD"``).

    Attempts the following formats in order; returns on the first successful
    match.  Invalid calendar values (e.g. month 13, day 32) are always
    rejected even when the pattern matches.

    1. **ISO date or ISO datetime prefix** — ``YYYY-MM-DD[…]``
       Month and day must be exactly two digits.  Any suffix (time, timezone)
       is silently discarded.
    2. **Slash-separated date** — ``YYYY/MM/DD[…]``
       Month and day may be one or two digits.  Any suffix is discarded.
    3. **Compact 8-digit date** — ``YYYYMMDD``
       The entire stripped string must be exactly eight ASCII digits.
    4. **RFC-2822 style** — e.g. ``Mon, 01 Jun 2025 10:30:00 +0000``
       Delegated to :func:`email.utils.parsedate`; handles both weekday-
       prefixed and bare forms accepted by that function.
    5. **Chinese-style date** — ``YYYY年M月D日[…]``
       Month and day may be one or two digits.  Any suffix is discarded.

    Parameters
    ----------
    s:
        Raw date string.  May be empty or contain only whitespace.

    Returns
    -------
    str | None
        ``"YYYY-MM-DD"`` on success, ``None`` when no format matched or the
        matched values represent an impossible calendar date.
    """
    s = s.strip() if s else ""
    if not s:
        return None

    # 1. ISO date or ISO datetime prefix: YYYY-MM-DD[…]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 2. Slash-separated date: YYYY/MM/DD[…] (1-2 digit month and day)
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 3. Compact 8-digit: YYYYMMDD — the full stripped string must be 8 digits
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 4. RFC-2822 style (RSS feeds, email headers, etc.)
    try:
        t = email.utils.parsedate(s)
        if t is not None:
            dt = datetime(t[0], t[1], t[2])
            return dt.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        pass

    # 5. Chinese-style: YYYY年M月D日[…] (1-2 digit month and day)
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


# ---------------------------------------------------------------------------
# Public single-item normalizer
# ---------------------------------------------------------------------------

def normalize_item_time(item: NewsItem) -> NewsItem:
    """Normalize ``item.published_at`` to ``"YYYY-MM-DD"`` and store audit info.

    Fallback order (first success wins):

    1. Parse ``item.published_at``.
    2. Parse ``item.raw_refs[i].date`` for each *i* in ascending index order.
    3. If every attempt fails, set ``published_at = ""`` (sentinel) and set
       ``metadata["time_normalization"]["status"]`` to ``"failed"``.

    The input ``NewsItem`` and all referenced ``RawDocument`` instances are
    **never mutated**.  The returned item is always a new ``NewsItem`` object.

    Parameters
    ----------
    item:
        The ``NewsItem`` to normalize.

    Returns
    -------
    NewsItem
        A new ``NewsItem`` with ``published_at`` set to ``"YYYY-MM-DD"``
        (or ``""`` on complete failure) and
        ``metadata["time_normalization"]`` populated with a full audit record.
    """
    original = item.published_at
    normalized: str | None = None
    fallback_source: str | None = None
    attempts: list[dict[str, str]] = []

    # Step 1: try item.published_at
    normalized = parse_date_string(item.published_at)
    attempts.append(
        {
            "source": "published_at",
            "value": item.published_at,
            "result": "ok" if normalized is not None else "parse_failed",
        }
    )

    # Step 2: try raw_refs[i].date in order (only if step 1 failed)
    if normalized is None:
        for i, raw in enumerate(item.raw_refs):
            source_key = f"raw_refs[{i}].date"
            parsed = parse_date_string(raw.date)
            attempts.append(
                {
                    "source": source_key,
                    "value": raw.date,
                    "result": "ok" if parsed is not None else "parse_failed",
                }
            )
            if parsed is not None:
                normalized = parsed
                fallback_source = source_key
                break

    # Step 3: determine final status and published_at value
    if normalized is not None:
        status = "ok" if fallback_source is None else "fallback"
        final_date = normalized
    else:
        status = "failed"
        final_date = _SENTINEL

    audit: dict[str, Any] = {
        "status": status,
        "original": original,
        "normalized": final_date,
        "fallback_source": fallback_source,
        "attempts": attempts,
    }

    # Build new metadata without mutating the original dict.
    # Use copy.copy so unrelated top-level keys are preserved as-is.
    new_metadata = copy.copy(item.metadata)
    new_metadata[_METADATA_KEY] = audit

    return NewsItem(
        title=item.title,
        content=item.content,
        url=item.url,
        published_at=final_date,
        source=item.source,
        provider=item.provider,
        raw_refs=list(item.raw_refs),  # shallow copy; RawDocuments not cloned
        metadata=new_metadata,
    )


# ---------------------------------------------------------------------------
# Public batch normalizer
# ---------------------------------------------------------------------------

def normalize_time(items: list[NewsItem]) -> list[NewsItem]:
    """Normalize ``published_at`` for every item in *items*.

    This is a pure transformation stage: it normalizes time fields but does
    not filter, merge, or reorder items.  The output list has the same length
    and the same order as the input.

    Parameters
    ----------
    items:
        List of ``NewsItem`` objects to normalize.  May be empty.

    Returns
    -------
    list[NewsItem]
        New list of ``NewsItem`` objects with normalized ``published_at``
        values and ``metadata["time_normalization"]`` audit records.
        No input instance is mutated.
    """
    return [normalize_item_time(item) for item in items]
