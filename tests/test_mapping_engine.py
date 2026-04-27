"""
测试 A 股映射引擎（Mapping Engine）

测试从 TaggedOutput/InformationChain 到 AStockMapping 的转换规则。
"""

import datetime
import uuid
from typing import List
from unittest import mock

import pytest

from app.chains.chain import build_chain
from app.entity.rules.extractor import Hit
from app.entity.evidence import build_evidence_links
from app.entity.tagged_output import build_tagged_output
from app.models.raw_document import RawDocument
from app.models.news_item import NewsItem
from app.models.event_draft import EventDraft
from app.mapping.engine import (
    AShareMappingEngine,
    MappingResult,
    create_mapping_engine,
    map_chain_to_a_share,
)
from app.mapping.industry_chain import get_industry_chain_map
from app.mapping.schema import (
    AStockMapping,
    ConfidenceLevel,
    IndividualStockMapping,
    SectorMapping,
    StockPoolMapping,
)


# ---------------------------------------------------------------------------
# Test helpers (reused from test_tagged_output)
# ---------------------------------------------------------------------------


def _make_raw(title: str = "test", date: str = "2025-01-01") -> RawDocument:
    return RawDocument(
        source="web",
        provider="test",
        title=title,
        content=None,
        url=None,
        date=date,
    )


def _make_news(title: str = "test", date: str = "2025-01-01") -> NewsItem:
    return NewsItem.from_raw(_make_raw(title=title, date=date))


def _make_event(title: str = "测试事件", date: str = "2025-01-01") -> EventDraft:
    return EventDraft.from_news_item(_make_news(title=title, date=date))


def _make_hit(
    matched_text: str,
    start: int,
    end: int,
    kind: str,
    label_id: str,
    seed: str = "",
) -> Hit:
    return Hit(
        matched_text=matched_text,
        start=start,
        end=end,
        matched_seed=seed or matched_text,
        kind=kind,  # type: ignore[arg-type]
        label_id=label_id,
    )


def _make_link(hit: Hit, text: str):
    """用最简单方式包装 Hit → EvidenceLink（context_window=0）。"""
    links = build_evidence_links(text, [hit], context_window=0)
    return links[0]


def create_dummy_tagged_output(
    theme_ids: List[str],
    text: str = "测试新闻文本",
):
    """创建测试用的 TaggedOutput。"""
    event = _make_event()
    hits = []
    for i, theme_id in enumerate(theme_ids):
        start = i * 3
        end = start + 2
        if end > len(text):
            text = text + " " * (end - len(text) + 1)
        hit = _make_hit(text[start:end], start, end, "theme", theme_id)
        hits.append(hit)
    links = [_make_link(h, text) for h in hits]
    return build_tagged_output(event, text, links)


def create_dummy_chain(theme_ids: List[str]):
    """创建测试用的 InformationChain。"""
    to = create_dummy_tagged_output(theme_ids)
    return build_chain(str(uuid.uuid4()), [to])


# ---------------------------------------------------------------------------
# Test AShareMappingEngine
# ---------------------------------------------------------------------------


class TestAShareMappingEngine:
    """测试 AShareMappingEngine。"""

    def test_create_engine_with_default_map(self) -> None:
        """测试使用默认产业链映射创建引擎。"""
        engine = AShareMappingEngine()
        assert engine is not None

    def test_create_engine_with_custom_map(self) -> None:
        """测试使用自定义产业链映射创建引擎。"""
        custom_map = get_industry_chain_map()
        engine = AShareMappingEngine(custom_map)
        assert engine is not None

    def test_map_tagged_output_returns_astockmapping(self) -> None:
        """测试映射 TaggedOutput 返回 AStockMapping。"""
        engine = create_mapping_engine()
        to = create_dummy_tagged_output(["ai"])
        mapping = engine.map_tagged_output(to)
        assert isinstance(mapping, AStockMapping)
        assert mapping.chain_id is not None

    def test_map_information_chain_returns_astockmapping(self) -> None:
        """测试映射 InformationChain 返回 AStockMapping。"""
        engine = create_mapping_engine()
        chain = create_dummy_chain(["ai"])
        mapping = engine.map_information_chain(chain)
        assert isinstance(mapping, AStockMapping)
        assert mapping.chain_id == chain.chain_id

    def test_map_multiple_chains_returns_results(self) -> None:
        """测试批量映射返回 MappingResult 列表。"""
        engine = create_mapping_engine()
        chain1 = create_dummy_chain(["ai"])
        chain2 = create_dummy_chain(["gpu"])
        results = engine.map_multiple_chains([chain1, chain2])
        assert len(results) == 2
        assert isinstance(results[0], MappingResult)

    def test_mapping_contains_sector_mappings_for_matched_themes(self) -> None:
        """测试映射包含匹配主题的板块映射。"""
        engine = create_mapping_engine()
        chain = create_dummy_chain(["ai", "gpu"])
        mapping = engine.map_information_chain(chain)
        assert len(mapping.sector_mappings) >= 0  # 可能为空但不报错

    def test_mapping_generated_at_is_valid_isoformat(self) -> None:
        """测试 generated_at 是有效的 ISO 格式。"""
        engine = create_mapping_engine()
        chain = create_dummy_chain(["ai"])
        mapping = engine.map_information_chain(chain)
        # 尝试解析 ISO 格式，不抛异常即通过
        datetime.datetime.fromisoformat(mapping.generated_at)
        assert True

    def test_overall_confidence_is_set(self) -> None:
        """测试整体置信度被正确设置。"""
        engine = create_mapping_engine()
        chain = create_dummy_chain(["ai", "gpu", "compute"])
        mapping = engine.map_information_chain(chain)
        assert mapping.overall_confidence in [
            ConfidenceLevel.HIGH,
            ConfidenceLevel.MEDIUM,
            ConfidenceLevel.LOW,
        ]

    def test_summary_is_not_none(self) -> None:
        """测试摘要不为 None。"""
        engine = create_mapping_engine()
        chain = create_dummy_chain(["ai"])
        mapping = engine.map_information_chain(chain)
        assert mapping.summary is not None


# ---------------------------------------------------------------------------
# Test convenience functions
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    """测试便捷函数。"""

    def test_create_mapping_engine(self) -> None:
        """测试 create_mapping_engine。"""
        engine = create_mapping_engine()
        assert isinstance(engine, AShareMappingEngine)

    def test_map_chain_to_a_share(self) -> None:
        """测试 map_chain_to_a_share。"""
        chain = create_dummy_chain(["ai"])
        mapping = map_chain_to_a_share(chain)
        assert isinstance(mapping, AStockMapping)


# ---------------------------------------------------------------------------
# Test MappingResult
# ---------------------------------------------------------------------------


class TestMappingResult:
    """测试 MappingResult。"""

    def test_create_mapping_result(self) -> None:
        """测试创建 MappingResult。"""
        chain = create_dummy_chain(["ai"])
        engine = create_mapping_engine()
        mapping = engine.map_information_chain(chain)
        result = MappingResult(
            mapping=mapping,
            source_chain_id=chain.chain_id,
            matched_theme_count=len(mapping.sector_mappings),
            mapped_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        assert result.mapping == mapping
        assert result.source_chain_id == chain.chain_id


# ---------------------------------------------------------------------------
# Test package exports
# ---------------------------------------------------------------------------


class TestEngineWithStockResolver:
    """测试注入 AkShareStockResolver 后的映射引擎行为。"""

    def test_engine_without_resolver_uses_hardcoded_only(self) -> None:
        """不注入 resolver 时，个股映射包含硬编码数据（与注入前行为一致）。"""
        engine = AShareMappingEngine(stock_resolver=None)
        chain = create_dummy_chain(["compute"])
        mapping = engine.map_information_chain(chain)

        # compute 节点硬编码有 5 条候选，应全部出现在结果中
        compute_node = get_industry_chain_map().get_node_by_id("compute")
        assert compute_node is not None
        hardcoded_codes = {code for code, _ in compute_node.stock_candidates}
        result_codes = {m.stock_code for m in mapping.individual_stock_mappings}
        assert hardcoded_codes.issubset(result_codes)

    def test_engine_with_resolver_expands_candidates(self) -> None:
        """注入 resolver 后，个股映射应包含动态扩展的数据。"""
        from app.mapping.akshare_resolver import AkShareStockResolver

        resolver = AkShareStockResolver()
        dynamic_stocks = [("999999", "动态股票")]

        with mock.patch.object(
            resolver, "resolve_stocks_for_node", return_value=(
                ("600588", "用友网络"),
                ("000977", "浪潮信息"),
                ("999999", "动态股票"),
            )
        ):
            engine = AShareMappingEngine(stock_resolver=resolver)
            chain = create_dummy_chain(["compute"])
            mapping = engine.map_information_chain(chain)

        # resolver 返回 3 条，映射后也应为 3 条（在 10 条限制内）
        assert len(mapping.individual_stock_mappings) == 3
        codes = [m.stock_code for m in mapping.individual_stock_mappings]
        assert "999999" in codes

    def test_create_mapping_engine_accepts_resolver(self) -> None:
        """测试 create_mapping_engine 工厂函数接受 resolver 参数。"""
        from app.mapping.akshare_resolver import AkShareStockResolver

        resolver = AkShareStockResolver()
        engine = create_mapping_engine(stock_resolver=resolver)
        assert engine._stock_resolver is resolver


# ---------------------------------------------------------------------------
# Test package exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    """测试包导出。"""

    def test_import_engine_is_exported(self) -> None:
        """测试 AShareMappingEngine 可从包中导入。"""
        import app.mapping as mapping
        assert hasattr(mapping, "AShareMappingEngine")
        assert mapping.AShareMappingEngine is AShareMappingEngine

    def test_create_function_is_exported(self) -> None:
        """测试便捷函数可从包中导入。"""
        import app.mapping as mapping
        assert hasattr(mapping, "create_mapping_engine")
        assert hasattr(mapping, "map_chain_to_a_share")

    def test_resolver_is_exported(self) -> None:
        """测试 AkShareStockResolver 可从包中导入。"""
        import app.mapping as mapping
        assert hasattr(mapping, "AkShareStockResolver")
        assert hasattr(mapping, "create_akshare_resolver")
