"""
测试 AkShare 动态股票解析器。

重点验证：
- 数据合并与去重逻辑
- 缓存行为
- AkShare 失败时的 graceful fallback
- 股票代码清洗规则
"""

from __future__ import annotations

import time as _time
from typing import Any, List, Tuple
from unittest import mock

import pytest

from app.mapping.akshare_resolver import (
    AkShareStockResolver,
    _CacheEntry,
    _clean_stock_code,
    create_akshare_resolver,
)
from app.mapping.industry_chain import (
    IndustryChainNode,
    IndustryChainPosition,
    get_industry_chain_map,
)
from app.mapping.schema import ConfidenceLevel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(
    stock_candidates: Tuple[Tuple[str, str], ...] = (),
    sector_name: str = "测试板块",
) -> IndustryChainNode:
    """快速创建测试用的产业链节点。"""
    return IndustryChainNode(
        node_id="test_node",
        node_name="测试节点",
        position=IndustryChainPosition.UPSTREAM,
        description="测试描述",
        related_theme_ids=(),
        sector_name=sector_name,
        related_concepts=(),
        stock_candidates=stock_candidates,
        confidence=ConfidenceLevel.HIGH,
        rationale="测试理由",
    )


# ---------------------------------------------------------------------------
# _clean_stock_code
# ---------------------------------------------------------------------------


class TestCleanStockCode:
    """测试股票代码清洗。"""

    def test_basic_six_digit_code(self) -> None:
        assert _clean_stock_code("600588") == "600588"

    def test_code_with_sh_suffix(self) -> None:
        assert _clean_stock_code("600588.SH") == "600588"

    def test_code_with_sz_suffix(self) -> None:
        assert _clean_stock_code("000977.SZ") == "000977"

    def test_code_with_space(self) -> None:
        assert _clean_stock_code(" 300308 ") == "300308"

    def test_non_digit_code_returns_none(self) -> None:
        assert _clean_stock_code("ABC123") is None

    def test_short_code_returns_none(self) -> None:
        assert _clean_stock_code("12345") is None

    def test_long_code_returns_none(self) -> None:
        assert _clean_stock_code("1234567") is None

    def test_empty_returns_none(self) -> None:
        assert _clean_stock_code("") is None


# ---------------------------------------------------------------------------
# AkShareStockResolver — cache & merge logic
# ---------------------------------------------------------------------------


class TestAkShareStockResolverCore:
    """测试解析器核心逻辑（不依赖真实 AkShare）。"""

    def test_no_resolver_returns_base_candidates(self) -> None:
        """无 resolver 时，引擎只使用硬编码数据（已在 engine 测试覆盖）。"""
        node = _make_node(stock_candidates=(("000001", "平安银行"),))
        resolver = AkShareStockResolver()

        # 默认没缓存也没注入 ak，应当回退到硬编码
        with mock.patch.object(resolver, "_fetch_stocks_for_sector", return_value=[]):
            result = resolver.resolve_stocks_for_node(node)

        assert result == (("000001", "平安银行"),)

    def test_merge_and_deduplicate(self) -> None:
        """动态数据与硬编码合并时去重，硬编码优先。"""
        node = _make_node(
            stock_candidates=(("000001", "平安银行"), ("000002", "万科A")),
            sector_name="测试板块",
        )
        resolver = AkShareStockResolver()

        with mock.patch.object(
            resolver,
            "_fetch_stocks_for_sector",
            return_value=[
                ("000002", "万科A-动态"),  # 重复代码
                ("000003", "招商银行"),    # 新增
            ],
        ):
            result = resolver.resolve_stocks_for_node(node)

        # 硬编码优先，000002 应保留硬编码名称；000003 追加
        assert len(result) == 3
        assert result[0] == ("000001", "平安银行")
        assert result[1] == ("000002", "万科A")
        assert result[2] == ("000003", "招商银行")

    def test_dynamic_results_extend_beyond_base(self) -> None:
        """当动态数据较多时，可以显著扩展候选池。"""
        node = _make_node(
            stock_candidates=(("600588", "用友网络"),),
            sector_name="人工智能",
        )
        resolver = AkShareStockResolver()

        dynamic = [(f"{i:06d}", f"股票{i}") for i in range(1, 20)]
        with mock.patch.object(
            resolver, "_fetch_stocks_for_sector", return_value=dynamic
        ):
            result = resolver.resolve_stocks_for_node(node)

        # 硬编码 1 条 + 动态 19 条（无重复）= 20 条
        assert len(result) == 20
        assert result[0] == ("600588", "用友网络")

    def test_cache_hit_avoids_repeated_fetch(self) -> None:
        """缓存命中时 _fetch_stocks_for_sector 不再调用底层 AkShare。"""
        resolver = AkShareStockResolver(ttl_seconds=3600)
        resolver._cache["sector:测试板块"] = _CacheEntry(
            stocks=(("999999", "缓存股票"),),
            expires_at=_time.time() + 3600,
        )

        # 直接测试 _fetch_stocks_for_sector：缓存命中时不应调用 _try_fetch_concept
        with mock.patch.object(resolver, "_try_fetch_concept") as mock_concept, \
             mock.patch.object(resolver, "_try_fetch_industry") as mock_industry:
            result = resolver._fetch_stocks_for_sector("测试板块")

        mock_concept.assert_not_called()
        mock_industry.assert_not_called()
        assert result == [("999999", "缓存股票")]

    def test_cache_expires(self) -> None:
        """缓存过期后会重新 fetch。"""
        resolver = AkShareStockResolver(ttl_seconds=1)
        resolver._cache["sector:测试板块"] = _CacheEntry(
            stocks=(("999999", "过期股票"),),
            expires_at=_time.time() - 1,  # 已过期
        )

        node = _make_node(sector_name="测试板块")
        with mock.patch.object(
            resolver, "_fetch_stocks_for_sector", return_value=[("000001", "平安银行")]
        ) as mock_fetch:
            result = resolver.resolve_stocks_for_node(node)

        mock_fetch.assert_called_once_with("测试板块")
        assert result == (("000001", "平安银行"),)

    def test_clear_cache(self) -> None:
        resolver = AkShareStockResolver()
        resolver._cache["sector:测试板块"] = _CacheEntry(
            stocks=(("999999", "缓存股票"),),
            expires_at=_time.time() + 3600,
        )
        resolver.clear_cache()
        assert len(resolver.cache_keys) == 0


# ---------------------------------------------------------------------------
# _parse_dataframe
# ---------------------------------------------------------------------------


class TestParseDataframe:
    """测试 DataFrame 解析逻辑。"""

    def test_parse_with_chinese_columns(self) -> None:
        resolver = AkShareStockResolver()

        # 模拟东方财富常见返回格式
        df = mock.Mock()
        df.empty = False
        df.columns = ["序号", "代码", "名称", "最新价", "涨跌幅"]
        df.iterrows.return_value = iter([
            (0, mock.Mock(get=lambda k, d="": {"代码": "600588", "名称": "用友网络"}.get(k, d))),
            (1, mock.Mock(get=lambda k, d="": {"代码": "000977", "名称": "浪潮信息"}.get(k, d))),
        ])

        result = resolver._parse_dataframe(df)
        assert len(result) == 2
        assert result[0] == ("600588", "用友网络")
        assert result[1] == ("000977", "浪潮信息")

    def test_parse_with_fcode_columns(self) -> None:
        """东方财富部分接口使用 f12/f14 列名。"""
        resolver = AkShareStockResolver()

        df = mock.Mock()
        df.empty = False
        df.columns = [" f12", " f14", " f2", " f3"]
        df.iterrows.return_value = iter([
            (0, mock.Mock(get=lambda k, d="": {" f12": "300308", " f14": "中际旭创"}.get(k, d))),
        ])

        result = resolver._parse_dataframe(df)
        assert result == [("300308", "中际旭创")]

    def test_parse_skips_invalid_rows(self) -> None:
        resolver = AkShareStockResolver()

        df = mock.Mock()
        df.empty = False
        df.columns = ["代码", "名称"]
        df.iterrows.return_value = iter([
            (0, mock.Mock(get=lambda k, d="": {"代码": "600588", "名称": "用友网络"}.get(k, d))),
            (1, mock.Mock(get=lambda k, d="": {"代码": "", "名称": ""}.get(k, d))),
            (2, mock.Mock(get=lambda k, d="": {"代码": "nan", "名称": "nan"}.get(k, d))),
        ])

        result = resolver._parse_dataframe(df)
        assert len(result) == 1
        assert result[0] == ("600588", "用友网络")

    def test_parse_none_or_empty_returns_empty(self) -> None:
        resolver = AkShareStockResolver()
        assert resolver._parse_dataframe(None) == []
        df = mock.Mock()
        df.empty = True
        assert resolver._parse_dataframe(df) == []


# ---------------------------------------------------------------------------
# _fetch_stocks_for_sector — fallback chain
# ---------------------------------------------------------------------------


class TestFetchStocksForSectorFallback:
    """测试概念板块 → 行业板块的回退链。"""

    def test_concept_success_no_industry_call(self) -> None:
        resolver = AkShareStockResolver()

        with mock.patch.object(
            resolver, "_try_fetch_concept", return_value=[("600588", "用友网络")]
        ) as mock_concept, mock.patch.object(
            resolver, "_try_fetch_industry", return_value=[]
        ) as mock_industry:
            result = resolver._fetch_stocks_for_sector("人工智能")

        mock_concept.assert_called_once()
        mock_industry.assert_not_called()
        assert result == [("600588", "用友网络")]

    def test_concept_falls_back_to_industry(self) -> None:
        resolver = AkShareStockResolver()

        with mock.patch.object(
            resolver, "_try_fetch_concept", return_value=[]
        ) as mock_concept, mock.patch.object(
            resolver, "_try_fetch_industry", return_value=[("000001", "平安银行")]
        ) as mock_industry:
            result = resolver._fetch_stocks_for_sector("人工智能")

        mock_concept.assert_called_once()
        mock_industry.assert_called_once()
        assert result == [("000001", "平安银行")]

    def test_no_mapping_returns_empty_and_caches(self) -> None:
        """没有映射的 sector 返回空列表，但也会写入缓存防止频繁重试。"""
        resolver = AkShareStockResolver(ttl_seconds=60)

        with mock.patch.object(resolver, "_try_fetch_concept", return_value=[]), \
             mock.patch.object(resolver, "_try_fetch_industry", return_value=[]):
            result = resolver._fetch_stocks_for_sector("未知板块")

        assert result == []
        assert "sector:未知板块" in resolver._cache


# ---------------------------------------------------------------------------
# Integration with real map nodes
# ---------------------------------------------------------------------------


class TestResolverWithRealNodes:
    """使用真实产业链节点测试 resolver 的整合行为。"""

    def test_real_nodes_have_sector_mapping(self) -> None:
        chain_map = get_industry_chain_map()
        resolver = AkShareStockResolver()

        for node in chain_map.nodes:
            # 每个节点的 sector_name 都应该在映射表中有对应（或没有，也不报错）
            assert node.sector_name
            # 调用 resolve 不应抛异常
            with mock.patch.object(resolver, "_fetch_stocks_for_sector", return_value=[]):
                result = resolver.resolve_stocks_for_node(node)
            # 至少返回硬编码数据
            assert len(result) >= len(node.stock_candidates)

    def test_real_node_with_mock_dynamic_expands(self) -> None:
        chain_map = get_industry_chain_map()
        node = chain_map.get_node_by_id("compute")
        assert node is not None

        resolver = AkShareStockResolver()
        dynamic = [(f"{i:06d}", f"股票{i}") for i in range(1, 15)]

        with mock.patch.object(
            resolver, "_fetch_stocks_for_sector", return_value=dynamic
        ):
            result = resolver.resolve_stocks_for_node(node)

        # 硬编码 5 条 + 动态 14 条 = 19 条（假设无代码重叠）
        assert len(result) == 5 + 14
        # 硬编码条目排在前面
        for idx, (code, name) in enumerate(node.stock_candidates):
            assert result[idx] == (code, name)


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


class TestCreateAkshareResolver:
    def test_factory_returns_instance(self) -> None:
        resolver = create_akshare_resolver()
        assert isinstance(resolver, AkShareStockResolver)
        assert resolver._enable_concept is True
        assert resolver._enable_industry is True
