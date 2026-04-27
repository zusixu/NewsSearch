"""
信息链数据结构（Information Chain Data Model）

将一组 :class:`~app.entity.tagged_output.TaggedOutput` 节点组织为一条有序的信息链。
每个节点保留完整的事件与证据溯源，链级别聚合主题与实体类型 ID，供下游关系类型定义
和链路构建算法直接消费。

设计决策
--------
- **节点包装**：:class:`ChainNode` 持有 ``TaggedOutput`` 引用（不拷贝），
  附加 0-based ``position`` 标注节点在链中的顺序。
- **关系占位**：``ChainNode.relation_to_prev`` 当前固定为 ``None``；
  节点 2（定义关系类型）负责填充，此处仅预留字段，保持接口稳定。
- **不可变**：``ChainNode`` 和 ``InformationChain`` 均为 ``frozen=True``
  dataclass，所有聚合字段为不可变元组，可安全哈希/缓存/并发读取。
- **证据溯源**：通过 ``node.tagged_output.evidence_links`` 可直达每条命中的
  原文 snippet；通过 ``node.tagged_output.event.source_items`` 可追溯原始
  ``NewsItem`` 与 ``RawDocument``。
- **严格校验**：``InformationChain`` 在 ``__post_init__`` 中验证
  非空节点列表、非空 ``chain_id``、以及 position 单调递增（0, 1, 2, …）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.chains.relation_type import RelationType
from app.entity.tagged_output import TaggedOutput


# ---------------------------------------------------------------------------
# ChainNode — 链中的单个事件节点
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainNode:
    """
    信息链中的单个事件节点，封装 :class:`~app.entity.tagged_output.TaggedOutput`
    并记录节点在链中的序号。

    字段
    ----
    tagged_output
        源 :class:`~app.entity.tagged_output.TaggedOutput`，保留完整的
        ``event``、``evidence_links`` 和标签集合，不做复制。
    position
        节点在链中的 0-based 序号（0 = 最早/最上游）。
    relation_to_prev
        当前节点与前一节点的关系类型；使用 :class:`~app.chains.relation_type.RelationType`
        枚举值（``None`` 表示链首节点或关系未知）。
    """

    tagged_output: TaggedOutput
    position: int
    relation_to_prev: RelationType | None = None


# ---------------------------------------------------------------------------
# InformationChain — 信息链顶层结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InformationChain:
    """
    一条有序的信息事件链，由多个 :class:`ChainNode` 组成。

    字段
    ----
    chain_id
        链的唯一标识符（推荐使用 UUID4 字符串），非空。
    nodes
        有序节点元组，至少包含 1 个节点；``position`` 值应为
        从 0 开始的连续整数（0, 1, 2, …）。
    theme_ids
        跨所有节点聚合的主题 ID 并集，已去重并升序排列。
    entity_type_ids
        跨所有节点聚合的实体类型 ID 并集，已去重并升序排列。

    不变量（由 ``__post_init__`` 强制执行）
    ----------------------------------------
    - ``chain_id`` 非空字符串。
    - ``nodes`` 非空。
    - 节点 ``position`` 值为从 0 开始的连续整数序列。
    """

    chain_id: str
    nodes: tuple[ChainNode, ...]
    theme_ids: tuple[str, ...]
    entity_type_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.chain_id:
            raise ValueError("InformationChain.chain_id 不能为空字符串。")
        if not self.nodes:
            raise ValueError("InformationChain.nodes 不能为空；链至少需要一个节点。")
        expected_positions = list(range(len(self.nodes)))
        actual_positions = [n.position for n in self.nodes]
        if actual_positions != expected_positions:
            raise ValueError(
                f"ChainNode.position 必须为从 0 开始的连续整数序列 {expected_positions}，"
                f"实际得到 {actual_positions}。"
            )


# ---------------------------------------------------------------------------
# build_chain — 构建辅助函数
# ---------------------------------------------------------------------------


def build_chain(
    chain_id: str,
    tagged_outputs: Sequence[TaggedOutput],
) -> InformationChain:
    """
    从有序的 :class:`~app.entity.tagged_output.TaggedOutput` 序列构建
    :class:`InformationChain`。

    节点顺序与 *tagged_outputs* 输入顺序一致；``position`` 自动赋值为
    0-based 递增整数；``relation_to_prev`` 保持 ``None``（供节点 2 填充）。
    链级别 ``theme_ids`` 和 ``entity_type_ids`` 为所有节点标签的并集，
    已去重并升序排列。

    参数
    ----
    chain_id
        链的唯一标识符（调用方负责生成，推荐 ``str(uuid.uuid4())``）。
    tagged_outputs
        构成链的事件节点序列，至少包含 1 个元素；顺序代表链路方向
        （索引 0 = 最早/最上游节点）。

    返回
    ----
    一个不可变的 :class:`InformationChain`。

    异常
    ----
    ValueError
        ``chain_id`` 为空字符串，或 ``tagged_outputs`` 为空序列。
    """
    if not chain_id:
        raise ValueError("chain_id 不能为空字符串。")
    if not tagged_outputs:
        raise ValueError("tagged_outputs 不能为空；链至少需要一个节点。")

    nodes = tuple(
        ChainNode(tagged_output=to, position=i)
        for i, to in enumerate(tagged_outputs)
    )

    # 聚合：所有节点的主题/实体类型 ID 并集
    all_theme_ids: set[str] = set()
    all_entity_type_ids: set[str] = set()
    for node in nodes:
        all_theme_ids.update(node.tagged_output.theme_ids)
        all_entity_type_ids.update(node.tagged_output.entity_type_ids)

    return InformationChain(
        chain_id=chain_id,
        nodes=nodes,
        theme_ids=tuple(sorted(all_theme_ids)),
        entity_type_ids=tuple(sorted(all_entity_type_ids)),
    )
