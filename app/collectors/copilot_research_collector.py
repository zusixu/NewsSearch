"""
app/collectors/copilot_research_collector.py

Research collector for Copilot / web-access deep-research queries.

Architecture
------------
This module defines the integration *contract* between the daily pipeline
and the web-access research execution layer.  Actual network/LLM calls are
deliberately separated behind the :class:`ResearchTransport` protocol so
that:

1. The collector is fully testable without live web access — inject a fake
   transport in tests.
2. The real web-access transport can be swapped in later without touching
   collector logic.
3. The interface is explicit and typed, making future maintenance easier.

This collector can be enabled or disabled via the ``copilot_research``
flag in ``sources_config`` (see :meth:`CopilotResearchCollector.is_enabled`).

Transport protocol
------------------
Concrete transports implement :class:`ResearchTransport` by overriding
:meth:`ResearchTransport.execute`.  The default is :class:`NullTransport`,
which raises :class:`~app.collectors.base.CollectorUnavailableError` so
that the pipeline logs the missing transport and continues rather than
crashing with ``NotImplementedError``.

To use a real or fake transport, pass it at construction time::

    collector = CopilotResearchCollector(transport=MyWebAccessTransport())

RawDocument schema produced by this collector
---------------------------------------------
The research-specific ``query`` field is stored in
:attr:`~app.collectors.raw_document.RawDocument.metadata` as
``{"query": "<query string or None>"}``.

web-access integration note
---------------------------
``web-access`` is an **optional scheduled component** in every daily run.
This module defines *only* the integration contract.  Full web-access
execution is a separate implementation task tracked after the transport
layer is finalised.
"""

from __future__ import annotations

import abc
import datetime
import time as _time
from dataclasses import dataclass, field
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

_SOURCE_ID = "copilot_research"


# ---------------------------------------------------------------------------
# Transport contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResearchRequest:
    """Immutable input bundle sent to a :class:`ResearchTransport`.

    Attributes:
        prompt_profile: Name of the active prompt profile.  The transport
                        *must* use this to customise the research query —
                        different profiles drive different query strategies.
        target_date:    Calendar date being researched.
        run_id:         Unique pipeline-run identifier for tracing/logging.
        dry_run:        When ``True``, the transport should simulate work
                        without making real network or LLM calls.
        search_keywords: Optional list of search keywords from the override
                        configuration.  Transports may use these to guide
                        their research queries.
    """

    prompt_profile: str
    target_date: datetime.date
    run_id: str
    dry_run: bool = False
    search_keywords: list[str] = field(default_factory=list)


@dataclass
class ResearchResponse:
    """Output returned by a :class:`ResearchTransport`.

    Attributes:
        items:    Zero or more raw research items as plain dicts.  Each
                  dict is produced by the transport layer and will be
                  normalised into a :class:`~app.collectors.raw_document.RawDocument`
                  by :class:`CopilotResearchCollector`.
        provider: Short label identifying which transport/engine produced
                  the items (e.g. ``"web-access"``).
        error:    If set, describes a non-fatal issue that caused partial
                  or no results.  The collector records this in
                  ``CollectResult.errors`` without failing the run entirely.
    """

    items: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "web-access"
    error: str | None = None


# ---------------------------------------------------------------------------
# Transport protocol
# ---------------------------------------------------------------------------

class ResearchTransport(abc.ABC):
    """Abstract base class for research execution backends.

    Implementations are responsible for taking a :class:`ResearchRequest`,
    running the actual research (web search, LLM query, Copilot API call,
    etc.) and returning a :class:`ResearchResponse`.

    The default concrete transport is :class:`NullTransport`.  Inject a
    real implementation into :class:`CopilotResearchCollector` when the
    execution layer is ready.
    """

    @abc.abstractmethod
    def execute(self, request: ResearchRequest) -> ResearchResponse:
        """Execute a research request and return the response.

        Args:
            request: Immutable research parameters — profile, date, run_id,
                     and dry_run flag.

        Returns:
            A :class:`ResearchResponse` containing collected items.

        Raises:
            CollectorError: (or a subclass) for unrecoverable transport
                            failures.  Non-fatal issues should be expressed
                            via :attr:`ResearchResponse.error` instead.
        """
        ...


class NullTransport(ResearchTransport):
    """Placeholder transport used when no real backend is wired up.

    Raises :class:`~app.collectors.base.CollectorUnavailableError` with
    ``retryable=False`` so that the retry layer does not loop on a
    configuration failure.  The pipeline can log the missing transport and
    continue gracefully rather than crashing with ``NotImplementedError``.
    """

    def execute(self, request: ResearchRequest) -> ResearchResponse:
        raise CollectorUnavailableError(
            "CopilotResearchCollector: no transport is configured. "
            "Inject a concrete ResearchTransport to enable research collection.",
            source_id=_SOURCE_ID,
            retryable=False,  # configuration failure — retrying will not help
        )


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class CopilotResearchCollector(BaseCollector):
    """Research collector for Copilot + web-access deep-research.

    This collector can be enabled or disabled via the ``copilot_research``
    flag in ``sources_config``.  When disabled, :meth:`is_enabled` returns
    ``False`` and the pipeline skips this collector.

    The ``prompt_profile`` from :class:`~app.collectors.base.RunContext` is
    forwarded verbatim to the transport via :class:`ResearchRequest`, making
    query customisation entirely a transport concern.

    Args:
        transport: A :class:`ResearchTransport` implementation.  Defaults to
                   :class:`NullTransport`, which raises
                   :class:`~app.collectors.base.CollectorUnavailableError`
                   until a real transport is injected.
        cache:     Optional :class:`~app.collectors.collection_cache.CollectionCache`
                   instance.  When provided, :meth:`collect` checks the cache
                   before calling the transport.  Cache key:
                   ``"{prompt_profile}"`` under
                   ``data/raw/copilot_research/{date}/``.

    Example — using a fake transport in tests::

        class FakeTransport(ResearchTransport):
            def execute(self, req: ResearchRequest) -> ResearchResponse:
                return ResearchResponse(items=[{
                    "title": "Test headline",
                    "content": "Body text",
                    "url": None,
                    "date": req.target_date.isoformat(),
                    "query": None,
                }])

        collector = CopilotResearchCollector(transport=FakeTransport())
        result = collector.collect(RunContext.for_today())
        assert result.ok
        assert isinstance(result.items[0], RawDocument)
    """

    source_id = _SOURCE_ID

    def __init__(
        self,
        transport: ResearchTransport | None = None,
        cache: CollectionCache | None = None,
        max_attempts: int = 3,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._transport: ResearchTransport = (
            transport if transport is not None else NullTransport()
        )
        self._cache = cache
        self._max_attempts = max_attempts
        self._sleeper: Callable[[float], None] = (
            sleeper if sleeper is not None else _time.sleep
        )

    def collect(self, ctx: RunContext) -> CollectResult:
        """Run a research collection for the date and profile in *ctx*.

        Checks the cache first (keyed by ``prompt_profile``).  On a cache hit
        the transport call is skipped entirely.  On a miss the transport is
        called normally; the normalised result is written back to cache when
        at least one item was collected.

        Builds a :class:`ResearchRequest` from *ctx* (forwarding
        ``prompt_profile``, ``target_date``, ``run_id``, and ``dry_run``),
        delegates to the configured transport, and normalises the response
        into a :class:`~app.collectors.base.CollectResult`.

        Partial-failure policy: if the transport returns a non-``None``
        :attr:`ResearchResponse.error`, it is appended to
        ``CollectResult.errors``; any items already returned are kept.

        Raises:
            CollectorError: propagated from the transport for fatal failures.
        """
        # ── Cache read ───────────────────────────────────────────────
        if self._cache is not None:
            cached = self._cache.get(self.source_id, ctx.target_date, ctx.prompt_profile)
            if cached is not None:
                return CollectResult(
                    source_id=self.source_id,
                    target_date=ctx.target_date,
                    items=cached,
                    metadata={
                        "prompt_profile": ctx.prompt_profile,
                        "item_count": len(cached),
                        "from_cache": True,
                    },
                )

        # ── Live transport call ───────────────────────────────────────
        search_keywords = (
            ctx.override.search_keywords
            if ctx.override and ctx.override.search_keywords
            else []
        )
        request = ResearchRequest(
            prompt_profile=ctx.prompt_profile,
            target_date=ctx.target_date,
            run_id=ctx.run_id,
            dry_run=ctx.dry_run,
            search_keywords=search_keywords,
        )

        response = with_retry(
            lambda: self._transport.execute(request),
            max_attempts=self._max_attempts,
            sleeper=self._sleeper,
        )

        items: list[RawDocument] = []
        for raw in response.items:
            normalised = _normalise_item(raw, response.provider, ctx.target_date)
            if normalised is not None:
                items.append(normalised)

        errors: list[CollectorError] = []
        if response.error:
            errors.append(CollectorError(response.error, source_id=_SOURCE_ID))

        # ── Cache write ───────────────────────────────────────────────
        if self._cache is not None and items:
            self._cache.put(self.source_id, ctx.target_date, ctx.prompt_profile, items)

        metadata: dict[str, Any] = {
            "provider": response.provider,
            "prompt_profile": ctx.prompt_profile,
            "item_count": len(items),
        }

        return CollectResult(
            source_id=self.source_id,
            target_date=ctx.target_date,
            items=items,
            errors=errors,
            metadata=metadata,
        )

    def is_enabled(self, sources_config: Any) -> bool:
        """Return ``True`` if this collector is enabled in *sources_config*.

        Reads the ``copilot_research`` attribute from *sources_config*.
        If the attribute is present, returns its value; otherwise defaults
        to ``True`` for backward compatibility.
        """
        if hasattr(sources_config, "copilot_research"):
            return bool(sources_config.copilot_research)
        return True


# ---------------------------------------------------------------------------
# Item normalisation helper
# ---------------------------------------------------------------------------

def _normalise_item(
    raw: dict[str, Any],
    provider: str,
    fallback_date: datetime.date,
) -> RawDocument | None:
    """Normalise a raw transport dict into a :class:`~app.collectors.raw_document.RawDocument`.

    Fills in missing keys with safe defaults.  Returns ``None`` if the
    item has neither a title nor content (it would be useless downstream).

    The research-specific ``query`` field is stored in
    :attr:`~app.collectors.raw_document.RawDocument.metadata` under the
    key ``"query"``.
    """
    title = str(raw.get("title") or "").strip()
    content_val = raw.get("content")
    content = str(content_val).strip() if content_val is not None else None

    if not title and not content:
        return None

    query = raw.get("query")
    return RawDocument(
        source=_SOURCE_ID,
        provider=str(raw.get("provider") or provider),
        title=title,
        content=content or None,
        url=raw.get("url"),
        date=str(raw.get("date") or fallback_date.isoformat()),
        metadata={"query": query},
    )
