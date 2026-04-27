"""
app/collectors/retry.py — Reusable retry utility for transient collection failures.

Only retries :class:`~app.collectors.base.CollectorError` exceptions whose
``retryable`` flag is ``True``.  All other exceptions propagate immediately
without any retry attempt.

Exponential backoff
-------------------
Between consecutive attempts the helper sleeps for
``backoff_base * 2 ** attempt`` seconds (attempt is 0-indexed).  With the
default ``backoff_base=1.0`` and ``max_attempts=3`` the sleep durations before
the second and third attempt are 1 s and 2 s respectively.

Testing
-------
Pass a no-op callable as *sleeper* for deterministic, instant unit tests::

    with_retry(fn, sleeper=lambda _: None)

Usage example::

    from app.collectors.retry import with_retry
    from app.collectors.base import CollectorUnavailableError

    def _fetch() -> list[dict]:
        ...  # may raise CollectorUnavailableError(retryable=True)

    items = with_retry(_fetch, max_attempts=3, sleeper=lambda _: None)
"""

from __future__ import annotations

import time as _time
from typing import Callable, TypeVar

from app.collectors.base import CollectorError

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    sleeper: Callable[[float], None] = _time.sleep,
) -> T:
    """Call *fn* up to *max_attempts* times, retrying on retryable CollectorErrors.

    Retry decision
    --------------
    Only :class:`~app.collectors.base.CollectorError` exceptions with
    ``exc.retryable is True`` cause a retry.  Non-retryable CollectorErrors
    (e.g. :class:`~app.collectors.base.CollectorAuthError`, or
    :class:`~app.collectors.base.CollectorUnavailableError` raised with
    ``retryable=False``) and all other exception types propagate immediately
    on the first occurrence without any retry.

    Backoff schedule
    ----------------
    Between consecutive attempts the helper calls ``sleeper`` with
    ``backoff_base * 2 ** attempt`` seconds (attempt 0-indexed).  With the
    default ``backoff_base=1.0`` and three attempts the sleep durations are
    ``1.0 s`` before the second attempt and ``2.0 s`` before the third.
    No sleep is called after the final attempt.

    Args:
        fn:           Zero-argument callable to invoke.
        max_attempts: Total number of attempts allowed (must be >= 1).
        backoff_base: Base multiplier for the exponential-backoff delay.
                      Set to ``0.0`` to disable sleeping while keeping
                      retry logic intact.
        sleeper:      Callable that blocks for the given number of seconds.
                      Defaults to :func:`time.sleep`.  Pass
                      ``lambda _: None`` in tests for instant, deterministic
                      execution.

    Returns:
        The return value of *fn* on the first successful call.

    Raises:
        CollectorError:  Re-raised after all attempts are exhausted for
                         retryable errors, or immediately for non-retryable
                         CollectorErrors.
        Exception:       Any non-CollectorError exception from *fn* is
                         propagated immediately without retry.
        ValueError:      If *max_attempts* is less than 1.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts!r}")

    last_exc: CollectorError | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except CollectorError as exc:
            if not exc.retryable:
                raise
            last_exc = exc
            if attempt < max_attempts - 1:
                sleeper(backoff_base * (2 ** attempt))

    # All attempts exhausted — re-raise the last retryable error.
    assert last_exc is not None  # guaranteed: loop ran >= 1 iteration
    raise last_exc
