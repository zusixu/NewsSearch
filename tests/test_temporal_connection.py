"""
tests/test_temporal_connection.py — apply_temporal_order 的专项测试套件

覆盖范围
--------
1. 时间升序重排（chronological reordering）
2. 等日期稳定性（equal-date stability）
3. 未知日期置后（unknown-date placement）
4. chain_id 保留（chain_id preservation）
5. 聚合字段保留（aggregate preservation：theme_ids, entity_type_ids）
6. relation_to_prev 赋值为 TEMPORAL（relation_to_prev assignment）
7. 单节点与空输入行为（singleton and empty input behavior）
8. 导入面（import surface）
"""

from __future__ import annotations

import pytest

from app.chains.temporal_connection import apply_temporal_order
from app.chains import apply_temporal_order as apply_temporal_order_pkg  # import surface
from app.chains.chain import ChainNode, InformationChain
from app.chains.relation_type import RelationType
from app.entity.evidence import build_evidence_links
from app.entity.rules.extractor import Hit
from app.entity.tagged_output import TaggedOutput, build_tagged_output
from app.models.event_draft import EventDraft
from app.models.news_item import NewsItem
from app.models.raw_document import RawDocument


# ---------------------------------------------------------------------------
# 测试辅助工厂
# ---------------------------------------------------------------------------


def _make_raw(title: str = "test", date: str = "2025-01-01") -> RawDocument:
    return RawDocument(
        source="web",
        provider="test",
        title=title,
        content=None,
        url=None,
        date=date,
    )


def _make_event(title: str = "测试事件", date: str = "2025-01-01") -> EventDraft:
    return EventDraft.from_news_item(NewsItem.from_raw(_make_raw(title=title, date=date)))


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
    entity_type_ids: list[str] | None = None,
) -> TaggedOutput:
    """构建带指定 occurred_at 日期的 TaggedOutput。"""
    hits: list[Hit] = []
    text_parts: list[str] = []
    for tid in theme_ids or []:
        hits.append(_make_hit(tid, kind="theme"))
        text_parts.append(tid)
    for eid in entity_type_ids or []:
        hits.append(_make_hit(eid, kind="entity_type"))
        text_parts.append(eid)
    text = " ".join(text_parts) or title
    links = build_evidence_links(text, hits, context_window=0)
    return build_tagged_output(_make_event(title=title, date=date), text, links)


def _make_chain(
    chain_id: str,
    tagged_outputs: list[TaggedOutput],
    theme_ids: tuple[str, ...] = (),
    entity_type_ids: tuple[str, ...] = (),
) -> InformationChain:
    """构建用于测试的 InformationChain（首节点 None，后续 SAME_TOPIC）。"""
    nodes = tuple(
        ChainNode(
            tagged_output=to,
            position=i,
            relation_to_prev=None if i == 0 else RelationType.SAME_TOPIC,
        )
        for i, to in enumerate(tagged_outputs)
    )
    return InformationChain(
        chain_id=chain_id,
        nodes=nodes,
        theme_ids=theme_ids,
        entity_type_ids=entity_type_ids,
    )


# ---------------------------------------------------------------------------
# 1. 时间升序重排（chronological reordering）
# ---------------------------------------------------------------------------


class TestChronologicalReordering:
    """节点应按 occurred_at 升序重排。"""

    def test_two_nodes_out_of_order_are_reordered(self):
        later = _make_tagged("B", date="2025-03-01")
        earlier = _make_tagged("A", date="2025-01-01")
        chain = _make_chain("c1", [later, earlier])
        result = apply_temporal_order([chain])
        assert len(result) == 1
        nodes = result[0].nodes
        assert nodes[0].tagged_output.event.occurred_at == "2025-01-01"
        assert nodes[1].tagged_output.event.occurred_at == "2025-03-01"

    def test_three_nodes_shuffled_sorted_ascending(self):
        t3 = _make_tagged("C", date="2025-12-31")
        t1 = _make_tagged("A", date="2025-01-01")
        t2 = _make_tagged("B", date="2025-06-15")
        chain = _make_chain("c2", [t3, t1, t2])
        result = apply_temporal_order([chain])
        dates = [n.tagged_output.event.occurred_at for n in result[0].nodes]
        assert dates == ["2025-01-01", "2025-06-15", "2025-12-31"]

    def test_already_sorted_chain_unchanged_order(self):
        t1 = _make_tagged("A", date="2025-01-01")
        t2 = _make_tagged("B", date="2025-02-01")
        t3 = _make_tagged("C", date="2025-03-01")
        chain = _make_chain("c3", [t1, t2, t3])
        result = apply_temporal_order([chain])
        dates = [n.tagged_output.event.occurred_at for n in result[0].nodes]
        assert dates == ["2025-01-01", "2025-02-01", "2025-03-01"]

    def test_positions_reassigned_0_based_after_reorder(self):
        t2 = _make_tagged("B", date="2025-06-01")
        t1 = _make_tagged("A", date="2025-01-01")
        chain = _make_chain("c4", [t2, t1])
        result = apply_temporal_order([chain])
        positions = [n.position for n in result[0].nodes]
        assert positions == [0, 1]

    def test_multiple_chains_each_independently_sorted(self):
        # chain A: reversed
        a2 = _make_tagged("A2", date="2025-09-01")
        a1 = _make_tagged("A1", date="2025-01-01")
        ca = _make_chain("ca", [a2, a1])
        # chain B: already sorted
        b1 = _make_tagged("B1", date="2024-06-01")
        b2 = _make_tagged("B2", date="2024-12-31")
        cb = _make_chain("cb", [b1, b2])
        results = apply_temporal_order([ca, cb])
        dates_a = [n.tagged_output.event.occurred_at for n in results[0].nodes]
        dates_b = [n.tagged_output.event.occurred_at for n in results[1].nodes]
        assert dates_a == ["2025-01-01", "2025-09-01"]
        assert dates_b == ["2024-06-01", "2024-12-31"]


# ---------------------------------------------------------------------------
# 2. 等日期稳定性（equal-date stability）
# ---------------------------------------------------------------------------


class TestEqualDateStability:
    """相同日期的节点应保持原始相对顺序。"""

    def test_two_same_date_nodes_preserve_order(self):
        first = _make_tagged("first", date="2025-05-01")
        second = _make_tagged("second", date="2025-05-01")
        chain = _make_chain("eq1", [first, second])
        result = apply_temporal_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["first", "second"]

    def test_three_same_date_nodes_preserve_order(self):
        a = _make_tagged("a", date="2025-03-15")
        b = _make_tagged("b", date="2025-03-15")
        c = _make_tagged("c", date="2025-03-15")
        chain = _make_chain("eq2", [a, b, c])
        result = apply_temporal_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["a", "b", "c"]

    def test_mixed_dates_with_equal_group_stable(self):
        # [later, early-first, early-second]
        later = _make_tagged("later", date="2025-12-01")
        e1 = _make_tagged("early-first", date="2025-01-01")
        e2 = _make_tagged("early-second", date="2025-01-01")
        chain = _make_chain("eq3", [later, e1, e2])
        result = apply_temporal_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["early-first", "early-second", "later"]

    def test_equal_dates_second_group_stable(self):
        # [a(Jan), b(Mar), c(Mar)] — b and c same date, should stay b,c
        a = _make_tagged("a", date="2025-01-10")
        b = _make_tagged("b", date="2025-03-20")
        c = _make_tagged("c", date="2025-03-20")
        chain = _make_chain("eq4", [a, b, c])
        result = apply_temporal_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# 3. 未知日期置后（unknown-date placement）
# ---------------------------------------------------------------------------


class TestUnknownDatePlacement:
    """空字符串 occurred_at 应排在所有已知日期之后。"""

    def test_unknown_date_placed_after_known(self):
        unknown = _make_tagged("unknown", date="")
        known = _make_tagged("known", date="2025-06-01")
        chain = _make_chain("u1", [unknown, known])
        result = apply_temporal_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["known", "unknown"]

    def test_multiple_unknown_dates_placed_after_all_known(self):
        u1 = _make_tagged("u1", date="")
        u2 = _make_tagged("u2", date="")
        k1 = _make_tagged("k1", date="2025-01-01")
        k2 = _make_tagged("k2", date="2025-06-01")
        chain = _make_chain("u2", [u1, u2, k1, k2])
        result = apply_temporal_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["k1", "k2", "u1", "u2"]

    def test_unknown_dates_preserve_relative_order(self):
        u1 = _make_tagged("u1", date="")
        u2 = _make_tagged("u2", date="")
        chain = _make_chain("u3", [u1, u2])
        result = apply_temporal_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["u1", "u2"]

    def test_all_unknown_dates_preserve_original_order(self):
        nodes = [_make_tagged(f"n{i}", date="") for i in range(4)]
        chain = _make_chain("u4", nodes)
        result = apply_temporal_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["n0", "n1", "n2", "n3"]

    def test_unknown_between_knowns_placed_last(self):
        k1 = _make_tagged("k1", date="2025-01-01")
        unknown = _make_tagged("unknown", date="")
        k2 = _make_tagged("k2", date="2025-03-01")
        chain = _make_chain("u5", [k1, unknown, k2])
        result = apply_temporal_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["k1", "k2", "unknown"]


# ---------------------------------------------------------------------------
# 4. chain_id 保留（chain_id preservation）
# ---------------------------------------------------------------------------


class TestChainIdPreservation:
    """输出链的 chain_id 必须与输入完全一致。"""

    def test_chain_id_preserved_single_chain(self):
        t1 = _make_tagged("A", date="2025-02-01")
        t2 = _make_tagged("B", date="2025-01-01")
        chain = _make_chain("my-chain-id-001", [t1, t2])
        result = apply_temporal_order([chain])
        assert result[0].chain_id == "my-chain-id-001"

    def test_chain_id_preserved_multiple_chains(self):
        chains = [
            _make_chain(f"chain-{i:03d}", [_make_tagged(f"n{i}", date="2025-01-01")])
            for i in range(5)
        ]
        results = apply_temporal_order(chains)
        for original, output in zip(chains, results):
            assert output.chain_id == original.chain_id

    def test_same_topic_style_chain_id_preserved(self):
        t1 = _make_tagged("A", date="2025-06-01")
        chain = _make_chain("same-topic-0003", [t1])
        result = apply_temporal_order([chain])
        assert result[0].chain_id == "same-topic-0003"


# ---------------------------------------------------------------------------
# 5. 聚合字段保留（aggregate preservation）
# ---------------------------------------------------------------------------


class TestAggregatePreservation:
    """theme_ids 和 entity_type_ids 应原样保留，不受节点重排影响。"""

    def test_theme_ids_preserved_after_reorder(self):
        t1 = _make_tagged("A", date="2025-09-01", theme_ids=["ai", "chip"])
        t2 = _make_tagged("B", date="2025-01-01", theme_ids=["ai"])
        chain = _make_chain("agg1", [t1, t2], theme_ids=("ai", "chip"))
        result = apply_temporal_order([chain])
        assert result[0].theme_ids == ("ai", "chip")

    def test_entity_type_ids_preserved_after_reorder(self):
        t1 = _make_tagged("A", date="2025-06-01", entity_type_ids=["company"])
        t2 = _make_tagged("B", date="2025-01-01", entity_type_ids=["product"])
        chain = _make_chain("agg2", [t1, t2], entity_type_ids=("company", "product"))
        result = apply_temporal_order([chain])
        assert result[0].entity_type_ids == ("company", "product")

    def test_empty_aggregates_preserved(self):
        t1 = _make_tagged("A", date="2025-01-01")
        chain = _make_chain("agg3", [t1], theme_ids=(), entity_type_ids=())
        result = apply_temporal_order([chain])
        assert result[0].theme_ids == ()
        assert result[0].entity_type_ids == ()

    def test_tagged_output_references_preserved(self):
        """重排后节点的 tagged_output 引用应指向原始对象（不拷贝）。"""
        t1 = _make_tagged("A", date="2025-09-01")
        t2 = _make_tagged("B", date="2025-01-01")
        chain = _make_chain("agg4", [t1, t2])
        result = apply_temporal_order([chain])
        # 重排后 position=0 应是 t2（早），position=1 是 t1（晚）
        assert result[0].nodes[0].tagged_output is t2
        assert result[0].nodes[1].tagged_output is t1


# ---------------------------------------------------------------------------
# 6. relation_to_prev 赋值为 TEMPORAL
# ---------------------------------------------------------------------------


class TestRelationToPrevAssignment:
    """首节点 relation_to_prev=None，后续节点 relation_to_prev=RelationType.TEMPORAL。"""

    def test_first_node_relation_is_none(self):
        t1 = _make_tagged("A", date="2025-01-01")
        t2 = _make_tagged("B", date="2025-06-01")
        chain = _make_chain("rel1", [t1, t2])
        result = apply_temporal_order([chain])
        assert result[0].nodes[0].relation_to_prev is None

    def test_second_node_relation_is_temporal(self):
        t1 = _make_tagged("A", date="2025-01-01")
        t2 = _make_tagged("B", date="2025-06-01")
        chain = _make_chain("rel2", [t1, t2])
        result = apply_temporal_order([chain])
        assert result[0].nodes[1].relation_to_prev == RelationType.TEMPORAL

    def test_all_non_first_nodes_relation_is_temporal(self):
        nodes = [_make_tagged(f"n{i}", date=f"2025-0{i + 1}-01") for i in range(4)]
        chain = _make_chain("rel3", nodes)
        result = apply_temporal_order([chain])
        relations = [n.relation_to_prev for n in result[0].nodes]
        assert relations[0] is None
        assert all(r == RelationType.TEMPORAL for r in relations[1:])

    def test_temporal_relation_value_is_string_time_continuation(self):
        """RelationType.TEMPORAL 的字符串值为"时间延续"。"""
        t1 = _make_tagged("A", date="2025-01-01")
        t2 = _make_tagged("B", date="2025-02-01")
        chain = _make_chain("rel4", [t1, t2])
        result = apply_temporal_order([chain])
        assert result[0].nodes[1].relation_to_prev == "时间延续"

    def test_relation_overrides_previous_same_topic(self):
        """即使输入节点原 relation_to_prev 为 SAME_TOPIC，输出应统一为 TEMPORAL。"""
        t1 = _make_tagged("A", date="2025-01-01")
        t2 = _make_tagged("B", date="2025-06-01")
        # 模拟 same_topic_grouping 输出：首节点 None，后续 SAME_TOPIC
        chain = _make_chain("rel5", [t1, t2])
        result = apply_temporal_order([chain])
        assert result[0].nodes[1].relation_to_prev == RelationType.TEMPORAL

    def test_reordered_chain_first_node_still_none(self):
        """重排后新的首节点 relation_to_prev 必须为 None（即使原始节点不是首节点）。"""
        later = _make_tagged("later", date="2025-09-01")
        earlier = _make_tagged("earlier", date="2025-01-01")
        chain = _make_chain("rel6", [later, earlier])
        result = apply_temporal_order([chain])
        assert result[0].nodes[0].tagged_output.event.title == "earlier"
        assert result[0].nodes[0].relation_to_prev is None


# ---------------------------------------------------------------------------
# 7. 单节点与空输入行为（singleton and empty input behavior）
# ---------------------------------------------------------------------------


class TestSingletonAndEmptyInput:
    """边界条件：单节点链和空输入应正确处理。"""

    def test_empty_input_returns_empty_list(self):
        result = apply_temporal_order([])
        assert result == []

    def test_singleton_chain_unchanged(self):
        t1 = _make_tagged("only", date="2025-05-01")
        chain = _make_chain("solo", [t1])
        result = apply_temporal_order([chain])
        assert len(result) == 1
        assert len(result[0].nodes) == 1
        assert result[0].nodes[0].relation_to_prev is None
        assert result[0].nodes[0].position == 0

    def test_singleton_chain_id_preserved(self):
        t1 = _make_tagged("only", date="2025-05-01")
        chain = _make_chain("solo-chain", [t1])
        result = apply_temporal_order([chain])
        assert result[0].chain_id == "solo-chain"

    def test_singleton_with_unknown_date(self):
        t1 = _make_tagged("no-date", date="")
        chain = _make_chain("solo-unknown", [t1])
        result = apply_temporal_order([chain])
        assert len(result[0].nodes) == 1
        assert result[0].nodes[0].relation_to_prev is None

    def test_input_list_is_non_mutating(self):
        """apply_temporal_order 不应修改输入链对象。"""
        t2 = _make_tagged("B", date="2025-09-01")
        t1 = _make_tagged("A", date="2025-01-01")
        chain = _make_chain("immutable", [t2, t1])
        original_titles = [n.tagged_output.event.title for n in chain.nodes]
        apply_temporal_order([chain])
        # 原始链的节点顺序不变
        titles_after = [n.tagged_output.event.title for n in chain.nodes]
        assert titles_after == original_titles

    def test_output_count_matches_input_count(self):
        chains = [
            _make_chain(f"c{i}", [_make_tagged(f"n{i}", date="2025-01-01")])
            for i in range(6)
        ]
        results = apply_temporal_order(chains)
        assert len(results) == 6


# ---------------------------------------------------------------------------
# 8. 导入面（import surface）
# ---------------------------------------------------------------------------


class TestImportSurface:
    """apply_temporal_order 应从 app.chains 包直接可导入。"""

    def test_apply_temporal_order_importable_from_package(self):
        assert apply_temporal_order_pkg is apply_temporal_order

    def test_apply_temporal_order_in_all(self):
        import app.chains as pkg

        assert "apply_temporal_order" in pkg.__all__

    def test_apply_temporal_order_callable(self):
        assert callable(apply_temporal_order)
