"""
测试日报输出模块（app.reports）。
"""

import datetime
import json
import pytest
import tempfile
from unittest import mock
from pathlib import Path

from app.reports.core import (
    DailyReportHeader,
    DailyReportChainEntry,
    DailyReport,
    RiskWarning,
    MarkdownReportGenerator,
    JsonReportGenerator,
    DailyReportBuilder,
    ReportArchiveManager,
    create_report_builder,
    create_archive_manager,
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
    AShareMappingWithEvidence,
    MappingEvidence,
    EvidenceSourceReference,
    EvidenceSnippetReference,
)
from app.analysis.adapters.contracts import (
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    RankingOutput,
    PromptProfile,
    PromptTaskType,
    ModelProviderInfo,
)


def create_test_mapping(chain_id: str = "test-chain-12345") -> AStockMapping:
    """创建测试用的 AStockMapping。"""
    sector_mappings = [
        SectorMapping(
            sector_name="AI 芯片",
            chain_segment="上游",
            confidence=ConfidenceLevel.HIGH,
            rationale="AI 芯片需求大幅增长，相关板块受益。",
            theme_ids=("ai", "gpu"),
        ),
    ]
    stock_pool_mappings = [
        StockPoolMapping(
            pool_name="算力设备商",
            criteria="市值 > 100 亿，AI 芯片相关业务占比 > 30%",
            confidence=ConfidenceLevel.MEDIUM,
            rationale="受益于 AI 芯片需求增长。",
            sector_name="AI 芯片",
        ),
    ]
    individual_stock_mappings = [
        IndividualStockMapping(
            stock_code="600519",
            stock_name="贵州茅台",
            confidence=ConfidenceLevel.LOW,
            rationale="虽然不直接相关，但市场情绪可能带动。",
            impact_direction="中性",
            pool_name="算力设备商",
            notes="需进一步验证",
        ),
    ]
    return AStockMapping(
        chain_id=chain_id,
        sector_mappings=tuple(sector_mappings),
        stock_pool_mappings=tuple(stock_pool_mappings),
        individual_stock_mappings=tuple(individual_stock_mappings),
        overall_confidence=ConfidenceLevel.MEDIUM,
        summary="AI 芯片需求增长，相关板块有望受益。",
        generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )


def create_test_score(chain_id: str = "test-chain-12345") -> AShareMappingScore:
    """创建测试用的 AShareMappingScore。"""
    dimensions = MappingScoreDimensions(
        theme_match_score=80.0,
        chain_clarity_score=70.0,
        confidence_weighted_score=65.0,
        timeliness_score=75.0,
        coverage_score=60.0,
    )
    return AShareMappingScore(
        chain_id=chain_id,
        dimensions=dimensions,
        overall_score=70.0,
        score_level="good",
        rationale="主题匹配度高，产业链清晰，时效性好。",
        scored_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )


def create_test_analysis_response() -> AnalysisResponse:
    """创建测试用的 AnalysisResponse。"""
    prompt_profile = PromptProfile(
        profile_name="default",
        task_type=PromptTaskType.INVESTMENT_RANKING,
        version="1.0",
        description="默认分析配置",
    )

    # 链分析结果
    chain_results = [
        ChainAnalysisResult(
            chain_id=f"test-chain-{i}",
            summary=f"这是第 {i+1} 条信息链的摘要内容，描述了相关事件。",
            completion_notes="",
            key_entities=("AI", "芯片"),
            confidence=0.7 - i * 0.05,
            prompt_profile=prompt_profile,
        )
        for i in range(10)
    ]

    # 排名结果
    ranking_entries = [
        ChainRankingEntry(
            chain_id=f"test-chain-{i}",
            rank=i + 1,
            score=100.0 - i * 10.0,
            rationale=f"这条信息链排名第 {i+1}，因为相关性高。",
        )
        for i in range(10)
    ]
    ranking_output = RankingOutput(
        entries=tuple(ranking_entries),
        prompt_profile=prompt_profile,
    )

    provider_info = ModelProviderInfo(
        provider="test_provider",
        model_id="test_model",
        model_version="1.0",
        endpoint="",
    )

    return AnalysisResponse(
        chain_results=tuple(chain_results),
        ranking=ranking_output,
        provider_info=provider_info,
    )


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

    def test_daily_report_header_invalid_batch(self) -> None:
        """测试无效的报告批次。"""
        with pytest.raises(ValueError):
            DailyReportHeader(
                report_date="2025-01-15",
                report_batch="invalid-batch",
                generated_at="2025-01-15T00:30:00Z",
            )

    def test_risk_warning_creation(self) -> None:
        """测试创建风险提示。"""
        warning = RiskWarning(
            risk_type="置信度提示",
            severity="medium",
            message="这条信息链的置信度较低。",
            related_chain_id="test-chain-12345",
            related_stock_code="600519",
        )

        assert warning.risk_type == "置信度提示"
        assert warning.severity == "medium"
        assert warning.message == "这条信息链的置信度较低。"
        assert warning.related_chain_id == "test-chain-12345"
        assert warning.related_stock_code == "600519"

    def test_risk_warning_invalid_type(self) -> None:
        """测试无效的风险类型。"""
        with pytest.raises(ValueError):
            RiskWarning(
                risk_type="无效类型",
                severity="medium",
                message="测试消息",
            )

    def test_daily_report_chain_entry_creation(self) -> None:
        """测试创建信息链条目。"""
        mapping = create_test_mapping()
        score = create_test_score()

        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长，相关板块受益。",
            confidence=0.85,
            rationale="排名第一是因为相关性最高。",
            a_share_mapping=mapping,
            a_share_score=score,
        )

        assert entry.chain_id == "test-chain-12345"
        assert entry.rank == 1
        assert entry.title == "AI 芯片需求增长"
        assert entry.confidence == 0.85
        assert entry.rationale == "排名第一是因为相关性最高。"
        assert entry.a_share_mapping is mapping
        assert entry.a_share_score is score

    def test_daily_report_chain_entry_invalid_rank(self) -> None:
        """测试无效的排名。"""
        mapping = create_test_mapping()
        with pytest.raises(ValueError):
            DailyReportChainEntry(
                chain_id="test-chain-12345",
                rank=0,
                title="测试",
                summary="测试",
                confidence=0.5,
                rationale="测试",
                a_share_mapping=mapping,
            )

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
            rationale="相关性高。",
            a_share_mapping=mapping,
        )

        warning = RiskWarning(
            risk_type="置信度提示",
            severity="high",
            message="测试风险提示。",
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            risk_warnings=[warning],
            summary="今日共 1 条信息链。",
        )

        assert report.header is header
        assert len(report.top_chains) == 1
        assert len(report.risk_warnings) == 1


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
        assert "开盘前" in markdown
        assert "生成时间" in markdown

    def test_generate_markdown_risk_warnings(self) -> None:
        """测试生成 Markdown 风险提示。"""
        generator = MarkdownReportGenerator()

        warnings = [
            RiskWarning(
                risk_type="置信度提示",
                severity="high",
                message="高风险提示消息。",
            ),
            RiskWarning(
                risk_type="估值提示",
                severity="medium",
                message="中等风险提示消息。",
            ),
        ]

        lines = generator._render_risk_warnings(warnings)
        markdown = "\n".join(lines)

        assert "风险提示" in markdown
        assert "置信度提示" in markdown
        assert "估值提示" in markdown
        assert "🔴" in markdown
        assert "🟡" in markdown

    def test_generate_markdown_overview(self) -> None:
        """测试生成 Markdown 总览。"""
        generator = MarkdownReportGenerator()

        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at="2025-01-15T00:30:00+00:00",
        )

        mapping = create_test_mapping()
        score = create_test_score()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            rationale="相关性高。",
            a_share_mapping=mapping,
            a_share_score=score,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            risk_warnings=[],
            summary="今日共 1 条信息链。",
        )

        lines = generator._render_overview(report)
        markdown = "\n".join(lines)

        assert "今日概览" in markdown
        assert "今日 TOP 10 信息链" in markdown

    def test_generate_complete_markdown(self) -> None:
        """测试生成完整 Markdown 报告。"""
        generator = MarkdownReportGenerator()

        header = DailyReportHeader(
            report_date="2025-01-15",
            report_batch="pre-market",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        mapping = create_test_mapping()
        score = create_test_score()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            rationale="相关性高。",
            a_share_mapping=mapping,
            a_share_score=score,
        )

        warning = RiskWarning(
            risk_type="置信度提示",
            severity="medium",
            message="测试风险提示。",
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            risk_warnings=[warning],
            summary="今日共 1 条信息链。",
        )

        markdown = generator.generate(report)

        assert "# 每日 AI 投资资讯" in markdown
        assert "今日概览" in markdown
        assert "风险提示" in markdown
        assert "今日 TOP 10 信息链详情" in markdown
        assert "A 股映射" in markdown
        assert "行业/板块映射" in markdown
        assert "可映射性评分详情" in markdown
        assert "免责声明" in markdown


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
        score = create_test_score()
        entry = DailyReportChainEntry(
            chain_id="test-chain-12345",
            rank=1,
            title="AI 芯片需求增长",
            summary="AI 芯片需求大幅增长。",
            confidence=0.85,
            rationale="相关性高。",
            a_share_mapping=mapping,
            a_share_score=score,
        )

        warning = RiskWarning(
            risk_type="置信度提示",
            severity="medium",
            message="测试风险。",
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            risk_warnings=[warning],
            summary="今日共 1 条信息链。",
        )

        report_dict = generator.generate_dict(report)

        assert "header" in report_dict
        assert "summary" in report_dict
        assert "risk_warnings" in report_dict
        assert "top_chains" in report_dict
        assert report_dict["header"]["report_date"] == "2025-01-15"
        assert len(report_dict["top_chains"]) == 1
        assert len(report_dict["risk_warnings"]) == 1

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
            rationale="相关性高。",
            a_share_mapping=mapping,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            risk_warnings=[],
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
            rationale="相关性高。",
            a_share_mapping=mapping,
        )

        report = DailyReport(
            header=header,
            top_chains=[entry],
            risk_warnings=[],
            summary="今日共 1 条信息链。",
        )

        report_dict = generator.generate_dict(report)
        chain_data = report_dict["top_chains"][0]

        assert "a_share_mapping" in chain_data
        assert "sector_mappings" in chain_data["a_share_mapping"]
        assert "stock_pool_mappings" in chain_data["a_share_mapping"]
        assert "individual_stock_mappings" in chain_data["a_share_mapping"]

    def test_json_includes_risk_warnings(self) -> None:
        """测试 JSON 包含风险提示数据。"""
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
            rationale="相关性高。",
            a_share_mapping=mapping,
        )

        warnings = [
            RiskWarning(
                risk_type="置信度提示",
                severity="high",
                message="测试风险 1",
            ),
            RiskWarning(
                risk_type="估值提示",
                severity="medium",
                message="测试风险 2",
            ),
        ]

        report = DailyReport(
            header=header,
            top_chains=[entry],
            risk_warnings=warnings,
            summary="今日共 1 条信息链。",
        )

        report_dict = generator.generate_dict(report)
        assert len(report_dict["risk_warnings"]) == 2
        assert report_dict["risk_warnings"][0]["risk_type"] == "置信度提示"
        assert report_dict["risk_warnings"][1]["severity"] == "medium"


class TestDailyReportBuilder:
    """测试日报构建器。"""

    def test_build_report_from_analysis_response(self) -> None:
        """测试从 AnalysisResponse 构建日报。"""
        builder = DailyReportBuilder()

        analysis_response = create_test_analysis_response()

        # 创建映射字典
        mappings = {}
        scores = {}
        for i in range(10):
            chain_id = f"test-chain-{i}"
            mappings[chain_id] = create_test_mapping(chain_id)
            scores[chain_id] = create_test_score(chain_id)

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            analysis_response=analysis_response,
            mappings=mappings,
            scores=scores,
        )

        assert report.header.report_date == "2025-01-15"
        assert report.header.report_batch == "pre-market"
        assert len(report.top_chains) == 10
        assert len(report.risk_warnings) > 0

    def test_build_report_with_missing_mappings(self) -> None:
        """测试构建报告时缺少映射。"""
        builder = DailyReportBuilder()

        analysis_response = create_test_analysis_response()

        # 只创建部分映射
        mappings = {}
        for i in range(5):
            chain_id = f"test-chain-{i}"
            mappings[chain_id] = create_test_mapping(chain_id)

        report = builder.build(
            report_date="2025-01-15",
            report_batch="midday",
            analysis_response=analysis_response,
            mappings=mappings,
        )

        assert len(report.top_chains) == 10
        # 缺少映射的应该会创建默认映射

    def test_build_summary(self) -> None:
        """测试构建日报摘要。"""
        builder = DailyReportBuilder()

        mapping = create_test_mapping()
        score = create_test_score()
        entries = [
            DailyReportChainEntry(
                chain_id=f"test-chain-{i}",
                rank=i + 1,
                title=f"测试标题 {i}",
                summary="测试摘要",
                confidence=0.7 + i * 0.05,
                rationale=f"理由 {i}",
                a_share_mapping=mapping,
                a_share_score=score,
            )
            for i in range(3)
        ]

        summary = builder._build_summary(entries)

        assert "3 条" in summary
        assert "AI 芯片" in summary

    def test_extract_title(self) -> None:
        """测试提取标题。"""
        builder = DailyReportBuilder()

        assert builder._extract_title("这是第一句话。这是第二句话。") == "这是第一句话"
        assert builder._extract_title("这是一个很长的句子，超过了六十个字符，会被截断。") is not None
        assert len(builder._extract_title("这是一个很长的句子，超过了六十个字符，会被截断。")) <= 63  # 60 + ...
        assert builder._extract_title("") == "无标题"

    def test_build_risk_warnings(self) -> None:
        """测试构建风险提示。"""
        builder = DailyReportBuilder()

        mapping = create_test_mapping()
        score = create_test_score()

        # 低置信度的条目
        low_conf_entry = DailyReportChainEntry(
            chain_id="test-chain-low",
            rank=2,
            title="低置信度标题",
            summary="低置信度摘要",
            confidence=0.3,
            rationale="低置信度理由",
            a_share_mapping=mapping,
            a_share_score=score,
        )

        warnings = builder._build_risk_warnings([low_conf_entry])

        assert len(warnings) > 0
        # 应该包含置信度提示
        risk_types = [w.risk_type for w in warnings]
        assert "置信度提示" in risk_types
        assert "其他风险" in risk_types

    def test_to_markdown(self) -> None:
        """测试转换为 Markdown。"""
        builder = DailyReportBuilder()

        analysis_response = create_test_analysis_response()
        mappings = {}
        for i in range(10):
            chain_id = f"test-chain-{i}"
            mappings[chain_id] = create_test_mapping(chain_id)

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            analysis_response=analysis_response,
            mappings=mappings,
        )

        markdown = builder.to_markdown(report)

        assert "# 每日 AI 投资资讯" in markdown
        assert "A 股映射" in markdown

    def test_to_json(self) -> None:
        """测试转换为 JSON。"""
        builder = DailyReportBuilder()

        analysis_response = create_test_analysis_response()
        mappings = {}
        for i in range(10):
            chain_id = f"test-chain-{i}"
            mappings[chain_id] = create_test_mapping(chain_id)

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            analysis_response=analysis_response,
            mappings=mappings,
        )

        json_str = builder.to_json(report)
        report_dict = json.loads(json_str)

        assert "header" in report_dict
        assert report_dict["header"]["report_date"] == "2025-01-15"


class TestReportArchiveManager:
    """测试报告归档管理器。"""

    def test_get_report_path(self) -> None:
        """测试获取报告路径。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ReportArchiveManager(tmpdir)

            md_path = manager.get_report_path(
                report_date="2025-01-15",
                report_batch="pre-market",
                extension="md",
            )

            assert "2025" in str(md_path)
            assert "01" in str(md_path)
            assert "15" in str(md_path)
            assert "20250115-pre-market.md" in str(md_path)

    def test_save_report(self) -> None:
        """测试保存报告。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ReportArchiveManager(tmpdir)
            builder = DailyReportBuilder()

            analysis_response = create_test_analysis_response()
            mappings = {}
            for i in range(3):
                chain_id = f"test-chain-{i}"
                mappings[chain_id] = create_test_mapping(chain_id)

            report = builder.build(
                report_date="2025-01-15",
                report_batch="pre-market",
                analysis_response=analysis_response,
                mappings=mappings,
            )

            saved_paths = manager.save_report(report, save_markdown=True, save_json=True)

            assert "markdown" in saved_paths
            assert "json" in saved_paths
            assert saved_paths["markdown"].exists()
            assert saved_paths["json"].exists()

            # 验证文件内容
            md_content = saved_paths["markdown"].read_text(encoding="utf-8")
            assert "# 每日 AI 投资资讯" in md_content

    def test_list_reports(self) -> None:
        """测试列出历史报告。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ReportArchiveManager(tmpdir)
            builder = DailyReportBuilder()

            # 保存几个测试报告
            analysis_response = create_test_analysis_response()
            mappings = {}
            for i in range(3):
                chain_id = f"test-chain-{i}"
                mappings[chain_id] = create_test_mapping(chain_id)

            report1 = builder.build(
                report_date="2025-01-15",
                report_batch="pre-market",
                analysis_response=analysis_response,
                mappings=mappings,
            )
            report2 = builder.build(
                report_date="2025-01-15",
                report_batch="midday",
                analysis_response=analysis_response,
                mappings=mappings,
            )
            report3 = builder.build(
                report_date="2025-01-16",
                report_batch="pre-market",
                analysis_response=analysis_response,
                mappings=mappings,
            )

            manager.save_report(report1)
            manager.save_report(report2)
            manager.save_report(report3)

            # 列出所有报告
            all_reports = manager.list_reports()
            assert len(all_reports) == 3

            # 只列出 pre-market 批次
            premarket_reports = manager.list_reports(batch="pre-market")
            assert len(premarket_reports) == 2

            # 日期过滤
            date_reports = manager.list_reports(start_date="2025-01-15", end_date="2025-01-15")
            assert len(date_reports) == 2


class TestConvenienceFunctions:
    """测试便捷函数。"""

    def test_create_report_builder(self) -> None:
        """测试创建报告构建器。"""
        builder = create_report_builder()
        assert isinstance(builder, DailyReportBuilder)

    def test_create_archive_manager(self) -> None:
        """测试创建归档管理器。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = create_archive_manager(tmpdir)
            assert isinstance(manager, ReportArchiveManager)

    def test_generate_markdown_report(self) -> None:
        """测试生成 Markdown 报告便捷函数。"""
        builder = DailyReportBuilder()
        analysis_response = create_test_analysis_response()
        mappings = {}
        for i in range(3):
            chain_id = f"test-chain-{i}"
            mappings[chain_id] = create_test_mapping(chain_id)

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            analysis_response=analysis_response,
            mappings=mappings,
        )

        markdown = generate_markdown_report(report)
        assert "# 每日 AI 投资资讯" in markdown

    def test_generate_json_report(self) -> None:
        """测试生成 JSON 报告便捷函数。"""
        builder = DailyReportBuilder()
        analysis_response = create_test_analysis_response()
        mappings = {}
        for i in range(3):
            chain_id = f"test-chain-{i}"
            mappings[chain_id] = create_test_mapping(chain_id)

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            analysis_response=analysis_response,
            mappings=mappings,
        )

        json_str = generate_json_report(report)
        report_dict = json.loads(json_str)
        assert "header" in report_dict


class TestEdgeCases:
    """测试边缘情况。"""

    def test_empty_report(self) -> None:
        """测试空报告。"""
        builder = DailyReportBuilder()

        # 创建一个只有空排名的 analysis response
        prompt_profile = PromptProfile(
            profile_name="default",
            task_type=PromptTaskType.INVESTMENT_RANKING,
            version="1.0",
        )
        ranking_output = RankingOutput(
            entries=(),
            prompt_profile=prompt_profile,
        )
        provider_info = ModelProviderInfo(
            provider="test",
            model_id="test",
            model_version="1.0",
        )
        analysis_response = AnalysisResponse(
            chain_results=(),
            ranking=ranking_output,
            provider_info=provider_info,
        )

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            analysis_response=analysis_response,
            mappings={},
        )

        assert len(report.top_chains) == 0

        markdown = builder.to_markdown(report)
        assert "# 每日 AI 投资资讯" in markdown

        json_str = builder.to_json(report)
        report_dict = json.loads(json_str)
        assert len(report_dict["top_chains"]) == 0

    def test_report_without_scores(self) -> None:
        """测试没有评分的报告。"""
        builder = DailyReportBuilder()

        analysis_response = create_test_analysis_response()
        mappings = {}
        for i in range(3):
            chain_id = f"test-chain-{i}"
            mappings[chain_id] = create_test_mapping(chain_id)

        report = builder.build(
            report_date="2025-01-15",
            report_batch="pre-market",
            analysis_response=analysis_response,
            mappings=mappings,
            scores=None,
        )

        markdown = builder.to_markdown(report)
        assert "A 股映射" in markdown

        json_str = builder.to_json(report)
        report_dict = json.loads(json_str)
        # 不包含评分的条目不应该有 a_share_score 字段
        if report_dict["top_chains"]:
            assert "a_share_score" not in report_dict["top_chains"][0]

    def test_markdown_helper_methods(self) -> None:
        """测试 Markdown 辅助方法。"""
        generator = MarkdownReportGenerator()

        assert generator._confidence_str(ConfidenceLevel.HIGH) == "高"
        assert generator._confidence_str(ConfidenceLevel.MEDIUM) == "中"
        assert generator._confidence_str(ConfidenceLevel.LOW) == "低"

        assert generator._score_level_desc("excellent") == "优秀"
        assert generator._score_level_desc("good") == "良好"
        assert generator._score_level_desc("fair") == "一般"
        assert generator._score_level_desc("poor") == "较差"

        score = create_test_score()
        assert generator._score_level_str(score) in ["优秀", "良好", "一般", "较差"]
        assert generator._score_level_str(None) == "-"
