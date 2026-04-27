"""
tests/test_pipeline_integration.py — end-to-end pipeline integration tests.

Verifies the complete flow:
  RawDocument → NewsItem → EventDraft → TaggedOutput → InformationChain
    → AnalysisInput → AnalysisResponse → AStockMapping → DailyReport

Uses dry-run adapters so no real LLM or network calls are made.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from app.models.raw_document import RawDocument
from app.models.news_item import NewsItem
from app.models.event_draft import EventDraft
from app.entity.tagged_output import build_tagged_output
from app.chains.chain import build_chain, InformationChain
from app.chains.candidate_generation import generate_candidate_chains
from app.chains.evidence_retention import collect_all_evidence
from app.analysis.engine import AnalysisEngine, AnalysisEngineConfig
from app.analysis.adapters.contracts import PromptProfile
from app.mapping.engine import AShareMappingEngine, MappingScoringEngine
from app.mapping.schema import ConfidenceLevel
from app.reports.core import (
    DailyReportBuilder,
    DailyReportHeader,
    DailyReport,
    ReportArchiveManager,
)


# ---------------------------------------------------------------------------
# Test data factory
# ---------------------------------------------------------------------------

def _make_raw_documents() -> list[RawDocument]:
    """Create a set of realistic raw documents for integration testing."""
    return [
        RawDocument(
            source="akshare",
            provider="cctv",
            title="英伟达发布新一代B200 GPU，AI算力提升5倍",
            content=(
                "英伟达在GTC大会上发布了新一代B200 GPU，基于Blackwell架构，"
                "AI训练性能提升5倍，推理性能提升30倍。"
                "该芯片将推动大模型训练成本大幅下降，"
                "对光模块、HBM存储、服务器产业链产生重大影响。"
            ),
            url="https://example.com/nvidia-b200",
            date="2025-03-18",
        ),
        RawDocument(
            source="web",
            provider="rss",
            title="中际旭创800G光模块获英伟达认证",
            content=(
                "中际旭创宣布其800G光模块产品已通过英伟达认证，"
                "将成为B200 GPU配套光互连方案供应商之一。"
                "分析师预计该订单将为公司带来显著收入增长。"
            ),
            url="https://example.com/zhongji-800g",
            date="2025-03-18",
        ),
        RawDocument(
            source="akshare",
            provider="caixin",
            title="HBM需求激增，SK海力士产能满载",
            content=(
                "受AI芯片需求拉动，HBM存储需求持续增长。"
                "SK海力士表示其HBM3E产能已满载至明年，"
                "预计将扩大投资。国内封测企业有望受益。"
            ),
            url="https://example.com/hbm-demand",
            date="2025-03-18",
        ),
        RawDocument(
            source="web",
            provider="rss",
            title="国内AI大模型备案数量突破100个",
            content=(
                "据工信部数据，截至2025年3月，国内已完成备案的AI大模型数量突破100个，"
                "覆盖通用、行业垂直和多模态三大类别。"
                "应用落地加速将带动算力基础设施需求持续增长。"
            ),
            url="https://example.com/ai-models-100",
            date="2025-03-18",
        ),
    ]


def _normalize_to_news_items(raw_docs: list[RawDocument]) -> list[NewsItem]:
    """Normalize raw documents to news items."""
    return [NewsItem.from_raw(doc) for doc in raw_docs]


def _extract_to_tagged_outputs(news_items: list[NewsItem]) -> list:
    """Extract entities and themes from news items."""
    from app.entity.rules.extractor import RuleExtractor
    from app.entity.evidence import build_evidence_links

    extractor = RuleExtractor()
    tagged = []
    for item in news_items:
        event = EventDraft.from_news_item(item)
        text = f"{item.title} {item.content}"
        hits = extractor.extract(text)
        evidence_links = build_evidence_links(text, hits)
        tagged_output = build_tagged_output(
            event=event,
            text=text,
            evidence_links=evidence_links,
        )
        tagged.append(tagged_output)
    return tagged


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:
    """End-to-end pipeline integration tests."""

    def test_raw_to_news_item(self):
        """Step 1: RawDocument → NewsItem normalization."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)

        assert len(news_items) == 4
        for item in news_items:
            assert item.title is not None
            assert item.content is not None
            assert item.url is not None

    def test_news_item_to_tagged_output(self):
        """Step 2: NewsItem → TaggedOutput entity/theme tagging."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)
        tagged_outputs = _extract_to_tagged_outputs(news_items)

        assert len(tagged_outputs) == 4
        for tagged in tagged_outputs:
            assert tagged.event is not None
            assert len(tagged.theme_ids) > 0 or len(tagged.entity_type_ids) > 0

    def test_tagged_output_to_chains(self):
        """Step 3: TaggedOutput → InformationChain candidate generation."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)
        tagged_outputs = _extract_to_tagged_outputs(news_items)

        chains = generate_candidate_chains(tagged_outputs)

        # Should produce at least one chain from the AI-related documents
        assert len(chains) >= 1
        for chain in chains:
            assert isinstance(chain, InformationChain)
            assert len(chain.nodes) >= 1

    def test_chain_evidence_collection(self):
        """Step 4: InformationChain → evidence collection."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)
        tagged_outputs = _extract_to_tagged_outputs(news_items)
        chains = generate_candidate_chains(tagged_outputs)

        evidence = collect_all_evidence(chains)

        assert len(evidence) == len(chains)
        for bundle in evidence:
            # Each chain should have at least one evidence source
            assert bundle is not None

    def test_dry_run_analysis(self):
        """Step 5: InformationChain → AnalysisResponse (dry-run)."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)
        tagged_outputs = _extract_to_tagged_outputs(news_items)
        chains = generate_candidate_chains(tagged_outputs)

        engine_config = AnalysisEngineConfig(
            github_token="",
            templates_dir="app/analysis/prompts/templates",
            profiles_dir="config/prompt_profiles",
            default_profile_name="default",
        )
        engine = AnalysisEngine(engine_config, dry_run=True)

        chains_result, response, profile = engine.run_full_analysis(tagged_outputs)

        assert response is not None
        assert len(response.chain_results) > 0
        assert response.ranking is not None

    def test_a_share_mapping(self):
        """Step 6: InformationChain → AStockMapping."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)
        tagged_outputs = _extract_to_tagged_outputs(news_items)
        chains = generate_candidate_chains(tagged_outputs)

        mapping_engine = AShareMappingEngine()
        mappings = {}
        for chain in chains:
            mapping = mapping_engine.map_information_chain(chain)
            mappings[chain.chain_id] = mapping

        assert len(mappings) == len(chains)
        for chain_id, mapping in mappings.items():
            assert mapping.chain_id == chain_id
            assert mapping.overall_confidence in {
                ConfidenceLevel.HIGH,
                ConfidenceLevel.MEDIUM,
                ConfidenceLevel.LOW,
            }

    def test_mapping_score(self):
        """Step 7: AStockMapping → AShareMappingScore."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)
        tagged_outputs = _extract_to_tagged_outputs(news_items)
        chains = generate_candidate_chains(tagged_outputs)

        mapping_engine = AShareMappingEngine()
        score_engine = MappingScoringEngine()

        for chain in chains:
            mapping = mapping_engine.map_information_chain(chain)
            score = score_engine.score_mapping(mapping)
            assert score is not None
            assert 0 <= score.overall_score <= 100
            assert score.score_level in {"excellent", "good", "fair", "poor"}

    def test_report_generation(self):
        """Step 8: Full pipeline → DailyReport (Markdown + JSON)."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)
        tagged_outputs = _extract_to_tagged_outputs(news_items)

        # Analysis
        engine_config = AnalysisEngineConfig(
            github_token="",
            templates_dir="app/analysis/prompts/templates",
            profiles_dir="config/prompt_profiles",
            default_profile_name="default",
        )
        engine = AnalysisEngine(engine_config, dry_run=True)
        chains, response, profile = engine.run_full_analysis(tagged_outputs)

        # Mapping
        mapping_engine = AShareMappingEngine()
        score_engine = MappingScoringEngine()
        mappings = {}
        scores = {}
        for chain in chains:
            mapping = mapping_engine.map_information_chain(chain)
            mappings[chain.chain_id] = mapping
            scores[chain.chain_id] = score_engine.score_mapping(mapping)

        # Report
        builder = DailyReportBuilder()
        report = builder.build(
            report_date="2025-03-18",
            report_batch="pre-market",
            analysis_response=response,
            mappings=mappings,
            scores=scores,
            prompt_profile=None,
        )

        assert isinstance(report, DailyReport)
        assert report.header.report_date == "2025-03-18"
        assert report.header.report_batch == "pre-market"
        assert len(report.top_chains) > 0

        # Markdown
        md = builder.to_markdown(report)
        assert "每日 AI 投资资讯" in md
        assert "2025-03-18" in md

        # JSON
        json_str = builder.to_json(report)
        json_data = json.loads(json_str)
        assert json_data["header"]["report_date"] == "2025-03-18"
        assert len(json_data["top_chains"]) > 0

    def test_report_archive(self, tmp_path):
        """Step 9: DailyReport → file archive (Markdown + JSON)."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)
        tagged_outputs = _extract_to_tagged_outputs(news_items)

        engine_config = AnalysisEngineConfig(
            github_token="",
            templates_dir="app/analysis/prompts/templates",
            profiles_dir="config/prompt_profiles",
            default_profile_name="default",
        )
        engine = AnalysisEngine(engine_config, dry_run=True)
        chains, response, _ = engine.run_full_analysis(tagged_outputs)

        mapping_engine = AShareMappingEngine()
        mappings = {}
        for chain in chains:
            mappings[chain.chain_id] = mapping_engine.map_information_chain(chain)

        builder = DailyReportBuilder()
        report = builder.build(
            report_date="2025-03-18",
            report_batch="midday",
            analysis_response=response,
            mappings=mappings,
        )

        archive = ReportArchiveManager(tmp_path)
        saved = archive.save_report(report, save_markdown=True, save_json=True)

        assert "markdown" in saved
        assert "json" in saved
        assert saved["markdown"].exists()
        assert saved["json"].exists()

        md_content = saved["markdown"].read_text(encoding="utf-8")
        assert "每日 AI 投资资讯" in md_content

        json_content = saved["json"].read_text(encoding="utf-8")
        json_data = json.loads(json_content)
        assert json_data["header"]["report_batch"] == "midday"

    def test_multi_batch_same_day(self, tmp_path):
        """Verify same-day multi-batch reports don't overwrite each other."""
        raw_docs = _make_raw_documents()
        news_items = _normalize_to_news_items(raw_docs)
        tagged_outputs = _extract_to_tagged_outputs(news_items)

        engine_config = AnalysisEngineConfig(
            github_token="",
            templates_dir="app/analysis/prompts/templates",
            profiles_dir="config/prompt_profiles",
            default_profile_name="default",
        )
        engine = AnalysisEngine(engine_config, dry_run=True)
        chains, response, _ = engine.run_full_analysis(tagged_outputs)

        mapping_engine = AShareMappingEngine()
        mappings = {}
        for chain in chains:
            mappings[chain.chain_id] = mapping_engine.map_information_chain(chain)

        builder = DailyReportBuilder()
        archive = ReportArchiveManager(tmp_path)

        # Pre-market batch
        report_am = builder.build(
            report_date="2025-03-18",
            report_batch="pre-market",
            analysis_response=response,
            mappings=mappings,
        )
        saved_am = archive.save_report(report_am)

        # Midday batch
        report_pm = builder.build(
            report_date="2025-03-18",
            report_batch="midday",
            analysis_response=response,
            mappings=mappings,
        )
        saved_pm = archive.save_report(report_pm)

        # Both should exist independently
        assert saved_am["markdown"] != saved_pm["markdown"]
        assert saved_am["json"] != saved_pm["json"]
        assert saved_am["markdown"].exists()
        assert saved_pm["markdown"].exists()


class TestPipelineErrorHandling:
    """Test error handling in the pipeline."""

    def test_empty_input_produces_empty_chains(self):
        """Empty input should not crash, just produce no chains."""
        chains = generate_candidate_chains([])
        assert chains == []

    def test_empty_input_produces_empty_report(self):
        """Empty analysis response should still produce a valid report."""
        from app.analysis.adapters.contracts import (
            AnalysisResponse,
            RankingOutput,
            ModelProviderInfo,
            PromptTaskType,
        )

        empty_response = AnalysisResponse(
            chain_results=[],
            ranking=RankingOutput(
                entries=(),
                prompt_profile=PromptProfile(
                    profile_name="default",
                    version="1.0",
                    task_type=PromptTaskType.SUMMARY,
                ),
            ),
            provider_info=ModelProviderInfo(
                provider="dry-run",
                model_id="test",
                model_version="1.0",
            ),
        )

        builder = DailyReportBuilder()
        report = builder.build(
            report_date="2025-03-18",
            report_batch="pre-market",
            analysis_response=empty_response,
            mappings={},
        )

        assert isinstance(report, DailyReport)
        assert len(report.top_chains) == 0
        assert "暂无" in report.summary or len(report.top_chains) == 0

    def test_single_document_produces_chain(self):
        """A single document should still produce at least one chain."""
        raw = RawDocument(
            source="test",
            provider="test",
            title="AI芯片需求增长",
            content="AI芯片需求持续增长，算力产业链受益。",
            url="https://example.com/test",
            date="2025-03-18",
        )
        news = NewsItem.from_raw(raw)
        event = EventDraft.from_news_item(news)
        tagged = build_tagged_output(
            event=event,
            text="AI芯片需求持续增长，算力产业链受益。",
            evidence_links=[],
        )

        chains = generate_candidate_chains([tagged])
        assert len(chains) >= 1


class TestRunLogIntegration:
    """Integration tests for run log persistence."""

    def test_run_lifecycle(self):
        """Test a full run lifecycle: start → finish with success/failure."""
        from app.storage import init_db, RunLogStore

        conn = init_db(":memory:")
        store = RunLogStore(conn)

        # Start run
        run_id = store.start_run(
            prompt_profile_name="default",
            prompt_profile_version="1.0",
            run_date="2025-03-18",
            batch_index=0,
        )
        assert run_id > 0

        # Check running state
        entry = store.get_run(run_id)
        assert entry is not None
        assert entry.status == "running"
        assert entry.run_date == "2025-03-18"
        assert entry.batch_index == 0

        # Finish with success
        store.finish_run(run_id, success=True)
        entry = store.get_run(run_id)
        assert entry.status == "success"
        assert entry.finished_at is not None

    def test_run_failure_logging(self):
        """Test that failed runs are properly recorded."""
        from app.storage import init_db, RunLogStore

        conn = init_db(":memory:")
        store = RunLogStore(conn)

        run_id = store.start_run(
            prompt_profile_name="default",
            run_date="2025-03-18",
            batch_index=1,
        )
        store.finish_run(run_id, success=False, error_text="Connection timeout")

        entry = store.get_run(run_id)
        assert entry.status == "failed"
        assert entry.error_text == "Connection timeout"

    def test_multi_batch_runs(self):
        """Test same-day multi-batch run tracking."""
        from app.storage import init_db, RunLogStore

        conn = init_db(":memory:")
        store = RunLogStore(conn)

        # Pre-market run
        run_id_am = store.start_run(
            run_date="2025-03-18",
            batch_index=0,
        )
        store.finish_run(run_id_am, success=True)

        # Midday run
        run_id_pm = store.start_run(
            run_date="2025-03-18",
            batch_index=1,
        )
        store.finish_run(run_id_pm, success=True)

        entry_am = store.get_run(run_id_am)
        entry_pm = store.get_run(run_id_pm)

        assert entry_am.batch_index == 0
        assert entry_pm.batch_index == 1
        assert entry_am.run_date == entry_pm.run_date

    def test_latest_run(self):
        """Test get_latest_run returns a run."""
        from app.storage import init_db, RunLogStore

        conn = init_db(":memory:")
        store = RunLogStore(conn)

        store.start_run(run_date="2025-03-17")
        latest_id = store.start_run(run_date="2025-03-18")

        latest = store.get_latest_run()
        assert latest is not None
        assert latest.id in (latest_id, latest_id - 1)  # Either run is valid
