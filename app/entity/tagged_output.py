"""
标签化结果输出模块（Tagged Output）

将 :class:`~app.models.event_draft.EventDraft`、原始文本、以及
:class:`~app.entity.evidence.EvidenceLink` 列表组合成一个不可变的
:class:`TaggedOutput` 结构，供下游信息链构建和 A 股映射直接消费。

设计决策
--------
- **EventDraft 集成**：直接持有 ``EventDraft`` 引用，不拷贝，保留完整的
  ``source_items`` 溯源链；下游可按需访问所有 ``NewsItem`` 字段。
- **theme_ids / entity_type_ids**：从 ``EvidenceLink.hit.label_id`` 归集，
  均已去重并按字符串升序排列（``tuple[str, ...]``），保证确定性输出。
- **evidence_links**：按 ``(hit.start, hit.end, hit.label_id)`` 升序排列，
  与 :class:`~app.entity.rules.extractor.RuleExtractor` 输出保持一致。
- **不可变**：``TaggedOutput`` 为 ``frozen=True`` dataclass，所有聚合字段
  均为不可变元组，任何时候都可以安全地哈希/缓存/传递。
- **不做链路构建或 A 股映射**：本模块仅生成中间结构，职责边界清晰。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.entity.evidence import EvidenceLink
from app.models.event_draft import EventDraft


# ---------------------------------------------------------------------------
# TaggedOutput — 标签化事件结果
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaggedOutput:
    """
    一个事件的完整标签化结果，供下游信息链构建和 A 股映射使用。

    字段
    ----
    event
        源 :class:`~app.models.event_draft.EventDraft`，保留完整 ``source_items``
        溯源链，不做复制。
    text
        产生本次标签的原始文本字符串（与传入 :func:`build_tagged_output` 的相同）。
    theme_ids
        从 ``EvidenceLink`` 中归集的主题标签 ID，已去重并升序排列（``ThemeId`` 值
        字符串，如 ``"ai"``、``"gpu"``）。
    entity_type_ids
        从 ``EvidenceLink`` 中归集的实体类型 ID，已去重并升序排列（``EntityTypeId``
        值字符串，如 ``"company"``、``"product"``）。
    evidence_links
        有序的证据关联元组，按 ``(hit.start, hit.end, hit.label_id)`` 升序排列，
        同时覆盖主题证据和实体类型证据。
    """

    event: EventDraft
    text: str
    theme_ids: tuple[str, ...]
    entity_type_ids: tuple[str, ...]
    evidence_links: tuple[EvidenceLink, ...]


# ---------------------------------------------------------------------------
# build_tagged_output — 构建辅助函数
# ---------------------------------------------------------------------------


def build_tagged_output(
    event: EventDraft,
    text: str,
    evidence_links: Sequence[EvidenceLink],
) -> TaggedOutput:
    """
    从 ``EventDraft``、原始文本和证据关联列表构建 :class:`TaggedOutput`。

    参数
    ----
    event
        事件草稿，通常来自事件抽取阶段的输出。
    text
        用于规则/模型抽取的原始文本（``EvidenceLink`` 中的偏移量必须对应此文本）。
    evidence_links
        :func:`~app.entity.evidence.build_evidence_links` 的返回值，可包含
        ``kind="theme"`` 和 ``kind="entity_type"`` 两类命中的证据关联。
        传入空序列时，``theme_ids``、``entity_type_ids``、``evidence_links``
        均为空元组。

    返回
    ----
    一个不可变的 :class:`TaggedOutput`，其中：

    - ``theme_ids``：仅包含 ``hit.kind == "theme"`` 的命中，去重并升序排列。
    - ``entity_type_ids``：仅包含 ``hit.kind == "entity_type"`` 的命中，
      去重并升序排列。
    - ``evidence_links``：全部证据关联，按 ``(hit.start, hit.end, hit.label_id)``
      升序排列。
    """
    # 归集并去重
    theme_id_set: set[str] = set()
    entity_type_id_set: set[str] = set()

    for link in evidence_links:
        if link.hit.kind == "theme":
            theme_id_set.add(link.hit.label_id)
        elif link.hit.kind == "entity_type":
            entity_type_id_set.add(link.hit.label_id)

    # 确定性排序
    sorted_theme_ids = tuple(sorted(theme_id_set))
    sorted_entity_type_ids = tuple(sorted(entity_type_id_set))

    # 证据按位置排序
    sorted_links = tuple(
        sorted(
            evidence_links,
            key=lambda lnk: (lnk.hit.start, lnk.hit.end, lnk.hit.label_id),
        )
    )

    return TaggedOutput(
        event=event,
        text=text,
        theme_ids=sorted_theme_ids,
        entity_type_ids=sorted_entity_type_ids,
        evidence_links=sorted_links,
    )
