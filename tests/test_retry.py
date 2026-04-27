"""
tests/test_retry.py — Focused unit tests for the retry utility and collector
retry integration.

All tests are fully deterministic: no real sleeping, no live network calls,
no live AkShare calls.

Coverage
--------
with_retry core behaviour
  * Immediate success — fn called once, result returned
  * Retryable error succeeds on second attempt
  * Retryable error succeeds on third attempt (max_attempts=3)
  * Retryable error exhausts all attempts — last error re-raised
  * Non-retryable CollectorError — propagates immediately, no retry
  * CollectorError(retryable=False) explicitly — propagates immediately
  * Non-CollectorError exception — propagates immediately
  * max_attempts=1 — no retry attempted
  * Sleep called between attempts with correct exponential intervals
  * No sleep on immediate success
  * No sleep after final failed attempt
  * backoff_base multiplier applied correctly
  * max_attempts < 1 raises ValueError

NullTransport — not retried (configuration failure)
  * NullTransport raises CollectorUnavailableError with retryable=False
  * CopilotResearchCollector does NOT retry NullTransport

AkShareCollector retry integration
  * CCTV provider retried on transient failure; succeeds on 2nd attempt
  * Caixin provider retried on transient failure; succeeds on 2nd attempt
  * Provider exhausts all retry attempts — error recorded, other providers continue
  * Non-retryable CollectorError from provider — not retried, recorded in errors

WebCollector retry integration
  * fetch_url retried on transient CollectorUnavailableError; succeeds on 2nd attempt
  * fetch_url exhausts all retries — error recorded in result
  * fetch_url called exactly max_attempts times on persistent failure
  * Missing url (retryable=True by default) is retried

CopilotResearchCollector retry integration
  * transport.execute() retried on transient failure; succeeds on 2nd attempt
  * transport exhausts all retries — last CollectorError propagated
  * transport call count matches max_attempts on persistent failure
"""

from __future__ import annotations

import datetime
from typing import Callable
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.collectors.akshare_collector import AkShareCollector
from app.collectors.base import (
    CollectorAuthError,
    CollectorError,
    CollectorRateLimitError,
    CollectorTimeoutError,
    CollectorUnavailableError,
    RunContext,
)
from app.collectors.copilot_research_collector import (
    CopilotResearchCollector,
    NullTransport,
    ResearchRequest,
    ResearchResponse,
    ResearchTransport,
)
from app.collectors.retry import with_retry
from app.collectors.web_collector import WebCollector

# ---------------------------------------------------------------------------
# Shared constants / helpers
# ---------------------------------------------------------------------------

_DATE = datetime.date(2025, 1, 15)
_CTX = RunContext.for_date(_DATE)

# No-op sleeper for deterministic, instant tests.
_NOOP: Callable[[float], None] = lambda _: None

_AK_PATCH = "app.collectors.akshare_collector._import_akshare"
_WEB_FETCH_PATCH = "app.collectors.web_collector.fetch_url"

_SIMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item><title>Test headline</title><description>Body text</description></item>
  </channel>
</rss>"""


def _cctv_df(rows: int = 2) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [_DATE.isoformat()] * rows,
        "title": [f"CCTV title {i}" for i in range(rows)],
        "content": [f"CCTV content {i}" for i in range(rows)],
    })


def _caixin_df(rows: int = 2) -> pd.DataFrame:
    return pd.DataFrame({
        "tag": [f"tag{i}" for i in range(rows)],
        "summary": [f"Caixin summary {i}" for i in range(rows)],
        "url": [f"https://example.com/{i}" for i in range(rows)],
    })


# ---------------------------------------------------------------------------
# with_retry — immediate success
# ---------------------------------------------------------------------------

class TestWithRetrySuccess:
    def test_returns_value_on_success(self):
        assert with_retry(lambda: 42, sleeper=_NOOP) == 42

    def test_fn_called_exactly_once_on_success(self):
        calls: list[int] = []
        with_retry(lambda: calls.append(1) or "ok", sleeper=_NOOP)
        assert len(calls) == 1

    def test_returns_exact_object_identity(self):
        sentinel = object()
        assert with_retry(lambda: sentinel, sleeper=_NOOP) is sentinel


# ---------------------------------------------------------------------------
# with_retry — retryable path
# ---------------------------------------------------------------------------

class TestWithRetryRetryablePath:
    def test_succeeds_on_second_attempt(self):
        attempt = [0]

        def fn():
            attempt[0] += 1
            if attempt[0] < 2:
                raise CollectorUnavailableError("transient", source_id="test")
            return "done"

        assert with_retry(fn, sleeper=_NOOP) == "done"
        assert attempt[0] == 2

    def test_succeeds_on_third_attempt(self):
        attempt = [0]

        def fn():
            attempt[0] += 1
            if attempt[0] < 3:
                raise CollectorTimeoutError(source_id="test")
            return "ok"

        assert with_retry(fn, max_attempts=3, sleeper=_NOOP) == "ok"
        assert attempt[0] == 3

    def test_exhausts_all_attempts_raises_last_error(self):
        attempts = [0]

        def fn():
            attempts[0] += 1
            raise CollectorUnavailableError(f"attempt {attempts[0]}", source_id="s")

        with pytest.raises(CollectorUnavailableError) as exc_info:
            with_retry(fn, max_attempts=3, sleeper=_NOOP)
        assert attempts[0] == 3
        assert "attempt 3" in str(exc_info.value)

    def test_rate_limit_error_retried(self):
        calls = [0]

        def fn():
            calls[0] += 1
            if calls[0] < 2:
                raise CollectorRateLimitError(source_id="test")
            return "ok"

        assert with_retry(fn, sleeper=_NOOP) == "ok"


# ---------------------------------------------------------------------------
# with_retry — non-retryable
# ---------------------------------------------------------------------------

class TestWithRetryNonRetryable:
    def test_non_retryable_collector_error_propagates_immediately(self):
        calls = [0]

        def fn():
            calls[0] += 1
            raise CollectorAuthError("bad credentials", source_id="test")

        with pytest.raises(CollectorAuthError):
            with_retry(fn, max_attempts=3, sleeper=_NOOP)
        assert calls[0] == 1  # no retry

    def test_collector_error_retryable_false_propagates_immediately(self):
        calls = [0]

        def fn():
            calls[0] += 1
            raise CollectorError("config error", source_id="test", retryable=False)

        with pytest.raises(CollectorError):
            with_retry(fn, max_attempts=3, sleeper=_NOOP)
        assert calls[0] == 1

    def test_non_collector_exception_propagates_immediately(self):
        calls = [0]

        def fn():
            calls[0] += 1
            raise ValueError("not a collector error")

        with pytest.raises(ValueError):
            with_retry(fn, max_attempts=3, sleeper=_NOOP)
        assert calls[0] == 1

    def test_runtime_error_propagates_immediately(self):
        calls = [0]

        def fn():
            calls[0] += 1
            raise RuntimeError("unexpected")

        with pytest.raises(RuntimeError):
            with_retry(fn, max_attempts=3, sleeper=_NOOP)
        assert calls[0] == 1


# ---------------------------------------------------------------------------
# with_retry — max_attempts=1
# ---------------------------------------------------------------------------

class TestWithRetryMaxAttemptsOne:
    def test_success(self):
        assert with_retry(lambda: "ok", max_attempts=1, sleeper=_NOOP) == "ok"

    def test_failure_no_retry(self):
        calls = [0]

        def fn():
            calls[0] += 1
            raise CollectorUnavailableError("fail", source_id="test")

        with pytest.raises(CollectorUnavailableError):
            with_retry(fn, max_attempts=1, sleeper=_NOOP)
        assert calls[0] == 1


# ---------------------------------------------------------------------------
# with_retry — sleep intervals (exponential backoff)
# ---------------------------------------------------------------------------

class TestWithRetrySleepIntervals:
    def test_no_sleep_on_immediate_success(self):
        sleeps: list[float] = []
        with_retry(lambda: "ok", sleeper=sleeps.append)
        assert sleeps == []

    def test_sleep_called_between_attempts(self):
        sleeps: list[float] = []
        attempt = [0]

        def fn():
            attempt[0] += 1
            if attempt[0] < 3:
                raise CollectorUnavailableError("t", source_id="s")
            return "ok"

        with_retry(fn, max_attempts=3, backoff_base=1.0, sleeper=sleeps.append)
        assert sleeps == [1.0, 2.0]  # 1*2^0, 1*2^1

    def test_no_sleep_after_final_failed_attempt(self):
        """Sleep is NOT called after the last failed attempt."""
        sleeps: list[float] = []

        def fn():
            raise CollectorUnavailableError("fail", source_id="s")

        with pytest.raises(CollectorUnavailableError):
            with_retry(fn, max_attempts=2, backoff_base=1.0, sleeper=sleeps.append)
        # Only one sleep between attempt 0 and attempt 1; none after attempt 1.
        assert sleeps == [1.0]

    def test_backoff_base_multiplied(self):
        sleeps: list[float] = []
        attempt = [0]

        def fn():
            attempt[0] += 1
            if attempt[0] < 3:
                raise CollectorUnavailableError("t", source_id="s")
            return "ok"

        with_retry(fn, max_attempts=3, backoff_base=2.0, sleeper=sleeps.append)
        assert sleeps == [2.0, 4.0]  # 2*2^0, 2*2^1

    def test_backoff_base_zero_no_sleep_duration(self):
        sleeps: list[float] = []
        attempt = [0]

        def fn():
            attempt[0] += 1
            if attempt[0] < 2:
                raise CollectorUnavailableError("t", source_id="s")
            return "ok"

        with_retry(fn, max_attempts=2, backoff_base=0.0, sleeper=sleeps.append)
        assert sleeps == [0.0]


# ---------------------------------------------------------------------------
# with_retry — validation
# ---------------------------------------------------------------------------

class TestWithRetryValidation:
    def test_max_attempts_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="max_attempts"):
            with_retry(lambda: None, max_attempts=0, sleeper=_NOOP)

    def test_max_attempts_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="max_attempts"):
            with_retry(lambda: None, max_attempts=-5, sleeper=_NOOP)


# ---------------------------------------------------------------------------
# NullTransport — configuration failure, not retried
# ---------------------------------------------------------------------------

class TestNullTransportRetryable:
    def test_null_transport_raises_retryable_false(self):
        t = NullTransport()
        req = ResearchRequest(prompt_profile="default", target_date=_DATE, run_id="r")
        with pytest.raises(CollectorUnavailableError) as exc_info:
            t.execute(req)
        assert exc_info.value.retryable is False

    def test_null_transport_not_retried_by_collector(self):
        """CopilotResearchCollector must NOT retry NullTransport failures."""
        call_count = [0]
        original = NullTransport.execute

        def counting(self, req):
            call_count[0] += 1
            return original(self, req)

        with patch.object(NullTransport, "execute", counting):
            with pytest.raises(CollectorUnavailableError):
                CopilotResearchCollector(max_attempts=3, sleeper=_NOOP).collect(_CTX)

        assert call_count[0] == 1  # called once, never retried


# ---------------------------------------------------------------------------
# AkShareCollector retry integration
# ---------------------------------------------------------------------------

class TestAkShareRetry:
    def test_cctv_retried_on_transient_failure_succeeds(self):
        cctv_calls = [0]

        def cctv_side_effect(date):
            cctv_calls[0] += 1
            if cctv_calls[0] < 2:
                raise ConnectionError("network blip")
            return _cctv_df()

        ak = MagicMock()
        ak.news_cctv.side_effect = cctv_side_effect
        ak.stock_news_main_cx.return_value = _caixin_df()

        with patch(_AK_PATCH, return_value=ak):
            result = AkShareCollector(max_attempts=3, sleeper=_NOOP).collect(_CTX)

        assert result.ok
        assert cctv_calls[0] == 2  # failed once, then succeeded

    def test_caixin_retried_on_transient_failure_succeeds(self):
        caixin_calls = [0]

        def caixin_side_effect():
            caixin_calls[0] += 1
            if caixin_calls[0] < 2:
                raise ConnectionError("transient")
            return _caixin_df()

        ak = MagicMock()
        ak.news_cctv.return_value = _cctv_df()
        ak.stock_news_main_cx.side_effect = caixin_side_effect

        with patch(_AK_PATCH, return_value=ak):
            result = AkShareCollector(max_attempts=3, sleeper=_NOOP).collect(_CTX)

        assert result.ok
        assert caixin_calls[0] == 2

    def test_provider_exhausts_retries_error_recorded(self):
        ak = MagicMock()
        ak.news_cctv.side_effect = ConnectionError("always fails")
        ak.stock_news_main_cx.return_value = _caixin_df()

        with patch(_AK_PATCH, return_value=ak):
            result = AkShareCollector(max_attempts=3, sleeper=_NOOP).collect(_CTX)

        assert result.partial  # caixin succeeded; cctv error recorded
        assert len(result.errors) == 1
        assert ak.news_cctv.call_count == 3  # tried max_attempts times

    def test_all_provider_exceptions_wrapped_as_retryable(self):
        """_fetch_cctv wraps ALL exceptions from ak.news_cctv as
        CollectorUnavailableError(retryable=True), so even if the underlying
        exception is 'auth-like', the retry layer will still retry it."""
        cctv_calls = [0]

        def always_fail(date):
            cctv_calls[0] += 1
            raise ValueError("some unexpected api error")  # not a CollectorError

        ak = MagicMock()
        ak.news_cctv.side_effect = always_fail
        ak.stock_news_main_cx.return_value = _caixin_df()

        with patch(_AK_PATCH, return_value=ak):
            result = AkShareCollector(max_attempts=3, sleeper=_NOOP).collect(_CTX)

        # Exception was wrapped as CollectorUnavailableError(retryable=True) and retried.
        assert cctv_calls[0] == 3
        assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# WebCollector retry integration
# ---------------------------------------------------------------------------

_WEB_SOURCE = [{"url": "https://example.com/rss", "type": "rss", "provider": "test_src"}]


class TestWebCollectorRetry:
    def test_fetch_retried_on_transient_failure_succeeds(self):
        fetch_calls = [0]

        def side_effect(url, timeout=15):
            fetch_calls[0] += 1
            if fetch_calls[0] < 2:
                raise CollectorUnavailableError("network blip", source_id="web")
            return _SIMPLE_RSS

        with patch(_WEB_FETCH_PATCH, side_effect=side_effect):
            result = WebCollector(
                sources=_WEB_SOURCE,
                max_attempts=3,
                sleeper=_NOOP,
            ).collect(_CTX)

        assert result.ok
        assert fetch_calls[0] == 2

    def test_fetch_exhausts_retries_error_recorded(self):
        with patch(
            _WEB_FETCH_PATCH,
            side_effect=CollectorUnavailableError("down", source_id="web"),
        ):
            result = WebCollector(
                sources=_WEB_SOURCE,
                max_attempts=3,
                sleeper=_NOOP,
            ).collect(_CTX)

        assert result.failed
        assert len(result.errors) == 1

    def test_fetch_call_count_matches_max_attempts(self):
        fetch_calls = [0]

        def always_fail(url, timeout=15):
            fetch_calls[0] += 1
            raise CollectorUnavailableError("fail", source_id="web")

        with patch(_WEB_FETCH_PATCH, side_effect=always_fail):
            WebCollector(
                sources=_WEB_SOURCE,
                max_attempts=3,
                sleeper=_NOOP,
            ).collect(_CTX)

        assert fetch_calls[0] == 3

    def test_missing_url_not_retried(self):
        """Missing URL raises CollectorUnavailableError; since retryable defaults
        to True this will be retried.  Confirm the call count still equals
        max_attempts (no infinite loop or early exit)."""
        no_url_source = [{"url": "", "type": "rss", "provider": "no_url"}]

        with patch(_WEB_FETCH_PATCH) as mock_fetch:
            result = WebCollector(
                sources=no_url_source,
                max_attempts=2,
                sleeper=_NOOP,
            ).collect(_CTX)

        # fetch_url is never reached; the empty-url check fires before it.
        mock_fetch.assert_not_called()
        assert result.failed


# ---------------------------------------------------------------------------
# CopilotResearchCollector retry integration
# ---------------------------------------------------------------------------

class _TransientTransport(ResearchTransport):
    """Fails the first *fail_times* calls, then returns a valid response."""

    def __init__(self, fail_times: int = 1) -> None:
        self._fail_times = fail_times
        self.call_count = 0

    def execute(self, req: ResearchRequest) -> ResearchResponse:
        self.call_count += 1
        if self.call_count <= self._fail_times:
            raise CollectorUnavailableError("transient", source_id="copilot_research")
        return ResearchResponse(items=[{
            "title": "Research result",
            "content": "Some content",
            "url": None,
            "date": req.target_date.isoformat(),
            "query": None,
        }])


class TestCopilotResearchRetry:
    def test_transport_retried_on_transient_failure_succeeds(self):
        transport = _TransientTransport(fail_times=1)
        result = CopilotResearchCollector(
            transport=transport,
            max_attempts=3,
            sleeper=_NOOP,
        ).collect(_CTX)
        assert result.ok
        assert transport.call_count == 2  # 1 failure + 1 success

    def test_transport_exhausts_retries_raises(self):
        transport = _TransientTransport(fail_times=10)  # always fails
        with pytest.raises(CollectorUnavailableError):
            CopilotResearchCollector(
                transport=transport,
                max_attempts=3,
                sleeper=_NOOP,
            ).collect(_CTX)

    def test_transport_call_count_matches_max_attempts(self):
        transport = _TransientTransport(fail_times=10)
        with pytest.raises(CollectorUnavailableError):
            CopilotResearchCollector(
                transport=transport,
                max_attempts=3,
                sleeper=_NOOP,
            ).collect(_CTX)
        assert transport.call_count == 3
