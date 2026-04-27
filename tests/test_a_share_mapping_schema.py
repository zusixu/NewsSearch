"""
Tests for A-share mapping schema (a-share-mapping Step 1)

验证 ConfidenceLevel、SectorMapping、StockPoolMapping、IndividualStockMapping 和 AStockMapping
的基本结构、不可变特性、以及约束校验。
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from app.mapping.schema import (
    ConfidenceLevel,
    SectorMapping,
    StockPoolMapping,
    IndividualStockMapping,
    AStockMapping,
)


# ---------------------------------------------------------------------------
# Test: ConfidenceLevel
# ---------------------------------------------------------------------------


def test_confidence_level_enum_values() -> None:
    """ConfidenceLevel 应包含 HIGH、MEDIUM、LOW 三个值。"""
    assert ConfidenceLevel.HIGH == "high"
    assert ConfidenceLevel.MEDIUM == "medium"
    assert ConfidenceLevel.LOW == "low"


def test_confidence_level_is_str_enum() -> None:
    """ConfidenceLevel 应是 str 枚举，可与字符串直接比较。"""
    assert ConfidenceLevel.HIGH.value == "high"
    assert ConfidenceLevel.HIGH == "high"  # 因为继承了 str，可以直接和字符串比较


# ---------------------------------------------------------------------------
# Test: SectorMapping
# ---------------------------------------------------------------------------


def test_sector_mapping_creation() -> None:
    """应能成功创建 SectorMapping 实例。"""
    mapping = SectorMapping(
        sector_name="人工智能",
        chain_segment="上游",
        confidence=ConfidenceLevel.HIGH,
        rationale="AI 大模型需求爆发，拉动算力基础设施建设",
        theme_ids=("ai", "compute"),
    )

    assert mapping.sector_name == "人工智能"
    assert mapping.chain_segment == "上游"
    assert mapping.confidence == ConfidenceLevel.HIGH
    assert mapping.rationale == "AI 大模型需求爆发，拉动算力基础设施建设"
    assert mapping.theme_ids == ("ai", "compute")


def test_sector_mapping_default_theme_ids() -> None:
    """theme_ids 默认为空元组。"""
    mapping = SectorMapping(
        sector_name="光模块",
        chain_segment="中游",
        confidence=ConfidenceLevel.MEDIUM,
        rationale="800G 光模块需求有望超预期",
    )

    assert mapping.theme_ids == ()


def test_sector_mapping_immutable() -> None:
    """SectorMapping 实例应是不可变的。"""
    mapping = SectorMapping(
        sector_name="半导体",
        chain_segment="全产业链",
        confidence=ConfidenceLevel.LOW,
        rationale="半导体国产化趋势延续",
    )

    with pytest.raises(FrozenInstanceError):
        mapping.sector_name = "其他"  # type: ignore


def test_sector_mapping_requires_sector_name() -> None:
    """sector_name 不能为空字符串。"""
    with pytest.raises(ValueError, match="sector_name 不能为空字符串"):
        SectorMapping(
            sector_name="",
            chain_segment="上游",
            confidence=ConfidenceLevel.HIGH,
            rationale="理由",
        )


def test_sector_mapping_requires_chain_segment() -> None:
    """chain_segment 不能为空字符串。"""
    with pytest.raises(ValueError, match="chain_segment 不能为空字符串"):
        SectorMapping(
            sector_name="人工智能",
            chain_segment="",
            confidence=ConfidenceLevel.HIGH,
            rationale="理由",
        )


def test_sector_mapping_requires_rationale() -> None:
    """rationale 不能为空字符串。"""
    with pytest.raises(ValueError, match="rationale 不能为空字符串"):
        SectorMapping(
            sector_name="人工智能",
            chain_segment="上游",
            confidence=ConfidenceLevel.HIGH,
            rationale="",
        )


# ---------------------------------------------------------------------------
# Test: StockPoolMapping
# ---------------------------------------------------------------------------


def test_stock_pool_mapping_creation() -> None:
    """应能成功创建 StockPoolMapping 实例。"""
    mapping = StockPoolMapping(
        pool_name="算力设备商",
        criteria="市值 > 100 亿，服务器收入占比 > 50%",
        confidence=ConfidenceLevel.HIGH,
        rationale="AI 算力需求爆发，服务器厂商优先受益",
        sector_name="人工智能",
    )

    assert mapping.pool_name == "算力设备商"
    assert mapping.criteria == "市值 > 100 亿，服务器收入占比 > 50%"
    assert mapping.confidence == ConfidenceLevel.HIGH
    assert mapping.rationale == "AI 算力需求爆发，服务器厂商优先受益"
    assert mapping.sector_name == "人工智能"


def test_stock_pool_mapping_default_sector_name() -> None:
    """sector_name 默认为 None。"""
    mapping = StockPoolMapping(
        pool_name="光模块龙头",
        criteria="光模块收入占比 > 30%，市场份额前 5",
        confidence=ConfidenceLevel.MEDIUM,
        rationale="800G 光模块渗透率提升",
    )

    assert mapping.sector_name is None


def test_stock_pool_mapping_immutable() -> None:
    """StockPoolMapping 实例应是不可变的。"""
    mapping = StockPoolMapping(
        pool_name="AI 应用厂商",
        criteria="AI 相关收入增速 > 50%",
        confidence=ConfidenceLevel.LOW,
        rationale="AI 应用商业化加速",
    )

    with pytest.raises(FrozenInstanceError):
        mapping.pool_name = "其他"  # type: ignore


def test_stock_pool_mapping_requires_pool_name() -> None:
    """pool_name 不能为空字符串。"""
    with pytest.raises(ValueError, match="pool_name 不能为空字符串"):
        StockPoolMapping(
            pool_name="",
            criteria="标准",
            confidence=ConfidenceLevel.HIGH,
            rationale="理由",
        )


def test_stock_pool_mapping_requires_criteria() -> None:
    """criteria 不能为空字符串。"""
    with pytest.raises(ValueError, match="criteria 不能为空字符串"):
        StockPoolMapping(
            pool_name="池名称",
            criteria="",
            confidence=ConfidenceLevel.HIGH,
            rationale="理由",
        )


def test_stock_pool_mapping_requires_rationale() -> None:
    """rationale 不能为空字符串。"""
    with pytest.raises(ValueError, match="rationale 不能为空字符串"):
        StockPoolMapping(
            pool_name="池名称",
            criteria="标准",
            confidence=ConfidenceLevel.HIGH,
            rationale="",
        )


# ---------------------------------------------------------------------------
# Test: IndividualStockMapping
# ---------------------------------------------------------------------------


def test_individual_stock_mapping_creation() -> None:
    """应能成功创建 IndividualStockMapping 实例。"""
    mapping = IndividualStockMapping(
        stock_code="300750",
        stock_name="宁德时代",
        confidence=ConfidenceLevel.HIGH,
        rationale="动力电池龙头，受益于新能源车销量增长",
        impact_direction="受益",
        pool_name="动力电池龙头",
        notes="估值已处于历史高位",
    )

    assert mapping.stock_code == "300750"
    assert mapping.stock_name == "宁德时代"
    assert mapping.confidence == ConfidenceLevel.HIGH
    assert mapping.rationale == "动力电池龙头，受益于新能源车销量增长"
    assert mapping.impact_direction == "受益"
    assert mapping.pool_name == "动力电池龙头"
    assert mapping.notes == "估值已处于历史高位"


def test_individual_stock_mapping_defaults() -> None:
    """应使用默认值：impact_direction='受益'，pool_name=None，notes=''。"""
    mapping = IndividualStockMapping(
        stock_code="600519",
        stock_name="贵州茅台",
        confidence=ConfidenceLevel.MEDIUM,
        rationale="白酒龙头，业绩稳定",
    )

    assert mapping.impact_direction == "受益"
    assert mapping.pool_name is None
    assert mapping.notes == ""


def test_individual_stock_mapping_immutable() -> None:
    """IndividualStockMapping 实例应是不可变的。"""
    mapping = IndividualStockMapping(
        stock_code="000001",
        stock_name="平安银行",
        confidence=ConfidenceLevel.LOW,
        rationale="金融 IT 投入增加",
    )

    with pytest.raises(FrozenInstanceError):
        mapping.stock_name = "其他"  # type: ignore


def test_individual_stock_mapping_requires_stock_code() -> None:
    """stock_code 不能为空字符串。"""
    with pytest.raises(ValueError, match="stock_code 不能为空字符串"):
        IndividualStockMapping(
            stock_code="",
            stock_name="名称",
            confidence=ConfidenceLevel.HIGH,
            rationale="理由",
        )


def test_individual_stock_mapping_requires_stock_name() -> None:
    """stock_name 不能为空字符串。"""
    with pytest.raises(ValueError, match="stock_name 不能为空字符串"):
        IndividualStockMapping(
            stock_code="000001",
            stock_name="",
            confidence=ConfidenceLevel.HIGH,
            rationale="理由",
        )


def test_individual_stock_mapping_requires_rationale() -> None:
    """rationale 不能为空字符串。"""
    with pytest.raises(ValueError, match="rationale 不能为空字符串"):
        IndividualStockMapping(
            stock_code="000001",
            stock_name="平安银行",
            confidence=ConfidenceLevel.HIGH,
            rationale="",
        )


def test_individual_stock_mapping_requires_impact_direction() -> None:
    """impact_direction 不能为空字符串。"""
    with pytest.raises(ValueError, match="impact_direction 不能为空字符串"):
        IndividualStockMapping(
            stock_code="000001",
            stock_name="平安银行",
            confidence=ConfidenceLevel.HIGH,
            rationale="理由",
            impact_direction="",
        )


# ---------------------------------------------------------------------------
# Test: AStockMapping
# ---------------------------------------------------------------------------


def test_astock_mapping_creation() -> None:
    """应能成功创建 AStockMapping 实例（完整三层映射）。"""
    sector_mapping = SectorMapping(
        sector_name="人工智能",
        chain_segment="上游",
        confidence=ConfidenceLevel.HIGH,
        rationale="AI 算力需求爆发",
        theme_ids=("ai", "compute"),
    )

    pool_mapping = StockPoolMapping(
        pool_name="算力设备商",
        criteria="服务器收入占比 > 50%",
        confidence=ConfidenceLevel.HIGH,
        rationale="服务器厂商优先受益",
        sector_name="人工智能",
    )

    stock_mapping = IndividualStockMapping(
        stock_code="000977",
        stock_name="浪潮信息",
        confidence=ConfidenceLevel.MEDIUM,
        rationale="国内服务器龙头",
        pool_name="算力设备商",
    )

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    mapping = AStockMapping(
        chain_id="test-chain-001",
        sector_mappings=(sector_mapping,),
        stock_pool_mappings=(pool_mapping,),
        individual_stock_mappings=(stock_mapping,),
        overall_confidence=ConfidenceLevel.HIGH,
        summary="AI 算力需求爆发，关注服务器产业链",
        generated_at=generated_at,
    )

    assert mapping.chain_id == "test-chain-001"
    assert len(mapping.sector_mappings) == 1
    assert len(mapping.stock_pool_mappings) == 1
    assert len(mapping.individual_stock_mappings) == 1
    assert mapping.overall_confidence == ConfidenceLevel.HIGH
    assert mapping.summary == "AI 算力需求爆发，关注服务器产业链"
    assert mapping.generated_at == generated_at
    assert mapping.is_empty is False


def test_astock_mapping_empty() -> None:
    """应能创建空映射（无任何映射内容），且 is_empty 返回 True。"""
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    mapping = AStockMapping(
        chain_id="test-chain-002",
        sector_mappings=(),
        stock_pool_mappings=(),
        individual_stock_mappings=(),
        overall_confidence=ConfidenceLevel.LOW,
        summary="暂无明确的 A 股映射方向",
        generated_at=generated_at,
    )

    assert mapping.is_empty is True


def test_astock_mapping_immutable() -> None:
    """AStockMapping 实例应是不可变的。"""
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    mapping = AStockMapping(
        chain_id="test-chain-003",
        sector_mappings=(),
        stock_pool_mappings=(),
        individual_stock_mappings=(),
        overall_confidence=ConfidenceLevel.LOW,
        summary="空映射",
        generated_at=generated_at,
    )

    with pytest.raises(FrozenInstanceError):
        mapping.summary = "其他"  # type: ignore


def test_astock_mapping_requires_chain_id() -> None:
    """chain_id 不能为空字符串。"""
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    with pytest.raises(ValueError, match="chain_id 不能为空字符串"):
        AStockMapping(
            chain_id="",
            sector_mappings=(),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="总结",
            generated_at=generated_at,
        )


def test_astock_mapping_requires_summary() -> None:
    """summary 不能为空字符串。"""
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    with pytest.raises(ValueError, match="summary 不能为空字符串"):
        AStockMapping(
            chain_id="test-chain-004",
            sector_mappings=(),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="",
            generated_at=generated_at,
        )


def test_astock_mapping_requires_generated_at() -> None:
    """generated_at 不能为空字符串。"""
    with pytest.raises(ValueError, match="generated_at 不能为空字符串"):
        AStockMapping(
            chain_id="test-chain-005",
            sector_mappings=(),
            stock_pool_mappings=(),
            individual_stock_mappings=(),
            overall_confidence=ConfidenceLevel.LOW,
            summary="总结",
            generated_at="",
        )


# ---------------------------------------------------------------------------
# Test: package exports
# ---------------------------------------------------------------------------


def test_package_exports() -> None:
    """app.mapping 应导出所有关键类型。"""
    import app.mapping

    assert app.mapping.ConfidenceLevel is ConfidenceLevel
    assert app.mapping.SectorMapping is SectorMapping
    assert app.mapping.StockPoolMapping is StockPoolMapping
    assert app.mapping.IndividualStockMapping is IndividualStockMapping
    assert app.mapping.AStockMapping is AStockMapping
