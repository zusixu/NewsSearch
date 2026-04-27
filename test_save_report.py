"""
测试保存报告到文件（不打印到控制台，避免编码问题）
"""

import os
from pathlib import Path

from app.reports import DailyReportBuilder, ReportArchiveManager
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


def create_simple_test_data():
    """创建简单的测试数据"""
    prompt_profile = PromptProfile(
        profile_name="default",
        task_type=PromptTaskType.INVESTMENT_RANKING,
        version="1.0",
    )

    # 创建一个链分析结果
    chain_result = ChainAnalysisResult(
        chain_id="chain-001",
        summary="AI 芯片需求大幅增长，GPU 价格上涨。",
        completion_notes="",
        key_entities=("AI", "芯片", "GPU"),
        confidence=0.85,
        prompt_profile=prompt_profile,
    )

    # 创建排名结果
    ranking_entry = ChainRankingEntry(
        chain_id="chain-001",
        rank=1,
        score=95,
        rationale="该信息链与 AI 芯片投资主题高度相关。",
    )
    ranking_output = RankingOutput(
        entries=(ranking_entry,),
        prompt_profile=prompt_profile,
    )

    provider_info = ModelProviderInfo(
        provider="demo",
        model_id="demo-model",
        model_version="1.0",
    )

    analysis_response = AnalysisResponse(
        chain_results=(chain_result,),
        ranking=ranking_output,
        provider_info=provider_info,
    )

    # 创建简单的 A 股映射
    sector_mappings = [
        SectorMapping(
            sector_name="人工智能",
            chain_segment="上游",
            confidence=ConfidenceLevel.HIGH,
            rationale="AI 芯片是人工智能行业的上游核心部件。",
        ),
    ]
    stock_pool_mappings = [
        StockPoolMapping(
            pool_name="AI 芯片龙头",
            criteria="市值 > 300 亿，AI 芯片业务占比 > 30%",
            confidence=ConfidenceLevel.MEDIUM,
            rationale="行业龙头将最受益于芯片需求增长。",
        ),
    ]
    individual_stock_mappings = [
        IndividualStockMapping(
            stock_code="688981",
            stock_name="中芯国际",
            confidence=ConfidenceLevel.MEDIUM,
            rationale="中芯国际是国内领先的芯片制造企业。",
            impact_direction="受益",
        ),
    ]
    mapping = AStockMapping(
        chain_id="chain-001",
        sector_mappings=tuple(sector_mappings),
        stock_pool_mappings=tuple(stock_pool_mappings),
        individual_stock_mappings=tuple(individual_stock_mappings),
        overall_confidence=ConfidenceLevel.MEDIUM,
        summary="AI 芯片需求增长将推动相关企业发展。",
        generated_at="2025-01-15T08:00:00+00:00",
    )

    mappings = {"chain-001": mapping}

    # 创建评分
    dimensions = MappingScoreDimensions(
        theme_match_score=85,
        chain_clarity_score=80,
        confidence_weighted_score=75,
        timeliness_score=90,
        coverage_score=85,
    )
    score = AShareMappingScore(
        chain_id="chain-001",
        dimensions=dimensions,
        overall_score=83,
        score_level="excellent",
        rationale="主题匹配度高，覆盖度好。",
        scored_at="2025-01-15T08:00:00+00:00",
    )
    scores = {"chain-001": score}

    return analysis_response, mappings, scores


def main():
    """主函数"""
    # 创建输出目录
    output_dir = Path("data/reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建测试数据
    analysis_response, mappings, scores = create_simple_test_data()

    # 构建报告
    builder = DailyReportBuilder()
    report = builder.build(
        report_date="2025-01-15",
        report_batch="pre-market",
        analysis_response=analysis_response,
        mappings=mappings,
        scores=scores,
    )

    # 保存报告
    manager = ReportArchiveManager(output_dir)
    saved_paths = manager.save_report(report, save_markdown=True, save_json=True)

    print(f"报告已保存到:")
    print(f"  Markdown: {saved_paths['markdown']}")
    print(f"  JSON: {saved_paths['json']}")


if __name__ == "__main__":
    main()
