"""
tests/test_collection_cache.py — Unit tests for CollectionCache and collector
cache integration.

All tests are fully offline (no network, no live AkShare calls, no live web
fetches).  The cache is exercised against a temporary directory provided by
the ``tmp_path`` pytest fixture.

Coverage areas
--------------
CollectionCache internals
  * _sanitize_key         — safe vs unsafe characters
  * _doc_to_dict          — field mapping
  * _dict_to_doc          — round-trip fidelity; required-field KeyError
  * cache_path()          — path structure / date_str / key sanitisation
  * exists()              — missing vs written file
  * put()                 — creates directories; correct JSON layout
  * get() — miss          — non-existent file → None
  * get() — hit           — round-trip of all RawDocument fields
  * get() — corrupt JSON  — returns None gracefully
  * get() — wrong schema  — non-list root → None
  * get() — missing key   — KeyError in _dict_to_doc → None
  * Empty list round-trip — caching zero items is valid
  * Metadata preservation — nested dicts survive JSON round-trip

AkShareCollector cache behaviour
  * Cache miss  → live fetch called; result written to cache
  * Cache hit   → live fetch NOT called; cached items returned
  * from_cache flag set on hit
  * No items from live fetch → cache NOT written

WebCollector cache behaviour
  * Cache miss per provider → live fetch called; result written
  * Cache hit per provider  → live fetch NOT called for that provider
  * Mixed: one provider cached, one not
  * from_cache not in metadata (web uses source_counts)
  * Cache write skipped on fetch error

CopilotResearchCollector cache behaviour
  * Cache miss  → transport called; result written to cache
  * Cache hit   → transport NOT called; cached items returned
  * from_cache flag set on hit
  * prompt_profile used as cache key
  * No items from transport → cache NOT written
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.collectors.collection_cache import (
    CollectionCache,
    _dict_to_doc,
    _doc_to_dict,
    _sanitize_key,
)
from app.collectors.raw_document import RawDocument
from app.collectors.base import (
    CollectResult,
    CollectorUnavailableError,
    RunContext,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_DATE = datetime.date(2025, 3, 10)
_CTX = RunContext.for_date(_DATE)


def _make_doc(
    *,
    source: str = "akshare",
    provider: str = "cctv",
    title: str = "Test title",
    content: str | None = "Test content",
    url: str | None = "https://example.com/1",
    date: str = "2025-03-10",
    metadata: dict[str, Any] | None = None,
) -> RawDocument:
    return RawDocument(
        source=source,
        provider=provider,
        title=title,
        content=content,
        url=url,
        date=date,
        metadata=metadata if metadata is not None else {},
    )


# ---------------------------------------------------------------------------
# _sanitize_key
# ---------------------------------------------------------------------------

class TestSanitizeKey:
    def test_alphanumeric_unchanged(self):
        assert _sanitize_key("abc123") == "abc123"

    def test_hyphens_and_underscores_unchanged(self):
        assert _sanitize_key("my-key_v2") == "my-key_v2"

    def test_spaces_replaced(self):
        assert _sanitize_key("my key") == "my_key"

    def test_dots_replaced(self):
        assert _sanitize_key("profile.v1") == "profile_v1"

    def test_slashes_replaced(self):
        assert _sanitize_key("a/b") == "a_b"

    def test_empty_string_becomes_underscore(self):
        assert _sanitize_key("") == "_"

    def test_all_unsafe_becomes_underscores(self):
        result = _sanitize_key("@#$%")
        assert all(c == "_" for c in result)

    def test_unicode_replaced(self):
        result = _sanitize_key("研究")
        assert result == "__"


# ---------------------------------------------------------------------------
# _doc_to_dict
# ---------------------------------------------------------------------------

class TestDocToDict:
    def test_all_fields_mapped(self):
        doc = _make_doc(metadata={"query": "AI"})
        d = _doc_to_dict(doc)
        assert d["source"] == "akshare"
        assert d["provider"] == "cctv"
        assert d["title"] == "Test title"
        assert d["content"] == "Test content"
        assert d["url"] == "https://example.com/1"
        assert d["date"] == "2025-03-10"
        assert d["metadata"] == {"query": "AI"}

    def test_none_content_preserved(self):
        doc = _make_doc(content=None)
        assert _doc_to_dict(doc)["content"] is None

    def test_none_url_preserved(self):
        doc = _make_doc(url=None)
        assert _doc_to_dict(doc)["url"] is None

    def test_empty_metadata_preserved(self):
        doc = _make_doc(metadata={})
        assert _doc_to_dict(doc)["metadata"] == {}


# ---------------------------------------------------------------------------
# _dict_to_doc
# ---------------------------------------------------------------------------

class TestDictToDoc:
    def _base_dict(self) -> dict[str, Any]:
        return {
            "source": "web",
            "provider": "xinhua",
            "title": "Headline",
            "content": "Body",
            "url": "https://xinhua.net/1",
            "date": "2025-03-10",
            "metadata": {},
        }

    def test_round_trip(self):
        doc = _dict_to_doc(self._base_dict())
        assert doc.source == "web"
        assert doc.provider == "xinhua"
        assert doc.title == "Headline"
        assert doc.content == "Body"
        assert doc.url == "https://xinhua.net/1"
        assert doc.date == "2025-03-10"
        assert doc.metadata == {}

    def test_optional_fields_default(self):
        d = self._base_dict()
        del d["content"]
        del d["url"]
        del d["metadata"]
        doc = _dict_to_doc(d)
        assert doc.content is None
        assert doc.url is None
        assert doc.metadata == {}

    def test_missing_required_field_raises(self):
        d = self._base_dict()
        del d["source"]
        with pytest.raises(KeyError):
            _dict_to_doc(d)

    def test_none_metadata_defaults_to_empty_dict(self):
        d = self._base_dict()
        d["metadata"] = None
        doc = _dict_to_doc(d)
        assert doc.metadata == {}


# ---------------------------------------------------------------------------
# CollectionCache.cache_path
# ---------------------------------------------------------------------------

class TestCachePathStructure:
    def test_path_components(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        p = cache.cache_path("akshare", _DATE, "full_run")
        assert p == tmp_path / "akshare" / "2025-03-10" / "full_run.json"

    def test_unsafe_key_sanitised_in_path(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        p = cache.cache_path("web", _DATE, "my provider")
        assert p.name == "my_provider.json"

    def test_date_isoformat_in_path(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        d = datetime.date(2025, 12, 1)
        p = cache.cache_path("web", d, "k")
        assert "2025-12-01" in str(p)


# ---------------------------------------------------------------------------
# CollectionCache.exists
# ---------------------------------------------------------------------------

class TestExists:
    def test_missing_file_returns_false(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        assert not cache.exists("akshare", _DATE, "full_run")

    def test_after_put_returns_true(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        cache.put("akshare", _DATE, "full_run", [_make_doc()])
        assert cache.exists("akshare", _DATE, "full_run")


# ---------------------------------------------------------------------------
# CollectionCache.put
# ---------------------------------------------------------------------------

class TestPut:
    def test_creates_parent_directories(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        cache.put("akshare", _DATE, "full_run", [_make_doc()])
        assert cache.cache_path("akshare", _DATE, "full_run").exists()

    def test_json_is_a_list(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        cache.put("akshare", _DATE, "full_run", [_make_doc()])
        path = cache.cache_path("akshare", _DATE, "full_run")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)

    def test_empty_list_written(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        cache.put("akshare", _DATE, "full_run", [])
        path = cache.cache_path("akshare", _DATE, "full_run")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == []

    def test_correct_item_count(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        docs = [_make_doc(title=f"T{i}") for i in range(5)]
        cache.put("akshare", _DATE, "full_run", docs)
        path = cache.cache_path("akshare", _DATE, "full_run")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 5

    def test_overwrite_existing_file(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        cache.put("akshare", _DATE, "full_run", [_make_doc(title="old")])
        cache.put("akshare", _DATE, "full_run", [_make_doc(title="new")])
        result = cache.get("akshare", _DATE, "full_run")
        assert result is not None
        assert result[0].title == "new"

    def test_metadata_serialised(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        doc = _make_doc(metadata={"query": "AI 2025", "score": 0.9})
        cache.put("copilot_research", _DATE, "default", [doc])
        path = cache.cache_path("copilot_research", _DATE, "default")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data[0]["metadata"] == {"query": "AI 2025", "score": 0.9}


# ---------------------------------------------------------------------------
# CollectionCache.get — round-trips
# ---------------------------------------------------------------------------

class TestGet:
    def test_miss_returns_none(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        assert cache.get("akshare", _DATE, "full_run") is None

    def test_hit_returns_list(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        docs = [_make_doc(title="headline")]
        cache.put("akshare", _DATE, "full_run", docs)
        result = cache.get("akshare", _DATE, "full_run")
        assert result is not None
        assert len(result) == 1

    def test_all_fields_restored(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        doc = _make_doc(
            source="web",
            provider="xinhua",
            title="Special chars: <>&",
            content=None,
            url=None,
            date="2025-03-10",
            metadata={"query": "q1"},
        )
        cache.put("web", _DATE, "xinhua", [doc])
        result = cache.get("web", _DATE, "xinhua")
        assert result is not None
        r = result[0]
        assert r.source == "web"
        assert r.provider == "xinhua"
        assert r.title == "Special chars: <>&"
        assert r.content is None
        assert r.url is None
        assert r.date == "2025-03-10"
        assert r.metadata == {"query": "q1"}

    def test_empty_list_restored(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        cache.put("akshare", _DATE, "full_run", [])
        result = cache.get("akshare", _DATE, "full_run")
        assert result == []

    def test_corrupt_json_returns_none(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        path = cache.cache_path("akshare", _DATE, "full_run")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT VALID JSON", encoding="utf-8")
        assert cache.get("akshare", _DATE, "full_run") is None

    def test_non_list_root_returns_none(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        path = cache.cache_path("akshare", _DATE, "full_run")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"key": "value"}', encoding="utf-8")
        assert cache.get("akshare", _DATE, "full_run") is None

    def test_missing_required_key_returns_none(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        path = cache.cache_path("akshare", _DATE, "full_run")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Missing 'source' field
        bad = [{"provider": "cctv", "title": "t", "date": "2025-03-10"}]
        path.write_text(json.dumps(bad), encoding="utf-8")
        assert cache.get("akshare", _DATE, "full_run") is None

    def test_multiple_items_round_trip(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        docs = [_make_doc(title=f"item {i}", url=None) for i in range(10)]
        cache.put("akshare", _DATE, "full_run", docs)
        result = cache.get("akshare", _DATE, "full_run")
        assert result is not None
        assert len(result) == 10
        assert [r.title for r in result] == [f"item {i}" for i in range(10)]

    def test_unicode_content_preserved(self, tmp_path: Path):
        cache = CollectionCache(root=tmp_path)
        doc = _make_doc(title="人工智能新闻", content="详细内容描述")
        cache.put("akshare", _DATE, "full_run", [doc])
        result = cache.get("akshare", _DATE, "full_run")
        assert result is not None
        assert result[0].title == "人工智能新闻"
        assert result[0].content == "详细内容描述"


# ---------------------------------------------------------------------------
# AkShareCollector cache behaviour
# ---------------------------------------------------------------------------

_AK_PATCH = "app.collectors.akshare_collector._import_akshare"


class TestAkShareCollectorCache:
    """Verify AkShareCollector integrates CollectionCache correctly."""

    def _make_ak_mock(self) -> MagicMock:
        import pandas as pd
        ak = MagicMock()
        ak.news_cctv.return_value = pd.DataFrame({
            "date": [_DATE.isoformat()],
            "title": ["CCTV headline"],
            "content": ["CCTV body"],
        })
        ak.stock_news_main_cx.return_value = pd.DataFrame({
            "tag": ["Caixin tag"],
            "summary": ["Caixin summary"],
            "url": ["https://caixin.com/1"],
        })
        return ak

    def test_cache_miss_calls_live_fetch(self, tmp_path: Path):
        """On a cache miss the collector fetches live data and writes the cache."""
        from app.collectors.akshare_collector import AkShareCollector
        cache = CollectionCache(root=tmp_path)
        collector = AkShareCollector(cache=cache)

        with patch(_AK_PATCH, return_value=self._make_ak_mock()):
            result = collector.collect(_CTX)

        assert result.items  # live data returned
        assert not result.metadata.get("from_cache")
        # cache should now be written
        assert cache.exists("akshare", _DATE, "full_run")

    def test_cache_hit_skips_live_fetch(self, tmp_path: Path):
        """On a cache hit _import_akshare must never be called."""
        from app.collectors.akshare_collector import AkShareCollector
        cache = CollectionCache(root=tmp_path)
        # Pre-populate cache
        cached_doc = _make_doc(source="akshare", provider="cctv", title="Cached headline")
        cache.put("akshare", _DATE, "full_run", [cached_doc])

        collector = AkShareCollector(cache=cache)
        with patch(_AK_PATCH) as mock_import:
            result = collector.collect(_CTX)
            mock_import.assert_not_called()

        assert len(result.items) == 1
        assert result.items[0].title == "Cached headline"

    def test_cache_hit_sets_from_cache_flag(self, tmp_path: Path):
        from app.collectors.akshare_collector import AkShareCollector
        cache = CollectionCache(root=tmp_path)
        cache.put("akshare", _DATE, "full_run", [_make_doc(source="akshare")])
        collector = AkShareCollector(cache=cache)
        with patch(_AK_PATCH):
            result = collector.collect(_CTX)
        assert result.metadata.get("from_cache") is True

    def test_no_items_does_not_write_cache(self, tmp_path: Path):
        """When the live fetch returns no items the cache file is NOT written."""
        import pandas as pd
        from app.collectors.akshare_collector import AkShareCollector
        cache = CollectionCache(root=tmp_path)
        collector = AkShareCollector(cache=cache)

        ak = MagicMock()
        ak.news_cctv.return_value = pd.DataFrame()
        ak.stock_news_main_cx.return_value = pd.DataFrame()

        with patch(_AK_PATCH, return_value=ak):
            result = collector.collect(_CTX)

        assert not result.items
        assert not cache.exists("akshare", _DATE, "full_run")

    def test_no_cache_does_not_break_collect(self):
        """Without a cache the collector still works normally."""
        from app.collectors.akshare_collector import AkShareCollector
        collector = AkShareCollector(cache=None)
        with patch(_AK_PATCH, return_value=self._make_ak_mock()):
            result = collector.collect(_CTX)
        assert result.items

    def test_cache_written_contains_correct_items(self, tmp_path: Path):
        from app.collectors.akshare_collector import AkShareCollector
        cache = CollectionCache(root=tmp_path)
        collector = AkShareCollector(cache=cache)

        with patch(_AK_PATCH, return_value=self._make_ak_mock()):
            live_result = collector.collect(_CTX)

        # Read back from cache and compare
        cached = cache.get("akshare", _DATE, "full_run")
        assert cached is not None
        assert len(cached) == len(live_result.items)
        for live, from_cache in zip(live_result.items, cached):
            assert live.title == from_cache.title
            assert live.provider == from_cache.provider


# ---------------------------------------------------------------------------
# WebCollector cache behaviour
# ---------------------------------------------------------------------------

_FETCH_PATCH = "app.collectors.web_collector.fetch_url"

_RSS_FEED = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>RSS headline</title>
      <description>RSS body</description>
      <pubDate>Mon, 10 Mar 2025 08:00:00 +0000</pubDate>
      <link>https://example.com/rss/1</link>
    </item>
  </channel>
</rss>"""

_SOURCES = [
    {"url": "https://a.com/feed.xml", "type": "rss", "provider": "source_a"},
    {"url": "https://b.com/feed.xml", "type": "rss", "provider": "source_b"},
]


class TestWebCollectorCache:
    """Verify WebCollector uses per-provider cache correctly."""

    def test_cache_miss_calls_live_fetch(self, tmp_path: Path):
        from app.collectors.web_collector import WebCollector
        cache = CollectionCache(root=tmp_path)
        collector = WebCollector(sources=_SOURCES, cache=cache)
        with patch(_FETCH_PATCH, return_value=_RSS_FEED) as mock_fetch:
            result = collector.collect(_CTX)
            assert mock_fetch.call_count == 2  # both sources fetched live

        assert len(result.items) == 2  # 1 item per source

    def test_cache_hit_skips_live_fetch_for_that_provider(self, tmp_path: Path):
        from app.collectors.web_collector import WebCollector
        cache = CollectionCache(root=tmp_path)
        # Pre-populate only source_a
        cached_doc = _make_doc(source="web", provider="source_a", title="Cached A")
        cache.put("web", _DATE, "source_a", [cached_doc])

        collector = WebCollector(sources=_SOURCES, cache=cache)
        with patch(_FETCH_PATCH, return_value=_RSS_FEED) as mock_fetch:
            result = collector.collect(_CTX)
            # Only source_b should be fetched live
            assert mock_fetch.call_count == 1

        providers = {item.provider for item in result.items}
        assert "source_a" in providers
        assert "source_b" in providers

    def test_both_providers_cached_no_live_fetch(self, tmp_path: Path):
        from app.collectors.web_collector import WebCollector
        cache = CollectionCache(root=tmp_path)
        for src in _SOURCES:
            cache.put("web", _DATE, src["provider"], [
                _make_doc(source="web", provider=src["provider"], title=f"Cached {src['provider']}")
            ])

        collector = WebCollector(sources=_SOURCES, cache=cache)
        with patch(_FETCH_PATCH) as mock_fetch:
            result = collector.collect(_CTX)
            mock_fetch.assert_not_called()

        assert len(result.items) == 2

    def test_cache_written_after_live_fetch(self, tmp_path: Path):
        from app.collectors.web_collector import WebCollector
        cache = CollectionCache(root=tmp_path)
        collector = WebCollector(sources=_SOURCES, cache=cache)
        with patch(_FETCH_PATCH, return_value=_RSS_FEED):
            collector.collect(_CTX)

        assert cache.exists("web", _DATE, "source_a")
        assert cache.exists("web", _DATE, "source_b")

    def test_fetch_error_does_not_write_cache(self, tmp_path: Path):
        from app.collectors.web_collector import WebCollector
        cache = CollectionCache(root=tmp_path)
        collector = WebCollector(sources=_SOURCES, cache=cache)
        with patch(_FETCH_PATCH, side_effect=CollectorUnavailableError("network down")):
            collector.collect(_CTX)

        assert not cache.exists("web", _DATE, "source_a")
        assert not cache.exists("web", _DATE, "source_b")

    def test_source_counts_metadata_correct_with_mixed_cache(self, tmp_path: Path):
        from app.collectors.web_collector import WebCollector
        cache = CollectionCache(root=tmp_path)
        # source_a from cache (1 item), source_b live (1 item from RSS)
        cache.put("web", _DATE, "source_a", [_make_doc(source="web", provider="source_a")])
        collector = WebCollector(sources=_SOURCES, cache=cache)
        with patch(_FETCH_PATCH, return_value=_RSS_FEED):
            result = collector.collect(_CTX)
        assert result.metadata["source_counts"]["source_a"] == 1
        assert result.metadata["source_counts"]["source_b"] == 1

    def test_no_cache_still_works(self):
        from app.collectors.web_collector import WebCollector
        collector = WebCollector(sources=_SOURCES, cache=None)
        with patch(_FETCH_PATCH, return_value=_RSS_FEED):
            result = collector.collect(_CTX)
        assert result.items


# ---------------------------------------------------------------------------
# CopilotResearchCollector cache behaviour
# ---------------------------------------------------------------------------

class _FakeTransport:
    """Minimal fake transport returning a single item."""

    def __init__(self, *, provider: str = "web-access") -> None:
        self._provider = provider
        self.call_count = 0

    def execute(self, request: Any) -> Any:
        from app.collectors.copilot_research_collector import ResearchResponse
        self.call_count += 1
        return ResearchResponse(
            items=[{
                "title": "Research headline",
                "content": "Research body",
                "url": "https://research.example.com/1",
                "date": request.target_date.isoformat(),
                "query": f"AI supply chain {request.target_date}",
            }],
            provider=self._provider,
        )


class TestCopilotResearchCollectorCache:
    """Verify CopilotResearchCollector integrates CollectionCache correctly."""

    def test_cache_miss_calls_transport(self, tmp_path: Path):
        from app.collectors.copilot_research_collector import CopilotResearchCollector
        cache = CollectionCache(root=tmp_path)
        transport = _FakeTransport()
        collector = CopilotResearchCollector(transport=transport, cache=cache)

        result = collector.collect(_CTX)
        assert transport.call_count == 1
        assert result.items

    def test_cache_written_after_transport(self, tmp_path: Path):
        from app.collectors.copilot_research_collector import CopilotResearchCollector
        cache = CollectionCache(root=tmp_path)
        transport = _FakeTransport()
        collector = CopilotResearchCollector(transport=transport, cache=cache)
        collector.collect(_CTX)

        # default prompt_profile is "default"
        assert cache.exists("copilot_research", _DATE, "default")

    def test_cache_hit_skips_transport(self, tmp_path: Path):
        from app.collectors.copilot_research_collector import CopilotResearchCollector
        cache = CollectionCache(root=tmp_path)
        # Pre-populate
        cached_doc = _make_doc(source="copilot_research", provider="web-access", title="Cached research")
        cache.put("copilot_research", _DATE, "default", [cached_doc])

        transport = _FakeTransport()
        collector = CopilotResearchCollector(transport=transport, cache=cache)
        result = collector.collect(_CTX)

        assert transport.call_count == 0
        assert result.items[0].title == "Cached research"

    def test_cache_hit_sets_from_cache_flag(self, tmp_path: Path):
        from app.collectors.copilot_research_collector import CopilotResearchCollector
        cache = CollectionCache(root=tmp_path)
        cache.put("copilot_research", _DATE, "default", [
            _make_doc(source="copilot_research")
        ])
        collector = CopilotResearchCollector(transport=_FakeTransport(), cache=cache)
        result = collector.collect(_CTX)
        assert result.metadata.get("from_cache") is True

    def test_prompt_profile_used_as_cache_key(self, tmp_path: Path):
        from app.collectors.copilot_research_collector import CopilotResearchCollector
        cache = CollectionCache(root=tmp_path)
        ctx = RunContext(run_id="r1", target_date=_DATE, prompt_profile="aggressive-v1")
        transport = _FakeTransport()
        collector = CopilotResearchCollector(transport=transport, cache=cache)
        collector.collect(ctx)

        assert cache.exists("copilot_research", _DATE, "aggressive-v1")
        # default profile should NOT exist
        assert not cache.exists("copilot_research", _DATE, "default")

    def test_different_profiles_cached_separately(self, tmp_path: Path):
        from app.collectors.copilot_research_collector import CopilotResearchCollector
        cache = CollectionCache(root=tmp_path)
        for profile in ("profile-a", "profile-b"):
            ctx = RunContext(run_id="r1", target_date=_DATE, prompt_profile=profile)
            transport = _FakeTransport()
            collector = CopilotResearchCollector(transport=transport, cache=cache)
            collector.collect(ctx)

        assert cache.exists("copilot_research", _DATE, "profile-a")
        assert cache.exists("copilot_research", _DATE, "profile-b")

    def test_no_items_does_not_write_cache(self, tmp_path: Path):
        from app.collectors.copilot_research_collector import (
            CopilotResearchCollector,
            ResearchResponse,
            ResearchTransport,
        )

        class EmptyTransport(ResearchTransport):
            def execute(self, request: Any) -> ResearchResponse:
                return ResearchResponse(items=[])

        cache = CollectionCache(root=tmp_path)
        collector = CopilotResearchCollector(transport=EmptyTransport(), cache=cache)
        result = collector.collect(_CTX)
        assert not result.items
        assert not cache.exists("copilot_research", _DATE, "default")

    def test_no_cache_does_not_break_collect(self):
        from app.collectors.copilot_research_collector import CopilotResearchCollector
        transport = _FakeTransport()
        collector = CopilotResearchCollector(transport=transport, cache=None)
        result = collector.collect(_CTX)
        assert result.items

    def test_cached_metadata_query_preserved(self, tmp_path: Path):
        from app.collectors.copilot_research_collector import CopilotResearchCollector
        cache = CollectionCache(root=tmp_path)
        transport = _FakeTransport()
        collector = CopilotResearchCollector(transport=transport, cache=cache)
        live_result = collector.collect(_CTX)

        # Second call should hit cache
        transport2 = _FakeTransport()
        collector2 = CopilotResearchCollector(transport=transport2, cache=cache)
        cached_result = collector2.collect(_CTX)

        assert transport2.call_count == 0
        assert cached_result.items[0].metadata == live_result.items[0].metadata
