"""
上下游连接模块（Upstream/Downstream Connection）

对已有 :class:`~app.chains.chain.InformationChain` 内的节点按供应链阶段排序，
将上游节点置前、下游节点置后，并将相邻节点间的关系类型标记为
:data:`~app.chains.relation_type.RelationType.UPSTREAM_DOWNSTREAM`。

设计决策（自主决策记录）
------------------------
用户不在线期间，在综合链路约束与简洁性后自主确定以下方案：

- **启发式阶段推断，不依赖归一化字段**：当前数据模型没有归一化的显式供应链阶段字段，
  因此从节点的 ``TaggedOutput.theme_ids`` 推断粗粒度阶段。
  这是高精度低召回的保守设计：命中者必定属于该阶段；未命中者进入未知阶段，不丢弃。

- **主题→阶段映射（确定性，不可随意扩展）**：

  =================  ==========================================
  阶段               对应 theme_id 集合
  =================  ==========================================
  upstream（上游）    semiconductor, memory, gpu, optical_module, storage
  midstream（中游）   compute, supply_chain
  downstream（下游）  cloud, foundation_model, ai_application, ai
  unknown（未知）     不匹配任何阶段的节点
  =================  ==========================================

  如需扩展映射，应修改本模块顶部的 ``_STAGE_THEMES`` 常量，并同步更新测试。

- **多阶段优先级**：若节点的 ``theme_ids`` 命中多个阶段桶，取优先级最高（最上游）的阶段：
  upstream(0) > midstream(1) > downstream(2)。

- **未知阶段置后**：theme_ids 不命中任何阶段的节点，阶段秩为 3（排在 downstream 之后）。

- **原地重排而非多关系存储**：上下游连接直接在现有节点内重新排序，不引入新的多关系节点结构。
  同主题语义通过链的分组来源与链级别 ``theme_ids`` 保留，本模块不试图发明多关系存储。

- **稳定性保证**：相同阶段秩的节点之间保留原始相对顺序（使用 Python 内置稳定排序）。

- **非破坏性**：输入链不会被修改；每次调用都返回全新的 ``InformationChain`` 对象。

- **确定性**：仅依赖 theme_ids 集合交集，无随机成分。

- **职责边界**：本模块仅负责确定性的阶段重排/连接；不实现候选筛选、评分、
  跨链合并或证据过滤。

局限性说明
----------
- 阶段推断依赖于 theme_ids 中预定义的字面量 ID，对于拼写变体或新增主题无法自动覆盖。
- 多主题节点只取最上游阶段，可能掩盖节点的真实跨阶段属性。
- unknown 阶段仅做保留处理，不尝试进一步推断其供应链位置。

实现参考
--------
- 节点 1（chain.py）：``ChainNode``、``InformationChain``
- 节点 2（relation_type.py）：``RelationType.UPSTREAM_DOWNSTREAM``
- 节点 3（same_topic_grouping.py）：上游输入来源
- 节点 4（temporal_connection.py）：设计模式参考
"""

from __future__ import annotations

from typing import Sequence

from app.chains.chain import ChainNode, InformationChain
from app.chains.relation_type import RelationType


# ---------------------------------------------------------------------------
# 阶段定义与主题映射
# ---------------------------------------------------------------------------

# 阶段秩常量（数值越小越上游）
_RANK_UPSTREAM: int = 0
_RANK_MIDSTREAM: int = 1
_RANK_DOWNSTREAM: int = 2
_RANK_UNKNOWN: int = 3

# 主题 ID → 阶段秩的映射表（确定性；不得在此之外动态修改）
_STAGE_THEMES: dict[str, int] = {
    # upstream
    "semiconductor": _RANK_UPSTREAM,
    "memory": _RANK_UPSTREAM,
    "gpu": _RANK_UPSTREAM,
    "optical_module": _RANK_UPSTREAM,
    "storage": _RANK_UPSTREAM,
    # midstream
    "compute": _RANK_MIDSTREAM,
    "supply_chain": _RANK_MIDSTREAM,
    # downstream
    "cloud": _RANK_DOWNSTREAM,
    "foundation_model": _RANK_DOWNSTREAM,
    "ai_application": _RANK_DOWNSTREAM,
    "ai": _RANK_DOWNSTREAM,
}


# ---------------------------------------------------------------------------
# 内部辅助：单节点阶段秩推断
# ---------------------------------------------------------------------------


def _stage_rank(node: ChainNode) -> int:
    """
    从节点的 ``theme_ids`` 推断供应链阶段秩。

    - 若命中一个或多个阶段桶，返回最小（最上游）的阶段秩。
    - 若无命中，返回 ``_RANK_UNKNOWN``（排在所有已知阶段之后）。
    """
    ranks = [
        _STAGE_THEMES[tid]
        for tid in node.tagged_output.theme_ids
        if tid in _STAGE_THEMES
    ]
    return min(ranks) if ranks else _RANK_UNKNOWN


# ---------------------------------------------------------------------------
# 内部辅助：单条链的阶段重排
# ---------------------------------------------------------------------------


def _reorder_chain(chain: InformationChain) -> InformationChain:
    """
    对单条链内的节点按供应链阶段秩升序重排，返回新的
    :class:`~app.chains.chain.InformationChain`。

    - 阶段秩：upstream(0) < midstream(1) < downstream(2) < unknown(3)。
    - 相同阶段秩的节点保持原始相对顺序（Python 稳定排序）。
    - 首节点 ``relation_to_prev = None``，其余节点
      ``relation_to_prev = RelationType.UPSTREAM_DOWNSTREAM``。
    - ``chain_id``、``theme_ids``、``entity_type_ids`` 原样保留。
    - 节点 ``position`` 重新赋值为 0-based 连续整数。
    """
    sorted_nodes = sorted(chain.nodes, key=_stage_rank)

    new_nodes: list[ChainNode] = []
    for position, old_node in enumerate(sorted_nodes):
        relation = None if position == 0 else RelationType.UPSTREAM_DOWNSTREAM
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


def apply_upstream_downstream_order(
    chains: Sequence[InformationChain],
) -> list[InformationChain]:
    """
    对每条 :class:`~app.chains.chain.InformationChain` 内的节点按供应链阶段升序重排，
    并将相邻节点间的关系类型标记为
    :data:`~app.chains.relation_type.RelationType.UPSTREAM_DOWNSTREAM`。

    阶段推断规则
    ------------
    节点的供应链阶段从其 ``tagged_output.theme_ids`` 通过预定义映射推断：

    - **upstream（上游）**：theme_ids 包含 ``semiconductor``、``memory``、``gpu``、
      ``optical_module`` 或 ``storage`` 之一。
    - **midstream（中游）**：theme_ids 包含 ``compute`` 或 ``supply_chain``。
    - **downstream（下游）**：theme_ids 包含 ``cloud``、``foundation_model``、
      ``ai_application`` 或 ``ai``。
    - **unknown（未知）**：theme_ids 不命中任何上述映射。

    优先级规则
    ----------
    - 若节点命中多个阶段桶，取最上游的阶段（upstream > midstream > downstream）。
    - 未知阶段节点排在所有已知阶段之后。

    稳定性
    ------
    相同阶段秩的节点之间保留原始相对顺序（稳定排序）。

    关系类型
    --------
    - 每条输出链的首节点 ``relation_to_prev = None``。
    - 其余节点 ``relation_to_prev = RelationType.UPSTREAM_DOWNSTREAM``。

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
        通常来自 :func:`~app.chains.temporal_connection.apply_temporal_order` 的输出。
        可以为空序列（返回空列表）。

    返回
    ----
    与输入等长的 :class:`~app.chains.chain.InformationChain` 列表，
    每条链的节点已按供应链阶段升序重排。
    """
    return [_reorder_chain(chain) for chain in chains]
