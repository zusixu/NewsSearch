"""
app/collectors/akshare_collector.py — AkShare news collector.

Collects financial news from AkShare using two providers:

  * CCTV   — ``akshare.news_cctv(date)``
             Returns a DataFrame with columns: date, title, content.
  * Caixin — ``akshare.stock_news_main_cx()``
             Returns a DataFrame with columns: tag, summary, url.

AkShare is imported lazily inside :func:`_import_akshare` so that missing
or broken installations surface as a typed :class:`CollectorUnavailableError`
rather than an ``ImportError`` at module import time.

Partial-failure policy
----------------------
Each provider is fetched independently.  If one provider raises an exception,
the error is recorded in ``CollectResult.errors`` and collection continues
with the remaining providers.  The run is only considered fully failed when
*no* items are collected.

RawDocument schema produced by this collector
---------------------------------------------
``metadata`` is always empty (``{}``); all fields map directly onto the
:class:`~app.collectors.raw_document.RawDocument` core schema.
"""

from __future__ import annotations

import datetime
import time as _time
from typing import Any, Callable

from app.collectors.base import (
    BaseCollector,
    CollectResult,
    CollectorError,
    CollectorUnavailableError,
    RunContext,
)
from app.collectors.collection_cache import CollectionCache
from app.collectors.raw_document import RawDocument
from app.collectors.retry import with_retry

# ---------------------------------------------------------------------------
# Lazy import helper
# ---------------------------------------------------------------------------

_SOURCE_ID = "akshare"  # stable constant used before the class is defined


def _import_akshare() -> Any:
    """Import akshare lazily, raising :class:`CollectorUnavailableError` on failure.

    Using a function rather than a top-level import keeps the module loadable
    even when akshare is not installed, and makes the failure path explicit
    and unit-testable.
    """
    try:
        import akshare as ak  # noqa: PLC0415
        return ak
    except ImportError as exc:
        raise CollectorUnavailableError(
            f"akshare package not available: {exc}",
            source_id=_SOURCE_ID,
        ) from exc


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _safe_str(val: Any, default: str = "") -> str:
    """Convert a pandas cell value to a clean string, treating NA/NaN as *default*."""
    if val is None:
        return default
    s = str(val)
    # Cover common pandas NA representations
    return default if s in {"nan", "NaT", "<NA>", "None"} else s


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class AkShareCollector(BaseCollector):
    """Collector that pulls financial news from AkShare (CCTV + Caixin).

    AkShare docs:   https://akshare.akfamily.xyz/
    AkShare GitHub: https://github.com/akfamily/akshare

    The two providers were chosen because they require the fewest parameters
    (CCTV takes only a date string; Caixin needs no arguments) and together
    give broad coverage of Chinese financial news for a daily run.

    Args:
        cache: Optional :class:`~app.collectors.collection_cache.CollectionCache`
               instance.  When provided, :meth:`collect` checks the cache
               before making any AkShare calls and writes back the result on
               a successful live fetch.  Cache key: ``"full_run"`` under
               ``data/raw/akshare/{date}/``.
    """

    source_id: str = _SOURCE_ID

    # Each entry: (provider_name, private_fetch_method_name)
    _PROVIDERS: list[tuple[str, str]] = [
        ("cctv", "_fetch_cctv"),
        ("caixin", "_fetch_caixin"),
    ]

    _CACHE_KEY = "full_run"

    def __init__(
        self,
        cache: CollectionCache | None = None,
        max_attempts: int = 3,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._cache = cache
        self._max_attempts = max_attempts
        self._sleeper: Callable[[float], None] = (
            sleeper if sleeper is not None else _time.sleep
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def collect(self, ctx: RunContext) -> CollectResult:
        """Collect news items from all enabled AkShare providers.

        Checks the cache first (if one is configured).  On a cache hit the
        live AkShare calls are skipped entirely.  On a miss the providers are
        fetched normally; the result is written back to cache when at least
        one item was collected.

        When ``ctx.override`` specifies ``akshare_providers``, only those
        providers are fetched; otherwise all providers in :attr:`_PROVIDERS`
        are used.

        The *ak* module is imported once per live call.  Each provider is
        wrapped in its own try/except; a failing provider appends to
        ``CollectResult.errors`` without stopping the others.

        Raises:
            CollectorUnavailableError: if the akshare package cannot be
                imported (propagates from :func:`_import_akshare`).
        """
        date_str = ctx.target_date.strftime("%Y%m%d")

        # ── Cache read ───────────────────────────────────────────────
        if self._cache is not None:
            cached = self._cache.get(self.source_id, ctx.target_date, self._CACHE_KEY)
            if cached is not None:
                return CollectResult(
                    source_id=self.source_id,
                    target_date=ctx.target_date,
                    items=cached,
                    metadata={
                        "date_str": date_str,
                        "from_cache": True,
                    },
                )

        # ── Live fetch ────────────────────────────────────────────────
        ak = _import_akshare()

        # Determine which providers to use (override filtering)
        providers = self._PROVIDERS
        if ctx.override and ctx.override.sources.akshare_providers:
            allowed = set(ctx.override.sources.akshare_providers)
            providers = [(n, m) for n, m in self._PROVIDERS if n in allowed]

        items: list[RawDocument] = []
        errors: list[CollectorError] = []
        provider_counts: dict[str, int] = {}

        for provider_name, method_name in providers:
            try:
                fetched = with_retry(
                    lambda mn=method_name: getattr(self, mn)(ak, ctx.target_date, date_str),
                    max_attempts=self._max_attempts,
                    sleeper=self._sleeper,
                )
                items.extend(fetched)
                provider_counts[provider_name] = len(fetched)
            except CollectorError as exc:
                errors.append(exc)
                provider_counts[provider_name] = 0
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    CollectorUnavailableError(
                        f"[{provider_name}] unexpected error: {exc}",
                        source_id=self.source_id,
                    )
                )
                provider_counts[provider_name] = 0

        # ── Cache write ───────────────────────────────────────────────
        if self._cache is not None and items:
            self._cache.put(self.source_id, ctx.target_date, self._CACHE_KEY, items)

        return CollectResult(
            source_id=self.source_id,
            target_date=ctx.target_date,
            items=items,
            errors=errors,
            metadata={
                "date_str": date_str,
                "provider_counts": provider_counts,
            },
        )

    def is_enabled(self, sources_config: Any) -> bool:
        """Return True unless ``sources_config.akshare`` is explicitly False."""
        return bool(getattr(sources_config, "akshare", True))

    # ------------------------------------------------------------------
    # Provider fetchers
    # ------------------------------------------------------------------

    def _fetch_cctv(
        self,
        ak: Any,
        target_date: datetime.date,
        date_str: str,
    ) -> list[RawDocument]:
        """Fetch CCTV news via ``akshare.news_cctv(date)``.

        Normalised fields: source, provider, title, content, url (None), date.
        """
        try:
            df = ak.news_cctv(date=date_str)
        except Exception as exc:
            raise CollectorUnavailableError(
                f"[cctv] news_cctv({date_str!r}) failed: {exc}",
                source_id=self.source_id,
            ) from exc

        if df is None or df.empty:
            return []

        items: list[RawDocument] = []
        for _, row in df.iterrows():
            title = _safe_str(row.get("title"))
            content = _safe_str(row.get("content")) or None
            date_val = _safe_str(row.get("date")) or target_date.isoformat()
            items.append(
                RawDocument(
                    source=self.source_id,
                    provider="cctv",
                    title=title,
                    content=content,
                    url=None,
                    date=date_val,
                )
            )
        return items

    def _fetch_caixin(
        self,
        ak: Any,
        target_date: datetime.date,
        date_str: str,  # noqa: ARG002  (unused; kept for uniform signature)
    ) -> list[RawDocument]:
        """Fetch Caixin news via ``akshare.stock_news_main_cx()``.

        ``stock_news_main_cx`` returns the latest headlines without a date
        filter, so ``target_date`` is used as the item date.

        Normalised fields: source, provider, title (from tag or summary),
        content (from summary), url, date.
        """
        try:
            df = ak.stock_news_main_cx()
        except Exception as exc:
            raise CollectorUnavailableError(
                f"[caixin] stock_news_main_cx() failed: {exc}",
                source_id=self.source_id,
            ) from exc

        if df is None or df.empty:
            return []

        items: list[RawDocument] = []
        for _, row in df.iterrows():
            tag = _safe_str(row.get("tag"))
            summary = _safe_str(row.get("summary"))
            # Use tag as title when available; fall back to the first 60 chars
            # of the summary so the item is never completely unlabelled.
            title = tag if tag else (summary[:60] if summary else "(no title)")
            url = _safe_str(row.get("url")) or None
            items.append(
                RawDocument(
                    source=self.source_id,
                    provider="caixin",
                    title=title,
                    content=summary or None,
                    url=url,
                    date=target_date.isoformat(),
                )
            )
        return items
