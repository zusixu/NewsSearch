"""app/models — shared domain models used across pipeline layers.

This package contains the typed data models that travel between the
collection layer (``app/collectors``) and the normalization layer
(``app/normalize``), as well as later pipeline stages.

Currently exported
------------------
RawDocument : The unified raw-source record produced by every collector
              and consumed as the primary input to the normalization
              pipeline.
NewsItem    : The normalized news record produced by the normalization
              pipeline and consumed by downstream stages (dedup, event
              extraction, storage).  Always backed by one or more
              ``RawDocument`` instances via ``raw_refs``.
EventDraft  : The intermediate event record produced by the event-
              extraction stage and consumed by downstream stages (entity
              tagging, theme tagging, information-chain construction).
              Always backed by one or more ``NewsItem`` instances via
              ``source_items``.
"""

from app.models.raw_document import RawDocument
from app.models.news_item import NewsItem
from app.models.event_draft import EventDraft

__all__ = ["RawDocument", "NewsItem", "EventDraft"]
