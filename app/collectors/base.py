"""
app/collectors/base.py — Unified collector interface (contracts only).

All concrete collectors (AkShare, web, copilot-research) must implement
BaseCollector.  No third-party dependencies; stdlib only.
"""

from __future__ import annotations

import abc
import datetime
from dataclasses import dataclass, field
from typing import Any

from app.config.override import OverrideConfig

from app.collectors.raw_document import RawDocument  # noqa: F401 — re-exported


# ---------------------------------------------------------------------------
# Structured error hierarchy
# ---------------------------------------------------------------------------

class CollectorError(Exception):
    """Base exception for all collector failures.

    Carries the originating source_id so callers can route errors without
    inspecting the exception message.
    """

    def __init__(self, message: str, source_id: str = "", *, retryable: bool = False) -> None:
        super().__init__(message)
        self.source_id = source_id
        self.retryable = retryable


class CollectorTimeoutError(CollectorError):
    """Raised when a collector exceeds its time budget."""

    def __init__(
        self,
        message: str = "collector timed out",
        *,
        retryable: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=retryable, **kwargs)


class CollectorAuthError(CollectorError):
    """Raised when credentials are missing or rejected."""

    def __init__(
        self,
        message: str = "authentication failed",
        *,
        retryable: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=retryable, **kwargs)


class CollectorRateLimitError(CollectorError):
    """Raised when the upstream source enforces a rate limit."""

    def __init__(
        self,
        message: str = "rate limit exceeded",
        *,
        retryable: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=retryable, **kwargs)


class CollectorUnavailableError(CollectorError):
    """Raised when the upstream source is unreachable or returns an error.

    The default ``retryable=True`` covers transient network failures.  Pass
    ``retryable=False`` explicitly for configuration failures that cannot be
    resolved by retrying (e.g. a missing transport implementation).
    """

    def __init__(
        self,
        message: str = "source unavailable",
        *,
        retryable: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=retryable, **kwargs)


# ---------------------------------------------------------------------------
# Run context — passed into every collect() call
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RunContext:
    """Immutable bundle of per-run parameters passed to every collector.

    Attributes:
        run_id:         Unique identifier for the current pipeline run
                        (e.g. "20250101_0830").
        target_date:    The calendar date being collected.  Use today for
                        live runs; set to a past date for backfills.
        is_backfill:    True when the run is replaying a past date rather
                        than collecting live data.
        prompt_profile: Name of the active prompt profile.  Passed through
                        to collectors that drive LLM-backed research
                        (e.g. copilot_research_collector).  Ignored by
                        collectors that do not use prompts.
        dry_run:        When True, collectors should simulate work without
                        writing to storage or calling external APIs.
        mode:           High-level run mode for the pipeline.  Recognised
                        values: "full" | "collect_only" | "analyse_only".
                        Collectors should proceed normally for "full" and
                        "collect_only"; skip for "analyse_only".
        override:       Optional per-run override configuration.  Collectors
                        may read search keywords, provider filters, or web
                        source overrides from this object.  ``None`` means
                        no override — use defaults.
    """

    run_id: str
    target_date: datetime.date
    is_backfill: bool = False
    prompt_profile: str = "default"
    dry_run: bool = False
    mode: str = "full"
    override: OverrideConfig | None = None

    # ------------------------------------------------------------------
    # Convenience factories
    # ------------------------------------------------------------------

    @classmethod
    def for_today(cls, run_id: str = "", **kwargs: Any) -> "RunContext":
        """Return a RunContext targeting today's date."""
        today = datetime.date.today()
        rid = run_id or f"{today.strftime('%Y%m%d')}_manual"
        return cls(run_id=rid, target_date=today, **kwargs)

    @classmethod
    def for_date(cls, date: datetime.date, run_id: str = "", **kwargs: Any) -> "RunContext":
        """Return a backfill RunContext for the given date."""
        rid = run_id or f"{date.strftime('%Y%m%d')}_backfill"
        return cls(run_id=rid, target_date=date, is_backfill=True, **kwargs)


# ---------------------------------------------------------------------------
# Collect result — predictable return type
# ---------------------------------------------------------------------------

@dataclass
class CollectResult:
    """Return value from BaseCollector.collect().

    Attributes:
        source_id:    Matches BaseCollector.source_id for this result.
        target_date:  The date that was collected.
        items:        Raw collected records as typed :class:`RawDocument`
                      instances.  Each document carries a ``source``,
                      ``provider``, ``title``, ``content``, ``url``,
                      ``date``, and a ``metadata`` dict for
                      source-specific extras.
        errors:       Non-fatal per-item errors accumulated during the
                      run.  A non-empty list does not mean the run failed;
                      it means some items were skipped or degraded.
        metadata:     Collector-specific diagnostic information
                      (e.g. page count, request duration, API quota used).
    """

    source_id: str
    target_date: datetime.date
    items: list[RawDocument] = field(default_factory=list)
    errors: list[CollectorError] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def ok(self) -> bool:
        """True when items were collected and no errors occurred."""
        return bool(self.items) and not self.errors

    @property
    def partial(self) -> bool:
        """True when items were collected but some errors also occurred."""
        return bool(self.items) and bool(self.errors)

    @property
    def failed(self) -> bool:
        """True when no items were collected (with or without errors)."""
        return not self.items


# ---------------------------------------------------------------------------
# Abstract base collector
# ---------------------------------------------------------------------------

class BaseCollector(abc.ABC):
    """Contract that every concrete collector must satisfy.

    Subclass protocol
    -----------------
    1. Set ``source_id`` to a stable, unique string identifier
       (e.g. ``"akshare"``, ``"web"``, ``"copilot_research"``).
    2. Implement ``collect(ctx)`` to return a ``CollectResult``.
    3. Raise ``CollectorError`` (or a subclass) for fatal failures;
       accumulate non-fatal issues in ``CollectResult.errors``.
    4. Never import third-party libraries at module level in this file;
       that is the concrete subclass's responsibility.
    """

    #: Stable identifier for this collector.  Set in each subclass.
    source_id: str = ""

    @abc.abstractmethod
    def collect(self, ctx: RunContext) -> CollectResult:
        """Execute a collection run for the date and context in *ctx*.

        Args:
            ctx: Immutable run context (date, backfill flag, prompt
                 profile, dry_run, mode).

        Returns:
            A ``CollectResult`` with zero or more items.

        Raises:
            CollectorError: (or subclass) for unrecoverable failures.
                            Partial failures should be captured in
                            ``CollectResult.errors`` instead.
        """
        ...

    def is_enabled(self, sources_config: Any) -> bool:
        """Return True if this collector should run for the given config.

        The default implementation always returns True.  Concrete
        collectors may override this to respect the ``sources`` section
        of ``AppConfig`` (e.g. ``sources_config.akshare``).

        Args:
            sources_config: The ``SourcesConfig`` object from AppConfig,
                            or any object with relevant boolean flags.
        """
        return True
