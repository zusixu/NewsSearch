"""
日报输出模块（Report Output）

将 A 股映射结果输出到日报，支持 Markdown 和 JSON 两种格式。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Union

from app.mapping.schema import (
    AStockMapping,
    AShareMappingWithEvidence,
    AShareMappingScore,
    ConfidenceLevel,
    SectorMapping,
    StockPoolMapping,
    IndividualStockMapping,
    MappingEvidence,
)
from app.chains.chain import InformationChain


# ---------------------------------------------------------------------------
# Daily Report Data Structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DailyReportHeader:
    """日报头部信息。"""
    report_date: str  # YYYY-MM-DD
    report_batch: str  # "pre-market" 或 "midday"
    generated_at: str  # ISO-8601 UTC
    prompt_profile: Optional[str] = None
    prompt_version: Optional[str] = None


@dataclass(frozen=True)
class DailyReportChainEntry:
    """单条信息链的日报条目。"""
    chain_id: str
    rank: int
    title: str
    summary: str
    confidence: float
    a_share_mapping: AStockMapping
    a_share_score: Optional[AShareMappingScore] = None
    with_evidence: Optional[AShareMappingWithEvidence] = None


@dataclass(frozen=True)
class DailyReport:
    """完整日报数据结构。"""
    header: DailyReportHeader
    top_chains: List[DailyReportChainEntry]
    summary: str


# ---------------------------------------------------------------------------
# Markdown Generator
# ---------------------------------------------------------------------------


class MarkdownReportGenerator:
    """Markdown 格式日报生成器。"""

    def __init__(self) -> None:
        pass

    def generate(self, report: DailyReport) -> str:
        """生成完整 Markdown 日报。"""
        lines = []

        # 头部
        lines.extend(self._render_header(report.header))

        # 总览
        lines.extend(self._render_overview(report))

        # Top 10 信息链
        lines.extend(self._render_top_chains(report.top_chains))

        # 底部
        lines.extend(self._render_footer())

        return "\n".join(lines)

    def _render_header(self, header: DailyReportHeader) -> List[str]:
        """渲染头部。"""
        lines = []
        lines.append(f"# 每日 AI 投资资讯 - {header.report_date}")
        lines.append("")

        batch_names = {
            "pre-market": "开盘前批次",
            "midday": "午间批次",
        }
        batch_name = batch_names.get(header.report_batch, header.report_batch)
        lines.append(f"**批次**: {batch_name}")

        generated_time = datetime.datetime.fromisoformat(header.generated_at)
        lines.append(f"**生成时间**: {generated_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        if header.prompt_profile:
            profile_info = f"**Prompt Profile**: {header.prompt_profile}"
            if header.prompt_version:
                profile_info += f" (v{header.prompt_version})"
            lines.append(profile_info)

        lines.append("")
        lines.append("---")
        lines.append("")

        return lines

    def _render_overview(self, report: DailyReport) -> List[str]:
        """渲染总览部分。"""
        lines = []
        lines.append("## 今日概览")
        lines.append("")
        lines.append(report.summary)
        lines.append("")

        if report.top_chains:
            lines.append("### 今日 TOP 10 摘要")
            lines.append("")
            lines.append("| 排名 | 信息链标题 | 置信度 | 可映射性 |")
            lines.append("|------|------------|--------|----------|")
            for entry in report.top_chains:
                score_level = self._score_level_str(entry.a_share_score)
                lines.append(
                    f"| {entry.rank} | {entry.title} | {entry.confidence:.2%} | {score_level} |"
                )
            lines.append("")

        lines.append("---")
        lines.append("")

        return lines

    def _render_top_chains(self, chains: List[DailyReportChainEntry]) -> List[str]:
        """渲染 Top 10 信息链详情。"""
        lines = []
        lines.append("## 今日 TOP 10 信息链详情")
        lines.append("")

        for entry in chains:
            lines.extend(self._render_chain_entry(entry))

        return lines

    def _render_chain_entry(self, entry: DailyReportChainEntry) -> List[str]:
        """渲染单条信息链条目。"""
        lines = []

        lines.append(f"### #{entry.rank} - {entry.title}")
        lines.append("")
        lines.append(f"**链 ID**: `{entry.chain_id[:16]}...`")
        lines.append(f"**置信度**: {entry.confidence:.2%}")

        if entry.a_share_score:
            lines.append(
                f"**可映射性**: {entry.a_share_score.overall_score:.1f}/100 ({entry.a_share_score.score_level})"
            )
        lines.append("")

        lines.append("#### 摘要")
        lines.append("")
        lines.append(entry.summary)
        lines.append("")

        lines.append("#### A 股映射")
        lines.append("")

        mapping = entry.a_share_mapping

        # 整体置信度和总结
        lines.append(f"**整体置信度**: {self._confidence_str(mapping.overall_confidence)}")
        lines.append(f"**映射总结**: {mapping.summary}")
        lines.append("")

        # 板块映射
        if mapping.sector_mappings:
            lines.append("##### 行业/板块映射")
            lines.append("")
            lines.append("| 板块名称 | 产业链环节 | 置信度 | 理由 |")
            lines.append("|----------|------------|--------|------|")
            for sm in mapping.sector_mappings:
                lines.append(
                    f"| {sm.sector_name} | {sm.chain_segment} | {self._confidence_str(sm.confidence)} | {sm.rationale} |"
                )
            lines.append("")

        # 标的池映射
        if mapping.stock_pool_mappings:
            lines.append("##### 候选标的池映射")
            lines.append("")
            for pm in mapping.stock_pool_mappings:
                lines.append(f"- **{pm.pool_name}**")
                lines.append(f"  - 筛选标准: {pm.criteria}")
                lines.append(f"  - 置信度: {self._confidence_str(pm.confidence)}")
                lines.append(f"  - 理由: {pm.rationale}")
            lines.append("")

        # 个股映射
        if mapping.individual_stock_mappings:
            lines.append("##### 具体个股映射")
            lines.append("")
            lines.append("| 代码 | 名称 | 置信度 | 影响方向 | 理由 |")
            lines.append("|------|------|--------|----------|------|")
            for im in mapping.individual_stock_mappings:
                lines.append(
                    f"| {im.stock_code} | {im.stock_name} | {self._confidence_str(im.confidence)} | {im.impact_direction} | {im.rationale} |"
                )
            lines.append("")

        # 可映射性评分详情
        if entry.a_share_score:
            lines.append("##### 可映射性评分详情")
            lines.append("")
            lines.append(f"**总体评分**: {entry.a_share_score.overall_score:.1f} 分")
            lines.append(f"**评分等级**: {self._score_level_desc(entry.a_share_score.score_level)}")
            lines.append("")
            lines.append("| 维度 | 评分 |")
            lines.append("|------|------|")
            d = entry.a_share_score.dimensions
            lines.append(f"| 主题匹配度 | {d.theme_match_score:.0f} |")
            lines.append(f"| 产业链清晰度 | {d.chain_clarity_score:.0f} |")
            lines.append(f"| 置信度加权 | {d.confidence_weighted_score:.0f} |")
            lines.append(f"| 时效性 | {d.timeliness_score:.0f} |")
            lines.append(f"| 覆盖度 | {d.coverage_score:.0f} |")
            lines.append("")
            lines.append(f"**评分理由**: {entry.a_share_score.rationale}")
            lines.append("")

        # 旁证引用
        if entry.with_evidence and entry.with_evidence.has_evidences:
            lines.append("##### 旁证引用")
            lines.append("")
            lines.extend(self._render_evidences(entry.with_evidence.evidences))
            lines.append("")

        lines.append("---")
        lines.append("")

        return lines

    def _render_evidences(self, evidences: Sequence[MappingEvidence]) -> List[str]:
        """渲染旁证引用。"""
        lines = []

        for idx, evidence in enumerate(evidences[:5]):  # 最多显示 5 个旁证
            lines.append(f"**旁证 #{idx + 1}**: {evidence.rationale}")
            if evidence.source_reference.source_name:
                lines.append(f"- 来源: {evidence.source_reference.source_name}")
            if evidence.source_reference.published_at:
                try:
                    pub_time = datetime.datetime.fromisoformat(evidence.source_reference.published_at)
                    lines.append(f"- 发布时间: {pub_time.strftime('%Y-%m-%d %H:%M:%S')}")
                except Exception:
                    pass
            if evidence.snippet_references:
                snippet = evidence.snippet_references[0].snippet
                lines.append(f"- 关键片段: \"{snippet[:80]}...\"")
            lines.append("")

        if len(evidences) > 5:
            lines.append(f"*还有 {len(evidences) - 5} 条旁证省略*")
            lines.append("")

        return lines

    def _render_footer(self) -> List[str]:
        """渲染底部。"""
        lines = []
        lines.append("---")
        lines.append("")
        lines.append("*报告由 AI 生成，仅供参考，不构成投资建议。*")
        lines.append("")
        return lines

    def _confidence_str(self, level: ConfidenceLevel) -> str:
        """置信度枚举转字符串。"""
        descriptions = {
            ConfidenceLevel.HIGH: "高",
            ConfidenceLevel.MEDIUM: "中",
            ConfidenceLevel.LOW: "低",
        }
        return descriptions.get(level, str(level))

    def _score_level_str(self, score: Optional[AShareMappingScore]) -> str:
        """评分等级转字符串。"""
        if not score:
            return "-"
        return score.score_level

    def _score_level_desc(self, level: str) -> str:
        """评分等级描述。"""
        descriptions = {
            "excellent": "优秀",
            "good": "良好",
            "fair": "一般",
            "poor": "较差",
        }
        return descriptions.get(level, level)


# ---------------------------------------------------------------------------
# JSON Report Generator
# ---------------------------------------------------------------------------


class JsonReportGenerator:
    """JSON 格式日报生成器。"""

    def __init__(self) -> None:
        pass

    def generate(self, report: DailyReport) -> str:
        """生成完整 JSON 日报。"""
        report_dict = self._to_dict(report)
        return json.dumps(report_dict, ensure_ascii=False, indent=2)

    def generate_dict(self, report: DailyReport) -> Dict[str, Any]:
        """生成字典格式。"""
        return self._to_dict(report)

    def _to_dict(self, report: DailyReport) -> Dict[str, Any]:
        """转换为可序列化的字典。"""
        result = {
            "header": {
                "report_date": report.header.report_date,
                "report_batch": report.header.report_batch,
                "generated_at": report.header.generated_at,
                "prompt_profile": report.header.prompt_profile,
                "prompt_version": report.header.prompt_version,
            },
            "summary": report.summary,
            "top_chains": [self._chain_entry_to_dict(entry) for entry in report.top_chains],
        }
        return result

    def _chain_entry_to_dict(self, entry: DailyReportChainEntry) -> Dict[str, Any]:
        """链条目转字典。"""
        result = {
            "chain_id": entry.chain_id,
            "rank": entry.rank,
            "title": entry.title,
            "summary": entry.summary,
            "confidence": entry.confidence,
            "a_share_mapping": self._mapping_to_dict(entry.a_share_mapping),
        }

        if entry.a_share_score:
            result["a_share_score"] = self._score_to_dict(entry.a_share_score)

        if entry.with_evidence:
            result["with_evidence"] = self._with_evidence_to_dict(entry.with_evidence)

        return result

    def _mapping_to_dict(self, mapping: AStockMapping) -> Dict[str, Any]:
        """映射转字典。"""
        return {
            "chain_id": mapping.chain_id,
            "sector_mappings": [self._sector_mapping_to_dict(sm) for sm in mapping.sector_mappings],
            "stock_pool_mappings": [self._pool_mapping_to_dict(pm) for pm in mapping.stock_pool_mappings],
            "individual_stock_mappings": [self._stock_mapping_to_dict(im) for im in mapping.individual_stock_mappings],
            "overall_confidence": mapping.overall_confidence.value,
            "summary": mapping.summary,
            "generated_at": mapping.generated_at,
        }

    def _sector_mapping_to_dict(self, sm: SectorMapping) -> Dict[str, Any]:
        return {
            "sector_name": sm.sector_name,
            "chain_segment": sm.chain_segment,
            "confidence": sm.confidence.value,
            "rationale": sm.rationale,
            "theme_ids": list(sm.theme_ids),
        }

    def _pool_mapping_to_dict(self, pm: StockPoolMapping) -> Dict[str, Any]:
        return {
            "pool_name": pm.pool_name,
            "criteria": pm.criteria,
            "confidence": pm.confidence.value,
            "rationale": pm.rationale,
            "sector_name": pm.sector_name,
        }

    def _stock_mapping_to_dict(self, im: IndividualStockMapping) -> Dict[str, Any]:
        return {
            "stock_code": im.stock_code,
            "stock_name": im.stock_name,
            "confidence": im.confidence.value,
            "rationale": im.rationale,
            "impact_direction": im.impact_direction,
            "pool_name": im.pool_name,
            "notes": im.notes,
        }

    def _score_to_dict(self, score: AShareMappingScore) -> Dict[str, Any]:
        return {
            "chain_id": score.chain_id,
            "dimensions": {
                "theme_match_score": score.dimensions.theme_match_score,
                "chain_clarity_score": score.dimensions.chain_clarity_score,
                "confidence_weighted_score": score.dimensions.confidence_weighted_score,
                "timeliness_score": score.dimensions.timeliness_score,
                "coverage_score": score.dimensions.coverage_score,
            },
            "overall_score": score.overall_score,
            "score_level": score.score_level,
            "rationale": score.rationale,
            "scored_at": score.scored_at,
        }

    def _with_evidence_to_dict(self, we: AShareMappingWithEvidence) -> Dict[str, Any]:
        return {
            "mapping": self._mapping_to_dict(we.mapping),
            "evidences": [self._evidence_to_dict(e) for e in we.evidences],
        }

    def _evidence_to_dict(self, e: MappingEvidence) -> Dict[str, Any]:
        return {
            "mapping_type": e.mapping_type,
            "mapping_identifier": e.mapping_identifier,
            "source_reference": {
                "chain_id": e.source_reference.chain_id,
                "node_position": e.source_reference.node_position,
                "news_item_id": e.source_reference.news_item_id,
                "source_name": e.source_reference.source_name,
                "published_at": e.source_reference.published_at,
            },
            "snippet_references": [
                {
                    "snippet": s.snippet,
                    "context_before": s.context_before,
                    "context_after": s.context_after,
                    "start_offset": s.start_offset,
                    "end_offset": s.end_offset,
                    "label_id": s.label_id,
                    "label_kind": s.label_kind,
                }
                for s in e.snippet_references
            ],
            "rationale": e.rationale,
        }


# ---------------------------------------------------------------------------
# Report Builder
# ---------------------------------------------------------------------------


class DailyReportBuilder:
    """日报构建器。"""

    def __init__(self) -> None:
        self.markdown_generator = MarkdownReportGenerator()
        self.json_generator = JsonReportGenerator()

    def build(
        self,
        report_date: str,
        report_batch: str,
        chains_with_mappings: Sequence[DailyReportChainEntry],
        prompt_profile: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> DailyReport:
        """构建日报。"""
        header = DailyReportHeader(
            report_date=report_date,
            report_batch=report_batch,
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
            prompt_profile=prompt_profile,
            prompt_version=prompt_version,
        )

        summary = self._build_summary(chains_with_mappings)

        return DailyReport(
            header=header,
            top_chains=list(chains_with_mappings),
            summary=summary,
        )

    def to_markdown(self, report: DailyReport) -> str:
        """生成 Markdown。"""
        return self.markdown_generator.generate(report)

    def to_json(self, report: DailyReport) -> str:
        """生成 JSON。"""
        return self.json_generator.generate(report)

    def to_json_dict(self, report: DailyReport) -> Dict[str, Any]:
        """生成 JSON 字典。"""
        return self.json_generator.generate_dict(report)

    def _build_summary(self, chains: Sequence[DailyReportChainEntry]) -> str:
        """构建日报摘要。"""
        if not chains:
            return "今日暂无可关注的信息链"

        chain_count = len(chains)

        # 统计可映射性等级
        level_counts: Dict[str, int] = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
        for entry in chains:
            if entry.a_share_score:
                level_counts[entry.a_share_score.score_level] += 1

        # 统计涉及的板块
        sector_set = set()
        for entry in chains:
            for sm in entry.a_share_mapping.sector_mappings:
                sector_set.add(sm.sector_name)

        sectors = list(sector_set)[:5]
        sector_str = "、".join(sectors)
        if len(sector_set) > 5:
            sector_str += f" 等 {len(sector_set)} 个板块"

        summary_parts = [
            f"今日共精选 {chain_count} 条值得关注的信息链。",
        ]

        if level_counts["excellent"] > 0:
            summary_parts.append(f"其中可映射性优秀的有 {level_counts['excellent']} 条。")
        if level_counts["good"] > 0:
            summary_parts.append(f"可映射性良好的有 {level_counts['good']} 条。")

        if sector_set:
            summary_parts.append(f"主要涉及 {sector_str}。")

        return " ".join(summary_parts)


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


def create_report_builder() -> DailyReportBuilder:
    """创建日报构建器。"""
    return DailyReportBuilder()


def generate_markdown_report(report: DailyReport) -> str:
    """便捷函数：生成 Markdown 日报。"""
    builder = create_report_builder()
    return builder.to_markdown(report)


def generate_json_report(report: DailyReport) -> str:
    """便捷函数：生成 JSON 日报。"""
    builder = create_report_builder()
    return builder.to_json(report)
