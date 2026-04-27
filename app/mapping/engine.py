"""
A 股映射引擎（Mapping Engine）

实现从 TaggedOutput/InformationChain 到 AStockMapping 的转换规则。
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.chains.chain import InformationChain
from app.entity.tagged_output import TaggedOutput
from app.entity.themes import ThemeId
from app.mapping.industry_chain import (
    IndustryChainMap,
    IndustryChainNode,
    IndustryChainPosition,
    get_industry_chain_map,
)
from app.mapping.akshare_resolver import AkShareStockResolver, create_akshare_resolver
from app.mapping.schema import (
    AStockMapping,
    ConfidenceLevel,
    IndividualStockMapping,
    SectorMapping,
    StockPoolMapping,
    MappingScoreDimensions,
    AShareMappingScore,
    EvidenceSourceReference,
    EvidenceSnippetReference,
    MappingEvidence,
    AShareMappingWithEvidence,
)


# ---------------------------------------------------------------------------
# MappingResult — 单次映射结果
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MappingResult:
    """
    单次映射的结果，包含映射和元数据。
    """

    mapping: AStockMapping
    source_chain_id: str
    matched_theme_count: int
    mapped_at: str


# ---------------------------------------------------------------------------
# AShareMappingEngine — A 股映射引擎
# ---------------------------------------------------------------------------


class AShareMappingEngine:
    """
    A 股映射引擎，实现从信息链到 A 股映射的转换规则。

    Parameters
    ----------
    industry_chain_map
        自定义产业链映射，默认使用全局单例。
    stock_resolver
        可选的 AkShare 股票解析器，用于动态补充个股映射。
        为 ``None`` 时完全依赖硬编码 ``stock_candidates``（向后兼容）。
    """

    def __init__(
        self,
        industry_chain_map: Optional[IndustryChainMap] = None,
        stock_resolver: Optional[AkShareStockResolver] = None,
    ) -> None:
        self._chain_map = industry_chain_map or get_industry_chain_map()
        self._stock_resolver = stock_resolver

    def map_tagged_output(
        self,
        tagged_output: TaggedOutput,
    ) -> AStockMapping:
        """
        将单个 TaggedOutput 映射为 AStockMapping。
        """
        chain_id = str(uuid.uuid4())
        return self._build_mapping(
            chain_id=chain_id,
            theme_ids=tuple(tagged_output.theme_ids),
            summary_text=tagged_output.text[:200] if tagged_output.text else "",
        )

    def map_information_chain(
        self,
        chain: InformationChain,
    ) -> AStockMapping:
        """
        将 InformationChain 映射为 AStockMapping。
        """
        return self._build_mapping(
            chain_id=chain.chain_id,
            theme_ids=chain.theme_ids,
            summary_text=self._extract_chain_summary(chain),
        )

    def map_multiple_chains(
        self,
        chains: Sequence[InformationChain],
    ) -> List[MappingResult]:
        """
        批量映射多个 InformationChain。
        """
        results = []
        for chain in chains:
            mapping = self.map_information_chain(chain)
            result = MappingResult(
                mapping=mapping,
                source_chain_id=chain.chain_id,
                matched_theme_count=len(mapping.sector_mappings),
                mapped_at=datetime.datetime.now(datetime.UTC).isoformat(),
            )
            results.append(result)
        return results

    # ---------------------------------------------------------------------------
    # Internal methods
    # ---------------------------------------------------------------------------

    def _build_mapping(
        self,
        chain_id: str,
        theme_ids: Tuple[str, ...],
        summary_text: str,
    ) -> AStockMapping:
        """
        内部方法：构建完整的 A 股映射。
        """
        sector_mappings = self._build_sector_mappings(theme_ids)
        stock_pool_mappings = self._build_stock_pool_mappings(theme_ids, sector_mappings)
        individual_stock_mappings = self._build_individual_stock_mappings(
            theme_ids,
            sector_mappings,
        )

        overall_confidence = self._calculate_overall_confidence(
            sector_mappings,
            stock_pool_mappings,
            individual_stock_mappings,
        )

        summary = self._build_summary(summary_text, sector_mappings)

        return AStockMapping(
            chain_id=chain_id,
            sector_mappings=tuple(sector_mappings),
            stock_pool_mappings=tuple(stock_pool_mappings),
            individual_stock_mappings=tuple(individual_stock_mappings),
            overall_confidence=overall_confidence,
            summary=summary,
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    def _build_sector_mappings(
        self,
        theme_ids: Tuple[str, ...],
    ) -> List[SectorMapping]:
        """
        构建行业/板块映射。
        """
        mappings = []
        matched_nodes: List[IndustryChainNode] = []

        # 查找匹配的产业链节点
        for theme_id_str in theme_ids:
            try:
                theme_id = ThemeId(theme_id_str)
                nodes = self._chain_map.get_nodes_by_theme(theme_id)
                matched_nodes.extend(nodes)
            except ValueError:
                continue  # 忽略未知的主题 ID

        # 去重（按 node_id）
        seen_node_ids = set()
        unique_nodes = []
        for node in matched_nodes:
            if node.node_id not in seen_node_ids:
                seen_node_ids.add(node.node_id)
                unique_nodes.append(node)

        # 构建 SectorMapping
        for node in unique_nodes:
            mapping = SectorMapping(
                sector_name=node.sector_name,
                chain_segment=self._position_to_segment(node.position),
                confidence=node.confidence,
                rationale=node.rationale,
                theme_ids=node.related_theme_ids,
            )
            mappings.append(mapping)

        return mappings

    def _build_stock_pool_mappings(
        self,
        theme_ids: Tuple[str, ...],
        sector_mappings: List[SectorMapping],
    ) -> List[StockPoolMapping]:
        """
        构建候选标的池映射。
        """
        mappings = []
        sector_names = {sm.sector_name for sm in sector_mappings}

        for sector in sector_mappings:
            # 为每个板块创建一个标的池映射
            pool_name = f"{sector.sector_name} 受益标的"
            criteria = f"{sector.sector_name} 产业链相关，受益于 AI 趋势"
            rationale = f"{sector.rationale}，建议关注相关标的"

            mapping = StockPoolMapping(
                pool_name=pool_name,
                criteria=criteria,
                confidence=sector.confidence,
                rationale=rationale,
                sector_name=sector.sector_name,
            )
            mappings.append(mapping)

        return mappings

    def _build_individual_stock_mappings(
        self,
        theme_ids: Tuple[str, ...],
        sector_mappings: List[SectorMapping],
    ) -> List[IndividualStockMapping]:
        """
        构建具体个股映射。

        当 ``stock_resolver`` 存在时，会通过 AkShare 动态补充板块成分股，
        与硬编码 ``stock_candidates`` 合并后去重输出。
        """
        mappings = []
        seen_codes = set()

        # 从产业链节点获取候选股票，按 sector 精确匹配
        for sector in sector_mappings:
            for theme_id_str in sector.theme_ids:
                try:
                    theme_id = ThemeId(theme_id_str)
                except ValueError:
                    continue
                nodes = self._chain_map.get_nodes_by_theme(theme_id)
                for node in nodes:
                    if node.sector_name != sector.sector_name:
                        continue

                    # 获取候选股票：优先使用 resolver 动态扩展，否则回退硬编码
                    if self._stock_resolver is not None:
                        candidates = self._stock_resolver.resolve_stocks_for_node(node)
                    else:
                        candidates = node.stock_candidates

                    for stock_code, stock_name in candidates:
                        if stock_code not in seen_codes:
                            seen_codes.add(stock_code)
                            mapping = IndividualStockMapping(
                                stock_code=stock_code,
                                stock_name=stock_name,
                                confidence=ConfidenceLevel.MEDIUM,
                                rationale=f"{stock_name} 属于 {node.sector_name} 板块，受益于 AI 产业趋势",
                                impact_direction="受益",
                                pool_name=f"{node.sector_name} 受益标的",
                                notes="建议结合基本面和估值进一步分析",
                            )
                            mappings.append(mapping)

        # 最多返回 10 个个股映射，避免输出过多
        return mappings[:10]

    def _calculate_overall_confidence(
        self,
        sector_mappings: List[SectorMapping],
        stock_pool_mappings: List[StockPoolMapping],
        individual_stock_mappings: List[IndividualStockMapping],
    ) -> ConfidenceLevel:
        """
        计算整体置信度。
        """
        if not sector_mappings:
            return ConfidenceLevel.LOW

        # 统计各置信等级的数量
        high_count = sum(1 for sm in sector_mappings if sm.confidence == ConfidenceLevel.HIGH)
        medium_count = sum(1 for sm in sector_mappings if sm.confidence == ConfidenceLevel.MEDIUM)

        if high_count >= 2:
            return ConfidenceLevel.HIGH
        elif high_count >= 1 or medium_count >= 2:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _build_summary(
        self,
        source_text: str,
        sector_mappings: List[SectorMapping],
    ) -> str:
        """
        构建 A 股视角总结。
        """
        if not sector_mappings:
            return "暂未发现明确的 A 股受益方向"

        sector_names = [sm.sector_name for sm in sector_mappings[:5]]
        sector_list = "、".join(sector_names)

        if len(sector_mappings) > 5:
            sector_list += f" 等 {len(sector_mappings)} 个板块"

        summary = f"当前事件主要涉及 A 股 {sector_list} 板块"

        if source_text:
            summary += f"，核心信息：{source_text[:100]}"

        return summary

    def _extract_chain_summary(self, chain: InformationChain) -> str:
        """
        从信息链提取摘要文本。
        """
        if not chain.nodes:
            return ""

        # 使用第一个节点的文本作为基础
        first_node = chain.nodes[0]
        text = first_node.tagged_output.text
        return text[:200] if text else ""

    def _position_to_segment(self, position: IndustryChainPosition) -> str:
        """
        将产业链位置枚举转换为中文字符串。
        """
        return position.value


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def create_mapping_engine(
    stock_resolver: Optional[AkShareStockResolver] = None,
) -> AShareMappingEngine:
    """
    创建默认配置的 A 股映射引擎。

    Parameters
    ----------
    stock_resolver
        可选的 AkShare 股票解析器，注入后可动态扩展个股映射。
    """
    return AShareMappingEngine(stock_resolver=stock_resolver)


def map_chain_to_a_share(chain: InformationChain) -> AStockMapping:
    """
    便捷函数：将单个信息链映射为 A 股映射。
    """
    engine = create_mapping_engine()
    return engine.map_information_chain(chain)


# ---------------------------------------------------------------------------
# Mapping Scoring — 可映射性评分
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoringResult:
    """
    评分结果，包含映射和评分。
    """

    mapping: AStockMapping
    score: AShareMappingScore
    source_chain_id: str
    scored_at: str


class MappingScoringEngine:
    """
    A 股可映射性评分引擎。

    评分维度：
    - theme_match_score（主题匹配度）：0-100
    - chain_clarity_score（产业链清晰度）：0-100
    - confidence_weighted_score（置信度加权）：0-100
    - timeliness_score（时效性）：0-100（默认 80，可扩展）
    - coverage_score（覆盖度）：0-100

    总体评分采用加权平均：
    - 主题匹配度：30%
    - 产业链清晰度：25%
    - 置信度加权：25%
    - 时效性：10%
    - 覆盖度：10%
    """

    # 维度权重
    THEME_MATCH_WEIGHT = 0.30
    CHAIN_CLARITY_WEIGHT = 0.25
    CONFIDENCE_WEIGHT = 0.25
    TIMELINESS_WEIGHT = 0.10
    COVERAGE_WEIGHT = 0.10

    # 置信度对应分数
    CONFIDENCE_SCORES = {
        ConfidenceLevel.HIGH: 100.0,
        ConfidenceLevel.MEDIUM: 65.0,
        ConfidenceLevel.LOW: 30.0,
    }

    def __init__(
        self,
        industry_chain_map: Optional[IndustryChainMap] = None,
    ) -> None:
        self._chain_map = industry_chain_map or get_industry_chain_map()

    def score_mapping(
        self,
        mapping: AStockMapping,
        theme_ids: Optional[Tuple[str, ...]] = None,
    ) -> AShareMappingScore:
        """
        为 AStockMapping 计算可映射性评分。
        """
        dimensions = self._calculate_dimensions(mapping, theme_ids)
        overall_score = self._calculate_overall_score(dimensions)
        score_level = AShareMappingScore.score_level_from_score(overall_score)
        rationale = self._build_score_rationale(dimensions, overall_score, score_level)

        return AShareMappingScore(
            chain_id=mapping.chain_id,
            dimensions=dimensions,
            overall_score=overall_score,
            score_level=score_level,
            rationale=rationale,
            scored_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    def score_chain(
        self,
        chain: InformationChain,
    ) -> ScoringResult:
        """
        为 InformationChain 同时生成映射和评分。
        """
        engine = AShareMappingEngine(self._chain_map)
        mapping = engine.map_information_chain(chain)
        score = self.score_mapping(mapping, chain.theme_ids)

        return ScoringResult(
            mapping=mapping,
            score=score,
            source_chain_id=chain.chain_id,
            scored_at=score.scored_at,
        )

    def score_multiple_chains(
        self,
        chains: Sequence[InformationChain],
    ) -> List[ScoringResult]:
        """
        批量为多条信息链生成映射和评分。
        """
        return [self.score_chain(chain) for chain in chains]

    # ---------------------------------------------------------------------------
    # Internal scoring methods
    # ---------------------------------------------------------------------------

    def _calculate_dimensions(
        self,
        mapping: AStockMapping,
        theme_ids: Optional[Tuple[str, ...]],
    ) -> MappingScoreDimensions:
        """
        计算各维度评分。
        """
        theme_match_score = self._calculate_theme_match_score(mapping, theme_ids)
        chain_clarity_score = self._calculate_chain_clarity_score(mapping)
        confidence_weighted_score = self._calculate_confidence_weighted_score(mapping)
        timeliness_score = self._calculate_timeliness_score(mapping)
        coverage_score = self._calculate_coverage_score(mapping)

        return MappingScoreDimensions(
            theme_match_score=theme_match_score,
            chain_clarity_score=chain_clarity_score,
            confidence_weighted_score=confidence_weighted_score,
            timeliness_score=timeliness_score,
            coverage_score=coverage_score,
        )

    def _calculate_theme_match_score(
        self,
        mapping: AStockMapping,
        theme_ids: Optional[Tuple[str, ...]],
    ) -> float:
        """
        计算主题匹配度评分。

        基于：
        - 匹配的主题数量
        - 主题与产业链节点的关联程度
        """
        if not theme_ids:
            # 从 mapping 的 sector_mappings 中提取主题
            all_theme_ids = set()
            for sm in mapping.sector_mappings:
                all_theme_ids.update(sm.theme_ids)
            theme_count = len(all_theme_ids)
        else:
            theme_count = len(theme_ids)

        # 主题数量评分：0 个主题得 0 分，1 个得 40，2 个得 70，3+ 个得 100
        if theme_count == 0:
            base_score = 0.0
        elif theme_count == 1:
            base_score = 40.0
        elif theme_count == 2:
            base_score = 70.0
        else:
            base_score = 100.0

        # 板块映射数量加成
        sector_bonus = min(len(mapping.sector_mappings) * 10, 20)

        return min(base_score + sector_bonus, 100.0)

    def _calculate_chain_clarity_score(
        self,
        mapping: AStockMapping,
    ) -> float:
        """
        计算产业链清晰度评分。

        基于：
        - 产业链环节分布的明确程度
        - 是否覆盖上下游
        """
        if not mapping.sector_mappings:
            return 0.0

        segments = {sm.chain_segment for sm in mapping.sector_mappings}

        # 环节多样性评分
        if len(segments) >= 3:
            diversity_score = 100.0
        elif len(segments) == 2:
            diversity_score = 75.0
        elif len(segments) == 1:
            diversity_score = 50.0
        else:
            diversity_score = 0.0

        # 关键环节覆盖检查
        has_upstream = "上游" in segments
        has_midstream = "中游" in segments
        has_downstream = "下游" in segments

        if has_upstream and has_midstream and has_downstream:
            coverage_bonus = 20.0
        elif (has_upstream and has_midstream) or (has_midstream and has_downstream):
            coverage_bonus = 10.0
        else:
            coverage_bonus = 0.0

        return min(diversity_score + coverage_bonus, 100.0)

    def _calculate_confidence_weighted_score(
        self,
        mapping: AStockMapping,
    ) -> float:
        """
        计算置信度加权评分。

        基于各层映射的置信度分级。
        """
        all_mappings = (
            list(mapping.sector_mappings)
            + list(mapping.stock_pool_mappings)
            + list(mapping.individual_stock_mappings)
        )

        if not all_mappings:
            return 0.0

        # 计算平均置信度分数
        total_score = sum(
            self.CONFIDENCE_SCORES.get(m.confidence, 0.0)
            for m in all_mappings
        )
        avg_score = total_score / len(all_mappings)

        # 整体置信度加成
        overall_bonus = self.CONFIDENCE_SCORES.get(mapping.overall_confidence, 0.0) * 0.2

        return min(avg_score + overall_bonus, 100.0)

    def _calculate_timeliness_score(
        self,
        mapping: AStockMapping,
    ) -> float:
        """
        计算时效性评分。

        目前默认 80 分，后续可扩展为基于新闻时间与当前时间的差值计算。
        """
        # 默认 80 分，后续可根据实际需求扩展
        return 80.0

    def _calculate_coverage_score(
        self,
        mapping: AStockMapping,
    ) -> float:
        """
        计算覆盖度评分。

        基于三层映射（板块/标的池/个股）的完整程度。
        """
        coverage_score = 0.0

        # 板块层
        if mapping.sector_mappings:
            coverage_score += 35.0
            if len(mapping.sector_mappings) >= 3:
                coverage_score += 10.0  # 数量加成

        # 标的池层
        if mapping.stock_pool_mappings:
            coverage_score += 25.0

        # 个股层
        if mapping.individual_stock_mappings:
            coverage_score += 20.0
            if len(mapping.individual_stock_mappings) >= 5:
                coverage_score += 10.0  # 数量加成

        return min(coverage_score, 100.0)

    def _calculate_overall_score(
        self,
        dimensions: MappingScoreDimensions,
    ) -> float:
        """
        计算总体评分（加权平均）。
        """
        overall = (
            dimensions.theme_match_score * self.THEME_MATCH_WEIGHT
            + dimensions.chain_clarity_score * self.CHAIN_CLARITY_WEIGHT
            + dimensions.confidence_weighted_score * self.CONFIDENCE_WEIGHT
            + dimensions.timeliness_score * self.TIMELINESS_WEIGHT
            + dimensions.coverage_score * self.COVERAGE_WEIGHT
        )
        return round(overall, 2)

    def _build_score_rationale(
        self,
        dimensions: MappingScoreDimensions,
        overall_score: float,
        score_level: str,
    ) -> str:
        """
        构建评分理由说明。
        """
        level_descriptions = {
            "excellent": "可映射性优秀，强烈推荐纳入关注",
            "good": "可映射性良好，建议重点关注",
            "fair": "可映射性一般，可适度关注",
            "poor": "可映射性较差，建议观望",
        }

        rationale = (
            f"{level_descriptions.get(score_level, '可映射性待评估')}。"
            f"总体评分 {overall_score:.1f} 分。"
            f"主题匹配度 {dimensions.theme_match_score:.0f} 分，"
            f"产业链清晰度 {dimensions.chain_clarity_score:.0f} 分，"
            f"置信度加权 {dimensions.confidence_weighted_score:.0f} 分，"
            f"时效性 {dimensions.timeliness_score:.0f} 分，"
            f"覆盖度 {dimensions.coverage_score:.0f} 分。"
        )

        return rationale


# ---------------------------------------------------------------------------
# Scoring convenience functions
# ---------------------------------------------------------------------------


def create_scoring_engine() -> MappingScoringEngine:
    """
    创建默认配置的评分引擎。
    """
    return MappingScoringEngine()


def score_chain(chain: InformationChain) -> ScoringResult:
    """
    便捷函数：为单个信息链生成映射和评分。
    """
    engine = create_scoring_engine()
    return engine.score_chain(chain)


def score_mapping(mapping: AStockMapping, theme_ids: Optional[Tuple[str, ...]] = None) -> AShareMappingScore:
    """
    便捷函数：为现有映射计算评分。
    """
    engine = create_scoring_engine()
    return engine.score_mapping(mapping, theme_ids)


# ---------------------------------------------------------------------------
# Evidence Collection — 旁证收集
# ---------------------------------------------------------------------------


class MappingEvidenceCollector:
    """
    映射旁证收集器，从 TaggedOutput/InformationChain 中提取证据并与映射关联。
    """

    def __init__(
        self,
        industry_chain_map: Optional[IndustryChainMap] = None,
    ) -> None:
        self._chain_map = industry_chain_map or get_industry_chain_map()

    def collect_for_tagged_output(
        self,
        tagged_output: TaggedOutput,
        mapping: AStockMapping,
    ) -> AShareMappingWithEvidence:
        """
        为单个 TaggedOutput 收集旁证。
        """
        chain_id = mapping.chain_id
        evidences = self._collect_evidences(
            chain_id=chain_id,
            tagged_outputs=[tagged_output],
            mapping=mapping,
            node_positions=[0],
        )

        return AShareMappingWithEvidence(
            mapping=mapping,
            evidences=tuple(evidences),
        )

    def collect_for_information_chain(
        self,
        chain: InformationChain,
        mapping: AStockMapping,
    ) -> AShareMappingWithEvidence:
        """
        为 InformationChain 收集旁证。
        """
        tagged_outputs = [node.tagged_output for node in chain.nodes]
        node_positions = [node.position for node in chain.nodes]

        evidences = self._collect_evidences(
            chain_id=chain.chain_id,
            tagged_outputs=tagged_outputs,
            mapping=mapping,
            node_positions=node_positions,
        )

        return AShareMappingWithEvidence(
            mapping=mapping,
            evidences=tuple(evidences),
        )

    def map_and_collect_for_chain(
        self,
        chain: InformationChain,
    ) -> AShareMappingWithEvidence:
        """
        同时执行映射和旁证收集。
        """
        engine = AShareMappingEngine(self._chain_map)
        mapping = engine.map_information_chain(chain)
        return self.collect_for_information_chain(chain, mapping)

    def _collect_evidences(
        self,
        chain_id: str,
        tagged_outputs: Sequence[TaggedOutput],
        mapping: AStockMapping,
        node_positions: Sequence[int],
    ) -> List[MappingEvidence]:
        """
        内部方法：收集所有旁证。
        """
        evidences: List[MappingEvidence] = []

        # 为每个板块映射收集旁证
        for sector_mapping in mapping.sector_mappings:
            sector_evidences = self._collect_for_sector(
                chain_id=chain_id,
                sector_mapping=sector_mapping,
                tagged_outputs=tagged_outputs,
                node_positions=node_positions,
            )
            evidences.extend(sector_evidences)

        # 为每个标的池映射收集旁证
        for pool_mapping in mapping.stock_pool_mappings:
            pool_evidences = self._collect_for_stock_pool(
                chain_id=chain_id,
                pool_mapping=pool_mapping,
                tagged_outputs=tagged_outputs,
                node_positions=node_positions,
            )
            evidences.extend(pool_evidences)

        # 为每个个股映射收集旁证
        for stock_mapping in mapping.individual_stock_mappings:
            stock_evidences = self._collect_for_individual_stock(
                chain_id=chain_id,
                stock_mapping=stock_mapping,
                tagged_outputs=tagged_outputs,
                node_positions=node_positions,
            )
            evidences.extend(stock_evidences)

        return evidences

    def _collect_for_sector(
        self,
        chain_id: str,
        sector_mapping: SectorMapping,
        tagged_outputs: Sequence[TaggedOutput],
        node_positions: Sequence[int],
    ) -> List[MappingEvidence]:
        """
        为板块映射收集旁证。
        """
        evidences: List[MappingEvidence] = []

        for idx, tagged_output in enumerate(tagged_outputs):
            node_position = node_positions[idx] if idx < len(node_positions) else None

            # 查找匹配的主题证据
            matched_theme_ids = set(sector_mapping.theme_ids) & set(tagged_output.theme_ids)

            if not matched_theme_ids:
                continue

            # 构建证据片段引用
            snippet_refs = self._build_snippet_references(tagged_output, matched_theme_ids)

            # 构建来源引用
            source_ref = self._build_source_reference(
                chain_id=chain_id,
                node_position=node_position,
                tagged_output=tagged_output,
            )

            # 构建映射旁证
            evidence = MappingEvidence(
                mapping_type="sector",
                mapping_identifier=sector_mapping.sector_name,
                source_reference=source_ref,
                snippet_references=tuple(snippet_refs),
                rationale=f"该新闻提及相关主题，支持 {sector_mapping.sector_name} 板块映射",
            )
            evidences.append(evidence)

        return evidences

    def _collect_for_stock_pool(
        self,
        chain_id: str,
        pool_mapping: StockPoolMapping,
        tagged_outputs: Sequence[TaggedOutput],
        node_positions: Sequence[int],
    ) -> List[MappingEvidence]:
        """
        为标的池映射收集旁证。
        """
        evidences: List[MappingEvidence] = []

        for idx, tagged_output in enumerate(tagged_outputs):
            node_position = node_positions[idx] if idx < len(node_positions) else None

            # 只要有主题就建立关联
            if not tagged_output.theme_ids:
                continue

            # 构建证据片段引用（所有主题相关）
            snippet_refs = self._build_snippet_references(tagged_output, set(tagged_output.theme_ids))

            # 构建来源引用
            source_ref = self._build_source_reference(
                chain_id=chain_id,
                node_position=node_position,
                tagged_output=tagged_output,
            )

            # 构建映射旁证
            evidence = MappingEvidence(
                mapping_type="stock_pool",
                mapping_identifier=pool_mapping.pool_name,
                source_reference=source_ref,
                snippet_references=tuple(snippet_refs),
                rationale=f"该新闻支持 {pool_mapping.pool_name} 的投资逻辑",
            )
            evidences.append(evidence)

        return evidences

    def _collect_for_individual_stock(
        self,
        chain_id: str,
        stock_mapping: IndividualStockMapping,
        tagged_outputs: Sequence[TaggedOutput],
        node_positions: Sequence[int],
    ) -> List[MappingEvidence]:
        """
        为个股映射收集旁证。
        """
        evidences: List[MappingEvidence] = []

        for idx, tagged_output in enumerate(tagged_outputs):
            node_position = node_positions[idx] if idx < len(node_positions) else None

            # 只要有主题就建立关联
            if not tagged_output.theme_ids:
                continue

            # 构建证据片段引用
            snippet_refs = self._build_snippet_references(tagged_output, set(tagged_output.theme_ids))

            # 构建来源引用
            source_ref = self._build_source_reference(
                chain_id=chain_id,
                node_position=node_position,
                tagged_output=tagged_output,
            )

            # 构建映射旁证
            evidence = MappingEvidence(
                mapping_type="individual_stock",
                mapping_identifier=stock_mapping.stock_code,
                source_reference=source_ref,
                snippet_references=tuple(snippet_refs),
                rationale=f"该新闻支持 {stock_mapping.stock_name}({stock_mapping.stock_code}) 的投资逻辑",
            )
            evidences.append(evidence)

        return evidences

    def _build_snippet_references(
        self,
        tagged_output: TaggedOutput,
        theme_ids: set[str],
    ) -> List[EvidenceSnippetReference]:
        """
        构建证据片段引用列表。
        """
        snippet_refs: List[EvidenceSnippetReference] = []

        for link in tagged_output.evidence_links:
            if link.hit.kind == "theme" and link.hit.label_id in theme_ids:
                snippet_ref = EvidenceSnippetReference(
                    snippet=link.span.snippet,
                    context_before=link.span.context_before,
                    context_after=link.span.context_after,
                    start_offset=link.span.start,
                    end_offset=link.span.end,
                    label_id=link.hit.label_id,
                    label_kind=link.hit.kind,
                )
                snippet_refs.append(snippet_ref)

        return snippet_refs

    def _build_source_reference(
        self,
        chain_id: str,
        node_position: Optional[int],
        tagged_output: TaggedOutput,
    ) -> EvidenceSourceReference:
        """
        构建证据来源引用。
        """
        source_name: Optional[str] = None
        published_at: Optional[str] = None
        news_item_id: Optional[str] = None

        # 尝试从 event 中提取信息
        event = tagged_output.event
        if event.source_items:
            first_item = event.source_items[0]
            source_name = getattr(first_item, "source_name", None)
            published_at = getattr(first_item, "published_at", None)
            news_item_id = getattr(first_item, "item_id", None)

        return EvidenceSourceReference(
            chain_id=chain_id,
            node_position=node_position,
            news_item_id=news_item_id,
            source_name=source_name,
            published_at=published_at,
        )


# ---------------------------------------------------------------------------
# Evidence collection convenience functions
# ---------------------------------------------------------------------------


def create_evidence_collector() -> MappingEvidenceCollector:
    """
    创建默认配置的旁证收集器。
    """
    return MappingEvidenceCollector()


def collect_evidence_for_chain(chain: InformationChain, mapping: AStockMapping) -> AShareMappingWithEvidence:
    """
    便捷函数：为信息链和映射收集旁证。
    """
    collector = create_evidence_collector()
    return collector.collect_for_information_chain(chain, mapping)


def map_and_collect_evidence(chain: InformationChain) -> AShareMappingWithEvidence:
    """
    便捷函数：同时执行映射和旁证收集。
    """
    collector = create_evidence_collector()
    return collector.map_and_collect_for_chain(chain)
