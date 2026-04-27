"""
产业链环节映射测试。

测试 IndustryChainNode、IndustryChainMap 的结构和功能，
以及默认产业链映射的完整性和正确性。
"""

import pytest

from app.entity.themes import ThemeId
from app.mapping.schema import ConfidenceLevel
from app.mapping.industry_chain import (
    IndustryChainPosition,
    IndustryChainNode,
    IndustryChainMap,
    get_industry_chain_map,
    reload_industry_chain_map,
)


# ---------------------------------------------------------------------------
# IndustryChainPosition 测试
# ---------------------------------------------------------------------------


class TestIndustryChainPosition:
    """测试产业链位置枚举。"""

    def test_enum_values(self) -> None:
        """测试枚举值正确定义。"""
        assert IndustryChainPosition.UPSTREAM == "上游"
        assert IndustryChainPosition.MIDSTREAM == "中游"
        assert IndustryChainPosition.DOWNSTREAM == "下游"
        assert IndustryChainPosition.FULL_CHAIN == "全产业链"

    def test_all_positions_covered(self) -> None:
        """测试所有位置都被枚举。"""
        positions = list(IndustryChainPosition)
        assert len(positions) == 4
        assert IndustryChainPosition.UPSTREAM in positions
        assert IndustryChainPosition.MIDSTREAM in positions
        assert IndustryChainPosition.DOWNSTREAM in positions
        assert IndustryChainPosition.FULL_CHAIN in positions


# ---------------------------------------------------------------------------
# IndustryChainNode 测试
# ---------------------------------------------------------------------------


class TestIndustryChainNode:
    """测试产业链节点类。"""

    def test_create_valid_node(self) -> None:
        """测试创建有效的产业链节点。"""
        node = IndustryChainNode(
            node_id="test",
            node_name="测试节点",
            position=IndustryChainPosition.UPSTREAM,
            description="测试描述",
            related_theme_ids=(ThemeId.AI,),
            sector_name="测试板块",
            related_concepts=("概念1", "概念2"),
            stock_candidates=(("000001", "平安银行"),),
            confidence=ConfidenceLevel.HIGH,
            rationale="测试理由",
        )

        assert node.node_id == "test"
        assert node.node_name == "测试节点"
        assert node.position == IndustryChainPosition.UPSTREAM
        assert node.sector_name == "测试板块"
        assert node.confidence == ConfidenceLevel.HIGH

    def test_node_id_required(self) -> None:
        """测试 node_id 不能为空。"""
        with pytest.raises(ValueError, match="node_id 不能为空"):
            IndustryChainNode(
                node_id="",
                node_name="测试节点",
                position=IndustryChainPosition.UPSTREAM,
                description="测试描述",
                related_theme_ids=(ThemeId.AI,),
                sector_name="测试板块",
                related_concepts=(),
                stock_candidates=(),
                confidence=ConfidenceLevel.HIGH,
                rationale="测试理由",
            )

    def test_node_name_required(self) -> None:
        """测试 node_name 不能为空。"""
        with pytest.raises(ValueError, match="node_name 不能为空"):
            IndustryChainNode(
                node_id="test",
                node_name="",
                position=IndustryChainPosition.UPSTREAM,
                description="测试描述",
                related_theme_ids=(ThemeId.AI,),
                sector_name="测试板块",
                related_concepts=(),
                stock_candidates=(),
                confidence=ConfidenceLevel.HIGH,
                rationale="测试理由",
            )

    def test_sector_name_required(self) -> None:
        """测试 sector_name 不能为空。"""
        with pytest.raises(ValueError, match="sector_name 不能为空"):
            IndustryChainNode(
                node_id="test",
                node_name="测试节点",
                position=IndustryChainPosition.UPSTREAM,
                description="测试描述",
                related_theme_ids=(ThemeId.AI,),
                sector_name="",
                related_concepts=(),
                stock_candidates=(),
                confidence=ConfidenceLevel.HIGH,
                rationale="测试理由",
            )

    def test_rationale_required(self) -> None:
        """测试 rationale 不能为空。"""
        with pytest.raises(ValueError, match="rationale 不能为空"):
            IndustryChainNode(
                node_id="test",
                node_name="测试节点",
                position=IndustryChainPosition.UPSTREAM,
                description="测试描述",
                related_theme_ids=(ThemeId.AI,),
                sector_name="测试板块",
                related_concepts=(),
                stock_candidates=(),
                confidence=ConfidenceLevel.HIGH,
                rationale="",
            )

    def test_frozen_dataclass(self) -> None:
        """测试 dataclass 是冻结的（不可变）。"""
        node = IndustryChainNode(
            node_id="test",
            node_name="测试节点",
            position=IndustryChainPosition.UPSTREAM,
            description="测试描述",
            related_theme_ids=(ThemeId.AI,),
            sector_name="测试板块",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="测试理由",
        )

        with pytest.raises(AttributeError, match="cannot assign to field"):
            node.node_id = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IndustryChainMap 测试
# ---------------------------------------------------------------------------


class TestIndustryChainMap:
    """测试产业链映射类。"""

    def test_create_valid_map(self) -> None:
        """测试创建有效的产业链映射。"""
        node1 = IndustryChainNode(
            node_id="node1",
            node_name="节点1",
            position=IndustryChainPosition.UPSTREAM,
            description="描述1",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块1",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由1",
        )
        node2 = IndustryChainNode(
            node_id="node2",
            node_name="节点2",
            position=IndustryChainPosition.DOWNSTREAM,
            description="描述2",
            related_theme_ids=(ThemeId.AI_APPLICATION,),
            sector_name="板块2",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.MEDIUM,
            rationale="理由2",
        )

        chain_map = IndustryChainMap(nodes=(node1, node2), version="1.0")

        assert len(chain_map.nodes) == 2
        assert chain_map.version == "1.0"

    def test_nodes_required(self) -> None:
        """测试 nodes 不能为空。"""
        with pytest.raises(ValueError, match="nodes 不能为空"):
            IndustryChainMap(nodes=())

    def test_get_node_by_id(self) -> None:
        """测试根据 ID 获取节点。"""
        node1 = IndustryChainNode(
            node_id="node1",
            node_name="节点1",
            position=IndustryChainPosition.UPSTREAM,
            description="描述1",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块1",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由1",
        )
        node2 = IndustryChainNode(
            node_id="node2",
            node_name="节点2",
            position=IndustryChainPosition.DOWNSTREAM,
            description="描述2",
            related_theme_ids=(ThemeId.AI_APPLICATION,),
            sector_name="板块2",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.MEDIUM,
            rationale="理由2",
        )

        chain_map = IndustryChainMap(nodes=(node1, node2))

        assert chain_map.get_node_by_id("node1") == node1
        assert chain_map.get_node_by_id("node2") == node2
        assert chain_map.get_node_by_id("nonexistent") is None

    def test_get_nodes_by_position(self) -> None:
        """测试根据位置获取节点。"""
        node1 = IndustryChainNode(
            node_id="up1",
            node_name="上游1",
            position=IndustryChainPosition.UPSTREAM,
            description="描述1",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块1",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由1",
        )
        node2 = IndustryChainNode(
            node_id="up2",
            node_name="上游2",
            position=IndustryChainPosition.UPSTREAM,
            description="描述2",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块2",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由2",
        )
        node3 = IndustryChainNode(
            node_id="down1",
            node_name="下游1",
            position=IndustryChainPosition.DOWNSTREAM,
            description="描述3",
            related_theme_ids=(ThemeId.AI_APPLICATION,),
            sector_name="板块3",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.MEDIUM,
            rationale="理由3",
        )

        chain_map = IndustryChainMap(nodes=(node1, node2, node3))

        upstream_nodes = chain_map.get_nodes_by_position(IndustryChainPosition.UPSTREAM)
        assert len(upstream_nodes) == 2
        assert node1 in upstream_nodes
        assert node2 in upstream_nodes

        downstream_nodes = chain_map.get_nodes_by_position(IndustryChainPosition.DOWNSTREAM)
        assert len(downstream_nodes) == 1
        assert node3 in downstream_nodes

    def test_get_nodes_by_theme(self) -> None:
        """测试根据主题获取节点。"""
        node1 = IndustryChainNode(
            node_id="node1",
            node_name="节点1",
            position=IndustryChainPosition.UPSTREAM,
            description="描述1",
            related_theme_ids=(ThemeId.AI, ThemeId.COMPUTE),
            sector_name="板块1",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由1",
        )
        node2 = IndustryChainNode(
            node_id="node2",
            node_name="节点2",
            position=IndustryChainPosition.DOWNSTREAM,
            description="描述2",
            related_theme_ids=(ThemeId.AI_APPLICATION,),
            sector_name="板块2",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.MEDIUM,
            rationale="理由2",
        )

        chain_map = IndustryChainMap(nodes=(node1, node2))

        ai_nodes = chain_map.get_nodes_by_theme(ThemeId.AI)
        assert len(ai_nodes) == 1
        assert node1 in ai_nodes

        compute_nodes = chain_map.get_nodes_by_theme(ThemeId.COMPUTE)
        assert len(compute_nodes) == 1
        assert node1 in compute_nodes

        app_nodes = chain_map.get_nodes_by_theme(ThemeId.AI_APPLICATION)
        assert len(app_nodes) == 1
        assert node2 in app_nodes

    def test_upstream_nodes_property(self) -> None:
        """测试 upstream_nodes 属性。"""
        node1 = IndustryChainNode(
            node_id="up1",
            node_name="上游1",
            position=IndustryChainPosition.UPSTREAM,
            description="描述1",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块1",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由1",
        )
        node2 = IndustryChainNode(
            node_id="mid1",
            node_name="中游1",
            position=IndustryChainPosition.MIDSTREAM,
            description="描述2",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块2",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由2",
        )

        chain_map = IndustryChainMap(nodes=(node1, node2))

        assert len(chain_map.upstream_nodes) == 1
        assert chain_map.upstream_nodes[0] == node1

    def test_midstream_nodes_property(self) -> None:
        """测试 midstream_nodes 属性。"""
        node1 = IndustryChainNode(
            node_id="up1",
            node_name="上游1",
            position=IndustryChainPosition.UPSTREAM,
            description="描述1",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块1",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由1",
        )
        node2 = IndustryChainNode(
            node_id="mid1",
            node_name="中游1",
            position=IndustryChainPosition.MIDSTREAM,
            description="描述2",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块2",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由2",
        )

        chain_map = IndustryChainMap(nodes=(node1, node2))

        assert len(chain_map.midstream_nodes) == 1
        assert chain_map.midstream_nodes[0] == node2

    def test_downstream_nodes_property(self) -> None:
        """测试 downstream_nodes 属性。"""
        node1 = IndustryChainNode(
            node_id="down1",
            node_name="下游1",
            position=IndustryChainPosition.DOWNSTREAM,
            description="描述1",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块1",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由1",
        )
        node2 = IndustryChainNode(
            node_id="mid1",
            node_name="中游1",
            position=IndustryChainPosition.MIDSTREAM,
            description="描述2",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块2",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由2",
        )

        chain_map = IndustryChainMap(nodes=(node1, node2))

        assert len(chain_map.downstream_nodes) == 1
        assert chain_map.downstream_nodes[0] == node1

    def test_get_all_sectors(self) -> None:
        """测试获取所有板块名称。"""
        node1 = IndustryChainNode(
            node_id="node1",
            node_name="节点1",
            position=IndustryChainPosition.UPSTREAM,
            description="描述1",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块A",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由1",
        )
        node2 = IndustryChainNode(
            node_id="node2",
            node_name="节点2",
            position=IndustryChainPosition.DOWNSTREAM,
            description="描述2",
            related_theme_ids=(ThemeId.AI_APPLICATION,),
            sector_name="板块A",  # 重复的板块名称
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.MEDIUM,
            rationale="理由2",
        )
        node3 = IndustryChainNode(
            node_id="node3",
            node_name="节点3",
            position=IndustryChainPosition.MIDSTREAM,
            description="描述3",
            related_theme_ids=(ThemeId.AI,),
            sector_name="板块B",
            related_concepts=(),
            stock_candidates=(),
            confidence=ConfidenceLevel.HIGH,
            rationale="理由3",
        )

        chain_map = IndustryChainMap(nodes=(node1, node2, node3))

        sectors = chain_map.get_all_sectors()
        assert len(sectors) == 2  # 去重后
        assert "板块A" in sectors
        assert "板块B" in sectors


# ---------------------------------------------------------------------------
# 默认产业链映射测试
# ---------------------------------------------------------------------------


class TestDefaultIndustryChainMap:
    """测试默认产业链映射的完整性和正确性。"""

    def test_get_industry_chain_map_returns_singleton(self) -> None:
        """测试 get_industry_chain_map 返回单例。"""
        map1 = get_industry_chain_map()
        map2 = get_industry_chain_map()
        assert map1 is map2

    def test_reload_industry_chain_map_creates_new_instance(self) -> None:
        """测试 reload_industry_chain_map 创建新实例。"""
        map1 = get_industry_chain_map()
        map2 = reload_industry_chain_map()
        map3 = get_industry_chain_map()

        assert map1 is not map2
        assert map2 is map3

    def test_default_map_has_all_required_nodes(self) -> None:
        """测试默认映射包含所有必需的节点。"""
        chain_map = get_industry_chain_map()

        # 检查关键节点存在
        assert chain_map.get_node_by_id("compute") is not None
        assert chain_map.get_node_by_id("storage") is not None
        assert chain_map.get_node_by_id("memory") is not None
        assert chain_map.get_node_by_id("gpu") is not None
        assert chain_map.get_node_by_id("semiconductor") is not None
        assert chain_map.get_node_by_id("optical_module") is not None
        assert chain_map.get_node_by_id("supply_chain") is not None
        assert chain_map.get_node_by_id("foundation_model") is not None
        assert chain_map.get_node_by_id("cloud") is not None
        assert chain_map.get_node_by_id("ai_application") is not None
        assert chain_map.get_node_by_id("ai_full") is not None

    def test_upstream_nodes_are_present(self) -> None:
        """测试上游节点存在。"""
        chain_map = get_industry_chain_map()
        upstream_nodes = chain_map.upstream_nodes
        assert len(upstream_nodes) >= 5

    def test_midstream_nodes_are_present(self) -> None:
        """测试中游节点存在。"""
        chain_map = get_industry_chain_map()
        midstream_nodes = chain_map.midstream_nodes
        assert len(midstream_nodes) >= 2

    def test_downstream_nodes_are_present(self) -> None:
        """测试下游节点存在。"""
        chain_map = get_industry_chain_map()
        downstream_nodes = chain_map.downstream_nodes
        assert len(downstream_nodes) >= 1

    def test_all_theme_ids_are_covered(self) -> None:
        """测试所有主题 ID 都被覆盖。"""
        chain_map = get_industry_chain_map()

        # 检查每个主题都有关联的节点
        for theme_id in ThemeId:
            nodes = chain_map.get_nodes_by_theme(theme_id)
            assert len(nodes) > 0, f"Theme {theme_id} 没有关联的产业链节点"

    def test_all_nodes_have_stock_candidates(self) -> None:
        """测试所有节点都有候选标的。"""
        chain_map = get_industry_chain_map()

        for node in chain_map.nodes:
            assert len(node.stock_candidates) > 0, f"Node {node.node_id} 没有候选标的"

    def test_all_nodes_have_related_concepts(self) -> None:
        """测试所有节点都有相关概念。"""
        chain_map = get_industry_chain_map()

        for node in chain_map.nodes:
            assert len(node.related_concepts) > 0, f"Node {node.node_id} 没有相关概念"

    def test_optical_module_node_has_correct_info(self) -> None:
        """测试光模块节点信息正确。"""
        chain_map = get_industry_chain_map()
        node = chain_map.get_node_by_id("optical_module")
        assert node is not None
        assert node.position == IndustryChainPosition.UPSTREAM
        assert ThemeId.OPTICAL_MODULE in node.related_theme_ids
        assert "中际旭创" in [name for _, name in node.stock_candidates]

    def test_gpu_node_has_correct_info(self) -> None:
        """测试 GPU 节点信息正确。"""
        chain_map = get_industry_chain_map()
        node = chain_map.get_node_by_id("gpu")
        assert node is not None
        assert node.position == IndustryChainPosition.UPSTREAM
        assert ThemeId.GPU in node.related_theme_ids

    def test_ai_application_node_has_correct_info(self) -> None:
        """测试 AI 应用节点信息正确。"""
        chain_map = get_industry_chain_map()
        node = chain_map.get_node_by_id("ai_application")
        assert node is not None
        assert node.position == IndustryChainPosition.DOWNSTREAM
        assert ThemeId.AI_APPLICATION in node.related_theme_ids
