"""
时序连接模块（Temporal Connection）

对已有 :class:`~app.chains.chain.InformationChain` 内的节点按事件发生日期升序重排，
并将相邻节点间的关系类型标记为 :data:`~app.chains.relation_type.RelationType.TEMPORAL`。

设计决策（自主决策记录）
------------------------
用户不在线期间，在综合链路约束与简洁性后自主确定以下方案：

- **原地重排而非多关系存储**：时序连接直接在现有 ``InformationChain`` 的节点内
  重新排序，而非引入新的多关系节点结构。同主题语义通过链的分组来源与链级别
  ``theme_ids`` 保留，本模块不试图发明多关系存储。
- **排序键**：使用 ``node.tagged_output.event.occurred_at``（``"YYYY-MM-DD"`` 字符串）
  作为排序依据；空字符串被视为"日期未知"，排在所有已知日期之后。
- **稳定性保证**：``occurred_at`` 相同（含均为空）的节点之间保留原始相对顺序
  （使用 Python 内置稳定排序）。
- **非破坏性**：输入链不会被修改；每次调用都返回全新的 ``InformationChain`` 对象。
- **确定性**：仅依赖字符串比较（ISO-8601 字典序与时间序等价），无随机成分。
- **职责边界**：本模块仅负责确定性的时序重排/连接；不实现上下游连接、评分、
  候选筛选或证据过滤。

实现参考
--------
- 节点 1（chain.py）：``ChainNode``、``InformationChain``
- 节点 2（relation_type.py）：``RelationType.TEMPORAL``
- 节点 3（same_topic_grouping.py）：上游输入来源
"""

from __future__ import annotations

from typing import Sequence

from app.chains.chain import ChainNode, InformationChain
from app.chains.relation_type import RelationType


# ---------------------------------------------------------------------------
# 内部辅助：单条链的时序重排
# ---------------------------------------------------------------------------

# ``occurred_at`` 为空字符串时的排序哨兵值（大于任何合法 ISO-8601 日期字符串）
_UNKNOWN_DATE_SENTINEL = "\xff"


def _sort_key(node: ChainNode) -> str:
    """返回节点的排序键：已知日期原样返回，未知/空日期返回哨兵值（置后）。"""
    date = node.tagged_output.event.occurred_at
    return date if date else _UNKNOWN_DATE_SENTINEL


def _reorder_chain(chain: InformationChain) -> InformationChain:
    """
    对单条链内的节点按 ``occurred_at`` 升序重排，返回新的
    :class:`~app.chains.chain.InformationChain`。

    - 已知日期按 ISO-8601 字典序升序。
    - 空日期（未知）排在所有已知日期之后。
    - 日期相同（含均为空）的节点保持原始相对顺序（Python 稳定排序）。
    - 首节点 ``relation_to_prev = None``，其余节点 ``relation_to_prev = RelationType.TEMPORAL``。
    - ``chain_id``、``theme_ids``、``entity_type_ids`` 原样保留。
    - 节点 ``position`` 重新赋值为 0-based 连续整数。
    """
    sorted_nodes = sorted(chain.nodes, key=_sort_key)

    new_nodes: list[ChainNode] = []
    for position, old_node in enumerate(sorted_nodes):
        relation = None if position == 0 else RelationType.TEMPORAL
        new_nodes.append(
            ChainNode(
                tagged_output=old_node.tagged_output,
                position=position,
                relation_to_prev=relation,
            )
        )

    return InformationChain(
        chain_id=chain.chain_id,
        nodes=tuple(new_nodes),
        theme_ids=chain.theme_ids,
        entity_type_ids=chain.entity_type_ids,
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def apply_temporal_order(
    chains: Sequence[InformationChain],
) -> list[InformationChain]:
    """
    对每条 :class:`~app.chains.chain.InformationChain` 内的节点按事件发生日期升序重排，
    并将相邻节点间的关系类型标记为
    :data:`~app.chains.relation_type.RelationType.TEMPORAL`。

    排序规则
    --------
    - 排序键为 ``node.tagged_output.event.occurred_at``（``"YYYY-MM-DD"`` 字符串）。
    - 日期非空时按 ISO-8601 字典序升序排列（与时间序等价）。
    - 日期为空字符串（未知）时，视为日期最大值，排在所有已知日期之后。
    - 日期相同（含均为空）的节点之间保留原始相对顺序（稳定排序）。

    关系类型
    --------
    - 每条输出链的首节点 ``relation_to_prev = None``。
    - 其余节点 ``relation_to_prev = RelationType.TEMPORAL``。

    保留字段
    --------
    - ``chain_id``：原样保留。
    - ``theme_ids``：原样保留。
    - ``entity_type_ids``：原样保留。
    - ``node.tagged_output``：保留原始引用，不做复制。
    - 节点 ``position``：重新赋值为 0-based 连续整数。

    非破坏性
    --------
    输入链不会被修改；每个输出链均为全新对象。

    参数
    ----
    chains
        待处理的 :class:`~app.chains.chain.InformationChain` 序列，
        通常来自 :func:`~app.chains.same_topic_grouping.group_same_topic` 的输出。
        可以为空序列（返回空列表）。

    返回
    ----
    与输入等长的 :class:`~app.chains.chain.InformationChain` 列表，
    每条链的节点已按时间升序重排。
    """
    return [_reorder_chain(chain) for chain in chains]
