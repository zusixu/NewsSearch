"""
app/models/raw_document.py — Canonical shared model for pipeline raw input.

``RawDocument`` is the typed record that travels from the collection layer
(``app/collectors``) into the normalization pipeline (``app/normalize``)
and all subsequent stages.  Every collector produces ``RawDocument``
instances; the normalization pipeline consumes them.

This module is the **single authoritative definition**.  The legacy path
``app/collectors/raw_document`` re-exports from here for backward
compatibility.

Field overview
--------------
source    : Collector source_id — e.g. ``"akshare"``, ``"web"``,
            ``"copilot_research"``.
provider  : Sub-source label — e.g. ``"cctv"``, ``"caixin"``,
            ``"web-access"``.
title     : Headline or section heading.  Empty string when absent;
            never ``None``.
content   : Body text.  ``None`` when the source provides no body.
url       : Canonical article URL.  ``None`` when unavailable.
date      : ISO-8601 date string (``"YYYY-MM-DD"``).  Source-reported
            date, or collection date as fallback.
metadata  : Source-specific extras that don't fit the common schema.
            Keeps the core fields lean while still supporting
            collector-specific data.

            Examples
            --------
            - ``copilot_research``: ``{"query": "AI supply chain 2025-06-01"}``
            - ``akshare`` / ``web``:  ``{}``  (empty — no extras needed)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawDocument:
    """Unified raw-source record produced by every collector.

    This is the single typed item that travels through the collection
    layer and is consumed as the primary input to the normalization
    pipeline.  Downstream pipeline stages (normalisation, dedup, entity
    extraction) operate on ``RawDocument`` objects rather than opaque
    dicts.

    Attributes:
        source:   Collector source_id (e.g. ``"akshare"``, ``"web"``,
                  ``"copilot_research"``).
        provider: Sub-source label (e.g. ``"cctv"``, ``"caixin"``,
                  ``"rss-xinhua"``, ``"web-access"``).
        title:    Headline or section heading.  Empty string when absent;
                  never ``None``.
        content:  Body text extracted from the source.  ``None`` when the
                  source provides no body text.
        url:      Canonical URL of the source article.  ``None`` when the
                  source does not include one.
        date:     ISO-8601 date string (``"YYYY-MM-DD"``).  The content
                  date as reported by the source, or the collection date
                  as a fallback.
        metadata: Source-specific extras that don't fit the common
                  schema.  Use this dict to carry fields like
                  ``"query"`` for the research collector without
                  widening the core schema.
    """

    source: str
    provider: str
    title: str
    content: str | None
    url: str | None
    date: str
    metadata: dict[str, Any] = field(default_factory=dict)
