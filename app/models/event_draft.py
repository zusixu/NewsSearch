"""
app/models/event_draft.py — Intermediate event-extraction structure.

``EventDraft`` is the typed output of the event-extraction stage.  It is
derived from one or more ``NewsItem`` records and preserves explicit
back-references to every contributing item so that any downstream stage
(entity tagging, information-chain construction, storage) can trace an
event back to the original normalized records and, through them, to the
originating ``RawDocument`` instances.

Pipeline position
-----------------
RawDocument  →  NewsItem  →  **EventDraft**  →  …
（采集层产出）   （归一化层产出）  （事件抽取层产出）

Relation to NewsItem
--------------------
- An ``EventDraft`` is always backed by at least one ``NewsItem``; the
  ``source_items`` list preserves every contributing record.
- When multiple ``NewsItem`` records describe the same real-world event
  they can be merged into a single ``EventDraft``, with all of them
  listed in ``source_items``.
- The helper constructor :meth:`EventDraft.from_news_item` builds an
  ``EventDraft`` directly from a single ``NewsItem`` with no
  transformation applied — actual event clustering and merging is
  implemented in later pipeline stages.
- Through ``source_items[n].raw_refs`` the full end-to-end provenance
  chain (EventDraft → NewsItem → RawDocument) is always reachable.

Relation to downstream stages
------------------------------
``entities`` and ``themes`` are left as empty lists by default.  They
are intentional placeholders for the entity-tagging and theme-tagging
stages that follow this checklist item.  Do **not** populate them here.

Field overview
--------------
title        : Event headline.  Empty string when absent; never ``None``.
summary      : Optional brief description of the event.  ``None`` when
               not yet extracted.
occurred_at  : ISO-8601 date string (``"YYYY-MM-DD"``).  Represents when
               the event occurred, taken from the primary ``NewsItem``.
source_items : Ordered list of all ``NewsItem`` instances that
               contributed to this event draft.  Always non-empty.
entities     : Named entities extracted from the event (persons,
               organisations, locations …).  Empty until the entity-
               tagging stage runs; do not populate here.
themes       : Thematic labels attached to the event (e.g. ``"monetary
               policy"``, ``"earnings"``).  Empty until the theme-tagging
               stage runs; do not populate here.
metadata     : Unstructured extras passed along for downstream stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.news_item import NewsItem


@dataclass
class EventDraft:
    """Intermediate event record derived from one or more ``NewsItem`` objects.

    This is the typed intermediate model produced by the event-extraction
    stage and consumed by downstream stages (entity tagging, theme tagging,
    information-chain construction).  Every ``EventDraft`` preserves
    references to all originating ``NewsItem`` records in ``source_items``
    for full end-to-end traceability.

    Attributes:
        title:        Event headline.  Empty string when absent; never
                      ``None``.
        summary:      Optional brief description of the event.  ``None``
                      when not yet extracted.
        occurred_at:  ISO-8601 date string (``"YYYY-MM-DD"``).  Represents
                      when the event occurred.
        source_items: All ``NewsItem`` instances that contributed to this
                      event.  Always contains at least one entry.
        entities:     Named entities (persons, orgs, locations …) extracted
                      from the event.  Populated by the entity-tagging stage;
                      empty list by default.
        themes:       Thematic labels attached to the event.  Populated by
                      the theme-tagging stage; empty list by default.
        metadata:     Unstructured extras for downstream stages.
    """

    title: str
    summary: str | None
    occurred_at: str
    source_items: list[NewsItem]
    entities: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Helper constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_news_item(cls, item: NewsItem) -> "EventDraft":
        """Build an ``EventDraft`` from a single ``NewsItem`` with no transformation.

        This constructor copies the headline and date verbatim, leaves
        ``summary`` as ``None``, ``entities`` and ``themes`` as empty
        lists, and stores the originating record in ``source_items``.
        No event extraction or clustering is performed here; those
        responsibilities belong to dedicated pipeline stages added in
        later checklist items.

        Args:
            item: The source ``NewsItem`` to wrap.

        Returns:
            A new ``EventDraft`` backed by ``item``.
        """
        return cls(
            title=item.title,
            summary=None,
            occurred_at=item.published_at,
            source_items=[item],
            entities=[],
            themes=[],
            metadata=dict(item.metadata),
        )
