"""
证据集合保留模块（Evidence Retention）

遍历 :class:`~app.chains.chain.InformationChain` 的有序节点，从每个节点的
:class:`~app.entity.tagged_output.TaggedOutput` 中聚合原始新闻条目与证据关联，
构建链级别的不可变证据束 :class:`ChainEvidenceBundle`。

设计决策
--------
- **不拷贝数据**：``source_items`` 和 ``evidence_links`` 均保留原始对象引用，
  不做深拷贝，确保下游可通过恒等比较（``is``）追溯到 原始 ``NewsItem`` 和 ``EvidenceLink``。
- **首见顺序（first-seen order）**：
  遍历节点时按 ``node.position`` 升序（即 ``chain.nodes`` 的存储顺序）处理，
  对每个节点的 ``source_items`` / ``evidence_links`` 子列表按原始顺序迭代，
  最终聚合元组的顺序等价于"在整个链中首次出现的位置"。
- **保守去重**：
  - ``source_items``：以对象身份（``id(...)``）为键去重，同一 ``NewsItem`` 实例
    出现多次时只保留首次引用；不同实例即使字段相同也各自保留。
  - ``evidence_links``：以值相等（``==`` / ``hash``）为键去重，内容完全相同的
    ``EvidenceLink`` 只保留首次出现；由于 ``EvidenceLink`` 为 ``frozen`` dataclass，
    ``==`` 语义为字段递归相等，``hash`` 由 Python 自动生成，去重行为确定且稳定。
- **不修改输入**：本模块不改写任何传入的 ``InformationChain``、``ChainNode`` 或
  ``TaggedOutput`` 对象，所有操作均为只读遍历。
- **不访问 DB、不排序、不过滤**：本模块仅做聚合，不与存储层交互，不做证据排序
  或重要性过滤，职责边界清晰。
- **冻结输出**：:class:`ChainEvidenceBundle` 为 ``frozen=True`` dataclass，
  所有字段为不可变元组，可安全哈希/缓存/传递。

职责边界
--------
本模块仅聚合链级别的证据集合，**不负责**：

- 修改存储 schema 或写入数据库；
- 对证据进行排名、评分或重要性过滤；
- 跨链合并或去重；
- 任何 LLM 调用或外部 I/O。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.chains.chain import InformationChain
from app.entity.evidence import EvidenceLink
from app.models.news_item import NewsItem


# ---------------------------------------------------------------------------
# ChainEvidenceBundle — 链级别证据束
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainEvidenceBundle:
    """
    一条 :class:`~app.chains.chain.InformationChain` 的链级别证据集合。

    字段
    ----
    chain_id
        来源链的唯一标识符，与 :attr:`InformationChain.chain_id` 相同。
    source_items
        链内所有节点贡献的原始 ``NewsItem`` 引用的有序元组，
        按首见顺序排列，按对象身份去重（不拷贝）。
    evidence_links
        链内所有节点贡献的 ``EvidenceLink`` 引用的有序元组，
        按首见顺序排列，按值相等去重（内容完全相同的证据关联只保留一次）。
    source_urls
        链内所有 source_items 的非空 URL，按首见顺序去重，用于
        报告中的来源链接溯源展示。默认值为空元组，
        确保已有代码向后兼容。
    """

    chain_id: str
    source_items: tuple[NewsItem, ...]
    evidence_links: tuple[EvidenceLink, ...]
    source_urls: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# collect_chain_evidence — 单链聚合
# ---------------------------------------------------------------------------


def collect_chain_evidence(chain: InformationChain) -> ChainEvidenceBundle:
    """
    遍历 *chain* 的所有节点，聚合并返回链级别的 :class:`ChainEvidenceBundle`。

    聚合规则
    --------
    - 按 ``chain.nodes`` 的原始顺序（即 ``position`` 升序）逐节点处理。
    - 每个节点贡献 ``node.tagged_output.event.source_items``（列表）和
      ``node.tagged_output.evidence_links``（元组）。
    - ``source_items`` 按对象身份（``id(obj)``）去重，首见者保留，后续重复引用丢弃。
    - ``evidence_links`` 按值相等（``==``）去重，首见者保留，后续内容相同者丢弃。
    - 去重后的顺序等价于整条链中各元素的首次出现位置。

    参数
    ----
    chain
        待聚合的 :class:`~app.chains.chain.InformationChain`；不可变，不会被修改。

    返回
    ----
    一个不可变的 :class:`ChainEvidenceBundle`，``chain_id`` 与 *chain* 一致。
    """
    seen_item_ids: set[int] = set()
    seen_link_keys: set[EvidenceLink] = set()
    seen_urls: set[str] = set()

    agg_items: list[NewsItem] = []
    agg_links: list[EvidenceLink] = []
    agg_urls: list[str] = []

    for node in chain.nodes:
        to = node.tagged_output

        for item in to.event.source_items:
            oid = id(item)
            if oid not in seen_item_ids:
                seen_item_ids.add(oid)
                agg_items.append(item)
            # 提取非空 URL 并去重
            if item.url and item.url not in seen_urls:
                seen_urls.add(item.url)
                agg_urls.append(item.url)

        for link in to.evidence_links:
            if link not in seen_link_keys:
                seen_link_keys.add(link)
                agg_links.append(link)

    return ChainEvidenceBundle(
        chain_id=chain.chain_id,
        source_items=tuple(agg_items),
        evidence_links=tuple(agg_links),
        source_urls=tuple(agg_urls),
    )


# ---------------------------------------------------------------------------
# collect_all_evidence — 多链聚合
# ---------------------------------------------------------------------------


def collect_all_evidence(
    chains: Sequence[InformationChain],
) -> list[ChainEvidenceBundle]:
    """
    对 *chains* 中的每条链分别调用 :func:`collect_chain_evidence`，
    返回与输入顺序对应的 :class:`ChainEvidenceBundle` 列表。

    每条链的证据聚合独立进行，链间不做跨链去重或合并。

    参数
    ----
    chains
        :class:`~app.chains.chain.InformationChain` 序列；可以为空（返回空列表）。

    返回
    ----
    与 *chains* 顺序对应的 :class:`ChainEvidenceBundle` 列表；
    输入为空时返回空列表。
    """
    return [collect_chain_evidence(chain) for chain in chains]
