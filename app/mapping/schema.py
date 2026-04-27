"""
A 股映射数据结构（A-share Mapping Data Models）

定义三层映射结构：
1. 行业/板块与产业链环节映射（SectorMapping）
2. 候选标的池映射（StockPoolMapping）
3. 具体个股映射（IndividualStockMapping）

所有结构均附带置信度分级（ConfidenceLevel），避免将弱信号写成强推荐。

设计决策
--------
- 所有模型使用 frozen dataclass，可安全哈希/缓存/并发读取。
- 置信度使用枚举（HIGH/MEDIUM/LOW）而非连续值，符合业务决策场景。
- 支持多个映射条目，允许一条信息链映射到多个行业板块或个股方向。
- 每个映射条目均包含理由说明（rationale），便于人工复核与审计。
- 旁证引用（Evidence Reference）支持追溯原始新闻/信息链和具体文本片段。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence


# ---------------------------------------------------------------------------
# ConfidenceLevel — 置信度分级
# ---------------------------------------------------------------------------


class ConfidenceLevel(str, Enum):
    """
    置信度分级，用于标注 A 股映射结论的可靠程度。

    取值
    ----
    HIGH
        强信号，高置信度，有充分证据支持该映射结论。
    MEDIUM
        中等信号，有部分证据支持，但仍需进一步确认。
    LOW
        弱信号，仅基于间接证据或推测，仅供参考。
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# SectorMapping — 行业/板块与产业链环节映射
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectorMapping:
    """
    行业/板块与产业链环节映射。

    字段
    ----
    sector_name
        A 股行业/板块名称，例如 "人工智能"、"算力"、"光模块"、"半导体"。
    chain_segment
        产业链环节，例如 "上游"、"中游"、"下游"、"全产业链"。
    confidence
        置信度分级，用于标注该映射的可靠程度。
    rationale
        映射理由说明，解释为什么该信息链与该行业/板块相关。
    theme_ids
        关联的主题 ID 列表，可选，用于追溯映射依据。
    """

    sector_name: str
    chain_segment: str
    confidence: ConfidenceLevel
    rationale: str
    theme_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.sector_name:
            raise ValueError("SectorMapping.sector_name 不能为空字符串。")
        if not self.chain_segment:
            raise ValueError("SectorMapping.chain_segment 不能为空字符串。")
        if not self.rationale:
            raise ValueError("SectorMapping.rationale 不能为空字符串。")


# ---------------------------------------------------------------------------
# StockPoolMapping — 候选标的池映射
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockPoolMapping:
    """
    候选标的池映射，定义一类受益标的而非具体个股。

    字段
    ----
    pool_name
        标的池名称，例如 "算力设备商"、"光模块龙头"、"AI 应用厂商"。
    criteria
        标的筛选标准描述，例如 "市值 > 100 亿，光模块收入占比 > 30%"。
    confidence
        置信度分级，用于标注该映射的可靠程度。
    rationale
        映射理由说明，解释为什么该类标的受益于该信息链。
    sector_name
        关联的行业/板块名称，可选，用于与 SectorMapping 关联。
    """

    pool_name: str
    criteria: str
    confidence: ConfidenceLevel
    rationale: str
    sector_name: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.pool_name:
            raise ValueError("StockPoolMapping.pool_name 不能为空字符串。")
        if not self.criteria:
            raise ValueError("StockPoolMapping.criteria 不能为空字符串。")
        if not self.rationale:
            raise ValueError("StockPoolMapping.rationale 不能为空字符串。")


# ---------------------------------------------------------------------------
# IndividualStockMapping — 具体个股映射
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndividualStockMapping:
    """
    具体个股映射。

    字段
    ----
    stock_code
        A 股股票代码，例如 "600519"、"300750"。
    stock_name
        股票名称，例如 "贵州茅台"、"宁德时代"。
    confidence
        置信度分级，用于标注该映射的可靠程度。
    rationale
        映射理由说明，解释为什么该个股受益于该信息链。
    impact_direction
        影响方向，例如 "受益"、"受损"、"中性"。
    pool_name
        关联的标的池名称，可选，用于与 StockPoolMapping 关联。
    notes
        附加说明，例如 "需进一步验证订单情况"、"估值已较高"。
    """

    stock_code: str
    stock_name: str
    confidence: ConfidenceLevel
    rationale: str
    impact_direction: str = "受益"
    pool_name: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.stock_code:
            raise ValueError("IndividualStockMapping.stock_code 不能为空字符串。")
        if not self.stock_name:
            raise ValueError("IndividualStockMapping.stock_name 不能为空字符串。")
        if not self.rationale:
            raise ValueError("IndividualStockMapping.rationale 不能为空字符串。")
        if not self.impact_direction:
            raise ValueError("IndividualStockMapping.impact_direction 不能为空字符串。")


# ---------------------------------------------------------------------------
# AStockMapping — 完整的 A 股映射结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AStockMapping:
    """
    完整的 A 股映射结构，包含三层映射。

    字段
    ----
    chain_id
        关联的信息链 ID，用于追溯映射来源。
    sector_mappings
        行业/板块映射列表，可为空。
    stock_pool_mappings
        候选标的池映射列表，可为空。
    individual_stock_mappings
        具体个股映射列表，可为空。
    overall_confidence
        整体置信度分级，用于标注整条映射的可靠程度。
    summary
        A 股视角的总结说明。
    generated_at
        映射生成时间（ISO-8601 UTC 字符串）。
    """

    chain_id: str
    sector_mappings: tuple[SectorMapping, ...]
    stock_pool_mappings: tuple[StockPoolMapping, ...]
    individual_stock_mappings: tuple[IndividualStockMapping, ...]
    overall_confidence: ConfidenceLevel
    summary: str
    generated_at: str

    def __post_init__(self) -> None:
        if not self.chain_id:
            raise ValueError("AStockMapping.chain_id 不能为空字符串。")
        if not self.summary:
            raise ValueError("AStockMapping.summary 不能为空字符串。")
        if not self.generated_at:
            raise ValueError("AStockMapping.generated_at 不能为空字符串。")

    @property
    def is_empty(self) -> bool:
        """判断是否包含任何映射内容。"""
        return (
            len(self.sector_mappings) == 0
            and len(self.stock_pool_mappings) == 0
            and len(self.individual_stock_mappings) == 0
        )


# ---------------------------------------------------------------------------
# MappingScoreDimensions — 可映射性评分维度
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MappingScoreDimensions:
    """
    A 股可映射性评分维度。

    字段
    ----
    theme_match_score
        主题匹配度评分（0-100）：信息链主题与 A 股产业链节点的匹配程度。
    chain_clarity_score
        产业链清晰度评分（0-100）：产业链环节定位的明确程度。
    confidence_weighted_score
        置信度加权评分（0-100）：基于置信度分级的加权得分。
    timeliness_score
        时效性评分（0-100）：信息的时效性对投资决策的价值。
    coverage_score
        覆盖度评分（0-100）：三层映射（板块/标的池/个股）的完整程度。
    """

    theme_match_score: float
    chain_clarity_score: float
    confidence_weighted_score: float
    timeliness_score: float
    coverage_score: float

    def __post_init__(self) -> None:
        for field_name, value in [
            ("theme_match_score", self.theme_match_score),
            ("chain_clarity_score", self.chain_clarity_score),
            ("confidence_weighted_score", self.confidence_weighted_score),
            ("timeliness_score", self.timeliness_score),
            ("coverage_score", self.coverage_score),
        ]:
            if not (0.0 <= value <= 100.0):
                raise ValueError(f"{field_name} 必须在 0-100 范围内，当前值：{value}")

    @property
    def dimension_scores(self) -> dict[str, float]:
        """获取所有维度的分数字典。"""
        return {
            "theme_match_score": self.theme_match_score,
            "chain_clarity_score": self.chain_clarity_score,
            "confidence_weighted_score": self.confidence_weighted_score,
            "timeliness_score": self.timeliness_score,
            "coverage_score": self.coverage_score,
        }


# ---------------------------------------------------------------------------
# AShareMappingScore — A 股可映射性评分
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AShareMappingScore:
    """
    A 股可映射性评分，包含各维度评分和总体评分。

    字段
    ----
    chain_id
        关联的信息链 ID。
    dimensions
        各维度评分详情。
    overall_score
        总体可映射性评分（0-100），加权汇总各维度得分。
    score_level
        评分等级："excellent"（优秀）、"good"（良好）、"fair"（一般）、"poor"（较差）。
    rationale
        评分理由说明，解释评分依据。
    scored_at
        评分生成时间（ISO-8601 UTC 字符串）。
    """

    chain_id: str
    dimensions: MappingScoreDimensions
    overall_score: float
    score_level: str
    rationale: str
    scored_at: str

    def __post_init__(self) -> None:
        if not self.chain_id:
            raise ValueError("AShareMappingScore.chain_id 不能为空字符串。")
        if not (0.0 <= self.overall_score <= 100.0):
            raise ValueError(f"overall_score 必须在 0-100 范围内，当前值：{self.overall_score}")
        if self.score_level not in {"excellent", "good", "fair", "poor"}:
            raise ValueError(f"score_level 必须是 'excellent'/'good'/'fair'/'poor' 之一，当前值：{self.score_level}")
        if not self.rationale:
            raise ValueError("AShareMappingScore.rationale 不能为空字符串。")
        if not self.scored_at:
            raise ValueError("AShareMappingScore.scored_at 不能为空字符串。")

    @classmethod
    def score_level_from_score(cls, score: float) -> str:
        """根据总体评分确定评分等级。"""
        if score >= 80.0:
            return "excellent"
        elif score >= 60.0:
            return "good"
        elif score >= 40.0:
            return "fair"
        else:
            return "poor"


# ---------------------------------------------------------------------------
# EvidenceSourceReference — 证据来源引用
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceSourceReference:
    """
    证据来源引用，指向原始新闻/信息链。

    字段
    ----
    chain_id
        关联的信息链 ID。
    node_position
        节点在信息链中的位置（0-based），可选。
    news_item_id
        关联的新闻项 ID，可选。
    source_name
        来源名称，如 "财联社"、"CCTV" 等，可选。
    published_at
        新闻发布时间（ISO-8601 UTC 字符串），可选。
    """

    chain_id: str
    node_position: Optional[int] = None
    news_item_id: Optional[str] = None
    source_name: Optional[str] = None
    published_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.chain_id:
            raise ValueError("EvidenceSourceReference.chain_id 不能为空字符串。")


# ---------------------------------------------------------------------------
# EvidenceSnippetReference — 证据片段引用
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceSnippetReference:
    """
    证据片段引用，指向具体的文本片段。

    字段
    ----
    snippet
        命中原文片段。
    context_before
        snippet 左侧的上下文文本（最多 context_window 字符）。
    context_after
        snippet 右侧的上下文文本（最多 context_window 字符）。
    start_offset
        snippet 在原始文本中的起始偏移（inclusive，Unicode 码点）。
    end_offset
        snippet 在原始文本中的结束偏移（exclusive）。
    label_id
        关联的标签 ID（主题 ID 或实体类型 ID），可选。
    label_kind
        标签类型："theme" 或 "entity_type"，可选。
    """

    snippet: str
    context_before: str
    context_after: str
    start_offset: int
    end_offset: int
    label_id: Optional[str] = None
    label_kind: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.snippet:
            raise ValueError("EvidenceSnippetReference.snippet 不能为空字符串。")
        if self.start_offset < 0:
            raise ValueError("EvidenceSnippetReference.start_offset 不能为负数。")
        if self.end_offset <= self.start_offset:
            raise ValueError("EvidenceSnippetReference.end_offset 必须大于 start_offset。")
        if self.label_kind is not None and self.label_kind not in {"theme", "entity_type"}:
            raise ValueError("EvidenceSnippetReference.label_kind 必须是 'theme'/'entity_type' 之一或 None。")


# ---------------------------------------------------------------------------
# MappingEvidence — 映射旁证关联
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MappingEvidence:
    """
    映射旁证关联，将映射结果与证据关联。

    字段
    ----
    mapping_type
        映射类型："sector"、"stock_pool" 或 "individual_stock"。
    mapping_identifier
        映射标识符（如 sector_name、pool_name、stock_code）。
    source_reference
        证据来源引用。
    snippet_references
        证据片段引用列表，可为空。
    rationale
        旁证说明，解释此证据如何支持该映射。
    """

    mapping_type: str
    mapping_identifier: str
    source_reference: EvidenceSourceReference
    snippet_references: tuple[EvidenceSnippetReference, ...]
    rationale: str

    def __post_init__(self) -> None:
        if self.mapping_type not in {"sector", "stock_pool", "individual_stock"}:
            raise ValueError("MappingEvidence.mapping_type 必须是 'sector'/'stock_pool'/'individual_stock' 之一。")
        if not self.mapping_identifier:
            raise ValueError("MappingEvidence.mapping_identifier 不能为空字符串。")
        if not self.rationale:
            raise ValueError("MappingEvidence.rationale 不能为空字符串。")


# ---------------------------------------------------------------------------
# AShareMappingWithEvidence — 带旁证的 A 股映射
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AShareMappingWithEvidence:
    """
    带旁证的完整 A 股映射。

    字段
    ----
    mapping
        基础的 A 股映射结构。
    evidences
        旁证关联列表，可为空。
    """

    mapping: AStockMapping
    evidences: tuple[MappingEvidence, ...]

    def __post_init__(self) -> None:
        pass

    @property
    def chain_id(self) -> str:
        """获取关联的信息链 ID。"""
        return self.mapping.chain_id

    @property
    def has_evidences(self) -> bool:
        """判断是否有旁证。"""
        return len(self.evidences) > 0

    def get_evidences_for_sector(self, sector_name: str) -> list[MappingEvidence]:
        """获取指定板块的旁证。"""
        return [
            e for e in self.evidences
            if e.mapping_type == "sector" and e.mapping_identifier == sector_name
        ]

    def get_evidences_for_stock_pool(self, pool_name: str) -> list[MappingEvidence]:
        """获取指定标的池的旁证。"""
        return [
            e for e in self.evidences
            if e.mapping_type == "stock_pool" and e.mapping_identifier == pool_name
        ]

    def get_evidences_for_stock(self, stock_code: str) -> list[MappingEvidence]:
        """获取指定个股的旁证。"""
        return [
            e for e in self.evidences
            if e.mapping_type == "individual_stock" and e.mapping_identifier == stock_code
        ]
