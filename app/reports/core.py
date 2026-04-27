"""
日报输出模块（Report Output）

将 A 股映射结果输出到日报，支持 Markdown 和 JSON 两种格式。
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Union
from pathlib import Path

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
from app.chains.evidence_retention import ChainEvidenceBundle
from app.analysis.adapters.contracts import (
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    PromptProfile,
)


# ---------------------------------------------------------------------------
# RiskWarning — 风险提示数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskWarning:
    """
    风险提示条目。

    字段
    ----
    risk_type
        风险类型，如 "置信度提示"、"估值提示"、"时效性提示"、"反证提示"。
    severity
        严重程度，"high"（高）、"medium"（中）、"low"（低）。
    message
        风险提示内容。
    related_chain_id
        关联的信息链 ID，可选。
    related_stock_code
        关联的股票代码，可选。
    """

    risk_type: str
    severity: str
    message: str
    related_chain_id: Optional[str] = None
    related_stock_code: Optional[str] = None

    def __post_init__(self) -> None:
        if self.risk_type not in {"置信度提示", "估值提示", "时效性提示", "反证提示", "其他风险"}:
            raise ValueError(f"未知的风险类型: {self.risk_type}")
        if self.severity not in {"high", "medium", "low"}:
            raise ValueError(f"严重程度必须是 high/medium/low 之一: {self.severity}")
        if not self.message:
            raise ValueError("风险提示内容不能为空")


# ---------------------------------------------------------------------------
# Daily Report Data Structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DailyReportHeader:
    """
    日报头部信息。

    字段
    ----
    report_date
        报告日期，格式为 "YYYY-MM-DD"。
    report_batch
        报告批次，"pre-market"（开盘前）或 "midday"（午间）。
    generated_at
        生成时间，ISO-8601 UTC 字符串。
    prompt_profile
        使用的 Prompt Profile 名称，可选。
    prompt_version
        Prompt Profile 版本，可选。
    """

    report_date: str
    report_batch: str
    generated_at: str
    prompt_profile: Optional[str] = None
    prompt_version: Optional[str] = None

    def __post_init__(self) -> None:
        if self.report_batch not in {"pre-market", "midday"}:
            raise ValueError(f"报告批次必须是 pre-market 或 midday: {self.report_batch}")


@dataclass(frozen=True)
class DailyReportChainEntry:
    """
    单条信息链的日报条目。

    字段
    ----
    chain_id
        信息链 ID。
    rank
        排名（1-based）。
    title
        标题（来自 LLM 分析或自动生成）。
    summary
        摘要（来自 LLM 的 ChainAnalysisResult）。
    confidence
        置信度（0.0-1.0）。
    rationale
        排名理由（来自 ChainRankingEntry）。
    a_share_mapping
        A 股映射结构。
    a_share_score
        A 股可映射性评分，可选。
    with_evidence
        带旁证的 A 股映射，可选。
    chain_analysis
        完整的链分析结果，可选。
    source_urls
        原始来源 URL 列表（按首见顺序去重），用于
        报告中的来源链接溯源展示。默认值为空元组，
        确保已有代码向后兼容。
    """

    chain_id: str
    rank: int
    title: str
    summary: str
    confidence: float
    rationale: str
    a_share_mapping: AStockMapping
    a_share_score: Optional[AShareMappingScore] = None
    with_evidence: Optional[AShareMappingWithEvidence] = None
    chain_analysis: Optional[ChainAnalysisResult] = None
    source_urls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError(f"排名必须 >= 1: {self.rank}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"置信度必须在 [0.0, 1.0] 范围内: {self.confidence}")


@dataclass(frozen=True)
class DailyReport:
    """
    完整日报数据结构。

    字段
    ----
    header
        日报头部信息。
    top_chains
        Top 10 信息链列表。
    risk_warnings
        风险提示列表。
    summary
        日报总览摘要。
    """

    header: DailyReportHeader
    top_chains: List[DailyReportChainEntry]
    risk_warnings: List[RiskWarning]
    summary: str


# ---------------------------------------------------------------------------
# Markdown Generator
# ---------------------------------------------------------------------------


class MarkdownReportGenerator:
    """
    Markdown 格式日报生成器。
    """

    def __init__(self) -> None:
        pass

    def generate(self, report: DailyReport) -> str:
        """
        生成完整 Markdown 日报。

        参数
        ------
        report
            DailyReport 对象。

        返回
        -------
        完整的 Markdown 字符串。
        """
        lines = []

        # 头部
        lines.extend(self._render_header(report.header))

        # 总览
        lines.extend(self._render_overview(report))

        # 风险提示
        if report.risk_warnings:
            lines.extend(self._render_risk_warnings(report.risk_warnings))

        # Top 10 信息链
        lines.extend(self._render_top_chains(report.top_chains))

        # 底部
        lines.extend(self._render_footer())

        return "\n".join(lines)

    def _render_header(self, header: DailyReportHeader) -> List[str]:
        """渲染头部。"""
        lines = []

        batch_names = {
            "pre-market": "开盘前",
            "midday": "午间",
        }
        batch_name = batch_names.get(header.report_batch, header.report_batch)

        lines.append(f"# 每日 AI 投资资讯 - {header.report_date}")
        lines.append("")
        lines.append(f"> **批次**：{batch_name}")
        lines.append(f"> **生成时间**：{header.generated_at} UTC")

        if header.prompt_profile:
            profile_info = f"> **Prompt Profile**：{header.prompt_profile}"
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
            lines.append("### 今日 TOP 10 信息链")
            lines.append("")
            lines.append("| 排名 | 标题 | 置信度 | 可映射性 |")
            lines.append("|------|------|--------|----------|")

            for entry in report.top_chains:
                score_level = self._score_level_str(entry.a_share_score)
                confidence_pct = f"{entry.confidence:.1%}"
                # 截断标题避免表格过宽
                title_short = entry.title[:30] + "..." if len(entry.title) > 30 else entry.title
                lines.append(f"| {entry.rank} | {title_short} | {confidence_pct} | {score_level} |")

            lines.append("")

        lines.append("---")
        lines.append("")

        return lines

    def _render_risk_warnings(self, warnings: List[RiskWarning]) -> List[str]:
        """渲染风险提示部分。"""
        lines = []
        lines.append("## 风险提示")
        lines.append("")

        # 按严重程度排序
        severity_order = {"high": 0, "medium": 1, "low": 2}
        sorted_warnings = sorted(warnings, key=lambda w: severity_order.get(w.severity, 999))

        for warning in sorted_warnings:
            severity_emoji = {
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢",
            }.get(warning.severity, "⚪")

            lines.append(f"### {severity_emoji} {warning.risk_type}")
            lines.append("")
            lines.append(warning.message)
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
        lines.append(f"**链 ID**：`{entry.chain_id[:16]}...`")
        lines.append(f"**置信度**：{entry.confidence:.1%}")

        if entry.a_share_score:
            lines.append(f"**可映射性评分**：{entry.a_share_score.overall_score:.1f}/100 ({self._score_level_desc(entry.a_share_score.score_level)})")

        lines.append("")
        lines.append("#### 摘要")
        lines.append("")
        lines.append(entry.summary)
        lines.append("")

        if entry.rationale:
            lines.append("#### 排名理由")
            lines.append("")
            lines.append(entry.rationale)
            lines.append("")

        lines.append("#### A 股映射")
        lines.append("")

        mapping = entry.a_share_mapping

        # 整体置信度和总结
        lines.append(f"**整体置信度**：{self._confidence_str(mapping.overall_confidence)}")
        lines.append(f"**映射总结**：{mapping.summary}")
        lines.append("")

        # 板块映射
        if mapping.sector_mappings:
            lines.append("##### 行业/板块映射")
            lines.append("")
            lines.append("| 板块名称 | 产业链环节 | 置信度 | 理由 |")
            lines.append("|----------|------------|--------|------|")
            for sm in mapping.sector_mappings:
                lines.append(f"| {sm.sector_name} | {sm.chain_segment} | {self._confidence_str(sm.confidence)} | {sm.rationale} |")
            lines.append("")

        # 标的池映射
        if mapping.stock_pool_mappings:
            lines.append("##### 候选标的池映射")
            lines.append("")
            for pm in mapping.stock_pool_mappings:
                lines.append(f"- **{pm.pool_name}**")
                lines.append(f"  - 筛选标准：{pm.criteria}")
                lines.append(f"  - 置信度：{self._confidence_str(pm.confidence)}")
                lines.append(f"  - 理由：{pm.rationale}")
            lines.append("")

        # 个股映射
        if mapping.individual_stock_mappings:
            lines.append("##### 具体个股映射")
            lines.append("")
            lines.append("| 代码 | 名称 | 置信度 | 影响方向 | 理由 |")
            lines.append("|------|------|--------|----------|------|")
            for im in mapping.individual_stock_mappings:
                lines.append(f"| {im.stock_code} | {im.stock_name} | {self._confidence_str(im.confidence)} | {im.impact_direction} | {im.rationale} |")
            lines.append("")

        # 可映射性评分详情
        if entry.a_share_score:
            lines.append("##### 可映射性评分详情")
            lines.append("")
            lines.append(f"**总体评分**：{entry.a_share_score.overall_score:.1f} 分")
            lines.append(f"**评分等级**：{self._score_level_desc(entry.a_share_score.score_level)}")
            lines.append("")
            lines.append("| 维度 | 评分 | 说明 |")
            lines.append("|------|------|------|")
            d = entry.a_share_score.dimensions
            lines.append(f"| 主题匹配度 | {d.theme_match_score:.0f} | 信息链主题与 A 股产业链节点的匹配程度 |")
            lines.append(f"| 产业链清晰度 | {d.chain_clarity_score:.0f} | 产业链环节定位的明确程度 |")
            lines.append(f"| 置信度加权 | {d.confidence_weighted_score:.0f} | 基于置信度分级的加权得分 |")
            lines.append(f"| 时效性 | {d.timeliness_score:.0f} | 信息的时效性对投资决策的价值 |")
            lines.append(f"| 覆盖度 | {d.coverage_score:.0f} | 三层映射（板块/标的池/个股）的完整程度 |")
            lines.append("")
            lines.append(f"**评分理由**：{entry.a_share_score.rationale}")
            lines.append("")

        # 旁证引用
        if entry.with_evidence and entry.with_evidence.has_evidences:
            lines.append("##### 旁证引用")
            lines.append("")
            lines.extend(self._render_evidences(entry.with_evidence.evidences))
            lines.append("")

        # 来源链接
        if entry.source_urls:
            lines.append("##### 来源链接")
            lines.append("")
            for idx, url in enumerate(entry.source_urls, start=1):
                # 截断过长 URL 作为显示文本
                display_text = url if len(url) <= 80 else url[:77] + "..."
                lines.append(f"- [{display_text}]({url})")
            lines.append("")

        lines.append("---")
        lines.append("")

        return lines

    def _render_evidences(self, evidences: Sequence[MappingEvidence]) -> List[str]:
        """渲染旁证引用。"""
        lines = []

        for idx, evidence in enumerate(evidences[:5]):  # 最多显示 5 个旁证
            lines.append(f"**旁证 #{idx + 1}**：{evidence.rationale}")
            if evidence.source_reference.source_name:
                lines.append(f"- 来源：{evidence.source_reference.source_name}")
            if evidence.source_reference.published_at:
                try:
                    pub_time = datetime.datetime.fromisoformat(evidence.source_reference.published_at)
                    lines.append(f"- 发布时间：{pub_time.strftime('%Y-%m-%d %H:%M:%S')}")
                except Exception:
                    pass
            if evidence.snippet_references:
                snippet = evidence.snippet_references[0].snippet
                snippet_short = snippet[:80] + "..." if len(snippet) > 80 else snippet
                lines.append(f"- 关键片段：\"{snippet_short}\"")
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
        lines.append("⚠️ **免责声明**")
        lines.append("")
        lines.append("本报告由 AI 自动生成，仅供参考，不构成任何投资建议。")
        lines.append("投资有风险，入市需谨慎。请结合自身情况独立判断，审慎决策。")
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
        level_desc = {
            "excellent": "优秀",
            "good": "良好",
            "fair": "一般",
            "poor": "较差",
        }
        return level_desc.get(score.score_level, score.score_level)

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
    """
    JSON 格式日报生成器。
    """

    def __init__(self) -> None:
        pass

    def generate(self, report: DailyReport) -> str:
        """
        生成完整 JSON 日报。

        参数
        ------
        report
            DailyReport 对象。

        返回
        -------
        格式化的 JSON 字符串。
        """
        report_dict = self._to_dict(report)
        return json.dumps(report_dict, ensure_ascii=False, indent=2)

    def generate_dict(self, report: DailyReport) -> Dict[str, Any]:
        """
        生成字典格式。

        参数
        ------
        report
            DailyReport 对象。

        返回
        -------
        可序列化为 JSON 的字典。
        """
        return self._to_dict(report)

    def _to_dict(self, report: DailyReport) -> Dict[str, Any]:
        """转换为可序列化的字典。"""
        return {
            "header": {
                "report_date": report.header.report_date,
                "report_batch": report.header.report_batch,
                "generated_at": report.header.generated_at,
                "prompt_profile": report.header.prompt_profile,
                "prompt_version": report.header.prompt_version,
            },
            "summary": report.summary,
            "risk_warnings": [self._risk_warning_to_dict(w) for w in report.risk_warnings],
            "top_chains": [self._chain_entry_to_dict(entry) for entry in report.top_chains],
        }

    def _risk_warning_to_dict(self, warning: RiskWarning) -> Dict[str, Any]:
        """风险提示转字典。"""
        return {
            "risk_type": warning.risk_type,
            "severity": warning.severity,
            "message": warning.message,
            "related_chain_id": warning.related_chain_id,
            "related_stock_code": warning.related_stock_code,
        }

    def _chain_entry_to_dict(self, entry: DailyReportChainEntry) -> Dict[str, Any]:
        """链条目转字典。"""
        result = {
            "chain_id": entry.chain_id,
            "rank": entry.rank,
            "title": entry.title,
            "summary": entry.summary,
            "confidence": entry.confidence,
            "rationale": entry.rationale,
            "a_share_mapping": self._mapping_to_dict(entry.a_share_mapping),
            "source_urls": list(entry.source_urls),
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
    """
    日报构建器。

    负责从原始数据构建完整的 DailyReport 对象。
    """

    def __init__(self) -> None:
        self.markdown_generator = MarkdownReportGenerator()
        self.json_generator = JsonReportGenerator()

    def build(
        self,
        report_date: str,
        report_batch: str,
        analysis_response: AnalysisResponse,
        mappings: Dict[str, AStockMapping],
        scores: Optional[Dict[str, AShareMappingScore]] = None,
        with_evidences: Optional[Dict[str, AShareMappingWithEvidence]] = None,
        prompt_profile: Optional[PromptProfile] = None,
        max_chains: int = 10,
        evidence_bundles: Optional[Dict[str, ChainEvidenceBundle]] = None,
    ) -> DailyReport:
        """
        构建日报。

        参数
        ------
        report_date
            报告日期，格式 "YYYY-MM-DD"。
        report_batch
            报告批次，"pre-market" 或 "midday"。
        analysis_response
            LLM 分析响应。
        mappings
            信息链 ID 到 AStockMapping 的字典。
        scores
            信息链 ID 到 AShareMappingScore 的字典，可选。
        with_evidences
            信息链 ID 到 AShareMappingWithEvidence 的字典，可选。
        prompt_profile
            使用的 PromptProfile，可选。
        max_chains
            最多包含的信息链数量，默认 10。
        evidence_bundles
            信息链 ID 到 ChainEvidenceBundle 的字典，可选。
            用于提取 source_urls 进行 URL 溯源透传。

        返回
        -------
        构建完成的 DailyReport 对象。
        """
        header = DailyReportHeader(
            report_date=report_date,
            report_batch=report_batch,
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
            prompt_profile=prompt_profile.profile_name if prompt_profile else None,
            prompt_version=prompt_profile.version if prompt_profile else None,
        )

        # 构建 Top 10 链条目
        top_chain_entries = self._build_top_chain_entries(
            analysis_response=analysis_response,
            mappings=mappings,
            scores=scores or {},
            with_evidences=with_evidences or {},
            max_chains=max_chains,
            evidence_bundles=evidence_bundles or {},
        )

        # 构建风险提示
        risk_warnings = self._build_risk_warnings(top_chain_entries)

        # 构建摘要
        summary = self._build_summary(top_chain_entries)

        return DailyReport(
            header=header,
            top_chains=top_chain_entries,
            risk_warnings=risk_warnings,
            summary=summary,
        )

    def _build_top_chain_entries(
        self,
        analysis_response: AnalysisResponse,
        mappings: Dict[str, AStockMapping],
        scores: Dict[str, AShareMappingScore],
        with_evidences: Dict[str, AShareMappingWithEvidence],
        max_chains: int,
        evidence_bundles: Dict[str, ChainEvidenceBundle],
    ) -> List[DailyReportChainEntry]:
        """构建 Top 10 链条目。"""
        entries = []

        # 按排名顺序处理
        for ranking_entry in analysis_response.ranking.entries[:max_chains]:
            chain_id = ranking_entry.chain_id

            # 查找对应的分析结果
            chain_analysis = None
            for ca in analysis_response.chain_results:
                if ca.chain_id == chain_id:
                    chain_analysis = ca
                    break

            if not chain_analysis:
                continue

            # 获取 A 股映射
            a_share_mapping = mappings.get(chain_id)
            if not a_share_mapping:
                # 创建空映射
                a_share_mapping = AStockMapping(
                    chain_id=chain_id,
                    sector_mappings=(),
                    stock_pool_mappings=(),
                    individual_stock_mappings=(),
                    overall_confidence=ConfidenceLevel.LOW,
                    summary="暂无 A 股映射",
                    generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
                )

            # 生成标题（从摘要中提取前 50 个字符或使用默认）
            title = self._extract_title(chain_analysis.summary)

            # 从 evidence_bundle 提取 source_urls（若可用）
            source_urls: tuple[str, ...] = ()
            bundle = evidence_bundles.get(chain_id)
            if bundle is not None:
                source_urls = bundle.source_urls

            entry = DailyReportChainEntry(
                chain_id=chain_id,
                rank=ranking_entry.rank,
                title=title,
                summary=chain_analysis.summary,
                confidence=chain_analysis.confidence,
                rationale=ranking_entry.rationale,
                a_share_mapping=a_share_mapping,
                a_share_score=scores.get(chain_id),
                with_evidence=with_evidences.get(chain_id),
                chain_analysis=chain_analysis,
                source_urls=source_urls,
            )
            entries.append(entry)

        return entries

    def _build_risk_warnings(self, entries: List[DailyReportChainEntry]) -> List[RiskWarning]:
        """构建风险提示列表。"""
        warnings = []

        for entry in entries:
            # 低置信度风险
            if entry.confidence < 0.5:
                warnings.append(RiskWarning(
                    risk_type="置信度提示",
                    severity="medium",
                    message=f"信息链「{entry.title}」的置信度较低（{entry.confidence:.1%}），请审慎参考。",
                    related_chain_id=entry.chain_id,
                ))

            # 低可映射性风险
            if entry.a_share_score and entry.a_share_score.score_level in {"fair", "poor"}:
                warnings.append(RiskWarning(
                    risk_type="置信度提示",
                    severity="low",
                    message=f"信息链「{entry.title}」的 A 股可映射性评分较低（{entry.a_share_score.overall_score:.1f}/100），映射结果仅供参考。",
                    related_chain_id=entry.chain_id,
                ))

            # 个股层面的低置信度风险
            for sm in entry.a_share_mapping.individual_stock_mappings:
                if sm.confidence == ConfidenceLevel.LOW:
                    warnings.append(RiskWarning(
                        risk_type="置信度提示",
                        severity="low",
                        message=f"个股「{sm.stock_name}({sm.stock_code})」的映射置信度较低，理由：{sm.rationale}",
                        related_chain_id=entry.chain_id,
                        related_stock_code=sm.stock_code,
                    ))

        # 全局提示
        warnings.append(RiskWarning(
            risk_type="其他风险",
            severity="high",
            message="本报告由 AI 自动生成，不构成任何投资建议。投资有风险，入市需谨慎。",
        ))

        return warnings

    def _build_summary(self, entries: List[DailyReportChainEntry]) -> str:
        """构建日报摘要。"""
        if not entries:
            return "今日暂无可关注的信息链。"

        chain_count = len(entries)

        # 统计可映射性等级
        level_counts: Dict[str, int] = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
        for entry in entries:
            if entry.a_share_score:
                level_counts[entry.a_share_score.score_level] += 1

        # 统计涉及的板块
        sector_set = set()
        for entry in entries:
            for sm in entry.a_share_mapping.sector_mappings:
                sector_set.add(sm.sector_name)

        # 统计涉及的个股数量
        stock_count = 0
        for entry in entries:
            stock_count += len(entry.a_share_mapping.individual_stock_mappings)

        summary_parts = [
            f"今日共精选 {chain_count} 条值得关注的信息链",
        ]

        excellent_good_count = level_counts["excellent"] + level_counts["good"]
        if excellent_good_count > 0:
            summary_parts.append(f"其中可映射性优秀/良好的有 {excellent_good_count} 条")

        if sector_set:
            sectors = list(sector_set)[:5]
            sector_str = "、".join(sectors)
            if len(sector_set) > 5:
                sector_str += f" 等 {len(sector_set)} 个板块"
            summary_parts.append(f"主要涉及 {sector_str}")

        if stock_count > 0:
            summary_parts.append(f"覆盖 {stock_count} 只个股")

        return "，".join(summary_parts) + "。"

    def _extract_title(self, summary: str) -> str:
        """从摘要中提取标题。"""
        # 取第一句话或前 50 个字符
        if not summary:
            return "无标题"

        # 尝试按标点符号分割
        for sep in ["。", "！", "!", "?", "？", "\n"]:
            if sep in summary:
                first_part = summary.split(sep)[0].strip()
                if first_part:
                    return first_part[:60] + ("..." if len(first_part) > 60 else "")

        # 直接截断
        return summary[:60] + ("..." if len(summary) > 60 else "")

    def to_markdown(self, report: DailyReport) -> str:
        """生成 Markdown。"""
        return self.markdown_generator.generate(report)

    def to_json(self, report: DailyReport) -> str:
        """生成 JSON。"""
        return self.json_generator.generate(report)

    def to_json_dict(self, report: DailyReport) -> Dict[str, Any]:
        """生成 JSON 字典。"""
        return self.json_generator.generate_dict(report)


# ---------------------------------------------------------------------------
# Report Archive Manager
# ---------------------------------------------------------------------------


class ReportArchiveManager:
    """
    报告归档管理器。

    负责报告的文件存储、目录组织和历史归档。
    """

    def __init__(self, reports_dir: str | Path) -> None:
        """
        初始化归档管理器。

        参数
        ------
        reports_dir
            报告存储根目录。
        """
        self.reports_dir = Path(reports_dir)

    def ensure_directories(self) -> None:
        """确保必要的目录存在。"""
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # 按日期组织的子目录
        # 结构：data/reports/YYYY/MM/DD/
        pass  # 动态创建

    def get_report_path(
        self,
        report_date: str,
        report_batch: str,
        extension: str = "md",
    ) -> Path:
        """
        获取报告文件路径。

        文件命名规范：
        - YYYYMMDD-pre-market.md
        - YYYYMMDD-midday.md

        目录结构：
        - data/reports/YYYY/MM/DD/
        """
        # 解析日期
        try:
            dt = datetime.datetime.strptime(report_date, "%Y-%m-%d")
        except ValueError:
            dt = datetime.datetime.now(datetime.UTC)

        # 目录：data/reports/YYYY/MM/DD/
        date_dir = self.reports_dir / f"{dt.year:04d}" / f"{dt.month:02d}" / f"{dt.day:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)

        # 文件名：YYYYMMDD-pre-market.md
        date_str = dt.strftime("%Y%m%d")
        filename = f"{date_str}-{report_batch}.{extension}"

        return date_dir / filename

    def save_report(
        self,
        report: DailyReport,
        save_markdown: bool = True,
        save_json: bool = True,
    ) -> Dict[str, Path]:
        """
        保存报告到文件。

        参数
        ------
        report
            DailyReport 对象。
        save_markdown
            是否保存 Markdown 版本。
        save_json
            是否保存 JSON 版本。

        返回
        -------
        保存的文件路径字典。
        """
        self.ensure_directories()

        builder = DailyReportBuilder()
        saved_paths = {}

        if save_markdown:
            md_path = self.get_report_path(
                report_date=report.header.report_date,
                report_batch=report.header.report_batch,
                extension="md",
            )
            md_content = builder.to_markdown(report)
            md_path.write_text(md_content, encoding="utf-8")
            saved_paths["markdown"] = md_path

        if save_json:
            json_path = self.get_report_path(
                report_date=report.header.report_date,
                report_batch=report.header.report_batch,
                extension="json",
            )
            json_content = builder.to_json(report)
            json_path.write_text(json_content, encoding="utf-8")
            saved_paths["json"] = json_path

        return saved_paths

    def list_reports(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        batch: Optional[str] = None,
    ) -> List[Path]:
        """
        列出历史报告。

        参数
        ------
        start_date
            起始日期（YYYY-MM-DD），可选。
        end_date
            结束日期（YYYY-MM-DD），可选。
        batch
            批次过滤（"pre-market"/"midday"），可选。

        返回
        -------
        报告文件路径列表。
        """
        if not self.reports_dir.exists():
            return []

        all_reports = []

        # 遍历目录结构
        for year_dir in sorted(self.reports_dir.iterdir()):
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue

            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir() or not month_dir.name.isdigit():
                    continue

                for day_dir in sorted(month_dir.iterdir()):
                    if not day_dir.is_dir() or not day_dir.name.isdigit():
                        continue

                    # 遍历该日期的所有报告
                    for report_file in sorted(day_dir.glob("*.md")):
                        # 检查是否符合过滤条件
                        if self._match_report_filter(report_file, start_date, end_date, batch):
                            all_reports.append(report_file)

        return all_reports

    def _match_report_filter(
        self,
        report_path: Path,
        start_date: Optional[str],
        end_date: Optional[str],
        batch: Optional[str],
    ) -> bool:
        """检查报告文件是否符合过滤条件。"""
        filename = report_path.stem

        # 解析文件名：YYYYMMDD-pre-market
        try:
            parts = filename.split("-")
            if len(parts) < 2:
                return False

            date_str = parts[0]
            file_batch = "-".join(parts[1:])

            # 批次过滤
            if batch and file_batch != batch:
                return False

            # 日期过滤
            dt = datetime.datetime.strptime(date_str, "%Y%m%d")
            report_date = dt.strftime("%Y-%m-%d")

            if start_date and report_date < start_date:
                return False

            if end_date and report_date > end_date:
                return False

            return True

        except Exception:
            return False


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


def create_report_builder() -> DailyReportBuilder:
    """创建日报构建器。"""
    return DailyReportBuilder()


def create_archive_manager(reports_dir: str | Path) -> ReportArchiveManager:
    """创建报告归档管理器。"""
    return ReportArchiveManager(reports_dir)


def generate_markdown_report(report: DailyReport) -> str:
    """便捷函数：生成 Markdown 日报。"""
    builder = create_report_builder()
    return builder.to_markdown(report)


def generate_json_report(report: DailyReport) -> str:
    """便捷函数：生成 JSON 日报。"""
    builder = create_report_builder()
    return builder.to_json(report)
