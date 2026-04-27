"""
tests/test_evidence_retention.py — ChainEvidenceBundle / collect_chain_evidence /
collect_all_evidence 的专项测试套件

覆盖范围
--------
1. source_items 聚合（多节点链跨节点汇总）
2. evidence_links 聚合（多节点链跨节点汇总）
3. source_items 去重行为（对象身份）
4. evidence_links 去重行为（值相等）
5. 首见顺序保留（source_items）
6. 首见顺序保留（evidence_links）
7. chain_id 原样保留
8. 空证据关联处理
9. 单节点链行为
10. collect_all_evidence 多链行为
11. 导入面（import surface）
"""

from __future__ import annotations

import pytest

from app.chains import (
    ChainEvidenceBundle,
    collect_all_evidence,
    collect_chain_evidence,
)
from app.chains.evidence_retention import (
    ChainEvidenceBundle as _DirectBundle,
    collect_all_evidence as _direct_collect_all,
    collect_chain_evidence as _direct_collect,
)
from app.chains.chain import ChainNode, InformationChain
from app.entity.evidence import EvidenceLink, EvidenceSpan, build_evidence_links
from app.entity.rules.extractor import Hit
from app.entity.tagged_output import TaggedOutput, build_tagged_output
from app.models.event_draft import EventDraft
from app.models.news_item import NewsItem
from app.models.raw_document import RawDocument


# ---------------------------------------------------------------------------
# 测试辅助工厂
# ---------------------------------------------------------------------------


def _make_raw(title: str = "raw", date: str = "2025-01-01") -> RawDocument:
    return RawDocument(
        source="web",
        provider="test",
        title=title,
        content=None,
        url=None,
        date=date,
    )


def _make_news_item(title: str = "item", date: str = "2025-01-01") -> NewsItem:
    return NewsItem.from_raw(_make_raw(title=title, date=date))


def _make_event(
    title: str = "事件",
    date: str = "2025-01-01",
    items: list[NewsItem] | None = None,
) -> EventDraft:
    if items is not None:
        draft = EventDraft.from_news_item(items[0])
        draft.source_items = items
        return draft
    return EventDraft.from_news_item(_make_news_item(title=title, date=date))


def _make_hit(label_id: str, kind: str = "theme") -> Hit:
    return Hit(
        matched_text=label_id,
        start=0,
        end=len(label_id),
        matched_seed=label_id,
        kind=kind,  # type: ignore[arg-type]
        label_id=label_id,
    )


def _make_tagged(
    title: str = "事件",
    date: str = "2025-01-01",
    theme_ids: list[str] | None = None,
    news_items: list[NewsItem] | None = None,
    extra_links: list[EvidenceLink] | None = None,
) -> TaggedOutput:
    """构建 TaggedOutput，可指定底层 NewsItem 列表和额外 EvidenceLink。"""
    hits: list[Hit] = []
    text_parts: list[str] = []
    for tid in theme_ids or []:
        hits.append(_make_hit(tid, kind="theme"))
        text_parts.append(tid)
    text = " ".join(text_parts) or title
    links = build_evidence_links(text, hits, context_window=0)
    if extra_links:
        links = list(links) + list(extra_links)
    event = _make_event(title=title, date=date, items=news_items)
    return build_tagged_output(event, text, links)


def _make_evidence_link(label_id: str = "ai", snippet: str = "ai") -> EvidenceLink:
    """构造独立的 EvidenceLink 用于精确测试。"""
    hit = Hit(
        matched_text=snippet,
        start=0,
        end=len(snippet),
        matched_seed=snippet,
        kind="theme",  # type: ignore[arg-type]
        label_id=label_id,
    )
    span = EvidenceSpan(
        snippet=snippet,
        context_before="",
        context_after="",
        start=0,
        end=len(snippet),
    )
    return EvidenceLink(hit=hit, span=span)


def _build_chain(
    chain_id: str,
    tagged_outputs: list[TaggedOutput],
) -> InformationChain:
    """直接用 TaggedOutput 列表构建 InformationChain（不经过流水线）。"""
    from app.chains.chain import build_chain
    return build_chain(chain_id, tagged_outputs)


# ---------------------------------------------------------------------------
# 1. source_items 聚合（多节点链跨节点汇总）
# ---------------------------------------------------------------------------


class TestSourceItemAggregationMultiNode:
    """多节点链中 source_items 应跨节点汇总。"""

    def test_two_node_chain_collects_both_items(self):
        item_a = _make_news_item("A")
        item_b = _make_news_item("B")
        to1 = _make_tagged("E1", news_items=[item_a])
        to2 = _make_tagged("E2", news_items=[item_b])
        chain = _build_chain("c-1", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert item_a in bundle.source_items
        assert item_b in bundle.source_items

    def test_two_node_chain_total_count(self):
        item_a = _make_news_item("A")
        item_b = _make_news_item("B")
        to1 = _make_tagged("E1", news_items=[item_a])
        to2 = _make_tagged("E2", news_items=[item_b])
        chain = _build_chain("c-1", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert len(bundle.source_items) == 2

    def test_three_node_chain_all_items_present(self):
        items = [_make_news_item(f"N{i}") for i in range(3)]
        tos = [_make_tagged(f"E{i}", news_items=[items[i]]) for i in range(3)]
        chain = _build_chain("c-3", tos)
        bundle = collect_chain_evidence(chain)
        for item in items:
            assert item in bundle.source_items

    def test_node_with_multiple_source_items(self):
        items = [_make_news_item(f"X{i}") for i in range(3)]
        to = _make_tagged("E", news_items=items)
        chain = _build_chain("c-multi", [to])
        bundle = collect_chain_evidence(chain)
        assert len(bundle.source_items) == 3
        for item in items:
            assert item in bundle.source_items


# ---------------------------------------------------------------------------
# 2. evidence_links 聚合（多节点链跨节点汇总）
# ---------------------------------------------------------------------------


class TestEvidenceLinkAggregationMultiNode:
    """多节点链中 evidence_links 应跨节点汇总。"""

    def test_two_node_chain_aggregates_links(self):
        to1 = _make_tagged("E1", theme_ids=["gpu"])
        to2 = _make_tagged("E2", theme_ids=["cloud"])
        chain = _build_chain("c-ev-1", [to1, to2])
        bundle = collect_chain_evidence(chain)
        all_label_ids = {lnk.hit.label_id for lnk in bundle.evidence_links}
        assert "gpu" in all_label_ids
        assert "cloud" in all_label_ids

    def test_three_node_chain_aggregates_all_links(self):
        to1 = _make_tagged("E1", theme_ids=["gpu"])
        to2 = _make_tagged("E2", theme_ids=["cloud"])
        to3 = _make_tagged("E3", theme_ids=["ai"])
        chain = _build_chain("c-ev-3", [to1, to2, to3])
        bundle = collect_chain_evidence(chain)
        all_label_ids = {lnk.hit.label_id for lnk in bundle.evidence_links}
        assert all_label_ids >= {"gpu", "cloud", "ai"}

    def test_evidence_links_count_without_duplicates(self):
        to1 = _make_tagged("E1", theme_ids=["gpu"])
        to2 = _make_tagged("E2", theme_ids=["cloud"])
        chain = _build_chain("c-count", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert len(bundle.evidence_links) == 2


# ---------------------------------------------------------------------------
# 3. source_items 去重行为（对象身份）
# ---------------------------------------------------------------------------


class TestSourceItemDedup:
    """source_items 去重以对象身份（id）为准。"""

    def test_same_instance_not_duplicated(self):
        shared_item = _make_news_item("shared")
        to1 = _make_tagged("E1", news_items=[shared_item])
        to2 = _make_tagged("E2", news_items=[shared_item])
        chain = _build_chain("c-dedup-id", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert bundle.source_items.count(shared_item) == 1

    def test_same_instance_appears_once_multi_node(self):
        shared_item = _make_news_item("shared")
        tos = [_make_tagged(f"E{i}", news_items=[shared_item]) for i in range(4)]
        chain = _build_chain("c-dedup-multi", tos)
        bundle = collect_chain_evidence(chain)
        assert len(bundle.source_items) == 1

    def test_different_instances_equal_fields_both_kept(self):
        """值相同但不同实例的 NewsItem 应各自保留（identity去重）。"""
        item_a = _make_news_item("same-title")
        item_b = _make_news_item("same-title")
        assert item_a is not item_b
        to1 = _make_tagged("E1", news_items=[item_a])
        to2 = _make_tagged("E2", news_items=[item_b])
        chain = _build_chain("c-dedup-ident", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert len(bundle.source_items) == 2

    def test_partial_overlap_dedup(self):
        item_shared = _make_news_item("shared")
        item_unique = _make_news_item("unique")
        to1 = _make_tagged("E1", news_items=[item_shared, item_unique])
        to2 = _make_tagged("E2", news_items=[item_shared])
        chain = _build_chain("c-partial", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert len(bundle.source_items) == 2


# ---------------------------------------------------------------------------
# 4. evidence_links 去重行为（值相等）
# ---------------------------------------------------------------------------


class TestEvidenceLinkDedup:
    """evidence_links 去重以值相等（==）为准。"""

    def test_identical_link_not_duplicated(self):
        link = _make_evidence_link("ai", "ai")
        to1 = _make_tagged("E1", extra_links=[link])
        to2 = _make_tagged("E2", extra_links=[link])
        chain = _build_chain("c-ev-dedup", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert bundle.evidence_links.count(link) == 1

    def test_distinct_links_both_kept(self):
        link_a = _make_evidence_link("gpu", "gpu")
        link_b = _make_evidence_link("cloud", "cloud")
        to1 = _make_tagged("E1", extra_links=[link_a])
        to2 = _make_tagged("E2", extra_links=[link_b])
        chain = _build_chain("c-ev-distinct", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert link_a in bundle.evidence_links
        assert link_b in bundle.evidence_links

    def test_value_equal_different_objects_deduped(self):
        """用相同参数构造的两个不同 EvidenceLink 对象应被视为相同并去重。"""
        link_x = _make_evidence_link("ai", "ai")
        link_y = _make_evidence_link("ai", "ai")
        assert link_x is not link_y
        assert link_x == link_y
        to1 = _make_tagged("E1", extra_links=[link_x])
        to2 = _make_tagged("E2", extra_links=[link_y])
        chain = _build_chain("c-ev-val-eq", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert len([lnk for lnk in bundle.evidence_links if lnk.hit.label_id == "ai"]) == 1


# ---------------------------------------------------------------------------
# 5. 首见顺序保留（source_items）
# ---------------------------------------------------------------------------


class TestSourceItemFirstSeenOrder:
    """source_items 应按在链中首次出现的顺序排列。"""

    def test_first_node_item_comes_first(self):
        item_first = _make_news_item("first")
        item_second = _make_news_item("second")
        to1 = _make_tagged("E1", news_items=[item_first])
        to2 = _make_tagged("E2", news_items=[item_second])
        chain = _build_chain("c-order-1", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert bundle.source_items[0] is item_first
        assert bundle.source_items[1] is item_second

    def test_multi_item_node_preserves_internal_order(self):
        items = [_make_news_item(f"item-{i}") for i in range(3)]
        to = _make_tagged("E", news_items=items)
        chain = _build_chain("c-internal-order", [to])
        bundle = collect_chain_evidence(chain)
        for i, item in enumerate(items):
            assert bundle.source_items[i] is item

    def test_shared_item_keeps_first_occurrence_position(self):
        item_shared = _make_news_item("shared")
        item_late = _make_news_item("late")
        to1 = _make_tagged("E1", news_items=[item_shared])
        to2 = _make_tagged("E2", news_items=[item_shared, item_late])
        chain = _build_chain("c-first-seen", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert bundle.source_items[0] is item_shared
        assert bundle.source_items[1] is item_late


# ---------------------------------------------------------------------------
# 6. 首见顺序保留（evidence_links）
# ---------------------------------------------------------------------------


class TestEvidenceLinkFirstSeenOrder:
    """evidence_links 应按在链中首次出现的顺序排列。"""

    def test_first_node_link_comes_first(self):
        to1 = _make_tagged("E1", theme_ids=["gpu"])
        to2 = _make_tagged("E2", theme_ids=["cloud"])
        chain = _build_chain("c-ev-order", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert bundle.evidence_links[0].hit.label_id == "gpu"
        assert bundle.evidence_links[1].hit.label_id == "cloud"

    def test_duplicate_link_position_is_first_occurrence(self):
        link = _make_evidence_link("ai", "ai")
        link_other = _make_evidence_link("gpu", "gpu")
        to1 = _make_tagged("E1", extra_links=[link])
        to2 = _make_tagged("E2", extra_links=[link, link_other])
        chain = _build_chain("c-ev-first-seen", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert bundle.evidence_links[0] == link
        assert bundle.evidence_links[-1] == link_other


# ---------------------------------------------------------------------------
# 7. chain_id 原样保留
# ---------------------------------------------------------------------------


class TestChainIdPreservation:
    """ChainEvidenceBundle.chain_id 应与来源链的 chain_id 完全一致。"""

    def test_chain_id_matches_source_chain(self):
        to = _make_tagged("E", theme_ids=["ai"])
        chain = _build_chain("my-chain-42", [to])
        bundle = collect_chain_evidence(chain)
        assert bundle.chain_id == "my-chain-42"

    def test_same_topic_chain_id_preserved(self):
        from app.chains.same_topic_grouping import group_same_topic
        to1 = _make_tagged("E1", theme_ids=["gpu"])
        to2 = _make_tagged("E2", theme_ids=["gpu"])
        chains = group_same_topic([to1, to2])
        assert len(chains) == 1
        bundle = collect_chain_evidence(chains[0])
        assert bundle.chain_id == chains[0].chain_id

    def test_collect_all_preserves_each_chain_id(self):
        to1 = _make_tagged("E1", theme_ids=["gpu"])
        to2 = _make_tagged("E2", theme_ids=["cloud"])
        chain_a = _build_chain("id-alpha", [to1])
        chain_b = _build_chain("id-beta", [to2])
        bundles = collect_all_evidence([chain_a, chain_b])
        assert bundles[0].chain_id == "id-alpha"
        assert bundles[1].chain_id == "id-beta"


# ---------------------------------------------------------------------------
# 8. 空证据关联处理
# ---------------------------------------------------------------------------


class TestEmptyEvidenceLinks:
    """节点没有 evidence_links 时 bundle 应有空元组，不抛出异常。"""

    def test_no_theme_ids_yields_empty_evidence_links(self):
        to = _make_tagged("E", theme_ids=[])
        chain = _build_chain("c-empty-ev", [to])
        bundle = collect_chain_evidence(chain)
        assert bundle.evidence_links == ()

    def test_multi_node_all_empty_links(self):
        to1 = _make_tagged("E1", theme_ids=[])
        to2 = _make_tagged("E2", theme_ids=[])
        chain = _build_chain("c-empty-multi", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert bundle.evidence_links == ()

    def test_mixed_some_empty_links(self):
        to1 = _make_tagged("E1", theme_ids=[])
        to2 = _make_tagged("E2", theme_ids=["gpu"])
        chain = _build_chain("c-mixed-ev", [to1, to2])
        bundle = collect_chain_evidence(chain)
        assert len(bundle.evidence_links) == 1
        assert bundle.evidence_links[0].hit.label_id == "gpu"


# ---------------------------------------------------------------------------
# 9. 单节点链行为
# ---------------------------------------------------------------------------


class TestSingleNodeChain:
    """单节点链应正确构建 bundle 而不抛出异常。"""

    def test_single_node_source_items(self):
        item = _make_news_item("solo")
        to = _make_tagged("E", news_items=[item])
        chain = _build_chain("c-solo", [to])
        bundle = collect_chain_evidence(chain)
        assert len(bundle.source_items) == 1
        assert bundle.source_items[0] is item

    def test_single_node_evidence_links(self):
        to = _make_tagged("E", theme_ids=["ai"])
        chain = _build_chain("c-solo-ev", [to])
        bundle = collect_chain_evidence(chain)
        assert len(bundle.evidence_links) == 1
        assert bundle.evidence_links[0].hit.label_id == "ai"

    def test_single_node_bundle_is_frozen(self):
        to = _make_tagged("E", theme_ids=["gpu"])
        chain = _build_chain("c-solo-frozen", [to])
        bundle = collect_chain_evidence(chain)
        with pytest.raises((AttributeError, TypeError)):
            bundle.chain_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 10. collect_all_evidence 多链行为
# ---------------------------------------------------------------------------


class TestCollectAllEvidence:
    """collect_all_evidence 应对每条链独立聚合，顺序与输入一致。"""

    def test_empty_chains_returns_empty_list(self):
        result = collect_all_evidence([])
        assert result == []

    def test_single_chain_wrapped_in_list(self):
        to = _make_tagged("E", theme_ids=["gpu"])
        chain = _build_chain("c-wrap", [to])
        result = collect_all_evidence([chain])
        assert len(result) == 1
        assert result[0].chain_id == "c-wrap"

    def test_two_chains_independent_evidence(self):
        item_a = _make_news_item("A")
        item_b = _make_news_item("B")
        to1 = _make_tagged("E1", news_items=[item_a], theme_ids=["gpu"])
        to2 = _make_tagged("E2", news_items=[item_b], theme_ids=["cloud"])
        chain_a = _build_chain("ca", [to1])
        chain_b = _build_chain("cb", [to2])
        bundles = collect_all_evidence([chain_a, chain_b])
        assert bundles[0].source_items == (item_a,)
        assert bundles[1].source_items == (item_b,)

    def test_output_order_matches_input_order(self):
        tos = [_make_tagged(f"E{i}", theme_ids=[f"t{i}"]) for i in range(4)]
        chains = [_build_chain(f"chain-{i}", [tos[i]]) for i in range(4)]
        bundles = collect_all_evidence(chains)
        assert [b.chain_id for b in bundles] == [f"chain-{i}" for i in range(4)]

    def test_chains_do_not_share_evidence_sets(self):
        """两条链的 bundle 即使有相同 NewsItem 实例，证据集合仍独立（链内各自聚合）。"""
        shared_item = _make_news_item("shared")
        to1 = _make_tagged("E1", news_items=[shared_item])
        to2 = _make_tagged("E2", news_items=[shared_item])
        chain_a = _build_chain("ca2", [to1])
        chain_b = _build_chain("cb2", [to2])
        bundles = collect_all_evidence([chain_a, chain_b])
        # each bundle independently includes the shared item
        assert shared_item in bundles[0].source_items
        assert shared_item in bundles[1].source_items

    def test_collect_all_returns_list_type(self):
        to = _make_tagged("E", theme_ids=["ai"])
        chain = _build_chain("c-type", [to])
        result = collect_all_evidence([chain])
        assert isinstance(result, list)

    def test_bundle_source_items_is_tuple(self):
        to = _make_tagged("E", theme_ids=["gpu"])
        chain = _build_chain("c-tuple", [to])
        bundle = collect_chain_evidence(chain)
        assert isinstance(bundle.source_items, tuple)

    def test_bundle_evidence_links_is_tuple(self):
        to = _make_tagged("E", theme_ids=["ai"])
        chain = _build_chain("c-ev-tuple", [to])
        bundle = collect_chain_evidence(chain)
        assert isinstance(bundle.evidence_links, tuple)


# ---------------------------------------------------------------------------
# 11. 导入面（import surface）
# ---------------------------------------------------------------------------


class TestImportSurface:
    """公开 API 应从 app.chains 包直接导入。"""

    def test_chain_evidence_bundle_importable_from_package(self):
        from app.chains import ChainEvidenceBundle
        assert ChainEvidenceBundle is _DirectBundle

    def test_collect_chain_evidence_importable_from_package(self):
        from app.chains import collect_chain_evidence
        assert collect_chain_evidence is _direct_collect

    def test_collect_all_evidence_importable_from_package(self):
        from app.chains import collect_all_evidence
        assert collect_all_evidence is _direct_collect_all

    def test_all_exports_present_in_dunder_all(self):
        import app.chains as pkg
        assert "ChainEvidenceBundle" in pkg.__all__
        assert "collect_chain_evidence" in pkg.__all__
        assert "collect_all_evidence" in pkg.__all__

    def test_chain_evidence_bundle_is_dataclass(self):
        import dataclasses
        assert dataclasses.is_dataclass(ChainEvidenceBundle)
