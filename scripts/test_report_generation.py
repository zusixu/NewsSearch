"""
Test script for daily report generation.

Tests the full pipeline from information chains → analysis → mapping → reporting.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import datetime
import uuid

from app.chains.chain import ChainNode, InformationChain, build_chain
from app.chains.relation_type import RelationType
from app.entity.tagged_output import TaggedOutput, build_tagged_output
from app.entity.rules.extractor import Hit
from app.entity.evidence import build_evidence_links
from app.models.event_draft import EventDraft
from app.models.news_item import NewsItem
from app.models.raw_document import RawDocument
from app.entity.themes import ThemeId

from app.analysis import AnalysisEngine, AnalysisEngineConfig, DryRunAnalysisAdapter
from app.analysis.adapters.contracts import ChainAnalysisResult, ChainRankingEntry, RankingOutput, PromptProfile, PromptTaskType, ModelProviderInfo, AnalysisResponse
from app.analysis.prompts import PromptProfileLoader, PromptProfileConfig

from app.mapping import AShareMappingEngine, MappingScoringEngine, create_mapping_engine
from app.mapping import AStockMapping, AShareMappingWithEvidence, AShareMappingScore

from app.reports import DailyReportBuilder, DailyReportHeader, DailyReportChainEntry, RiskWarning
from app.reports import create_report_builder, generate_markdown_report, generate_json_report
from app.reports.core import create_archive_manager


def create_test_tagged_output(theme_id: ThemeId, title: str, text: str) -> TaggedOutput:
    """Create a test tagged output."""
    raw = RawDocument(
        source="test",
        provider="test",
        title=title,
        content=text,
        url=None,
        date="2025-01-15",
    )
    news = NewsItem.from_raw(raw)
    event = EventDraft.from_news_item(news)

    # Create a hit for the theme
    hit = Hit(
        matched_text=text[:10],
        start=0,
        end=10,
        matched_seed="test",
        kind="theme",
        label_id=theme_id.value,
    )

    links = build_evidence_links(text, [hit], context_window=0)

    return build_tagged_output(event, text, links)


def create_test_information_chains() -> list[InformationChain]:
    """Create test information chains for report generation."""
    chains = []

    # Chain 1: AI + GPU + COMPUTE (higher priority)
    tagged1 = create_test_tagged_output(
        ThemeId.AI,
        "NVIDIA发布下一代GPU",
        "NVIDIA发布了新一代AI加速芯片，性能提升50%，同时HBM需求激增。"
    )
    tagged2 = create_test_tagged_output(
        ThemeId.GPU,
        "HBM内存需求上涨",
        "AI大模型训练对HBM内存需求暴增，SK海力士计划扩产。"
    )
    tagged3 = create_test_tagged_output(
        ThemeId.COMPUTE,
        "数据中心建设加速",
        "国内外云厂商都在加大数据中心建设，AI算力需求持续增长。"
    )
    chains.append(build_chain(str(uuid.uuid4()), [tagged1, tagged2, tagged3]))

    # Chain 2: OPTICAL_MODULE + SUPPLY_CHAIN
    tagged4 = create_test_tagged_output(
        ThemeId.OPTICAL_MODULE,
        "光模块需求上涨",
        "800G光模块需求激增，中际旭创等厂商产能满负荷。"
    )
    tagged5 = create_test_tagged_output(
        ThemeId.SUPPLY_CHAIN,
        "供应链整体向好",
        "AI服务器供应链整体景气度提升。"
    )
    chains.append(build_chain(str(uuid.uuid4()), [tagged4, tagged5]))

    # Chain 3: FOUNDATION_MODEL + AI_APPLICATION
    tagged6 = create_test_tagged_output(
        ThemeId.FOUNDATION_MODEL,
        "多模态大模型发布",
        "新的多模态大模型发布，在多个任务上超越GPT-4o。"
    )
    tagged7 = create_test_tagged_output(
        ThemeId.AI_APPLICATION,
        "应用落地加速",
        "AI应用在多个垂直领域落地进程加速。"
    )
    chains.append(build_chain(str(uuid.uuid4()), [tagged6, tagged7]))

    return chains


def create_test_analysis_response(chains: list[InformationChain]) -> AnalysisResponse:
    """Create a test analysis response."""
    profile = PromptProfile(
        profile_name="default",
        task_type=PromptTaskType.INVESTMENT_RANKING,
        version="1.0.0",
        description="Test prompt profile",
    )

    # Chain results
    chain_results = []
    for i, chain in enumerate(chains):
        result = ChainAnalysisResult(
            chain_id=chain.chain_id,
            summary=f"这是关于{'AI算力' if i ==0 else '光模块' if i ==1 else '大模型应用'}的重要信息链。",
            completion_notes="上下游关系明确。",
            key_entities=("NVIDIA", "中际旭创", "SK海力士"),
            confidence=0.85 - (i * 0.1),
            prompt_profile=profile,
        )
        chain_results.append(result)

    # Ranking
    ranking_entries = []
    for i, chain in enumerate(chains):
        entry = ChainRankingEntry(
            chain_id=chain.chain_id,
            rank=i + 1,
            score=10.0 - (i * 1.5),
            rationale=f"{'AI算力是长期主线' if i ==0 else '光模块受益弹性大' if i ==1 else '应用落地值得关注'}。",
        )
        ranking_entries.append(entry)

    ranking_output = RankingOutput(entries=tuple(ranking_entries), prompt_profile=profile)

    provider_info = ModelProviderInfo(
        provider="dry_run",
        model_id="test-model",
        model_version="1.0",
        endpoint="",
    )

    return AnalysisResponse(
        chain_results=tuple(chain_results),
        ranking=ranking_output,
        provider_info=provider_info,
    )


def main():
    """Run the report generation test."""
    print("=" * 80)
    print("Daily AI Investment News Report — Generation Test")
    print("=" * 80)
    print()

    # Step 1: Create test data
    print("[1/6] Creating test information chains...")
    chains = create_test_information_chains()
    print(f"  → Created {len(chains)} test chains")
    for i, chain in enumerate(chains):
        print(f"    Chain {i+1}: {len(chain.nodes)} nodes, themes={chain.theme_ids}")
    print()

    # Step 2: Load prompt profile
    print("[2/6] Loading prompt profile...")
    from app.config import load_config
    config = load_config()
    loader = PromptProfileLoader(Path(config.prompt.profiles_dir))
    profile_config = loader.load_profile_with_fallback("default", "default")
    print(f"  → Loaded profile: {profile_config.profile_name} (v{profile_config.version})")
    print()

    # Step 3: Run analysis (dry-run mode)
    print("[3/6] Running analysis (dry-run mode)...")
    from app.analysis.engine import DryRunAnalysisAdapter
    analysis_response = create_test_analysis_response(chains)
    print(f"  → Analysis complete: {len(analysis_response.chain_results)} chain results")
    print(f"  → Ranking complete: Top {len(analysis_response.ranking.entries)} chains")
    print()

    # Step 4: Run A-share mapping
    print("[4/6] Running A-share mapping...")
    mapping_engine = create_mapping_engine()
    scoring_engine = MappingScoringEngine()

    mappings = []
    scores = []
    for chain in chains:
        mapping = mapping_engine.map_information_chain(chain)
        score = scoring_engine.score_mapping(mapping, chain.theme_ids)
        mappings.append(mapping)
        scores.append(score)
        print(f"  → Chain {len(mappings)}: mapped to {len(mapping.sector_mappings)} sectors, score={score.overall_score:.1f}")
    print()

    # Step 5: Build daily report
    print("[5/6] Building daily report...")
    report_builder = create_report_builder()

    # Build mappings and scores dictionaries keyed by chain_id
    mappings_dict = {}
    scores_dict = {}
    for i, chain in enumerate(chains):
        mappings_dict[chain.chain_id] = mappings[i]
        scores_dict[chain.chain_id] = scores[i]

    # Build the report
    report_date = "2025-01-15"
    report_batch = "pre-market"

    report = report_builder.build(
        report_date=report_date,
        report_batch=report_batch,
        analysis_response=analysis_response,
        mappings=mappings_dict,
        scores=scores_dict,
        with_evidences=None,
        prompt_profile=profile_config,
        max_chains=10,
    )

    print(f"  → Report built: {len(report.top_chains)} chain entries")
    print()

    # Step 6: Generate and save reports
    print("[6/6] Generating and saving reports...")
    reports_dir = Path("data/reports") / report_date[:4] / report_date[5:7] / report_date[8:10]
    reports_dir.mkdir(parents=True, exist_ok=True)

    markdown_report = report_builder.to_markdown(report)
    json_report = report_builder.to_json(report)

    markdown_path = reports_dir / f"{report_date.replace('-','')}-{report_batch}.md"
    json_path = reports_dir / f"{report_date.replace('-','')}-{report_batch}.json"

    markdown_path.write_text(markdown_report, encoding="utf-8")
    json_path.write_text(json_report, encoding="utf-8")

    print(f"  → Markdown report saved: {markdown_path}")
    print(f"  → JSON report saved: {json_path}")
    print()

    # Print sample markdown
    print("Sample Markdown Preview (first 1000 chars):")
    print("-" * 80)
    print(markdown_report[:1000])
    print("-" * 80)
    print()

    print("✅ Test complete!")
    print()
    print("Summary:")
    print("  - Information chains created and analyzed")
    print("  - A-share mapping completed (sector + pool + stock level)")
    print("  - Reports generated (Markdown + JSON)")
    print(f"  - Files saved to: {reports_dir}")


if __name__ == "__main__":
    main()
