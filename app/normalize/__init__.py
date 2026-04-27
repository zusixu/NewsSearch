"""app/normalize — normalization pipeline.

``RawDocument`` (from ``app.models``) is the typed input to every stage
in this pipeline.  ``NewsItem`` is the typed output produced after
normalization and dedup.  ``EventDraft`` is the typed output produced
by the event-extraction stage.  Import them from here or directly from
``app.models``.

Deduplication stages
--------------------
``deduplicate_by_url``   — URL-based dedup on ``list[NewsItem]``
``canonicalize_url``     — URL canonicalization helper (also exported for
                           testing and reuse)
``deduplicate_by_text``  — Text-hash dedup on ``list[NewsItem]``
``text_fingerprint``     — Text fingerprint helper (SHA-256 of title+body,
                           also exported for testing and reuse)

Time normalization
------------------
``normalize_time``       — Normalize ``published_at`` for a ``list[NewsItem]``
``normalize_item_time``  — Normalize a single ``NewsItem`` (also exported for
                           testing and reuse)
``parse_date_string``    — Parse a raw date string to ``"YYYY-MM-DD"`` or
                           ``None`` (also exported for testing and reuse)

Date filtering
--------------
``filter_by_date_range`` — Filter items to a specific date range
``filter_last_n_days``   — Filter items to the last N days (default: 7)

Source credibility grading
--------------------------
``grade_credibility``       — Grade credibility for a ``list[NewsItem]``
``grade_item_credibility``  — Grade a single ``NewsItem`` (also exported for
                              testing and reuse)
"""

from app.models.raw_document import RawDocument  # noqa: F401 — pipeline input contract
from app.models.news_item import NewsItem  # noqa: F401 — pipeline output contract
from app.models.event_draft import EventDraft  # noqa: F401 — event-extraction output contract
from app.normalize.url_dedup import canonicalize_url, deduplicate_by_url  # noqa: F401
from app.normalize.text_dedup import text_fingerprint, deduplicate_by_text  # noqa: F401
from app.normalize.time_norm import (  # noqa: F401
    parse_date_string,
    normalize_item_time,
    normalize_time,
)
from app.normalize.date_filter import (  # noqa: F401
    filter_by_date_range,
    filter_last_n_days,
)
from app.normalize.source_credibility import (  # noqa: F401
    grade_item_credibility,
    grade_credibility,
)

__all__ = [
    "RawDocument",
    "NewsItem",
    "EventDraft",
    "canonicalize_url",
    "deduplicate_by_url",
    "text_fingerprint",
    "deduplicate_by_text",
    "parse_date_string",
    "normalize_item_time",
    "normalize_time",
    "filter_by_date_range",
    "filter_last_n_days",
    "grade_item_credibility",
    "grade_credibility",
]
