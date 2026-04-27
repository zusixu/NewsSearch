"""
测试 A 股可映射性评分功能。
"""

import datetime
import pytest

from app.mapping.schema import (
    ConfidenceLevel,
    SectorMapping,
    StockPoolMapping,
    IndividualStockMapping,
    AStockMapping,
    MappingScoreDimensions,
    AShareMappingScore,
)
from app.mapping.engine import (
    MappingScoringEngine,
    create_scoring_engine,
    score_mapping,
)


# ---------------------------------------------------------------------------
# 测试数据结构
# ---------------------------------------------------------------------------


class TestMappingScoreDimensions:
    """测试 MappingScoreDimensions 数据结构。"""

    def test_create_valid_dimensions(self) -> None:
        """测试创建有效的评分维度。"""
        dimensions = MappingScoreDimensions(
            theme_match_score=85.0,
            chain_clarity_score=75.0,
            confidence_weighted_score=90.0,
            timeliness_score=80.0,
            coverage_score=70.0,
        )
        assert dimensions.theme_match_score == 85.0
        assert dimensions.chain_clarity_score == 75.0
        assert dimensions.confidence_weighted_score == 90.0
        assert dimensions.timeliness_score == 80.0
        assert dimensions.coverage_score == 70.0

    def test_dimension_scores_property(self) -> None:
        """测试 dimension_scores 属性。"""
        dimensions = MappingScoreDimensions(
            theme_match_score=85.0,
            chain_clarity_score=75.0,
            confidence_weighted_score=90.0,
            timeliness_score=80.0,
            coverage_score=70.0,
        )
        scores = dimensions.dimension_scores
        assert scores["theme_match_score"] == 85.0
        assert scores["chain_clarity_score"] == 75.0
        assert scores["confidence_weighted_score"] == 90.0
        assert scores["timeliness_score"] == 80.0
        assert scores["coverage_score"] == 70.0

    def test_invalid_score_raises_error(self) -> None:
        """测试无效的评分值会抛出错误。"""
        with pytest.raises(ValueError, match="theme_match_score"):
            MappingScoreDimensions(
                theme_match_score=101.0,  # 超过 100
                chain_clarity_score=75.0,
                confidence_weighted_score=90.0,
                timeliness_score=80.0,
                coverage_score=70.0,
            )

        with pytest.raises(ValueError, match="coverage_score"):
            MappingScoreDimensions(
                theme_match_score=85.0,
                chain_clarity_score=75.0,
                confidence_weighted_score=90.0,
                timeliness_score=80.0,
                coverage_score=-5.0,  # 小于 0
            )


class TestAShareMappingScore:
    """测试 AShareMappingScore 数据结构。"""

    def test_create_valid_score(self) -> None:
        """测试创建有效的评分。"""
        dimensions = MappingScoreDimensions(
            theme_match_score=85.0,
            chain_clarity_score=75.0,
            confidence_weighted_score=90.0,
            timeliness_score=80.0,
            coverage_score=70.0,
        )
        score = AShareMappingScore(
            chain_id="test-chain-1",
            dimensions=dimensions,
            overall_score=82.5,
            score_level="excellent",
            rationale="测试评分理由",
            scored_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        assert score.chain_id == "test-chain-1"
        assert score.overall_score == 82.5
        assert score.score_level == "excellent"
        assert score.rationale == "测试评分理由"

    def test_score_level_from_score(self) -> None:
        """测试 score_level_from_score 方法。"""
        assert AShareMappingScore.score_level_from_score(90.0) == "excellent"
        assert AShareMappingScore.score_level_from_score(80.0) == "excellent"
        assert AShareMappingScore.score_level_from_score(75.0) == "good"
        assert AShareMappingScore.score_level_from_score(60.0) == "good"
        assert AShareMappingScore.score_level_from_score(50.0) == "fair"
        assert AShareMappingScore.score_level_from_score(40.0) == "fair"
        assert AShareMappingScore.score_level_from_score(30.0) == "poor"
        assert AShareMappingScore.score_level_from_score(0.0) == "poor"

    def test_invalid_score_level_raises_error(self) -> None:
        """测试无效的评分等级会抛出错误。"""
        dimensions = MappingScoreDimensions(
            theme_match_score=85.0,
            chain_clarity_score=75.0,
            confidence_weighted_score=90.0,
            timeliness_score=80.0,
            coverage_score=70.0,
        )
        with pytest.raises(ValueError, match="score_level"):
            AShareMappingScore(
                chain_id="test-chain-1",
                dimensions=dimensions,
                overall_score=82.5,
                score_level="invalid",  # 无效等级
                rationale="测试评分理由",
                scored_at=datetime.datetime.now(datetime.UTC).isoformat(),
            )


# ---------------------------------------------------------------------------
# 测试评分引擎
# ---------------------------------------------------------------------------


class TestMappingScoringEngine:
    """测试 MappingScoringEngine 评分引擎。"""

    def test_create_engine(self) -> None:
        """测试创建评分引擎。"""
        engine = MappingScoringEngine()
        assert engine is not None

    def test_score_empty_mapping(self) -> None:
        """测试评分空映射。"""
        engine = create_scoring_engine()
        mapping = AStockMapping(
            chain_id="test-chain-empty",
            sector_mappings=(),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="空映射",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        score = engine.score_mapping(mapping)
        assert score is not None
        assert score.chain_id == "test-chain-empty"
        assert score.overall_score < 50.0  # 空映射应该得分较低
        assert score.score_level in {"fair", "poor"}

    def test_score_complete_mapping(self) -> None:
        """测试评分完整映射。"""
        engine = create_scoring_engine()

        # 创建完整的映射
        sector_mappings = [
            SectorMapping(
                sector_name="算力",
                chain_segment="上游",
                confidence=ConfidenceLevel.HIGH,
                rationale="算力需求增长",
                theme_ids=("compute",),
            ),
            SectorMapping(
                sector_name="光模块",
                chain_segment="上游",
                confidence=ConfidenceLevel.HIGH,
                rationale="光模块需求增长",
                theme_ids=("optical_module",),
            ),
            SectorMapping(
                sector_name="AI应用",
                chain_segment="下游",
                confidence=ConfidenceLevel.MEDIUM,
                rationale="AI应用落地加速",
                theme_ids=("ai_application",),
            ),
        ]

        stock_pool_mappings = [
            StockPoolMapping(
                pool_name="算力设备商",
                criteria="算力相关收入占比高",
                confidence=ConfidenceLevel.HIGH,
                rationale="受益于算力需求增长",
                sector_name="算力",
            ),
        ]

        individual_stock_mappings = [
            IndividualStockMapping(
                stock_code="000001",
                stock_name="测试股票1",
                confidence=ConfidenceLevel.MEDIUM,
                rationale="属于算力板块",
                impact_direction="受益",
                pool_name="算力设备商",
            ),
            IndividualStockMapping(
                stock_code="000002",
                stock_name="测试股票2",
                confidence=ConfidenceLevel.MEDIUM,
                rationale="属于光模块板块",
                impact_direction="受益",
                pool_name="光模块龙头",
            ),
        ]

        mapping = AStockMapping(
            chain_id="test-chain-complete",
            sector_mappings=tuple(sector_mappings),
            stock_pool_mappings=tuple(stock_pool_mappings),
            individual_stock_mappings=tuple(individual_stock_mappings),
            overall_confidence=ConfidenceLevel.HIGH,
            summary="完整映射测试",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        score = engine.score_mapping(
            mapping,
            theme_ids=("ai", "compute", "optical_module", "ai_application"),
        )

        assert score is not None
        assert score.chain_id == "test-chain-complete"
        assert score.overall_score > 60.0  # 完整映射应该得分较高
        assert score.score_level in {"good", "excellent"}

    def test_score_dimensions_are_populated(self) -> None:
        """测试各评分维度都被正确计算。"""
        engine = create_scoring_engine()

        sector_mappings = [
            SectorMapping(
                sector_name="算力",
                chain_segment="上游",
                confidence=ConfidenceLevel.HIGH,
                rationale="算力需求增长",
                theme_ids=("compute",),
            ),
        ]

        mapping = AStockMapping(
            chain_id="test-chain-dimensions",
            sector_mappings=tuple(sector_mappings),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.MEDIUM,
            summary="维度测试",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        score = engine.score_mapping(mapping, theme_ids=("ai", "compute"))

        # 验证所有维度都有值
        assert score.dimensions.theme_match_score > 0
        assert score.dimensions.chain_clarity_score >= 0
        assert score.dimensions.confidence_weighted_score > 0
        assert score.dimensions.timeliness_score == 80.0  # 默认值
        assert score.dimensions.coverage_score > 0


class TestConvenienceFunctions:
    """测试便捷函数。"""

    def test_create_scoring_engine(self) -> None:
        """测试 create_scoring_engine 函数。"""
        engine = create_scoring_engine()
        assert isinstance(engine, MappingScoringEngine)

    def test_score_mapping_function(self) -> None:
        """测试 score_mapping 便捷函数。"""
        mapping = AStockMapping(
            chain_id="test-chain-func",
            sector_mappings=(),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="测试映射",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        score = score_mapping(mapping)
        assert isinstance(score, AShareMappingScore)
        assert score.chain_id == "test-chain-func"


# ---------------------------------------------------------------------------
# 测试评分维度计算
# ---------------------------------------------------------------------------


class TestScoringDimensions:
    """测试各评分维度的计算逻辑。"""

    def test_theme_match_score_calculation(self) -> None:
        """测试主题匹配度评分计算。"""
        engine = create_scoring_engine()

        # 创建多个主题的映射
        sector_mappings = [
            SectorMapping(
                sector_name="算力",
                chain_segment="上游",
                confidence=ConfidenceLevel.HIGH,
                rationale="算力需求",
                theme_ids=("compute",),
            ),
        ]

        mapping = AStockMapping(
            chain_id="test-theme-match",
            sector_mappings=tuple(sector_mappings),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.MEDIUM,
            summary="主题匹配测试",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        # 测试多个主题
        score = engine.score_mapping(
            mapping,
            theme_ids=("ai", "compute", "gpu", "semiconductor"),
        )

        assert score.dimensions.theme_match_score >= 70.0

    def test_coverage_score_calculation(self) -> None:
        """测试覆盖度评分计算。"""
        engine = create_scoring_engine()

        # 三层都有的映射
        sector_mappings = [
            SectorMapping(
                sector_name="算力",
                chain_segment="上游",
                confidence=ConfidenceLevel.HIGH,
                rationale="算力需求",
                theme_ids=("compute",),
            ),
        ]
        stock_pool_mappings = [
            StockPoolMapping(
                pool_name="测试池",
                criteria="测试标准",
                confidence=ConfidenceLevel.MEDIUM,
                rationale="测试理由",
                sector_name="算力",
            ),
        ]
        individual_stock_mappings = [
            IndividualStockMapping(
                stock_code="000001",
                stock_name="测试股票",
                confidence=ConfidenceLevel.MEDIUM,
                rationale="测试理由",
                impact_direction="受益",
            ),
        ]

        mapping = AStockMapping(
            chain_id="test-coverage",
            sector_mappings=tuple(sector_mappings),
            stock_pool_mappings=tuple(stock_pool_mappings),
            individual_stock_mappings=tuple(individual_stock_mappings),
            overall_confidence=ConfidenceLevel.HIGH,
            summary="覆盖度测试",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        score = engine.score_mapping(mapping)

        # 三层都有应该覆盖度得分较高
        assert score.dimensions.coverage_score >= 60.0

    def test_confidence_weighted_score(self) -> None:
        """测试置信度加权评分。"""
        engine = create_scoring_engine()

        # HIGH 置信度的映射
        sector_mappings_high = [
            SectorMapping(
                sector_name="算力",
                chain_segment="上游",
                confidence=ConfidenceLevel.HIGH,
                rationale="高置信度",
                theme_ids=("compute",),
            ),
        ]

        mapping_high = AStockMapping(
            chain_id="test-confidence-high",
            sector_mappings=tuple(sector_mappings_high),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.HIGH,
            summary="高置信度测试",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        score_high = engine.score_mapping(mapping_high)

        # LOW 置信度的映射
        sector_mappings_low = [
            SectorMapping(
                sector_name="算力",
                chain_segment="上游",
                confidence=ConfidenceLevel.LOW,
                rationale="低置信度",
                theme_ids=("compute",),
            ),
        ]

        mapping_low = AStockMapping(
            chain_id="test-confidence-low",
            sector_mappings=tuple(sector_mappings_low),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="低置信度测试",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        score_low = engine.score_mapping(mapping_low)

        # 高置信度的得分应该高于低置信度
        assert score_high.dimensions.confidence_weighted_score > score_low.dimensions.confidence_weighted_score


class TestOverallScoreCalculation:
    """测试总体评分计算。"""

    def test_weighted_average_calculation(self) -> None:
        """测试加权平均计算逻辑。"""
        engine = create_scoring_engine()

        # 创建一个各维度都是 100 分的映射
        sector_mappings = [
            SectorMapping(
                sector_name="算力",
                chain_segment="上游",
                confidence=ConfidenceLevel.HIGH,
                rationale="测试",
                theme_ids=("compute", "gpu", "semiconductor"),
            ),
            SectorMapping(
                sector_name="光模块",
                chain_segment="中游",
                confidence=ConfidenceLevel.HIGH,
                rationale="测试",
                theme_ids=("optical_module",),
            ),
            SectorMapping(
                sector_name="AI应用",
                chain_segment="下游",
                confidence=ConfidenceLevel.HIGH,
                rationale="测试",
                theme_ids=("ai_application",),
            ),
        ]
        stock_pool_mappings = [
            StockPoolMapping(
                pool_name="测试池1",
                criteria="测试",
                confidence=ConfidenceLevel.HIGH,
                rationale="测试",
                sector_name="算力",
            ),
        ]
        individual_stock_mappings = [
            IndividualStockMapping(
                stock_code="000001",
                stock_name="测试1",
                confidence=ConfidenceLevel.HIGH,
                rationale="测试",
                impact_direction="受益",
            ),
            IndividualStockMapping(
                stock_code="000002",
                stock_name="测试2",
                confidence=ConfidenceLevel.HIGH,
                rationale="测试",
                impact_direction="受益",
            ),
            IndividualStockMapping(
                stock_code="000003",
                stock_name="测试3",
                confidence=ConfidenceLevel.HIGH,
                rationale="测试",
                impact_direction="受益",
            ),
            IndividualStockMapping(
                stock_code="000004",
                stock_name="测试4",
                confidence=ConfidenceLevel.HIGH,
                rationale="测试",
                impact_direction="受益",
            ),
            IndividualStockMapping(
                stock_code="000005",
                stock_name="测试5",
                confidence=ConfidenceLevel.HIGH,
                rationale="测试",
                impact_direction="受益",
            ),
        ]

        mapping = AStockMapping(
            chain_id="test-high-score",
            sector_mappings=tuple(sector_mappings),
            stock_pool_mappings=tuple(stock_pool_mappings),
            individual_stock_mappings=tuple(individual_stock_mappings),
            overall_confidence=ConfidenceLevel.HIGH,
            summary="高评分测试",
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        score = engine.score_mapping(
            mapping,
            theme_ids=("ai", "compute", "gpu", "semiconductor", "optical_module"),
        )

        # 应该是优秀或良好等级
        assert score.score_level in {"good", "excellent"}
        # 总体评分应该较高
        assert score.overall_score > 70.0
