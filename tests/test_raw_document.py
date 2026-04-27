"""
tests/test_raw_document.py — Tests for the shared RawDocument model.

Verifies that:
- RawDocument lives at its canonical location (app.models.raw_document)
- The collector-layer shim re-exports the *same* class (not a copy)
- The normalize package exposes it as the pipeline input contract
- Field types and defaults behave as documented
"""

from __future__ import annotations

import pytest

from app.models.raw_document import RawDocument as RawDocumentFromModels
from app.collectors.raw_document import RawDocument as RawDocumentFromCollectors
from app.normalize import RawDocument as RawDocumentFromNormalize


# ---------------------------------------------------------------------------
# Identity: all import paths must refer to the same class object
# ---------------------------------------------------------------------------

class TestImportIdentity:
    def test_models_and_collectors_are_same_class(self):
        assert RawDocumentFromModels is RawDocumentFromCollectors

    def test_models_and_normalize_are_same_class(self):
        assert RawDocumentFromModels is RawDocumentFromNormalize

    def test_collectors_and_normalize_are_same_class(self):
        assert RawDocumentFromCollectors is RawDocumentFromNormalize


# ---------------------------------------------------------------------------
# Construction and field defaults
# ---------------------------------------------------------------------------

class TestRawDocumentConstruction:
    def _minimal(self) -> RawDocumentFromModels:
        return RawDocumentFromModels(
            source="web",
            provider="rss-xinhua",
            title="Test headline",
            content=None,
            url=None,
            date="2025-01-01",
        )

    def test_minimal_construction(self):
        doc = self._minimal()
        assert doc.source == "web"
        assert doc.provider == "rss-xinhua"
        assert doc.title == "Test headline"
        assert doc.content is None
        assert doc.url is None
        assert doc.date == "2025-01-01"

    def test_metadata_default_is_empty_dict(self):
        doc = self._minimal()
        assert doc.metadata == {}

    def test_metadata_instances_are_independent(self):
        d1 = self._minimal()
        d2 = self._minimal()
        d1.metadata["key"] = "value"
        assert "key" not in d2.metadata

    def test_full_construction_with_content_and_url(self):
        doc = RawDocumentFromModels(
            source="akshare",
            provider="cctv",
            title="AI chip breakthrough",
            content="Full body text here.",
            url="https://example.com/news/123",
            date="2025-06-01",
            metadata={"extra": "value"},
        )
        assert doc.content == "Full body text here."
        assert doc.url == "https://example.com/news/123"
        assert doc.metadata == {"extra": "value"}

    def test_title_allows_empty_string(self):
        doc = RawDocumentFromModels(
            source="web",
            provider="p",
            title="",
            content=None,
            url=None,
            date="2025-01-01",
        )
        assert doc.title == ""

    def test_content_allows_none(self):
        doc = self._minimal()
        assert doc.content is None

    def test_url_allows_none(self):
        doc = self._minimal()
        assert doc.url is None


# ---------------------------------------------------------------------------
# Type checks
# ---------------------------------------------------------------------------

class TestRawDocumentTypes:
    def test_source_is_str(self):
        doc = RawDocumentFromModels(
            source="copilot_research",
            provider="web-access",
            title="t",
            content=None,
            url=None,
            date="2025-01-01",
        )
        assert isinstance(doc.source, str)
        assert isinstance(doc.provider, str)
        assert isinstance(doc.title, str)
        assert isinstance(doc.date, str)
        assert isinstance(doc.metadata, dict)

    def test_metadata_accepts_arbitrary_values(self):
        doc = RawDocumentFromModels(
            source="copilot_research",
            provider="web-access",
            title="t",
            content=None,
            url=None,
            date="2025-01-01",
            metadata={"query": "AI supply chain", "page": 2, "nested": {"k": "v"}},
        )
        assert doc.metadata["query"] == "AI supply chain"
        assert doc.metadata["page"] == 2
        assert doc.metadata["nested"] == {"k": "v"}
