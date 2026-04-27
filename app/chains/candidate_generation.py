"""
候选信息链生成模块（Candidate Chain Generation）

将一组 :class:`~app.entity.tagged_output.TaggedOutput` 通过已有的三个构建阶段
串联为候选信息链列表，供下游排序/评分/证据汇总阶段消费。

**本模块仅生成候选链，不做任何排名、评分、重要性过滤或 Top-K 筛选。**

流水线顺序
----------
1. :func:`~app.chains.same_topic_grouping.group_same_topic`
   — 按共享 ``theme_ids`` 做传递闭包聚合，生成初始链列表。
2. :func:`~app.chains.temporal_connection.apply_temporal_order`
   — 对每条链内节点按 ``occurred_at`` 升序重排，填写时序关系标签。
3. :func:`~app.chains.upstream_downstream.apply_upstream_downstream_order`
   — 对每条链内节点按供应链阶段（上游→中游→下游）重排，填写上下游关系标签。

设计决策
--------
- **确定性**：三个阶段均为确定性算法，相同输入始终产生相同输出顺序。
- **保守保留**：``theme_ids`` 为空的 singleton 链及无法映射阶段的 unknown
  节点均**不会**被丢弃，行为与各上游模块一致。
- **非破坏性**：每个阶段均返回新对象；输入 ``tagged_outputs`` 不会被修改。
- **链 ID 溯源**：链 ID 由 ``group_same_topic`` 在第 1 阶段赋值（格式
  ``same-topic-NNNN``），后续阶段原样保留，调用方可用于追踪链路来源。
- **证据可达性**：每个节点的 ``tagged_output`` 引用保持不变，
  可通过 ``node.tagged_output.evidence_links`` 和
  ``node.tagged_output.event.source_items`` 溯源到原始数据。
- **职责边界**：本模块不实现排序、评分、重要性过滤、Top-K 选择或 LLM 分析；
  这些职责属于后续节点（节点 7+）。

实现参考
--------
- 节点 3：``same_topic_grouping.group_same_topic``
- 节点 4：``temporal_connection.apply_temporal_order``
- 节点 5：``upstream_downstream.apply_upstream_downstream_order``
"""

from __future__ import annotations

from typing import Sequence

from app.chains.chain import InformationChain
from app.chains.same_topic_grouping import group_same_topic
from app.chains.temporal_connection import apply_temporal_order
from app.chains.upstream_downstream import apply_upstream_downstream_order
from app.entity.tagged_output import TaggedOutput


def generate_candidate_chains(
    tagged_outputs: Sequence[TaggedOutput],
) -> list[InformationChain]:
    """
    将 *tagged_outputs* 经三阶段流水线处理，返回候选信息链列表。

    流水线阶段
    ----------
    1. 同主题聚合（:func:`~app.chains.same_topic_grouping.group_same_topic`）
    2. 时序排序（:func:`~app.chains.temporal_connection.apply_temporal_order`）
    3. 上下游排序（:func:`~app.chains.upstream_downstream.apply_upstream_downstream_order`）

    参数
    ----
    tagged_outputs
        上游产出的 :class:`~app.entity.tagged_output.TaggedOutput` 序列；
        可以为空（返回空列表）。

    返回
    ----
    有序的 :class:`~app.chains.chain.InformationChain` 列表（候选链）；
    输入为空时返回空列表。
    列表顺序由 ``group_same_topic`` 的分组顺序决定（按各组首个节点的原始索引升序），
    后续两个阶段不改变链间顺序，仅改变每条链内节点顺序。

    注意
    ----
    **本函数仅生成候选链，不做排名、评分或最终筛选。**
    调用方负责后续的重要性评估和 Top-K 选择。
    """
    if not tagged_outputs:
        return []

    chains = group_same_topic(tagged_outputs)
    chains = apply_temporal_order(chains)
    chains = apply_upstream_downstream_order(chains)
    return chains
