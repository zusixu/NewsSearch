"""
AI 产业链到 A 股环节的映射规则。

定义了完整的 AI 产业链结构（上游/中游/下游），并建立了从主题标签到 A 股板块的映射关系。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from app.entity.themes import ThemeId
from app.mapping.schema import ConfidenceLevel


# ---------------------------------------------------------------------------
# IndustryChainPosition — 产业链位置枚举
# ---------------------------------------------------------------------------


class IndustryChainPosition(str, Enum):
    """产业链位置枚举。"""

    UPSTREAM = "上游"
    MIDSTREAM = "中游"
    DOWNSTREAM = "下游"
    FULL_CHAIN = "全产业链"


# ---------------------------------------------------------------------------
# IndustryChainNode — 产业链节点
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndustryChainNode:
    """
    AI 产业链节点定义。

    字段
    ----
    node_id
        节点唯一标识符，例如 "compute", "optical_module"。
    node_name
        节点名称，例如 "算力", "光模块"。
    position
        产业链位置：上游/中游/下游/全产业链。
    description
        节点描述，说明该环节在产业链中的作用。
    related_theme_ids
        关联的主题 ID 列表，用于与主题标签体系对接。
    sector_name
        对应的 A 股板块名称。
    related_concepts
        相关概念板块列表，例如 ["人工智能", "算力", "东数西算"]。
    stock_candidates
        候选标的池列表，每个元素是 (股票代码, 股票名称)。
    confidence
        该映射的置信度。
    rationale
        映射理由说明。
    """

    node_id: str
    node_name: str
    position: IndustryChainPosition
    description: str
    related_theme_ids: Tuple[ThemeId, ...]
    sector_name: str
    related_concepts: Tuple[str, ...]
    stock_candidates: Tuple[Tuple[str, str], ...]  # (code, name)
    confidence: ConfidenceLevel
    rationale: str

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("IndustryChainNode.node_id 不能为空。")
        if not self.node_name:
            raise ValueError("IndustryChainNode.node_name 不能为空。")
        if not self.sector_name:
            raise ValueError("IndustryChainNode.sector_name 不能为空。")
        if not self.rationale:
            raise ValueError("IndustryChainNode.rationale 不能为空。")


# ---------------------------------------------------------------------------
# IndustryChainMap — 完整产业链映射
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndustryChainMap:
    """
    完整的 AI 产业链映射定义。

    包含所有产业链节点，并提供按主题、位置等方式查询的方法。
    """

    nodes: Tuple[IndustryChainNode, ...]
    version: str = "1.0"
    description: str = "AI 产业链到 A 股环节的映射规则"

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("IndustryChainMap.nodes 不能为空。")

    def get_node_by_id(self, node_id: str) -> Optional[IndustryChainNode]:
        """根据节点 ID 获取节点定义。"""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_nodes_by_position(
        self, position: IndustryChainPosition
    ) -> List[IndustryChainNode]:
        """根据产业链位置获取节点列表。"""
        return [node for node in self.nodes if node.position == position]

    def get_nodes_by_theme(self, theme_id: ThemeId) -> List[IndustryChainNode]:
        """根据主题 ID 获取关联的节点列表。"""
        return [node for node in self.nodes if theme_id in node.related_theme_ids]

    def get_all_sectors(self) -> List[str]:
        """获取所有涉及的 A 股板块名称。"""
        return list({node.sector_name for node in self.nodes})

    @property
    def upstream_nodes(self) -> List[IndustryChainNode]:
        """上游节点列表。"""
        return self.get_nodes_by_position(IndustryChainPosition.UPSTREAM)

    @property
    def midstream_nodes(self) -> List[IndustryChainNode]:
        """中游节点列表。"""
        return self.get_nodes_by_position(IndustryChainPosition.MIDSTREAM)

    @property
    def downstream_nodes(self) -> List[IndustryChainNode]:
        """下游节点列表。"""
        return self.get_nodes_by_position(IndustryChainPosition.DOWNSTREAM)


# ---------------------------------------------------------------------------
# 产业链节点定义（主数据）
# ---------------------------------------------------------------------------


def _create_default_industry_chain_map() -> IndustryChainMap:
    """创建默认的产业链映射实例。"""

    nodes: List[IndustryChainNode] = []

    # -----------------------------------------------------------------------
    # 上游 — 基础设施层
    # -----------------------------------------------------------------------

    # 算力节点
    nodes.append(
        IndustryChainNode(
            node_id="compute",
            node_name="算力",
            position=IndustryChainPosition.UPSTREAM,
            description="AI 训练与推理所需的算力基础设施，包括数据中心、算力集群等",
            related_theme_ids=(ThemeId.COMPUTE, ThemeId.CLOUD),
            sector_name="算力",
            related_concepts=("人工智能", "算力", "东数西算", "数据中心"),
            stock_candidates=(
                ("600588", "用友网络"),
                ("000977", "浪潮信息"),
                ("000938", "紫光股份"),
                ("603019", "中科曙光"),
                ("000021", "深科技"),
            ),
            confidence=ConfidenceLevel.HIGH,
            rationale="算力是 AI 产业的基础设施，相关厂商直接受益于 AI 算力需求增长",
        )
    )

    # 存储节点
    nodes.append(
        IndustryChainNode(
            node_id="storage",
            node_name="存储",
            position=IndustryChainPosition.UPSTREAM,
            description="NAND Flash、企业级 SSD、存储控制器及存储系统",
            related_theme_ids=(ThemeId.STORAGE, ThemeId.MEMORY),
            sector_name="存储",
            related_concepts=("存储", "闪存", "SSD", "东数西算"),
            stock_candidates=(
                ("603986", "兆易创新"),
                ("300223", "北京君正"),
                ("000021", "深科技"),
                ("600536", "中国软件"),
            ),
            confidence=ConfidenceLevel.HIGH,
            rationale="AI 大模型训练与推理需要海量存储支持，存储厂商受益于数据量增长",
        )
    )

    # 内存节点
    nodes.append(
        IndustryChainNode(
            node_id="memory",
            node_name="内存",
            position=IndustryChainPosition.UPSTREAM,
            description="高带宽内存（HBM）、DRAM 及内存带宽相关技术",
            related_theme_ids=(ThemeId.MEMORY,),
            sector_name="内存",
            related_concepts=("半导体", "内存", "HBM"),
            stock_candidates=(
                ("603986", "兆易创新"),
                ("300223", "北京君正"),
                ("688525", "佰维存储"),
                ("688126", "沪硅产业"),
            ),
            confidence=ConfidenceLevel.MEDIUM,
            rationale="HBM 是 AI 训练的关键组件，相关厂商受益于 HBM 需求爆发",
        )
    )

    # GPU/AI 芯片节点
    nodes.append(
        IndustryChainNode(
            node_id="gpu",
            node_name="GPU / AI 芯片",
            position=IndustryChainPosition.UPSTREAM,
            description="GPU、NPU、TPU 等 AI 加速芯片的研发与制造",
            related_theme_ids=(ThemeId.GPU, ThemeId.SEMICONDUCTOR),
            sector_name="AI 芯片",
            related_concepts=("芯片", "半导体", "人工智能", "GPU"),
            stock_candidates=(
                ("688256", "寒武纪-U"),
                ("688981", "中芯国际"),
                ("688008", "澜起科技"),
                ("300474", "景嘉微"),
                ("688728", "寒武纪"),
            ),
            confidence=ConfidenceLevel.HIGH,
            rationale="AI 芯片是 AI 产业的核心硬件，国产替代背景下相关厂商成长空间大",
        )
    )

    # 半导体节点
    nodes.append(
        IndustryChainNode(
            node_id="semiconductor",
            node_name="半导体",
            position=IndustryChainPosition.UPSTREAM,
            description="芯片设计、晶圆代工、封装测试、EDA/材料设备等",
            related_theme_ids=(ThemeId.SEMICONDUCTOR, ThemeId.GPU),
            sector_name="半导体",
            related_concepts=("半导体", "芯片", "国产替代", "光刻机"),
            stock_candidates=(
                ("688981", "中芯国际"),
                ("600584", "长电科技"),
                ("600171", "上海贝岭"),
                ("688012", "中微公司"),
                ("688126", "沪硅产业"),
            ),
            confidence=ConfidenceLevel.HIGH,
            rationale="半导体是 AI 产业的底层支撑，国产替代趋势下全产业链受益",
        )
    )

    # 光模块节点
    nodes.append(
        IndustryChainNode(
            node_id="optical_module",
            node_name="光模块",
            position=IndustryChainPosition.UPSTREAM,
            description="数据中心高速光互联，包括光模块、光芯片、硅光技术",
            related_theme_ids=(ThemeId.OPTICAL_MODULE, ThemeId.SUPPLY_CHAIN),
            sector_name="光模块",
            related_concepts=("光模块", "光通信", "5G", "数据中心"),
            stock_candidates=(
                ("300308", "中际旭创"),
                ("300502", "新易盛"),
                ("300394", "天孚通信"),
                ("600487", "华工科技"),
                ("000063", "中兴通讯"),
            ),
            confidence=ConfidenceLevel.HIGH,
            rationale="光模块是 AI 算力网络的关键连接组件，800G/1.6T 升级驱动需求增长",
        )
    )

    # 供应链节点
    nodes.append(
        IndustryChainNode(
            node_id="supply_chain",
            node_name="供应链",
            position=IndustryChainPosition.UPSTREAM,
            description="AI 硬件与基础设施的上下游供应链，含 PCB、电源、散热等",
            related_theme_ids=(ThemeId.SUPPLY_CHAIN, ThemeId.COMPUTE),
            sector_name="AI 供应链",
            related_concepts=("服务器", "PCB", "散热", "电源"),
            stock_candidates=(
                ("002897", "科创新源"),
                ("603268", "松芝股份"),
                ("300739", "明阳电路"),
                ("002916", "深南电路"),
                ("600745", "闻泰科技"),
            ),
            confidence=ConfidenceLevel.MEDIUM,
            rationale="AI 服务器需求增长带动供应链各环节配套需求",
        )
    )

    # -----------------------------------------------------------------------
    # 中游 — 技术与模型层
    # -----------------------------------------------------------------------

    # 基础模型节点
    nodes.append(
        IndustryChainNode(
            node_id="foundation_model",
            node_name="基础模型",
            position=IndustryChainPosition.MIDSTREAM,
            description="预训练大语言模型、多模态模型、模型架构创新",
            related_theme_ids=(ThemeId.FOUNDATION_MODEL, ThemeId.AI),
            sector_name="AI 大模型",
            related_concepts=("人工智能", "大模型", "ChatGPT"),
            stock_candidates=(
                ("300418", "昆仑万维"),
                ("300624", "世纪华通"),
                ("002230", "科大讯飞"),
                ("600588", "用友网络"),
                ("603019", "中科曙光"),
            ),
            confidence=ConfidenceLevel.HIGH,
            rationale="大模型是 AI 产业的核心技术引擎，相关厂商具备技术壁垒",
        )
    )

    # 云服务节点
    nodes.append(
        IndustryChainNode(
            node_id="cloud",
            node_name="云服务",
            position=IndustryChainPosition.MIDSTREAM,
            description="公有云、私有云、云厂商算力投入、云 AI 服务",
            related_theme_ids=(ThemeId.CLOUD, ThemeId.COMPUTE),
            sector_name="云服务",
            related_concepts=("云计算", "云服务", "人工智能"),
            stock_candidates=(
                ("600588", "用友网络"),
                ("000938", "紫光股份"),
                ("603019", "中科曙光"),
                ("600845", "宝信软件"),
                ("002410", "广联达"),
            ),
            confidence=ConfidenceLevel.HIGH,
            rationale="云服务是 AI 能力输出的主要渠道，云厂商受益于 AI 算力需求",
        )
    )

    # -----------------------------------------------------------------------
    # 下游 — 应用层
    # -----------------------------------------------------------------------

    # AI 应用节点
    nodes.append(
        IndustryChainNode(
            node_id="ai_application",
            node_name="AI 应用",
            position=IndustryChainPosition.DOWNSTREAM,
            description="AI 在各行业的落地应用，包括 AIGC、智能体、自动驾驶等",
            related_theme_ids=(ThemeId.AI_APPLICATION, ThemeId.AI),
            sector_name="AI 应用",
            related_concepts=("人工智能", "AIGC", "应用落地"),
            stock_candidates=(
                ("300418", "昆仑万维"),
                ("002230", "科大讯飞"),
                ("002607", "中公教育"),
                ("300251", "光线传媒"),
                ("002230", "科大讯飞"),
                ("300496", "中科创达"),
            ),
            confidence=ConfidenceLevel.HIGH,
            rationale="AI 应用是 AI 技术价值兑现的关键环节，各垂直领域应用空间广阔",
        )
    )

    # 人工智能全产业节点
    nodes.append(
        IndustryChainNode(
            node_id="ai_full",
            node_name="人工智能",
            position=IndustryChainPosition.FULL_CHAIN,
            description="涵盖 AI 行业整体动态，包括大模型研发、AI 政策、行业投融资等",
            related_theme_ids=(ThemeId.AI,),
            sector_name="人工智能",
            related_concepts=("人工智能", "AI", "数字经济"),
            stock_candidates=(
                ("002230", "科大讯飞"),
                ("300418", "昆仑万维"),
                ("603019", "中科曙光"),
                ("600588", "用友网络"),
                ("000938", "紫光股份"),
            ),
            confidence=ConfidenceLevel.MEDIUM,
            rationale="AI 全产业链受益于产业趋势，综合性厂商具备全栈能力",
        )
    )

    return IndustryChainMap(nodes=tuple(nodes))


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


# 默认产业链映射单例
_DEFAULT_INDUSTRY_CHAIN_MAP: Optional[IndustryChainMap] = None


def get_industry_chain_map() -> IndustryChainMap:
    """获取默认的产业链映射实例（单例）。"""
    global _DEFAULT_INDUSTRY_CHAIN_MAP
    if _DEFAULT_INDUSTRY_CHAIN_MAP is None:
        _DEFAULT_INDUSTRY_CHAIN_MAP = _create_default_industry_chain_map()
    return _DEFAULT_INDUSTRY_CHAIN_MAP


def reload_industry_chain_map() -> IndustryChainMap:
    """重新加载产业链映射（用于更新后刷新）。"""
    global _DEFAULT_INDUSTRY_CHAIN_MAP
    _DEFAULT_INDUSTRY_CHAIN_MAP = _create_default_industry_chain_map()
    return _DEFAULT_INDUSTRY_CHAIN_MAP
