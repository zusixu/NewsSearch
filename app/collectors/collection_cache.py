"""
app/collectors/collection_cache.py — Filesystem cache for RawDocument results.

Cache files are stored under a configurable root (default ``data/raw``) with
the layout::

    {root}/{source}/{date_str}/{cache_key}.json

Each file is a JSON array of :class:`~app.collectors.raw_document.RawDocument`-
compatible dicts serialised via :func:`_doc_to_dict` / :func:`_dict_to_doc`.
The cache is *read-through* at the collector level:

- :meth:`CollectionCache.get` returns ``None`` on a cache miss so the caller
  can proceed with a live fetch.
- :meth:`CollectionCache.put` persists the result after a successful fetch.

Cache key conventions (per collector)
--------------------------------------
``source`` corresponds to the collector's ``source_id``.  ``date_str`` is the
ISO-8601 date (``"YYYY-MM-DD"``).  The ``cache_key`` is collector-specific:

- ``AkShareCollector``         →  ``"full_run"``
  path: ``data/raw/akshare/YYYY-MM-DD/full_run.json``
- ``WebCollector`` per source  →  ``"{provider}"``
  path: ``data/raw/web/YYYY-MM-DD/{provider}.json``
- ``CopilotResearchCollector`` →  ``"{prompt_profile}"``
  path: ``data/raw/copilot_research/YYYY-MM-DD/{prompt_profile}.json``

Unsafe filesystem characters in ``cache_key`` are replaced with underscores by
:func:`_sanitize_key` before the path is constructed.

This module has no third-party imports and is fully testable in isolation.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

from app.collectors.raw_document import RawDocument

# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

_UNSAFE_RE = re.compile(r"[^a-zA-Z0-9_\-]")


def _sanitize_key(key: str) -> str:
    """Replace unsafe filesystem characters in *key* with underscores.

    Only ASCII letters, digits, hyphens, and underscores are preserved.
    An empty result is replaced with ``"_"`` to avoid a bare ``.json`` file.
    """
    safe = _UNSAFE_RE.sub("_", key)
    return safe or "_"


def _doc_to_dict(doc: RawDocument) -> dict[str, Any]:
    """Serialise a :class:`~app.collectors.raw_document.RawDocument` to a plain dict."""
    return {
        "source": doc.source,
        "provider": doc.provider,
        "title": doc.title,
        "content": doc.content,
        "url": doc.url,
        "date": doc.date,
        "metadata": doc.metadata,
    }


def _dict_to_doc(d: dict[str, Any]) -> RawDocument:
    """Deserialise a plain dict back to a :class:`~app.collectors.raw_document.RawDocument`.

    Raises:
        KeyError: if a required field (``source``, ``provider``, ``title``,
                  ``date``) is missing from *d*.
    """
    return RawDocument(
        source=d["source"],
        provider=d["provider"],
        title=d["title"],
        content=d.get("content"),
        url=d.get("url"),
        date=d["date"],
        metadata=d.get("metadata") or {},
    )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class CollectionCache:
    """Filesystem cache for :class:`~app.collectors.raw_document.RawDocument` lists.

    Stores collected documents as JSON under a configurable root directory so
    that re-running the pipeline for the same date can skip expensive network
    or API calls.

    Cache layout
    ------------
    ``{root}/{source}/{date_str}/{cache_key}.json``

    Inject an instance into any collector at construction time::

        cache = CollectionCache()                   # default root: data/raw
        cache = CollectionCache(root="data/raw")    # explicit root
        cache = CollectionCache(root=tmp_path)      # tests: use pytest tmp_path

    Thread-safety
    -------------
    Not thread-safe.  Suitable for single-threaded daily pipeline runs.
    """

    def __init__(self, root: str | Path = Path("data/raw")) -> None:
        self._root = Path(root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        source: str,
        date: datetime.date,
        cache_key: str,
    ) -> list[RawDocument] | None:
        """Return cached items for (*source*, *date*, *cache_key*), or ``None``.

        Returns ``None`` (rather than raising) on any read error — missing
        file, invalid JSON, or schema mismatch — so callers can fall through
        to a live fetch transparently.
        """
        path = self.cache_path(source, date, cache_key)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, list):
                return None
            return [_dict_to_doc(d) for d in raw]
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def put(
        self,
        source: str,
        date: datetime.date,
        cache_key: str,
        items: list[RawDocument],
    ) -> None:
        """Persist *items* to ``{root}/{source}/{date}/{cache_key}.json``.

        Parent directories are created automatically.  An empty *items* list
        is a valid cache entry (it records that the source returned nothing).

        Raises:
            OSError: if the file cannot be written.
        """
        path = self.cache_path(source, date, cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(
                [_doc_to_dict(d) for d in items],
                fh,
                ensure_ascii=False,
                indent=2,
            )

    def exists(self, source: str, date: datetime.date, cache_key: str) -> bool:
        """Return ``True`` if a cache file exists for the given key triple."""
        return self.cache_path(source, date, cache_key).exists()

    def cache_path(self, source: str, date: datetime.date, cache_key: str) -> Path:
        """Return the :class:`pathlib.Path` for the cache file (may not exist)."""
        date_str = date.isoformat()
        safe_key = _sanitize_key(cache_key)
        return self._root / source / date_str / f"{safe_key}.json"
