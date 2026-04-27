"""
tests/test_url_preservation.py

Tests for URL preservation through the full pipeline:
RawDocument -> NewsItem -> EventDraft -> TaggedOutput -> InformationChain
-> ChainEvidenceBundle -> DailyReportChainEntry -> DailyReport.

Coverage:
- collect_chain_evidence() correctly extracts source_urls
- URL deduplication in ChainEvidenceBundle
- DailyReportChainEntry.source_urls field
- MarkdownReportGenerator renders source links (markdown [text](url))
- JsonReportGenerator output includes source_urls
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.chains.chain import InformationChain, ChainNode, build_chain
from app.chains.candidate_generation import generate_candidate_chains
from app.chains.evidence_retention import (
    ChainEvidenceBundle,
    collect_chain_evidence,
    collect_all_evidence,
)
from app.entity.tagged_output import TaggedOutput
from app.models.news_item import NewsItem
from app.models.raw_document import RawDocument
from app.reports.core import (
    DailyReportBuilder,
    DailyReport,
    DailyReportHeader,
    DailyReportChainEntry,
    MarkdownReportGenerator,
    JsonReportGenerator,
    RiskWarning,
)
from app.mapping.schema import (
    AStockMapping,
    ConfidenceLevel,
)
from app.analysis.adapters.contracts import (
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    ModelProviderInfo,
    PromptProfile,
    PromptTaskType,
    RankingOutput,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dummy_raw_with_url() -> RawDocument:
    return RawDocument(
        source="test",
        provider="test",
        title="Test News with URL",
        content="Some content about AI",
        url="https://example.com/article/123",
        date="2025-01-01",
    )


@pytest.fixture
def dummy_raw_without_url() -> RawDocument:
    return RawDocument(
        source="test",
        provider="test",
        title="Test News without URL",
        content="Some content about GPU",
        url=None,
        date="2025-01-01",
    )


@pytest.fixture
def dummy_chain_with_urls(dummy_raw_with_url, dummy_raw_without_url):
    """Create an InformationChain with multiple source items containing URLs."""
    from app.entity.tagged_output import build_tagged_output
    from app.models.event_draft import EventDraft

    # Item with URL
    news1 = NewsItem.from_raw(dummy_raw_with_url)
    event1 = EventDraft.from_news_item(news1)
    event1.source_items = [news1]
    tagged1 = build_tagged_output(event=event1, text="AI content", evidence_links=[])

    # Item without URL
    news2 = NewsItem.from_raw(dummy_raw_without_url)
    event2 = EventDraft.from_news_item(news2)
    event2.source_items = [news2]
    tagged2 = build_tagged_output(event=event2, text="GPU content", evidence_links=[])

    return build_chain("url-chain-1", [tagged1, tagged2])


@pytest.fixture
def dummy_chain_multiple_urls():
    """Create an InformationChain with duplicate URLs across items."""
    from app.entity.tagged_output import build_tagged_output
    from app.models.event_draft import EventDraft

    raws = [
        RawDocument("t1", "p", "News 1", "Body 1", "https://example.com/a", "2025-01-01"),
        RawDocument("t2", "p", "News 2", "Body 2", "https://example.com/b", "2025-01-01"),
        RawDocument("t3", "p", "News 3", "Body 3", "https://example.com/a", "2025-01-01"),  # duplicate
    ]

    tagged_list = []
    for raw in raws:
        news = NewsItem.from_raw(raw)
        event = EventDraft.from_news_item(news)
        event.source_items = [news]
        tagged = build_tagged_output(event=event, text=raw.content, evidence_links=[])
        tagged_list.append(tagged)

    return build_chain("url-chain-2", tagged_list)


# ---------------------------------------------------------------------------
# ChainEvidenceBundle source_urls tests
# ---------------------------------------------------------------------------


class TestCollectChainEvidenceSourceUrls:
    """Tests for source_urls extraction in collect_chain_evidence()."""

    def test_single_url_extracted(self, dummy_chain_with_urls):
        """collect_chain_evidence() extracts the single URL correctly."""
        bundle = collect_chain_evidence(dummy_chain_with_urls)
        assert isinstance(bundle, ChainEvidenceBundle)
        assert "https://example.com/article/123" in bundle.source_urls

    def test_none_url_not_included(self, dummy_chain_with_urls):
        """None URLs are not included in source_urls."""
        bundle = collect_chain_evidence(dummy_chain_with_urls)
        assert None not in bundle.source_urls
        assert len(bundle.source_urls) == 1  # only the non-None URL

    def test_empty_urls_for_no_url_chain(self, dummy_raw_without_url):
        """When no items have URLs, source_urls is empty."""
        from app.entity.tagged_output import build_tagged_output
        from app.models.event_draft import EventDraft

        news = NewsItem.from_raw(dummy_raw_without_url)
        event = EventDraft.from_news_item(news)
        event.source_items = [news]
        tagged = build_tagged_output(event=event, text="content", evidence_links=[])
        chain = build_chain("no-url-chain", [tagged])

        bundle = collect_chain_evidence(chain)
        assert bundle.source_urls == ()

    def test_urls_deduplicated(self, dummy_chain_multiple_urls):
        """Duplicate URLs are deduplicated, keeping first occurrence."""
        bundle = collect_chain_evidence(dummy_chain_multiple_urls)
        # Only 2 unique URLs: 'https://example.com/a' and 'https://example.com/b'
        assert len(bundle.source_urls) == 2
        assert "https://example.com/a" in bundle.source_urls
        assert "https://example.com/b" in bundle.source_urls

    def test_urls_preserve_first_seen_order(self):
        """URLs are in first-seen order."""
        from app.entity.tagged_output import build_tagged_output
        from app.models.event_draft import EventDraft

        raws = [
            RawDocument("s", "p", "B first", "b", "https://b.com", "2025-01-01"),
            RawDocument("s", "p", "A second", "a", "https://a.com", "2025-01-01"),
        ]
        tagged_list = []
        for raw in raws:
            news = NewsItem.from_raw(raw)
            event = EventDraft.from_news_item(news)
            event.source_items = [news]
            tagged = build_tagged_output(event=event, text=raw.content, evidence_links=[])
            tagged_list.append(tagged)

        chain = build_chain("order-chain", tagged_list)
        bundle = collect_chain_evidence(chain)

        assert list(bundle.source_urls) == ["https://b.com", "https://a.com"]

    def test_collect_all_evidence_returns_one_per_chain(self, dummy_chain_with_urls):
        """collect_all_evidence() returns one bundle per chain."""
        bundles = collect_all_evidence([dummy_chain_with_urls])
        assert len(bundles) == 1
        assert isinstance(bundles[0], ChainEvidenceBundle)

    def test_chain_id_preserved_in_bundle(self, dummy_chain_with_urls):
        """Bundle chain_id matches the source chain."""
        bundle = collect_chain_evidence(dummy_chain_with_urls)
        assert bundle.chain_id == dummy_chain_with_urls.chain_id


# ---------------------------------------------------------------------------
# DailyReportChainEntry source_urls tests
# ---------------------------------------------------------------------------


class TestDailyReportChainEntrySourceUrls:
    """Tests for DailyReportChainEntry.source_urls field."""

    def test_source_urls_field_default(self):
        """source_urls defaults to empty tuple."""
        entry = DailyReportChainEntry(
            chain_id="c1",
            rank=1,
            title="Test",
            summary="Summary",
            confidence=0.8,
            rationale="Rationale",
            a_share_mapping=AStockMapping(
                chain_id="c1",
                sector_mappings=(),
                stock_pool_mappings=(),
                individual_stock_mappings=(),
                overall_confidence=ConfidenceLevel.LOW,
                summary="No mapping",
                generated_at="2025-01-01T00:00:00",
            ),
        )
        assert entry.source_urls == ()

    def test_source_urls_can_be_set(self):
        """source_urls can be explicitly set."""
        urls = ("https://example.com/1", "https://example.com/2")
        entry = DailyReportChainEntry(
            chain_id="c1",
            rank=1,
            title="Test",
            summary="Summary",
            confidence=0.8,
            rationale="Rationale",
            a_share_mapping=AStockMapping(
                chain_id="c1",
                sector_mappings=(),
                stock_pool_mappings=(),
                individual_stock_mappings=(),
                overall_confidence=ConfidenceLevel.LOW,
                summary="No mapping",
                generated_at="2025-01-01T00:00:00",
            ),
            source_urls=urls,
        )
        assert entry.source_urls == urls


# ---------------------------------------------------------------------------
# Markdown report source links rendering
# ---------------------------------------------------------------------------


class TestMarkdownReportSourceLinks:
    """Tests for source URL rendering in Markdown reports."""

    def _make_report(self, source_urls: tuple[str, ...] = ()) -> DailyReport:
        """Build a minimal DailyReport with a chain entry that has source URLs."""
        mapping = AStockMapping(
            chain_id="c1",
            sector_mappings=(),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="No mapping",
            generated_at="2025-01-01T00:00:00",
        )
        entry = DailyReportChainEntry(
            chain_id="c1",
            rank=1,
            title="Test Chain",
            summary="A test chain summary.",
            confidence=0.85,
            rationale="Ranked first because relevant.",
            a_share_mapping=mapping,
            source_urls=source_urls,
        )
        return DailyReport(
            header=DailyReportHeader(
                report_date="2025-01-01",
                report_batch="pre-market",
                generated_at="2025-01-01T00:00:00Z",
            ),
            top_chains=[entry],
            risk_warnings=[],
            summary="Today's summary.",
        )

    def test_source_links_section_present(self):
        """Markdown output contains source link section when URLs exist."""
        report = self._make_report(source_urls=("https://example.com/article",))
        generator = MarkdownReportGenerator()
        md = generator.generate(report)

        assert "##### 来源链接" in md
        assert "https://example.com/article" in md
        # Should be a markdown link
        assert "[https://example.com/article](https://example.com/article)" in md

    def test_no_source_links_when_empty(self):
        """Markdown output does NOT contain source link section when no URLs."""
        report = self._make_report(source_urls=())
        generator = MarkdownReportGenerator()
        md = generator.generate(report)

        assert "##### 来源链接" not in md

    def test_multiple_source_links_rendered(self):
        """Multiple URLs are all rendered."""
        urls = ("https://a.com/1", "https://b.com/2")
        report = self._make_report(source_urls=urls)
        generator = MarkdownReportGenerator()
        md = generator.generate(report)

        assert "[https://a.com/1](https://a.com/1)" in md
        assert "[https://b.com/2](https://b.com/2)" in md

    def test_long_url_truncated_in_display(self):
        """Very long URLs (>80 chars) are truncated in display text."""
        long_url = "https://example.com/" + "x" * 100
        report = self._make_report(source_urls=(long_url,))
        generator = MarkdownReportGenerator()
        md = generator.generate(report)

        # The truncated version should appear as display text
        assert long_url[:77] + "..." in md
        # The full URL should appear as the href
        assert f"]({long_url})" in md


# ---------------------------------------------------------------------------
# JSON report source_urls tests
# ---------------------------------------------------------------------------


class TestJsonReportSourceUrls:
    """Tests for source_urls in JSON report output."""

    def _make_report(self, source_urls: tuple[str, ...] = ()) -> DailyReport:
        mapping = AStockMapping(
            chain_id="c1",
            sector_mappings=(),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="No mapping",
            generated_at="2025-01-01T00:00:00",
        )
        entry = DailyReportChainEntry(
            chain_id="c1",
            rank=1,
            title="Test Chain",
            summary="A test chain summary.",
            confidence=0.85,
            rationale="Ranked first.",
            a_share_mapping=mapping,
            source_urls=source_urls,
        )
        return DailyReport(
            header=DailyReportHeader(
                report_date="2025-01-01",
                report_batch="pre-market",
                generated_at="2025-01-01T00:00:00Z",
            ),
            top_chains=[entry],
            risk_warnings=[],
            summary="Today's summary.",
        )

    def test_source_urls_in_json_output(self):
        """JSON output includes source_urls as a list."""
        urls = ("https://example.com/1", "https://example.com/2")
        report = self._make_report(source_urls=urls)
        generator = JsonReportGenerator()
        json_str = generator.generate(report)
        data = json.loads(json_str)

        chain_entry = data["top_chains"][0]
        assert "source_urls" in chain_entry
        assert chain_entry["source_urls"] == list(urls)

    def test_empty_source_urls_in_json(self):
        """JSON output includes source_urls as empty list when no URLs."""
        report = self._make_report(source_urls=())
        generator = JsonReportGenerator()
        json_str = generator.generate(report)
        data = json.loads(json_str)

        chain_entry = data["top_chains"][0]
        assert chain_entry["source_urls"] == []


# ---------------------------------------------------------------------------
# DailyReportBuilder source_urls integration
# ---------------------------------------------------------------------------


class TestDailyReportBuilderSourceUrls:
    """Tests for DailyReportBuilder correctly wiring source_urls from evidence bundles."""

    def test_builder_wires_source_urls_from_evidence_bundle(self):
        """DailyReportBuilder extracts source_urls from provided evidence bundles."""
        from app.chains.chain import build_chain
        from app.entity.tagged_output import build_tagged_output
        from app.models.event_draft import EventDraft

        # Create a chain with a URL-bearing item
        raw = RawDocument(
            source="test", provider="test",
            title="Chain Item", content="Content",
            url="https://example.com/evidence-url",
            date="2025-01-01",
        )
        news = NewsItem.from_raw(raw)
        event = EventDraft.from_news_item(news)
        event.source_items = [news]
        tagged = build_tagged_output(event=event, text="Content", evidence_links=[])
        chain = build_chain("builder-chain", [tagged])

        bundle = collect_chain_evidence(chain)

        # Build minimal analysis response
        profile = PromptProfile(
            profile_name="test", task_type=PromptTaskType.SUMMARY, version="1.0")
        chain_result = ChainAnalysisResult(
            chain_id=chain.chain_id, summary="Test summary.",
            completion_notes="", key_entities=("AI",), confidence=0.9,
            prompt_profile=profile,
        )
        ranking_entry = ChainRankingEntry(
            chain_id=chain.chain_id, rank=1, score=0.9,
            rationale="Top pick.",
        )
        ranking = RankingOutput(entries=(ranking_entry,), prompt_profile=profile)
        analysis_response = AnalysisResponse(
            chain_results=(chain_result,),
            ranking=ranking,
            provider_info=ModelProviderInfo(
                provider="test", model_id="test", model_version="1.0"),
        )

        # Minimal mapping
        mapping = AStockMapping(
            chain_id=chain.chain_id,
            sector_mappings=(),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="No mapping",
            generated_at="2025-01-01T00:00:00",
        )

        builder = DailyReportBuilder()
        report = builder.build(
            report_date="2025-01-01",
            report_batch="pre-market",
            analysis_response=analysis_response,
            mappings={chain.chain_id: mapping},
            evidence_bundles={chain.chain_id: bundle},
        )

        assert len(report.top_chains) == 1
        entry = report.top_chains[0]
        assert "https://example.com/evidence-url" in entry.source_urls

    def test_builder_empty_urls_when_no_bundle(self):
        """DailyReportBuilder uses empty source_urls when evidence_bundles not provided."""
        from app.chains.chain import build_chain
        from app.entity.tagged_output import build_tagged_output
        from app.models.event_draft import EventDraft

        raw = RawDocument("s", "p", "T", "C", None, "2025-01-01")
        news = NewsItem.from_raw(raw)
        event = EventDraft.from_news_item(news)
        event.source_items = [news]
        tagged = build_tagged_output(event=event, text="C", evidence_links=[])
        chain = build_chain("no-bundle-chain", [tagged])

        profile = PromptProfile(
            profile_name="test", task_type=PromptTaskType.SUMMARY, version="1.0")
        chain_result = ChainAnalysisResult(
            chain_id=chain.chain_id, summary="S", completion_notes="",
            key_entities=(), confidence=0.5, prompt_profile=profile,
        )
        ranking_entry = ChainRankingEntry(
            chain_id=chain.chain_id, rank=1, score=0.5, rationale="R",
        )
        ranking = RankingOutput(entries=(ranking_entry,), prompt_profile=profile)
        analysis_response = AnalysisResponse(
            chain_results=(chain_result,), ranking=ranking,
            provider_info=ModelProviderInfo(
                provider="test", model_id="test", model_version="1.0"),
        )
        mapping = AStockMapping(
            chain_id=chain.chain_id,
            sector_mappings=(), stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="No mapping",
            generated_at="2025-01-01T00:00:00",
        )

        builder = DailyReportBuilder()
        report = builder.build(
            report_date="2025-01-01",
            report_batch="pre-market",
            analysis_response=analysis_response,
            mappings={chain.chain_id: mapping},
        )

        entry = report.top_chains[0]
        assert entry.source_urls == ()
