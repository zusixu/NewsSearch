"""
tests/test_copilot_research_collector.py

Focused unit tests for the CopilotResearchCollector interface layer.

All tests use fakes or mocks only — no live web access, no LLM calls.

Coverage:
- ResearchRequest dataclass (frozen, fields, defaults)
- ResearchResponse dataclass (defaults, partial error)
- ResearchTransport ABC enforcement
- NullTransport raises CollectorUnavailableError
- CopilotResearchCollector.collect() with a FakeTransport:
    * prompt_profile forwarded to transport
    * target_date forwarded
    * run_id forwarded
    * dry_run forwarded
    * items normalised and returned in CollectResult
    * metadata contains provider, prompt_profile, item_count
    * transport error recorded in CollectResult.errors
    * items still kept on partial error
    * empty transport response gives failed result
    * items without title+content are dropped
    * missing item fields filled with defaults
    * CollectorError from transport propagates
- is_enabled respects sources_config.copilot_research (defaults True for backward compat)
- source_id is "copilot_research"
"""

from __future__ import annotations

import datetime

import pytest

from app.collectors.base import (
    CollectResult,
    CollectorError,
    CollectorUnavailableError,
    RunContext,
)
from app.collectors.copilot_research_collector import (
    CopilotResearchCollector,
    NullTransport,
    ResearchRequest,
    ResearchResponse,
    ResearchTransport,
    _normalise_item,
)
from app.collectors.raw_document import RawDocument

# ---------------------------------------------------------------------------
# Shared helpers / fakes
# ---------------------------------------------------------------------------

_DATE = datetime.date(2025, 6, 1)
_CTX = RunContext(run_id="test_run_001", target_date=_DATE, prompt_profile="default")


def _ctx(profile: str = "default", dry_run: bool = False) -> RunContext:
    return RunContext(
        run_id="test_run",
        target_date=_DATE,
        prompt_profile=profile,
        dry_run=dry_run,
    )


def _item(**overrides) -> dict:
    base = {
        "source": "copilot_research",
        "provider": "fake",
        "title": "Test headline",
        "content": "Some body text",
        "url": "https://example.com/article",
        "date": _DATE.isoformat(),
        "query": "market overview",
    }
    base.update(overrides)
    return base


class _FakeTransport(ResearchTransport):
    """Transport fake that returns a configurable fixed response."""

    def __init__(self, response: ResearchResponse | None = None) -> None:
        self._response = response or ResearchResponse(items=[_item()])
        self.received: list[ResearchRequest] = []

    def execute(self, request: ResearchRequest) -> ResearchResponse:
        self.received.append(request)
        return self._response


class _ErrorTransport(ResearchTransport):
    """Transport fake that raises a CollectorError."""

    def __init__(self, exc: CollectorError | None = None) -> None:
        self._exc = exc or CollectorUnavailableError("transport down", source_id="copilot_research")

    def execute(self, request: ResearchRequest) -> ResearchResponse:
        raise self._exc


# ---------------------------------------------------------------------------
# ResearchRequest
# ---------------------------------------------------------------------------

class TestResearchRequest:
    def test_fields_are_set(self):
        req = ResearchRequest(
            prompt_profile="aggressive-v1",
            target_date=_DATE,
            run_id="r1",
        )
        assert req.prompt_profile == "aggressive-v1"
        assert req.target_date == _DATE
        assert req.run_id == "r1"
        assert req.dry_run is False

    def test_dry_run_default_false(self):
        req = ResearchRequest(prompt_profile="p", target_date=_DATE, run_id="r")
        assert req.dry_run is False

    def test_dry_run_can_be_true(self):
        req = ResearchRequest(prompt_profile="p", target_date=_DATE, run_id="r", dry_run=True)
        assert req.dry_run is True

    def test_frozen_prevents_mutation(self):
        req = ResearchRequest(prompt_profile="p", target_date=_DATE, run_id="r")
        with pytest.raises((AttributeError, TypeError)):
            req.prompt_profile = "other"  # type: ignore[misc]

    def test_equality_by_value(self):
        r1 = ResearchRequest(prompt_profile="p", target_date=_DATE, run_id="r")
        r2 = ResearchRequest(prompt_profile="p", target_date=_DATE, run_id="r")
        assert r1 == r2


# ---------------------------------------------------------------------------
# ResearchResponse
# ---------------------------------------------------------------------------

class TestResearchResponse:
    def test_defaults(self):
        resp = ResearchResponse()
        assert resp.items == []
        assert resp.provider == "web-access"
        assert resp.error is None

    def test_items_set(self):
        items = [_item()]
        resp = ResearchResponse(items=items)
        assert resp.items == items

    def test_provider_custom(self):
        resp = ResearchResponse(provider="copilot-v2")
        assert resp.provider == "copilot-v2"

    def test_error_set(self):
        resp = ResearchResponse(error="rate limit hit")
        assert resp.error == "rate limit hit"

    def test_items_default_is_independent_per_instance(self):
        r1 = ResearchResponse()
        r2 = ResearchResponse()
        r1.items.append({"x": 1})
        assert r2.items == []


# ---------------------------------------------------------------------------
# ResearchTransport ABC
# ---------------------------------------------------------------------------

class TestResearchTransportABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ResearchTransport()  # type: ignore[abstract]

    def test_subclass_without_execute_cannot_instantiate(self):
        class _Bad(ResearchTransport):
            pass

        with pytest.raises(TypeError):
            _Bad()  # type: ignore[abstract]

    def test_concrete_subclass_can_instantiate(self):
        transport = _FakeTransport()
        assert isinstance(transport, ResearchTransport)


# ---------------------------------------------------------------------------
# NullTransport
# ---------------------------------------------------------------------------

class TestNullTransport:
    def test_execute_raises_collector_unavailable(self):
        t = NullTransport()
        req = ResearchRequest(prompt_profile="default", target_date=_DATE, run_id="r")
        with pytest.raises(CollectorUnavailableError):
            t.execute(req)

    def test_error_is_retryable(self):
        t = NullTransport()
        req = ResearchRequest(prompt_profile="default", target_date=_DATE, run_id="r")
        with pytest.raises(CollectorUnavailableError) as exc_info:
            t.execute(req)
        assert exc_info.value.retryable is False

    def test_error_carries_source_id(self):
        t = NullTransport()
        req = ResearchRequest(prompt_profile="default", target_date=_DATE, run_id="r")
        with pytest.raises(CollectorUnavailableError) as exc_info:
            t.execute(req)
        assert exc_info.value.source_id == "copilot_research"

    def test_is_research_transport_subclass(self):
        assert isinstance(NullTransport(), ResearchTransport)


# ---------------------------------------------------------------------------
# CopilotResearchCollector — basic contract
# ---------------------------------------------------------------------------

class TestCopilotResearchCollectorContract:
    def test_source_id(self):
        assert CopilotResearchCollector.source_id == "copilot_research"

    def test_is_enabled_true_when_no_config_attribute(self):
        """Default to True when sources_config has no copilot_research attr (backward compat)."""
        c = CopilotResearchCollector()
        assert c.is_enabled(None) is True

        class _CfgNoAttr:
            pass

        assert c.is_enabled(_CfgNoAttr()) is True

    def test_is_enabled_respects_config_true(self):
        class _Cfg:
            copilot_research = True

        c = CopilotResearchCollector()
        assert c.is_enabled(_Cfg()) is True

    def test_is_enabled_respects_config_false(self):
        class _Cfg:
            copilot_research = False

        c = CopilotResearchCollector()
        assert c.is_enabled(_Cfg()) is False

    def test_default_transport_is_null(self):
        c = CopilotResearchCollector()
        assert isinstance(c._transport, NullTransport)

    def test_inject_fake_transport(self):
        fake = _FakeTransport()
        c = CopilotResearchCollector(transport=fake)
        assert c._transport is fake

    def test_collect_returns_collect_result(self):
        c = CopilotResearchCollector(transport=_FakeTransport())
        result = c.collect(_ctx())
        assert isinstance(result, CollectResult)

    def test_result_source_id(self):
        c = CopilotResearchCollector(transport=_FakeTransport())
        result = c.collect(_ctx())
        assert result.source_id == "copilot_research"

    def test_result_target_date(self):
        c = CopilotResearchCollector(transport=_FakeTransport())
        result = c.collect(_ctx())
        assert result.target_date == _DATE

    def test_null_transport_raises_unavailable(self):
        c = CopilotResearchCollector()
        with pytest.raises(CollectorUnavailableError):
            c.collect(_ctx())


# ---------------------------------------------------------------------------
# CopilotResearchCollector — prompt-profile forwarding
# ---------------------------------------------------------------------------

class TestPromptProfileForwarding:
    def test_prompt_profile_forwarded_to_transport(self):
        fake = _FakeTransport()
        c = CopilotResearchCollector(transport=fake)
        c.collect(_ctx(profile="aggressive-v2"))
        assert len(fake.received) == 1
        assert fake.received[0].prompt_profile == "aggressive-v2"

    def test_default_profile_forwarded(self):
        fake = _FakeTransport()
        c = CopilotResearchCollector(transport=fake)
        c.collect(_ctx(profile="default"))
        assert fake.received[0].prompt_profile == "default"

    def test_target_date_forwarded(self):
        fake = _FakeTransport()
        c = CopilotResearchCollector(transport=fake)
        c.collect(_ctx())
        assert fake.received[0].target_date == _DATE

    def test_run_id_forwarded(self):
        fake = _FakeTransport()
        c = CopilotResearchCollector(transport=fake)
        ctx = RunContext(run_id="pipeline_42", target_date=_DATE, prompt_profile="p1")
        c.collect(ctx)
        assert fake.received[0].run_id == "pipeline_42"

    def test_dry_run_true_forwarded(self):
        fake = _FakeTransport()
        c = CopilotResearchCollector(transport=fake)
        c.collect(_ctx(dry_run=True))
        assert fake.received[0].dry_run is True

    def test_dry_run_false_forwarded(self):
        fake = _FakeTransport()
        c = CopilotResearchCollector(transport=fake)
        c.collect(_ctx(dry_run=False))
        assert fake.received[0].dry_run is False


# ---------------------------------------------------------------------------
# CopilotResearchCollector — items & metadata
# ---------------------------------------------------------------------------

class TestCollectItems:
    def test_single_item_ok_result(self):
        c = CopilotResearchCollector(transport=_FakeTransport())
        result = c.collect(_ctx())
        assert result.ok
        assert len(result.items) == 1

    def test_item_schema_keys(self):
        c = CopilotResearchCollector(transport=_FakeTransport())
        result = c.collect(_ctx())
        item = result.items[0]
        assert hasattr(item, "source")
        assert hasattr(item, "provider")
        assert hasattr(item, "title")
        assert hasattr(item, "content")
        assert hasattr(item, "url")
        assert hasattr(item, "date")
        assert "query" in item.metadata

    def test_item_source_is_copilot_research(self):
        c = CopilotResearchCollector(transport=_FakeTransport())
        result = c.collect(_ctx())
        assert result.items[0].source == "copilot_research"

    def test_item_values_pass_through(self):
        raw = _item(title="Market update", content="Stocks rose", url="https://x.com")
        fake = _FakeTransport(ResearchResponse(items=[raw], provider="web-access"))
        result = CopilotResearchCollector(transport=fake).collect(_ctx())
        item = result.items[0]
        assert item.title == "Market update"
        assert item.content == "Stocks rose"
        assert item.url == "https://x.com"

    def test_multiple_items(self):
        items = [_item(title=f"Headline {i}") for i in range(5)]
        fake = _FakeTransport(ResearchResponse(items=items))
        result = CopilotResearchCollector(transport=fake).collect(_ctx())
        assert len(result.items) == 5

    def test_empty_transport_gives_failed_result(self):
        fake = _FakeTransport(ResearchResponse(items=[]))
        result = CopilotResearchCollector(transport=fake).collect(_ctx())
        assert result.failed

    def test_metadata_keys(self):
        fake = _FakeTransport()
        result = CopilotResearchCollector(transport=fake).collect(_ctx(profile="pro"))
        assert "provider" in result.metadata
        assert "prompt_profile" in result.metadata
        assert "item_count" in result.metadata

    def test_metadata_prompt_profile_value(self):
        fake = _FakeTransport()
        result = CopilotResearchCollector(transport=fake).collect(_ctx(profile="pro"))
        assert result.metadata["prompt_profile"] == "pro"

    def test_metadata_item_count(self):
        items = [_item(title=f"H{i}") for i in range(3)]
        fake = _FakeTransport(ResearchResponse(items=items))
        result = CopilotResearchCollector(transport=fake).collect(_ctx())
        assert result.metadata["item_count"] == 3

    def test_metadata_provider(self):
        fake = _FakeTransport(ResearchResponse(items=[_item()], provider="my-transport"))
        result = CopilotResearchCollector(transport=fake).collect(_ctx())
        assert result.metadata["provider"] == "my-transport"


# ---------------------------------------------------------------------------
# CopilotResearchCollector — partial failure handling
# ---------------------------------------------------------------------------

class TestPartialFailure:
    def test_transport_error_in_response_appended_to_errors(self):
        resp = ResearchResponse(items=[_item()], error="rate limit hit")
        fake = _FakeTransport(resp)
        result = CopilotResearchCollector(transport=fake).collect(_ctx())
        assert len(result.errors) == 1
        assert "rate limit" in str(result.errors[0])

    def test_items_kept_on_partial_error(self):
        resp = ResearchResponse(items=[_item()], error="partial failure")
        fake = _FakeTransport(resp)
        result = CopilotResearchCollector(transport=fake).collect(_ctx())
        assert result.partial
        assert len(result.items) == 1

    def test_transport_error_source_id(self):
        resp = ResearchResponse(items=[_item()], error="timeout")
        fake = _FakeTransport(resp)
        result = CopilotResearchCollector(transport=fake).collect(_ctx())
        assert result.errors[0].source_id == "copilot_research"

    def test_collector_error_from_transport_propagates(self):
        c = CopilotResearchCollector(transport=_ErrorTransport())
        with pytest.raises(CollectorError):
            c.collect(_ctx())

    def test_unavailable_error_from_transport_propagates(self):
        c = CopilotResearchCollector(transport=_ErrorTransport())
        with pytest.raises(CollectorUnavailableError):
            c.collect(_ctx())

    def test_no_error_field_means_no_errors_in_result(self):
        fake = _FakeTransport(ResearchResponse(items=[_item()], error=None))
        result = CopilotResearchCollector(transport=fake).collect(_ctx())
        assert result.errors == []


# ---------------------------------------------------------------------------
# Item normalisation (_normalise_item helper)
# ---------------------------------------------------------------------------

class TestNormaliseItem:
    def test_full_item_passes_through(self):
        raw = _item()
        out = _normalise_item(raw, "fallback-provider", _DATE)
        assert out is not None
        assert out.title == raw["title"]
        assert out.content == raw["content"]
        assert out.url == raw["url"]
        assert out.date == raw["date"]
        assert out.metadata.get("query") == raw["query"]

    def test_source_always_copilot_research(self):
        raw = _item(source="something-else")
        out = _normalise_item(raw, "p", _DATE)
        assert out.source == "copilot_research"

    def test_provider_from_item_preferred_over_fallback(self):
        raw = _item(provider="item-provider")
        out = _normalise_item(raw, "fallback", _DATE)
        assert out.provider == "item-provider"

    def test_missing_provider_uses_fallback(self):
        raw = {k: v for k, v in _item().items() if k != "provider"}
        out = _normalise_item(raw, "fallback-provider", _DATE)
        assert out.provider == "fallback-provider"

    def test_missing_date_uses_fallback(self):
        raw = {k: v for k, v in _item().items() if k != "date"}
        out = _normalise_item(raw, "p", _DATE)
        assert out.date == _DATE.isoformat()

    def test_none_content_stays_none(self):
        raw = _item(content=None)
        out = _normalise_item(raw, "p", _DATE)
        assert out.content is None

    def test_empty_content_becomes_none(self):
        raw = _item(content="   ")
        out = _normalise_item(raw, "p", _DATE)
        assert out.content is None

    def test_no_title_and_no_content_returns_none(self):
        raw = _item(title="", content=None)
        out = _normalise_item(raw, "p", _DATE)
        assert out is None

    def test_no_title_but_has_content_is_kept(self):
        raw = _item(title="", content="Something useful")
        out = _normalise_item(raw, "p", _DATE)
        assert out is not None
        assert out.content == "Something useful"

    def test_has_title_but_no_content_is_kept(self):
        raw = _item(title="Headline only", content=None)
        out = _normalise_item(raw, "p", _DATE)
        assert out is not None
        assert out.title == "Headline only"

    def test_whitespace_title_treated_as_empty(self):
        raw = _item(title="   ", content=None)
        out = _normalise_item(raw, "p", _DATE)
        assert out is None

    def test_missing_url_defaults_to_none(self):
        raw = {k: v for k, v in _item().items() if k != "url"}
        out = _normalise_item(raw, "p", _DATE)
        assert out.url is None

    def test_missing_query_defaults_to_none(self):
        raw = {k: v for k, v in _item().items() if k != "query"}
        out = _normalise_item(raw, "p", _DATE)
        assert out.metadata.get("query") is None


# ---------------------------------------------------------------------------
# Normalisation integration: items dropped by normaliser are not in result
# ---------------------------------------------------------------------------

class TestNormalisationIntegration:
    def test_empty_items_dropped(self):
        empty = {"title": "", "content": None, "provider": "fake",
                 "url": None, "date": _DATE.isoformat(), "query": None}
        valid = _item(title="Keeper")
        resp = ResearchResponse(items=[empty, valid], provider="fake")
        result = CopilotResearchCollector(transport=_FakeTransport(resp)).collect(_ctx())
        assert len(result.items) == 1
        assert result.items[0].title == "Keeper"

    def test_all_empty_items_gives_failed_result(self):
        empty = {"title": "", "content": None, "provider": "fake",
                 "url": None, "date": _DATE.isoformat(), "query": None}
        resp = ResearchResponse(items=[empty, empty], provider="fake")
        result = CopilotResearchCollector(transport=_FakeTransport(resp)).collect(_ctx())
        assert result.failed
