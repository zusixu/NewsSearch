"""
实体证据关联模块（Evidence Linking）

将 :class:`~app.entity.rules.extractor.Hit` 对象与原始文本中的证据片段关联，
生成可复用的 :class:`EvidenceLink` 结构，供节点 6（输出标签化结果）统一消费。

设计决策
--------
- **通用性**：``kind="theme"`` 和 ``kind="entity_type"`` 的 Hit 均可关联；
  实体证据是当前直接用例，主题证据同样受支持。
- **不可变**：``EvidenceSpan`` 和 ``EvidenceLink`` 均为 frozen dataclass，
  与 Hit 保持一致的不可变风格，便于哈希/缓存。
- **偏移验证**：任何不合法偏移（负值、越界、end ≤ start）都将抛出
  :class:`EvidenceLinkError`，绝不静默接受。
- **context_window**：snippet 两侧各截取最多 *context_window* 个字符作为上下文，
  不越过文本边界；默认 50 字符。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.entity.rules.extractor import Hit

# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------


class EvidenceLinkError(ValueError):
    """偏移量非法或文本与 Hit 不一致时抛出。"""


# ---------------------------------------------------------------------------
# EvidenceSpan — 文本证据片段
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceSpan:
    """
    原始文本中的一个证据片段，携带 snippet 与上下文窗口。

    字段
    ----
    snippet
        命中原文片段（等价于 ``text[start:end]``，与 :attr:`Hit.matched_text` 一致）。
    context_before
        snippet 左侧的上下文文本（最多 *context_window* 字符，可能为空串）。
    context_after
        snippet 右侧的上下文文本（最多 *context_window* 字符，可能为空串）。
    start
        snippet 在原始文本中的起始偏移（inclusive，Unicode 码点）。
    end
        snippet 在原始文本中的结束偏移（exclusive）。
    """

    snippet: str
    context_before: str
    context_after: str
    start: int
    end: int


# ---------------------------------------------------------------------------
# EvidenceLink — Hit 与证据的关联
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceLink:
    """
    一条命中（:class:`Hit`）与其文本证据（:class:`EvidenceSpan`）的关联记录。

    ``hit`` 字段完整保留原始 Hit 对象（包括 kind / label_id / matched_seed 等），
    ``span`` 字段提供 snippet 与上下文，便于下游展示与推理。

    主要用例：实体类型证据关联（``hit.kind == "entity_type"``）。
    主题证据关联（``hit.kind == "theme"``）同样受支持，供节点 6 统一处理。
    """

    hit: Hit
    span: EvidenceSpan


# ---------------------------------------------------------------------------
# 偏移验证
# ---------------------------------------------------------------------------


def _validate_offsets(text: str, start: int, end: int) -> None:
    """
    严格验证偏移量合法性，不合法时抛出 :class:`EvidenceLinkError`。

    规则
    ----
    1. ``start`` 和 ``end`` 必须为非负整数。
    2. ``end > start``（不允许零长度或反向 span）。
    3. ``start < len(text)``（起始不越界）。
    4. ``end <= len(text)``（结束不越界）。
    """
    text_len = len(text)

    if start < 0:
        raise EvidenceLinkError(
            f"start={start!r} 为负数；偏移量必须 ≥ 0。"
        )
    if end < 0:
        raise EvidenceLinkError(
            f"end={end!r} 为负数；偏移量必须 ≥ 0。"
        )
    if end <= start:
        raise EvidenceLinkError(
            f"end={end!r} ≤ start={start!r}；span 长度必须 > 0。"
        )
    if start >= text_len:
        raise EvidenceLinkError(
            f"start={start!r} 超出文本长度 {text_len}。"
        )
    if end > text_len:
        raise EvidenceLinkError(
            f"end={end!r} 超出文本长度 {text_len}（文本共 {text_len} 字符）。"
        )


# ---------------------------------------------------------------------------
# 核心公开 helper
# ---------------------------------------------------------------------------


def build_evidence_links(
    text: str,
    hits: List[Hit],
    context_window: int = 50,
) -> List[EvidenceLink]:
    """
    给定原始文本与命中列表，为每个 Hit 构建 :class:`EvidenceLink`。

    参数
    ----
    text
        原始文本（完整字符串，与产生 hits 时使用的文本相同）。
    hits
        :class:`Hit` 对象列表（可来自规则抽取器或模型抽取器，kind 不限）。
    context_window
        snippet 两侧上下文各截取的最大字符数，默认 50。
        传入 0 时上下文为空串（仅保留 snippet）。

    返回
    ----
    与 *hits* 顺序对应的 :class:`EvidenceLink` 列表。
    空 hits 输入返回空列表。

    异常
    ----
    :class:`EvidenceLinkError`
        任意 Hit 的 start / end 偏移量不合法时抛出，包含具体违规描述。
    ValueError
        ``context_window < 0`` 时抛出。
    """
    if context_window < 0:
        raise ValueError(
            f"context_window={context_window!r} 不能为负数。"
        )

    if not hits:
        return []

    # 允许 text 为空串（空文本不会有合法 Hit，若 hits 非空则验证时自然报错）
    results: List[EvidenceLink] = []

    for hit in hits:
        _validate_offsets(text, hit.start, hit.end)

        snippet = text[hit.start : hit.end]

        ctx_start = max(0, hit.start - context_window)
        ctx_end = min(len(text), hit.end + context_window)

        context_before = text[ctx_start : hit.start]
        context_after = text[hit.end : ctx_end]

        span = EvidenceSpan(
            snippet=snippet,
            context_before=context_before,
            context_after=context_after,
            start=hit.start,
            end=hit.end,
        )
        results.append(EvidenceLink(hit=hit, span=span))

    return results
