"""
tests/test_news_item.py — Tests for the shared NewsItem model.

Verifies that:
- NewsItem lives at its canonical location (app.models.news_item)
- app.models and app.normalize expose the same class object
- Field types and defaults behave as documented
- from_raw() produces a correctly populated NewsItem
- raw_refs always preserves originating RawDocument references
- metadata instances are independent (no shared-default mutation)
"""

from __future__ import annotations

import pytest

from app.models.news_item import NewsItem as NewsItemFromModelsModule
from app.models import NewsItem as NewsItemFromModels
from app.normalize import NewsItem as NewsItemFromNormalize
from app.models import RawDocument


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw(
    *,
    source: str = "web",
    provider: str = "rss-xinhua",
    title: str = "Test headline",
    content: str | None = None,
    url: str | None = None,
    date: str = "2025-01-15",
    metadata: dict | None = None,
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


def _make_news_item(**overrides) -> NewsItemFromModels:
    defaults = dict(
        title="Test headline",
        content=None,
        url=None,
        published_at="2025-01-15",
        source="web",
        provider="rss-xinhua",
        raw_refs=[_make_raw()],
    )
    defaults.update(overrides)
    return NewsItemFromModels(**defaults)


# ---------------------------------------------------------------------------
# Identity: all import paths must refer to the same class object
# ---------------------------------------------------------------------------

class TestImportIdentity:
    def test_module_and_package_are_same_class(self):
        assert NewsItemFromModelsModule is NewsItemFromModels

    def test_models_and_normalize_are_same_class(self):
        assert NewsItemFromModels is NewsItemFromNormalize

    def test_module_and_normalize_are_same_class(self):
        assert NewsItemFromModelsModule is NewsItemFromNormalize


# ---------------------------------------------------------------------------
# Construction: direct instantiation
# ---------------------------------------------------------------------------

class TestNewsItemConstruction:
    def test_minimal_construction(self):
        raw = _make_raw()
        item = NewsItemFromModels(
            title="Headline",
            content=None,
            url=None,
            published_at="2025-01-15",
            source="web",
            provider="rss-xinhua",
            raw_refs=[raw],
        )
        assert item.title == "Headline"
        assert item.content is None
        assert item.url is None
        assert item.published_at == "2025-01-15"
        assert item.source == "web"
        assert item.provider == "rss-xinhua"
        assert item.raw_refs == [raw]

    def test_metadata_default_is_empty_dict(self):
        item = _make_news_item()
        assert item.metadata == {}

    def test_metadata_instances_are_independent(self):
        i1 = _make_news_item()
        i2 = _make_news_item()
        i1.metadata["key"] = "value"
        assert "key" not in i2.metadata

    def test_full_construction(self):
        raw = _make_raw(
            source="akshare",
            provider="cctv",
            title="AI chip breakthrough",
            content="Body text.",
            url="https://example.com/news/1",
            date="2025-06-01",
            metadata={"extra": "val"},
        )
        item = NewsItemFromModels(
            title="AI chip breakthrough",
            content="Body text.",
            url="https://example.com/news/1",
            published_at="2025-06-01",
            source="akshare",
            provider="cctv",
            raw_refs=[raw],
            metadata={"tag": "technology"},
        )
        assert item.content == "Body text."
        assert item.url == "https://example.com/news/1"
        assert item.metadata == {"tag": "technology"}

    def test_title_allows_empty_string(self):
        item = _make_news_item(title="")
        assert item.title == ""

    def test_content_allows_none(self):
        item = _make_news_item(content=None)
        assert item.content is None

    def test_url_allows_none(self):
        item = _make_news_item(url=None)
        assert item.url is None

    def test_raw_refs_accepts_multiple(self):
        r1 = _make_raw(title="first")
        r2 = _make_raw(title="second", source="akshare", provider="cctv")
        item = _make_news_item(raw_refs=[r1, r2])
        assert len(item.raw_refs) == 2
        assert item.raw_refs[0] is r1
        assert item.raw_refs[1] is r2


# ---------------------------------------------------------------------------
# from_raw() helper constructor
# ---------------------------------------------------------------------------

class TestFromRaw:
    def test_from_raw_copies_all_fields(self):
        raw = _make_raw(
            source="akshare",
            provider="caixin",
            title="Market update",
            content="Content body.",
            url="https://caixin.com/article/1",
            date="2025-03-10",
            metadata={"query": "market 2025"},
        )
        item = NewsItemFromModels.from_raw(raw)
        assert item.title == raw.title
        assert item.content == raw.content
        assert item.url == raw.url
        assert item.published_at == raw.date
        assert item.source == raw.source
        assert item.provider == raw.provider

    def test_from_raw_stores_raw_ref(self):
        raw = _make_raw()
        item = NewsItemFromModels.from_raw(raw)
        assert len(item.raw_refs) == 1
        assert item.raw_refs[0] is raw

    def test_from_raw_metadata_is_a_copy(self):
        raw = _make_raw(metadata={"q": "test"})
        item = NewsItemFromModels.from_raw(raw)
        # mutating item metadata must not affect the raw document
        item.metadata["extra"] = "added"
        assert "extra" not in raw.metadata

    def test_from_raw_metadata_original_not_affected(self):
        raw = _make_raw(metadata={"k": "v"})
        item = NewsItemFromModels.from_raw(raw)
        raw.metadata["new"] = "x"
        assert "new" not in item.metadata

    def test_from_raw_with_none_content(self):
        raw = _make_raw(content=None)
        item = NewsItemFromModels.from_raw(raw)
        assert item.content is None

    def test_from_raw_with_none_url(self):
        raw = _make_raw(url=None)
        item = NewsItemFromModels.from_raw(raw)
        assert item.url is None

    def test_from_raw_with_empty_title(self):
        raw = _make_raw(title="")
        item = NewsItemFromModels.from_raw(raw)
        assert item.title == ""

    def test_from_raw_metadata_empty_dict_by_default(self):
        raw = _make_raw()  # metadata defaults to {}
        item = NewsItemFromModels.from_raw(raw)
        assert item.metadata == {}

    def test_from_raw_returns_news_item_instance(self):
        raw = _make_raw()
        item = NewsItemFromModels.from_raw(raw)
        assert isinstance(item, NewsItemFromModels)


# ---------------------------------------------------------------------------
# raw_refs traceability contract
# ---------------------------------------------------------------------------

class TestRawRefsTraceability:
    def test_raw_refs_preserves_identity(self):
        raw = _make_raw()
        item = NewsItemFromModels.from_raw(raw)
        assert item.raw_refs[0] is raw

    def test_raw_refs_reflects_originating_source(self):
        raw = _make_raw(source="copilot_research", provider="web-access")
        item = NewsItemFromModels.from_raw(raw)
        assert item.raw_refs[0].source == "copilot_research"
        assert item.raw_refs[0].provider == "web-access"

    def test_multi_raw_refs_all_sources_accessible(self):
        r1 = _make_raw(source="web", provider="xinhua")
        r2 = _make_raw(source="akshare", provider="cctv")
        r3 = _make_raw(source="copilot_research", provider="web-access")
        item = _make_news_item(raw_refs=[r1, r2, r3])
        sources = [r.source for r in item.raw_refs]
        assert sources == ["web", "akshare", "copilot_research"]


# ---------------------------------------------------------------------------
# Type checks
# ---------------------------------------------------------------------------

class TestNewsItemTypes:
    def test_string_fields_are_str(self):
        item = _make_news_item()
        assert isinstance(item.title, str)
        assert isinstance(item.published_at, str)
        assert isinstance(item.source, str)
        assert isinstance(item.provider, str)

    def test_metadata_is_dict(self):
        item = _make_news_item()
        assert isinstance(item.metadata, dict)

    def test_raw_refs_is_list(self):
        item = _make_news_item()
        assert isinstance(item.raw_refs, list)

    def test_raw_refs_elements_are_raw_documents(self):
        raw = _make_raw()
        item = _make_news_item(raw_refs=[raw])
        assert all(isinstance(r, RawDocument) for r in item.raw_refs)

    def test_metadata_accepts_arbitrary_values(self):
        item = _make_news_item(
            metadata={"query": "AI supply chain", "page": 2, "nested": {"k": "v"}}
        )
        assert item.metadata["query"] == "AI supply chain"
        assert item.metadata["page"] == 2
        assert item.metadata["nested"] == {"k": "v"}
