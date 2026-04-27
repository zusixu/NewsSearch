"""
演示 reports 模块的使用方法
"""

import tempfile
from pathlib import Path

from app.reports import (
    DailyReportBuilder,
    ReportArchiveManager,
    create_report_builder,
    create_archive_manager,
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
from app.analysis.adapters.contracts import (
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    RankingOutput,
    PromptProfile,
    PromptTaskType,
    ModelProviderInfo,
)


def create_test_data():
    """创建测试数据"""
    prompt_profile = PromptProfile(
        profile_name="default",
        task_type=PromptTaskType.INVESTMENT_RANKING,
        version="1.0",
        description="默认分析配置",
    )

    # 创建链分析结果
    chain_results = [
        ChainAnalysisResult(
            chain_id=f"chain-{i}",
            summary=f"AI 技术在 {['医疗', '金融', '制造', '交通', '教育'][i % 5]} 领域的应用取得重大突破。",
            completion_notes="",
            key_entities=("AI", "技术突破"),
            confidence=0.9 - i * 0.1,
            prompt_profile=prompt_profile,
        )
        for i in range(5)
    ]

    # 创建排名结果
    ranking_entries = [
        ChainRankingEntry(
            chain_id=f"chain-{i}",
            rank=i + 1,
            score=100 - i * 20,
            rationale=f"该信息链与投资主题的相关性排名第 {i + 1}。",
        )
        for i in range(5)
    ]
    ranking_output = RankingOutput(
        entries=tuple(ranking_entries),
        prompt_profile=prompt_profile,
    )

    provider_info = ModelProviderInfo(
        provider="demo_provider",
        model_id="demo_model",
        model_version="1.0",
    )

    analysis_response = AnalysisResponse(
        chain_results=tuple(chain_results),
        ranking=ranking_output,
        provider_info=provider_info,
    )

    # 创建 A 股映射
    mappings = {}
    scores = {}

    sector_names = ["人工智能", "金融科技", "智能制造", "智能交通", "在线教育"]
    for i in range(5):
        chain_id = f"chain-{i}"
        sector_mappings = [
            SectorMapping(
                sector_name=sector_names[i],
                chain_segment="上游",
                confidence=ConfidenceLevel.HIGH,
                rationale=f"{sector_names[i]} 行业将直接受益于该技术突破。",
                theme_ids=("ai",),
            ),
        ]
        stock_pool_mappings = [
            StockPoolMapping(
                pool_name=f"{sector_names[i]} 龙头股",
                criteria=f"市值 > 500 亿，{sector_names[i]} 业务占比 > 40%",
                confidence=ConfidenceLevel.MEDIUM,
                rationale=f"行业龙头将最受益于行业增长。",
                sector_name=sector_names[i],
            ),
        ]
        individual_stock_mappings = [
            IndividualStockMapping(
                stock_code=f"{600000 + i}",
                stock_name=f"{sector_names[i]}股份",
                confidence=ConfidenceLevel.MEDIUM,
                rationale=f"该公司是 {sector_names[i]} 行业的领先企业。",
                impact_direction="受益",
                pool_name=f"{sector_names[i]} 龙头股",
            ),
        ]
        mappings[chain_id] = AStockMapping(
            chain_id=chain_id,
            sector_mappings=tuple(sector_mappings),
            stock_pool_mappings=tuple(stock_pool_mappings),
            individual_stock_mappings=tuple(individual_stock_mappings),
            overall_confidence=ConfidenceLevel.MEDIUM,
            summary=f"{sector_names[i]} 行业将受益于 AI 技术突破。",
            generated_at="2025-01-15T08:00:00+00:00",
        )

        dimensions = MappingScoreDimensions(
            theme_match_score=85 - i * 10,
            chain_clarity_score=80 - i * 10,
            confidence_weighted_score=75 - i * 10,
            timeliness_score=90 - i * 10,
            coverage_score=70 - i * 10,
        )
        overall_score = (
            dimensions.theme_match_score
            + dimensions.chain_clarity_score
            + dimensions.confidence_weighted_score
            + dimensions.timeliness_score
            + dimensions.coverage_score
        ) / 5
        scores[chain_id] = AShareMappingScore(
            chain_id=chain_id,
            dimensions=dimensions,
            overall_score=overall_score,
            score_level=AShareMappingScore.score_level_from_score(overall_score),
            rationale=f"主题匹配度高，产业链清晰。",
            scored_at="2025-01-15T08:00:00+00:00",
        )

    return analysis_response, mappings, scores


def main():
    """主函数"""
    print("=== 日报输出模块演示 ===\n")

    # 创建测试数据
    print("1. 创建测试数据...")
    analysis_response, mappings, scores = create_test_data()

    # 构建日报
    print("2. 构建日报...")
    builder = create_report_builder()
    report = builder.build(
        report_date="2025-01-15",
        report_batch="pre-market",
        analysis_response=analysis_response,
        mappings=mappings,
        scores=scores,
        prompt_profile=analysis_response.ranking.prompt_profile,
    )

    # 生成 Markdown
    print("3. 生成 Markdown 报告...")
    markdown = builder.to_markdown(report)
    print("\n=== Markdown 报告预览 ===\n")
    print(markdown[:1000] + "..." if len(markdown) > 1000 else markdown)

    # 生成 JSON
    print("\n4. 生成 JSON 报告...")
    json_str = builder.to_json(report)
    print("\n=== JSON 报告预览 ===\n")
    print(json_str[:500] + "..." if len(json_str) > 500 else json_str)

    # 保存报告
    print("\n5. 保存报告到临时目录...")
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"   临时目录: {tmpdir}")
        manager = create_archive_manager(tmpdir)
        saved_paths = manager.save_report(report, save_markdown=True, save_json=True)

        print(f"   Markdown 报告: {saved_paths['markdown']}")
        print(f"   JSON 报告: {saved_paths['json']}")

        # 列出报告
        reports = manager.list_reports()
        print(f"   报告文件数: {len(reports)}")

    print("\n=== 演示完成 ===")


if __name__ == "__main__":
    main()
