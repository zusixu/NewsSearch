"""
tests/test_collector_interface.py — Focused tests for the unified collector interface.

Tests cover:
- RunContext construction (live and backfill factory methods)
- CollectResult state helpers (ok, partial, failed)
- CollectorError hierarchy (retryable flag, source_id propagation)
- BaseCollector ABC enforcement (cannot instantiate without collect())
- Concrete stub imports (akshare, web, copilot_research all implement interface)
- is_enabled() contract
"""

from __future__ import annotations

import datetime

import pytest

from app.collectors.base import (
    BaseCollector,
    CollectResult,
    CollectorAuthError,
    CollectorError,
    CollectorRateLimitError,
    CollectorTimeoutError,
    CollectorUnavailableError,
    RunContext,
)
from app.collectors.akshare_collector import AkShareCollector
from app.collectors.copilot_research_collector import CopilotResearchCollector
from app.collectors.raw_document import RawDocument
from app.collectors.web_collector import WebCollector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_DOC = RawDocument(
    source="test",
    provider="p",
    title="test item",
    content=None,
    url=None,
    date="2025-01-01",
)


class _AlwaysEmptyCollector(BaseCollector):
    """Minimal concrete implementation for interface-level testing."""

    source_id = "test_empty"

    def collect(self, ctx: RunContext) -> CollectResult:
        return CollectResult(source_id=self.source_id, target_date=ctx.target_date)


class _AlwaysOneItemCollector(BaseCollector):
    source_id = "test_one_item"

    def collect(self, ctx: RunContext) -> CollectResult:
        doc = RawDocument(
            source=self.source_id,
            provider="test",
            title="test item",
            content=None,
            url=None,
            date=ctx.target_date.isoformat(),
        )
        return CollectResult(
            source_id=self.source_id,
            target_date=ctx.target_date,
            items=[doc],
        )


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------

class TestRunContext:
    def test_for_today_returns_today(self):
        ctx = RunContext.for_today()
        assert ctx.target_date == datetime.date.today()
        assert ctx.is_backfill is False

    def test_for_today_auto_generates_run_id(self):
        ctx = RunContext.for_today()
        assert ctx.run_id != ""
        assert datetime.date.today().strftime("%Y%m%d") in ctx.run_id

    def test_for_today_accepts_explicit_run_id(self):
        ctx = RunContext.for_today(run_id="myrun")
        assert ctx.run_id == "myrun"

    def test_for_date_sets_backfill(self):
        past = datetime.date(2024, 1, 1)
        ctx = RunContext.for_date(past)
        assert ctx.target_date == past
        assert ctx.is_backfill is True

    def test_for_date_auto_generates_run_id(self):
        past = datetime.date(2024, 6, 15)
        ctx = RunContext.for_date(past)
        assert "20240615" in ctx.run_id
        assert "backfill" in ctx.run_id

    def test_defaults(self):
        ctx = RunContext(run_id="r1", target_date=datetime.date.today())
        assert ctx.prompt_profile == "default"
        assert ctx.dry_run is False
        assert ctx.mode == "full"

    def test_custom_prompt_profile(self):
        ctx = RunContext(
            run_id="r1",
            target_date=datetime.date.today(),
            prompt_profile="aggressive-v1",
        )
        assert ctx.prompt_profile == "aggressive-v1"

    def test_frozen_prevents_mutation(self):
        ctx = RunContext.for_today()
        with pytest.raises((AttributeError, TypeError)):
            ctx.dry_run = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CollectResult state helpers
# ---------------------------------------------------------------------------

class TestCollectResult:
    _DATE = datetime.date(2025, 1, 1)

    def test_empty_result_is_failed(self):
        r = CollectResult(source_id="x", target_date=self._DATE)
        assert r.failed is True
        assert r.ok is False
        assert r.partial is False

    def test_items_no_errors_is_ok(self):
        r = CollectResult(
            source_id="x",
            target_date=self._DATE,
            items=[_SAMPLE_DOC],
        )
        assert r.ok is True
        assert r.partial is False
        assert r.failed is False

    def test_items_with_errors_is_partial(self):
        r = CollectResult(
            source_id="x",
            target_date=self._DATE,
            items=[_SAMPLE_DOC],
            errors=[CollectorError("oops", source_id="x")],
        )
        assert r.partial is True
        assert r.ok is False
        assert r.failed is False

    def test_errors_no_items_is_failed(self):
        r = CollectResult(
            source_id="x",
            target_date=self._DATE,
            errors=[CollectorError("fatal", source_id="x")],
        )
        assert r.failed is True

    def test_metadata_default_is_empty_dict(self):
        r = CollectResult(source_id="x", target_date=self._DATE)
        assert r.metadata == {}

    def test_items_default_is_empty_list(self):
        r = CollectResult(source_id="x", target_date=self._DATE)
        assert r.items == []


# ---------------------------------------------------------------------------
# CollectorError hierarchy
# ---------------------------------------------------------------------------

class TestCollectorErrors:
    def test_base_error_is_exception(self):
        e = CollectorError("test", source_id="src")
        assert isinstance(e, Exception)
        assert e.source_id == "src"
        assert e.retryable is False

    def test_timeout_is_retryable(self):
        e = CollectorTimeoutError(source_id="src")
        assert e.retryable is True
        assert isinstance(e, CollectorError)

    def test_auth_is_not_retryable(self):
        e = CollectorAuthError(source_id="src")
        assert e.retryable is False
        assert isinstance(e, CollectorError)

    def test_rate_limit_is_retryable(self):
        e = CollectorRateLimitError(source_id="src")
        assert e.retryable is True

    def test_unavailable_is_retryable(self):
        e = CollectorUnavailableError(source_id="src")
        assert e.retryable is True

    def test_all_are_collector_error_subclasses(self):
        for cls in (
            CollectorTimeoutError,
            CollectorAuthError,
            CollectorRateLimitError,
            CollectorUnavailableError,
        ):
            assert issubclass(cls, CollectorError)

    def test_source_id_propagates(self):
        e = CollectorTimeoutError(source_id="akshare")
        assert e.source_id == "akshare"


# ---------------------------------------------------------------------------
# BaseCollector ABC
# ---------------------------------------------------------------------------

class TestBaseCollectorABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseCollector()  # type: ignore[abstract]

    def test_concrete_subclass_can_instantiate(self):
        c = _AlwaysEmptyCollector()
        assert c.source_id == "test_empty"

    def test_collect_returns_collect_result(self):
        ctx = RunContext.for_today()
        result = _AlwaysEmptyCollector().collect(ctx)
        assert isinstance(result, CollectResult)

    def test_is_enabled_defaults_true(self):
        c = _AlwaysEmptyCollector()
        assert c.is_enabled(None) is True
        assert c.is_enabled(object()) is True

    def test_failed_result_for_empty_collector(self):
        ctx = RunContext.for_today()
        result = _AlwaysEmptyCollector().collect(ctx)
        assert result.failed

    def test_ok_result_for_one_item_collector(self):
        ctx = RunContext.for_today()
        result = _AlwaysOneItemCollector().collect(ctx)
        assert result.ok

    def test_collect_receives_ctx_date(self):
        target = datetime.date(2024, 3, 15)
        ctx = RunContext.for_date(target)
        result = _AlwaysOneItemCollector().collect(ctx)
        assert result.target_date == target


# ---------------------------------------------------------------------------
# Concrete stub imports implement the interface
# ---------------------------------------------------------------------------

class TestConcreteStubs:
    def test_akshare_collector_is_base_collector(self):
        assert issubclass(AkShareCollector, BaseCollector)

    def test_web_collector_is_base_collector(self):
        assert issubclass(WebCollector, BaseCollector)

    def test_copilot_research_collector_is_base_collector(self):
        assert issubclass(CopilotResearchCollector, BaseCollector)

    def test_akshare_source_id(self):
        assert AkShareCollector.source_id == "akshare"

    def test_web_source_id(self):
        assert WebCollector.source_id == "web"

    def test_copilot_research_source_id(self):
        assert CopilotResearchCollector.source_id == "copilot_research"

    def test_copilot_research_collect_raises_unavailable_without_transport(self):
        """Default NullTransport raises CollectorUnavailableError, not NotImplementedError."""
        ctx = RunContext.for_today()
        with pytest.raises(CollectorUnavailableError):
            CopilotResearchCollector().collect(ctx)

    @pytest.mark.parametrize("flag,expected", [(True, True), (False, False)])
    def test_akshare_is_enabled_respects_sources_config(self, flag, expected):
        class _Cfg:
            akshare = flag
        assert AkShareCollector().is_enabled(_Cfg()) is expected

    @pytest.mark.parametrize("flag,expected", [(True, True), (False, False)])
    def test_web_is_enabled_respects_sources_config(self, flag, expected):
        class _Cfg:
            web = flag
        assert WebCollector().is_enabled(_Cfg()) is expected

    def test_copilot_research_is_enabled_respects_config(self):
        """is_enabled now reads copilot_research from sources_config."""
        class _CfgTrue:
            copilot_research = True
        class _CfgFalse:
            copilot_research = False

        assert CopilotResearchCollector().is_enabled(_CfgTrue()) is True
        assert CopilotResearchCollector().is_enabled(_CfgFalse()) is False

    def test_copilot_research_is_enabled_defaults_true(self):
        """Default to True when sources_config lacks copilot_research attr."""
        assert CopilotResearchCollector().is_enabled(None) is True

        class _CfgNoAttr:
            pass

        assert CopilotResearchCollector().is_enabled(_CfgNoAttr()) is True
