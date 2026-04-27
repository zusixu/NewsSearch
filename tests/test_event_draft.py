"""
tests/test_event_draft.py — Tests for the shared EventDraft model.

Verifies that:
- EventDraft lives at its canonical location (app.models.event_draft)
- app.models and app.normalize expose the same class object
- Field types and defaults behave as documented
- from_news_item() produces a correctly populated EventDraft
- source_items always preserves originating NewsItem references
- entities and themes default to empty lists (not populated here)
- metadata instances are independent (no shared-default mutation)
- The full traceability chain EventDraft → NewsItem → RawDocument works
"""

from __future__ import annotations

import pytest

from app.models.event_draft import EventDraft as EventDraftFromModule
from app.models import EventDraft as EventDraftFromModels
from app.normalize import EventDraft as EventDraftFromNormalize
from app.models import NewsItem, RawDocument


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


def _make_news_item(**overrides) -> NewsItem:
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
    return NewsItem(**defaults)


def _make_event_draft(**overrides) -> EventDraftFromModels:
    defaults = dict(
        title="Test event",
        summary=None,
        occurred_at="2025-01-15",
        source_items=[_make_news_item()],
    )
    defaults.update(overrides)
    return EventDraftFromModels(**defaults)


# ---------------------------------------------------------------------------
# Identity: all import paths must refer to the same class object
# ---------------------------------------------------------------------------

class TestImportIdentity:
    def test_module_and_package_are_same_class(self):
        assert EventDraftFromModule is EventDraftFromModels

    def test_models_and_normalize_are_same_class(self):
        assert EventDraftFromModels is EventDraftFromNormalize

    def test_module_and_normalize_are_same_class(self):
        assert EventDraftFromModule is EventDraftFromNormalize


# ---------------------------------------------------------------------------
# Construction: direct instantiation
# ---------------------------------------------------------------------------

class TestEventDraftConstruction:
    def test_minimal_construction(self):
        item = _make_news_item()
        draft = EventDraftFromModels(
            title="Market rally",
            summary=None,
            occurred_at="2025-01-15",
            source_items=[item],
        )
        assert draft.title == "Market rally"
        assert draft.summary is None
        assert draft.occurred_at == "2025-01-15"
        assert draft.source_items == [item]
        assert draft.entities == []
        assert draft.themes == []
        assert draft.metadata == {}

    def test_entities_default_is_empty_list(self):
        draft = _make_event_draft()
        assert draft.entities == []

    def test_themes_default_is_empty_list(self):
        draft = _make_event_draft()
        assert draft.themes == []

    def test_metadata_default_is_empty_dict(self):
        draft = _make_event_draft()
        assert draft.metadata == {}

    def test_metadata_instances_are_independent(self):
        d1 = _make_event_draft()
        d2 = _make_event_draft()
        d1.metadata["key"] = "value"
        assert "key" not in d2.metadata

    def test_entities_instances_are_independent(self):
        d1 = _make_event_draft()
        d2 = _make_event_draft()
        d1.entities.append("SomeOrg")
        assert "SomeOrg" not in d2.entities

    def test_themes_instances_are_independent(self):
        d1 = _make_event_draft()
        d2 = _make_event_draft()
        d1.themes.append("monetary policy")
        assert "monetary policy" not in d2.themes

    def test_full_construction(self):
        item = _make_news_item(
            title="AI chip ban announced",
            content="Full article body.",
            url="https://example.com/ai-ban",
            published_at="2025-06-01",
            source="akshare",
            provider="cctv",
        )
        draft = EventDraftFromModels(
            title="AI chip ban announced",
            summary="Government announces new restrictions on AI chip exports.",
            occurred_at="2025-06-01",
            source_items=[item],
            entities=["Ministry of Commerce", "Nvidia"],
            themes=["trade policy", "semiconductors"],
            metadata={"confidence": 0.9},
        )
        assert draft.summary == "Government announces new restrictions on AI chip exports."
        assert draft.entities == ["Ministry of Commerce", "Nvidia"]
        assert draft.themes == ["trade policy", "semiconductors"]
        assert draft.metadata == {"confidence": 0.9}

    def test_title_allows_empty_string(self):
        draft = _make_event_draft(title="")
        assert draft.title == ""

    def test_summary_allows_none(self):
        draft = _make_event_draft(summary=None)
        assert draft.summary is None

    def test_summary_allows_string(self):
        draft = _make_event_draft(summary="Brief summary.")
        assert draft.summary == "Brief summary."

    def test_source_items_accepts_multiple(self):
        i1 = _make_news_item(title="report A", source="web", provider="xinhua")
        i2 = _make_news_item(title="report B", source="akshare", provider="cctv")
        draft = _make_event_draft(source_items=[i1, i2])
        assert len(draft.source_items) == 2
        assert draft.source_items[0] is i1
        assert draft.source_items[1] is i2


# ---------------------------------------------------------------------------
# from_news_item() helper constructor
# ---------------------------------------------------------------------------

class TestFromNewsItem:
    def test_from_news_item_copies_title(self):
        item = _make_news_item(title="Fed raises rates")
        draft = EventDraftFromModels.from_news_item(item)
        assert draft.title == "Fed raises rates"

    def test_from_news_item_copies_published_at_to_occurred_at(self):
        item = _make_news_item(published_at="2025-03-10")
        draft = EventDraftFromModels.from_news_item(item)
        assert draft.occurred_at == "2025-03-10"

    def test_from_news_item_summary_is_none(self):
        item = _make_news_item()
        draft = EventDraftFromModels.from_news_item(item)
        assert draft.summary is None

    def test_from_news_item_entities_is_empty(self):
        item = _make_news_item()
        draft = EventDraftFromModels.from_news_item(item)
        assert draft.entities == []

    def test_from_news_item_themes_is_empty(self):
        item = _make_news_item()
        draft = EventDraftFromModels.from_news_item(item)
        assert draft.themes == []

    def test_from_news_item_stores_source_item(self):
        item = _make_news_item()
        draft = EventDraftFromModels.from_news_item(item)
        assert len(draft.source_items) == 1
        assert draft.source_items[0] is item

    def test_from_news_item_metadata_is_a_copy(self):
        item = _make_news_item()
        item.metadata["q"] = "test"
        draft = EventDraftFromModels.from_news_item(item)
        draft.metadata["extra"] = "added"
        assert "extra" not in item.metadata

    def test_from_news_item_metadata_original_not_affected(self):
        item = _make_news_item()
        item.metadata["k"] = "v"
        draft = EventDraftFromModels.from_news_item(item)
        item.metadata["new"] = "x"
        assert "new" not in draft.metadata

    def test_from_news_item_with_empty_title(self):
        item = _make_news_item(title="")
        draft = EventDraftFromModels.from_news_item(item)
        assert draft.title == ""

    def test_from_news_item_returns_event_draft_instance(self):
        item = _make_news_item()
        draft = EventDraftFromModels.from_news_item(item)
        assert isinstance(draft, EventDraftFromModels)


# ---------------------------------------------------------------------------
# source_items traceability contract
# ---------------------------------------------------------------------------

class TestSourceItemsTraceability:
    def test_source_items_preserves_identity(self):
        item = _make_news_item()
        draft = EventDraftFromModels.from_news_item(item)
        assert draft.source_items[0] is item

    def test_source_items_reflects_originating_source(self):
        item = _make_news_item(source="copilot_research", provider="web-access")
        draft = EventDraftFromModels.from_news_item(item)
        assert draft.source_items[0].source == "copilot_research"
        assert draft.source_items[0].provider == "web-access"

    def test_multi_source_items_all_accessible(self):
        i1 = _make_news_item(source="web", provider="xinhua")
        i2 = _make_news_item(source="akshare", provider="cctv")
        i3 = _make_news_item(source="copilot_research", provider="web-access")
        draft = _make_event_draft(source_items=[i1, i2, i3])
        sources = [n.source for n in draft.source_items]
        assert sources == ["web", "akshare", "copilot_research"]

    def test_full_provenance_chain_event_draft_to_raw_document(self):
        """EventDraft → NewsItem → RawDocument traceability."""
        raw = _make_raw(source="akshare", provider="caixin", url="https://caixin.com/1")
        item = NewsItem.from_raw(raw)
        draft = EventDraftFromModels.from_news_item(item)

        # Traverse the full chain
        recovered_raw = draft.source_items[0].raw_refs[0]
        assert recovered_raw is raw
        assert recovered_raw.url == "https://caixin.com/1"


# ---------------------------------------------------------------------------
# Type checks
# ---------------------------------------------------------------------------

class TestEventDraftTypes:
    def test_title_is_str(self):
        draft = _make_event_draft()
        assert isinstance(draft.title, str)

    def test_occurred_at_is_str(self):
        draft = _make_event_draft()
        assert isinstance(draft.occurred_at, str)

    def test_entities_is_list(self):
        draft = _make_event_draft()
        assert isinstance(draft.entities, list)

    def test_themes_is_list(self):
        draft = _make_event_draft()
        assert isinstance(draft.themes, list)

    def test_metadata_is_dict(self):
        draft = _make_event_draft()
        assert isinstance(draft.metadata, dict)

    def test_source_items_is_list(self):
        draft = _make_event_draft()
        assert isinstance(draft.source_items, list)

    def test_source_items_elements_are_news_items(self):
        draft = _make_event_draft()
        assert all(isinstance(n, NewsItem) for n in draft.source_items)

    def test_metadata_accepts_arbitrary_values(self):
        draft = _make_event_draft(
            metadata={"confidence": 0.85, "page": 1, "nested": {"k": "v"}}
        )
        assert draft.metadata["confidence"] == 0.85
        assert draft.metadata["page"] == 1
        assert draft.metadata["nested"] == {"k": "v"}
