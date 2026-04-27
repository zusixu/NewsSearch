"""
测试日报输出模块。
"""

import datetime
import json
import pytest
from unittest import mock

from app.mapping.report import (
    DailyReportHeader,
    DailyReportChainEntry,
    DailyReport,
    MarkdownReportGenerator,
    JsonReportGenerator,
    DailyReportBuilder,
    create_report_builder,
    generate_markdown_report,
    generate_json_report,
)
from app.mapping.schema import (
    AStockMapping,
    SectorMapping,
    StockPoolMapping,
    IndividualStockMapping,
    ConfidenceLevel,
    MappingScoreDimensions,
    AShareMappingScore,
)
from app.mapping.engine import create_mapping_engine, create_scoring_engine
from app.chains.chain import InformationChain, build_chain
from app.entity.tagged_output import TaggedOutput, build_tagged_output
from app.entity.rules.extractor import Hit
from app.entity.evidence import EvidenceLink, EvidenceSpan, build_evidence_links
from app.models.event_draft import EventDraft
from app.models.news_item import NewsItem
from app.models.raw_document import RawDocument


def create_test_raw_document() -> RawDocument:
    """创建测试用的 RawDocument。"""
    return RawDocument(
        source="test_source",
        provider="test_provider",
        title="AI 芯片需求大幅增长",
        content="随着人工智能技术的快速发展，AI 芯片需求大幅增长。GPU、存储等板块受益明显。",
        url=None,
        date="2025-01-15",
    )


def _make_hit(matched_text: str, start: int, end: int, kind: str, label_id: str) -> Hit:
    """创建测试 Hit。"""
    return Hit(
        matched_text=matched_text,
        start=start,
        end=end,
        matched_seed=matched_text,
        kind=kind,  # type: ignore[arg-type]
        label_id=label_id,
    )


def create_test_tagged_output() -> TaggedOutput:
    """创建测试用的 TaggedOutput。"""
    raw = create_test_raw_document()
    news = NewsItem.from_raw(raw)
    event = EventDraft.from_news_item(news)

    text = "AI 芯片需求大幅增长，GPU、存储等板块受益。"
    hits = [
        _make_hit("AI", 0, 2, "theme", "ai"),
        _make_hit("GPU", 12, 15, "theme", "gpu"),
        _make_hit("存储", 17, 19, "theme", "storage"),
    ]
    links = build_evidence_links(text, hits, context_window=0)

    return build_tagged_output(
        event=event,
        text=text,
        evidence_links=links,
    )


def create_test_information_chain() -> InformationChain:
    """创建测试用的 InformationChain。"""
    tagged = create_test_tagged_output()
    return build_chain(
        chain_id="test-chain-12345",
        tagged_outputs=[tagged],
    )


def create_test_mapping() -> AStockMapping:
    """创建测试用的 AStockMapping。"""
    chain = create_test_information_chain()
    engine = create_mapping_engine()
    return engine.map_information_chain(chain)


def create_test_score(mapping: AStockMapping) -> AShareMappingScore:
    """创建测试用的 AShareMappingScore。"""
    engine = create_scoring_engine()
    return engine.score_mapping(mapping)


class TestDailyReportDataStructures:
    """测试日报数据结构。"""

    def test_daily_report_header_creation(self) -> None:
        """测试创建日报头部。"""
        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at="2025-01-15T00:30:00Z",
            prompt_profile="default",
            prompt_version="1.0",
        )

        assert header.report_date == "2025-01-15"
        assert header.report_batch == "pre-market"
        assert header.generated_at == "2025-01-15T00:30:00Z"
        assert header.prompt_profile == "default"
        assert header.prompt_version == "1.0"

    def test_daily_report_chain_entry_creation(self) -> None:
        """测试创建信息链条目。"""
        mapping = create_test_mapping()
        score = create_test_score(mapping)

        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长，相关板块受益。",
            confidence=0.85,
            a_share_mapping=mapping,
            a_share_score=score,
        )

        assert entry.chain_id == "test-chain-12345"
        assert entry.rank == 1
        assert entry.title == "AI 芯片需求增长"
        assert entry.confidence == 0.85
        assert entry.a_share_mapping is mapping
        assert entry.a_share_score is score

    def test_daily_report_creation(self) -> None:
        """测试创建完整日报。"""
        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at="2025-01-15T00:30:00Z",
        )

        mapping = create_test_mapping()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            summary="今日共 1 条信息链。",
        )

        assert report.header is header
        assert len(report.top_chains) == 1
        assert report.top_chains[0] is entry


class TestMarkdownReportGenerator:
    """测试 Markdown 报告生成器。"""

    def test_generate_markdown_header(self) -> None:
        """测试生成 Markdown 头部。"""
        generator = MarkdownReportGenerator()

        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at="2025-01-15T00:30:00+00:00",
        )

        lines = generator._render_header(header)
        markdown = "\n".join(lines)

        assert "# 每日 AI 投资资讯 - 2025-01-15" in markdown
        assert "开盘前批次" in markdown
        assert "生成时间" in markdown

    def test_generate_markdown_overview(self) -> None:
        """测试生成 Markdown 总览。"""
        generator = MarkdownReportGenerator()

        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at="2025-01-15T00:30:00+00:00",
        )

        mapping = create_test_mapping()
        score = create_test_score(mapping)
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
            a_share_score=score,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            summary="今日共 1 条信息链。",
        )

        lines = generator._render_overview(report)
        markdown = "\n".join(lines)

        assert "今日概览" in markdown
        assert "今日 TOP 10 摘要" in markdown

    def test_generate_complete_markdown(self) -> None:
        """测试生成完整 Markdown 报告。"""
        generator = MarkdownReportGenerator()

        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        mapping = create_test_mapping()
        score = create_test_score(mapping)
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
            a_share_score=score,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            summary="今日共 1 条信息链。",
        )

        markdown = generator.generate(report)

        assert "# 每日 AI 投资资讯" in markdown
        assert "今日概览" in markdown
        assert "今日 TOP 10 信息链详情" in markdown
        assert "A 股映射" in markdown
        assert "行业/板块映射" in markdown
        assert "可映射性评分详情" in markdown


class TestJsonReportGenerator:
    """测试 JSON 报告生成器。"""

    def test_generate_json_dict(self) -> None:
        """测试生成 JSON 字典。"""
        generator = JsonReportGenerator()

        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        mapping = create_test_mapping()
        score = create_test_score(mapping)
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
            a_share_score=score,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            summary="今日共 1 条信息链。",
        )

        report_dict = generator.generate_dict(report)

        assert "header" in report_dict
        assert "summary" in report_dict
        assert "top_chains" in report_dict
        assert report_dict["header"]["report_date"] == "2025-01-15"
        assert len(report_dict["top_chains"]) == 1

    def test_generate_json_string(self) -> None:
        """测试生成 JSON 字符串。"""
        generator = JsonReportGenerator()

        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        mapping = create_test_mapping()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            summary="今日共 1 条信息链。",
        )

        json_str = generator.generate(report)
        report_dict = json.loads(json_str)

        assert "header" in report_dict
        assert report_dict["header"]["report_date"] == "2025-01-15"

    def test_json_includes_a_share_mapping(self) -> None:
        """测试 JSON 包含 A 股映射数据。"""
        generator = JsonReportGenerator()

        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        mapping = create_test_mapping()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            summary="今日共 1 条信息链。",
        )

        report_dict = generator.generate_dict(report)
        chain_data = report_dict["top_chains"][0]

        assert "a_share_mapping" in chain_data
        assert "sector_mappings" in chain_data["a_share_mapping"]
        assert "stock_pool_mappings" in chain_data["a_share_mapping"]
        assert "individual_stock_mappings" in chain_data["a_share_mapping"]

    def test_json_includes_a_share_score(self) -> None:
        """测试 JSON 包含 A 股评分数据。"""
        generator = JsonReportGenerator()

        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        mapping = create_test_mapping()
        score = create_test_score(mapping)
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
            a_share_score=score,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            summary="今日共 1 条信息链。",
        )

        report_dict = generator.generate_dict(report)
        chain_data = report_dict["top_chains"][0]

        assert "a_share_score" in chain_data
        assert "overall_score" in chain_data["a_share_score"]
        assert "dimensions" in chain_data["a_share_score"]


class TestDailyReportBuilder:
    """测试日报构建器。"""

    def test_build_report(self) -> None:
        """测试构建日报。"""
        builder = DailyReportBuilder()

        mapping = create_test_mapping()
        score = create_test_score(mapping)
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
            a_share_score=score,
        )

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            chains_with_mappings=[entry],
            prompt_profile="default",
            prompt_version="1.0",
        )

        assert report.header.report_date == "2025-01-15"
        assert report.header.report_batch == "pre-market"
        assert report.header.prompt_profile == "default"
        assert report.header.prompt_version == "1.0"
        assert len(report.top_chains) == 1

    def test_to_markdown(self) -> None:
        """测试转换为 Markdown。"""
        builder = DailyReportBuilder()

        mapping = create_test_mapping()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
        )

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            chains_with_mappings=[entry],
        )

        markdown = builder.to_markdown(report)

        assert "# 每日 AI 投资资讯" in markdown
        assert "A 股映射" in markdown

    def test_to_json(self) -> None:
        """测试转换为 JSON。"""
        builder = DailyReportBuilder()

        mapping = create_test_mapping()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
        )

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            chains_with_mappings=[entry],
        )

        json_str = builder.to_json(report)
        report_dict = json.loads(json_str)

        assert "header" in report_dict
        assert report_dict["header"]["report_date"] == "2025-01-15"

    def test_build_summary(self) -> None:
        """测试构建日报摘要。"""
        builder = DailyReportBuilder()

        mapping = create_test_mapping()
        score = create_test_score(mapping)
        entries = [
            DailyReportChainEntry(
                chain_id=f"test-chain-{i}",
                rank=i + 1,
                title=f"测试标题 {i}",
                summary="测试摘要",
                confidence=0.7 + i * 0.05,
                a_share_mapping=mapping,
                a_share_score=score,
            )
            for i in range(3)
        ]

        summary = builder._build_summary(entries)

        assert "3 条" in summary
        assert "AI" in summary  # 应该提到 AI 板块


class TestConvenienceFunctions:
    """测试便捷函数。"""

    def test_create_report_builder(self) -> None:
        """测试创建报告构建器。"""
        builder = create_report_builder()
        assert isinstance(builder, DailyReportBuilder)

    def test_generate_markdown_report(self) -> None:
        """测试生成 Markdown 报告便捷函数。"""
        mapping = create_test_mapping()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
        )

        builder = create_report_builder()
        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            chains_with_mappings=[entry],
        )

        markdown = generate_markdown_report(report)
        assert "# 每日 AI 投资资讯" in markdown

    def test_generate_json_report(self) -> None:
        """测试生成 JSON 报告便捷函数。"""
        mapping = create_test_mapping()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
        )

        builder = create_report_builder()
        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            chains_with_mappings=[entry],
        )

        json_str = generate_json_report(report)
        report_dict = json.loads(json_str)
        assert "header" in report_dict


class TestMarkdownHelperMethods:
    """测试 Markdown 辅助方法。"""

    def test_confidence_str(self) -> None:
        """测试置信度转字符串。"""
        generator = MarkdownReportGenerator()
        assert generator._confidence_str(ConfidenceLevel.HIGH) == "高"
        assert generator._confidence_str(ConfidenceLevel.MEDIUM) == "中"
        assert generator._confidence_str(ConfidenceLevel.LOW) == "低"

    def test_score_level_desc(self) -> None:
        """测试评分等级描述。"""
        generator = MarkdownReportGenerator()
        assert generator._score_level_desc("excellent") == "优秀"
        assert generator._score_level_desc("good") == "良好"
        assert generator._score_level_desc("fair") == "一般"
        assert generator._score_level_desc("poor") == "较差"

    def test_score_level_str(self) -> None:
        """测试评分等级字符串。"""
        generator = MarkdownReportGenerator()
        mapping = create_test_mapping()
        score = create_test_score(mapping)

        assert generator._score_level_str(score) in ["excellent", "good", "fair", "poor"]
        assert generator._score_level_str(None) == "-"


class TestEdgeCases:
    """测试边缘情况。"""

    def test_empty_report(self) -> None:
        """测试空报告。"""
        builder = DailyReportBuilder()

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            chains_with_mappings=[],
        )

        assert "暂无可关注" in report.summary

        markdown = builder.to_markdown(report)
        assert "# 每日 AI 投资资讯" in markdown

        json_str = builder.to_json(report)
        report_dict = json.loads(json_str)
        assert len(report_dict["top_chains"]) == 0

    def test_report_without_scores(self) -> None:
        """测试没有评分的报告。"""
        builder = DailyReportBuilder()

        mapping = create_test_mapping()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            a_share_mapping=mapping,
            a_share_score=None,
        )

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            chains_with_mappings=[entry],
        )

        markdown = builder.to_markdown(report)
        assert "A 股映射" in markdown

        json_str = builder.to_json(report)
        report_dict = json.loads(json_str)
        assert "a_share_score" not in report_dict["top_chains"][0]
