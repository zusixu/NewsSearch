"""
同主题聚合模块（Same-Topic Grouping）

将一组 :class:`~app.entity.tagged_output.TaggedOutput` 按共享的 ``theme_ids``
进行传递闭包聚合，生成多条 :class:`~app.chains.chain.InformationChain`，
每条链的内部节点关系标记为 :data:`~app.chains.relation_type.RelationType.SAME_TOPIC`。

设计决策
--------
- **传递闭包**：使用路径压缩 Union-Find 算法实现传递性聚合。
  若 A 与 B 共享主题、B 与 C 共享主题，则 A、B、C 归入同一组，
  即使 A 与 C 不直接共享任何主题。
- **空 theme_ids 处理**：``theme_ids`` 为空的输入**不会被丢弃**；
  它们各自形成一个单节点链（singleton chain），以便下游阶段可继续处理。
  这是保守选择：保留数据优先于过早过滤。
- **输入顺序保留**：每组内各节点保留原始输入顺序，不按时间或其他字段重排序。
  排序职责由后续阶段（时序连接等）承担。
- **分组顺序确定性**：各组按其组内最小原始索引升序排列，确保相同输入始终
  产生相同输出顺序。
- **链 ID 格式**：``same-topic-NNNN``（4 位零填充，1-based），
  如 ``same-topic-0001``、``same-topic-0002``。
- **relation_to_prev 赋值**：每条链的首节点为 ``None``；后续节点为
  :data:`~app.chains.relation_type.RelationType.SAME_TOPIC`。
- **不负责评分或候选筛选**：本模块仅做确定性分组，不涉及时序排序、评分、
  上下游连接或最终候选选择。
"""

from __future__ import annotations

from typing import Sequence

from app.chains.chain import ChainNode, InformationChain
from app.chains.relation_type import RelationType
from app.entity.tagged_output import TaggedOutput


# ---------------------------------------------------------------------------
# 内部辅助：路径压缩 Union-Find
# ---------------------------------------------------------------------------


def _make_union_find(n: int) -> list[int]:
    """返回大小为 *n* 的 Union-Find 父节点数组（初始每个节点为自身根）。"""
    return list(range(n))


def _find(parent: list[int], x: int) -> int:
    """带路径压缩的查找操作，返回 *x* 的根节点。"""
    while parent[x] != x:
        parent[x] = parent[parent[x]]  # 路径减半
        x = parent[x]
    return x


def _union(parent: list[int], x: int, y: int) -> None:
    """将 *x* 和 *y* 所在的集合合并（按根节点合并，无按秩优化——输入规模小）。"""
    rx, ry = _find(parent, x), _find(parent, y)
    if rx != ry:
        parent[rx] = ry


# ---------------------------------------------------------------------------
# 内部辅助：按输入顺序归集分组
# ---------------------------------------------------------------------------


def _collect_groups(
    tagged_outputs: Sequence[TaggedOutput],
    parent: list[int],
) -> list[list[int]]:
    """
    将索引按 Union-Find 根节点分组，各组内按原始索引升序，
    各组间按组内最小索引升序。

    返回
    ----
    有序的索引列表的列表，每个子列表对应一个聚合组。
    """
    from collections import defaultdict

    buckets: dict[int, list[int]] = defaultdict(list)
    for i in range(len(tagged_outputs)):
        buckets[_find(parent, i)].append(i)

    # 各组内已按升序遍历；各组间按最小索引（即列表首元素）排序
    return sorted(buckets.values(), key=lambda g: g[0])


# ---------------------------------------------------------------------------
# 内部辅助：从一组索引构建 InformationChain
# ---------------------------------------------------------------------------


def _build_same_topic_chain(
    chain_id: str,
    indices: list[int],
    tagged_outputs: Sequence[TaggedOutput],
) -> InformationChain:
    """
    按 *indices* 顺序从 *tagged_outputs* 中取出节点，构建一条
    :class:`~app.chains.chain.InformationChain`。

    首节点 ``relation_to_prev = None``，后续节点
    ``relation_to_prev = RelationType.SAME_TOPIC``。
    """
    nodes: list[ChainNode] = []
    for position, original_idx in enumerate(indices):
        to = tagged_outputs[original_idx]
        relation = None if position == 0 else RelationType.SAME_TOPIC
        nodes.append(ChainNode(tagged_output=to, position=position, relation_to_prev=relation))

    # 链级别聚合：所有节点的主题/实体类型 ID 并集，去重升序
    all_theme_ids: set[str] = set()
    all_entity_type_ids: set[str] = set()
    for node in nodes:
        all_theme_ids.update(node.tagged_output.theme_ids)
        all_entity_type_ids.update(node.tagged_output.entity_type_ids)

    return InformationChain(
        chain_id=chain_id,
        nodes=tuple(nodes),
        theme_ids=tuple(sorted(all_theme_ids)),
        entity_type_ids=tuple(sorted(all_entity_type_ids)),
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def group_same_topic(
    tagged_outputs: Sequence[TaggedOutput],
) -> list[InformationChain]:
    """
    将 *tagged_outputs* 按共享 ``theme_ids`` 做传递闭包聚合，
    返回有序的 :class:`~app.chains.chain.InformationChain` 列表。

    聚合规则
    --------
    - 若两个 :class:`~app.entity.tagged_output.TaggedOutput` 共享至少一个
      ``theme_id``，则归入同一组（传递闭包：A-B、B-C 共享主题 ⇒ A、B、C 同组）。
    - ``theme_ids`` 为空的输入各自形成单节点链，**不会被丢弃**。
    - 各组内节点按原始输入顺序排列（不按时间重排）。
    - 各组间按组内首个节点的原始索引升序排列（确定性）。

    链 ID 格式
    ----------
    ``same-topic-NNNN``（4 位零填充，1-based），例如
    ``same-topic-0001``、``same-topic-0002``。

    关系类型
    --------
    每条链的首节点 ``relation_to_prev = None``；
    后续节点 ``relation_to_prev = RelationType.SAME_TOPIC``。

    参数
    ----
    tagged_outputs
        待聚合的 :class:`~app.entity.tagged_output.TaggedOutput` 序列，
        可以为空（返回空列表）。

    返回
    ----
    有序的 :class:`~app.chains.chain.InformationChain` 列表；
    输入为空时返回空列表。
    """
    if not tagged_outputs:
        return []

    n = len(tagged_outputs)
    parent = _make_union_find(n)

    # 按主题 ID 做传递闭包：同一主题的所有节点归入同一组
    theme_to_first_idx: dict[str, int] = {}
    for i, to in enumerate(tagged_outputs):
        for tid in to.theme_ids:
            if tid in theme_to_first_idx:
                _union(parent, i, theme_to_first_idx[tid])
            else:
                theme_to_first_idx[tid] = i

    groups = _collect_groups(tagged_outputs, parent)

    chains: list[InformationChain] = []
    for seq_num, indices in enumerate(groups, start=1):
        chain_id = f"same-topic-{seq_num:04d}"
        chains.append(_build_same_topic_chain(chain_id, indices, tagged_outputs))

    return chains
