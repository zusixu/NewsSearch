"""
app/models/news_item.py — Normalized news record produced by the normalization pipeline.

``NewsItem`` is the typed output of the normalization stage.  It is derived
from one or more ``RawDocument`` records (collected from any source) and
carries cleaned, normalized fields together with explicit back-references to
every ``RawDocument`` that contributed to it.

Pipeline position
-----------------
RawDocument  →  **NewsItem**  →  EventDraft  →  …

Relation to RawDocument
-----------------------
- A ``NewsItem`` is always backed by at least one ``RawDocument``; the
  ``raw_refs`` list preserves the full set of contributing raw records so
  that any downstream stage can trace a normalized item back to its origin.
- When dedup logic merges duplicates (same URL or near-identical text) the
  merged ``NewsItem`` will carry multiple entries in ``raw_refs``.
- The helper constructor :meth:`NewsItem.from_raw` builds a ``NewsItem``
  directly from a single ``RawDocument`` with no transformation applied —
  this is intentionally minimal.  Actual field cleaning (text normalisation,
  date parsing, credibility scoring, etc.) is implemented in later pipeline
  stages.

Relation to EventDraft
----------------------
``EventDraft`` (to be defined in the next checklist step) is derived from
``NewsItem``.  ``NewsItem`` is therefore the stable intermediate contract
between the normalization stage and the event-extraction stage.

Field overview
--------------
title        : Normalized headline.  Empty string when absent; never ``None``.
content      : Normalized body text.  ``None`` when unavailable.
url          : Canonical article URL.  ``None`` when unavailable.
published_at : ISO-8601 date string (``"YYYY-MM-DD"``), normalized.
source       : Primary collector source_id (mirrors ``RawDocument.source``
               of the first / most authoritative contributing document).
provider     : Primary sub-source label (mirrors ``RawDocument.provider``).
raw_refs     : Ordered list of all ``RawDocument`` instances that produced
               this item.  Always non-empty.
metadata     : Normalized extras that don't fit the common schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from app.models.raw_document import RawDocument


@dataclass
class NewsItem:
    """Normalized news record derived from one or more ``RawDocument`` objects.

    This is the stable intermediate model that the normalization pipeline
    produces and that subsequent stages (dedup, event extraction, storage)
    consume.  Every ``NewsItem`` preserves the full list of originating
    ``RawDocument`` records in ``raw_refs`` for end-to-end traceability.

    Attributes:
        title:        Normalized headline.  Empty string when absent; never
                      ``None``.
        content:      Normalized body text.  ``None`` when unavailable.
        url:          Canonical article URL.  ``None`` when unavailable.
        published_at: ISO-8601 date string (``"YYYY-MM-DD"``), normalized.
        source:       Primary collector source_id — e.g. ``"akshare"``,
                      ``"web"``, ``"copilot_research"``.
        provider:     Primary sub-source label — e.g. ``"cctv"``,
                      ``"caixin"``, ``"web-access"``.
        raw_refs:     All ``RawDocument`` instances that contributed to this
                      item.  Always contains at least one entry.
        metadata:     Normalized extras that don't fit the common schema.
    """

    title: str
    content: str | None
    url: str | None
    published_at: str
    source: str
    provider: str
    raw_refs: list[RawDocument]
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Helper constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_raw(cls, raw: RawDocument) -> "NewsItem":
        """Build a ``NewsItem`` from a single ``RawDocument`` with no transformation.

        This constructor copies fields verbatim — title, content, url, date,
        source, provider, and metadata — and stores the originating record in
        ``raw_refs``.  No cleaning or normalization is performed here; that
        responsibility belongs to dedicated pipeline stages added in later
        checklist items.

        Args:
            raw: The source ``RawDocument`` to wrap.

        Returns:
            A new ``NewsItem`` backed by ``raw``.
        """
        return cls(
            title=raw.title,
            content=raw.content,
            url=raw.url,
            published_at=raw.date,
            source=raw.source,
            provider=raw.provider,
            raw_refs=[raw],
            metadata=dict(raw.metadata),
        )
