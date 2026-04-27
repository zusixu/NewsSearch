"""
tests/test_same_topic_grouping.py — group_same_topic 的专项测试套件

覆盖范围
--------
1. 共享主题聚合（shared-theme grouping）
2. 传递性聚合（transitive grouping）
3. 分组顺序确定性（deterministic group order）
4. 组内输入顺序稳定性（stable in-group order）
5. relation_to_prev 赋值（首节点 None，后续 SAME_TOPIC）
6. 空 theme_ids 处理（singleton chains，不丢弃）
7. 混合有/无主题输入（mixed themed/unthemed inputs）
8. 导入面（import surface）
"""

from __future__ import annotations

import pytest

from app.chains.same_topic_grouping import group_same_topic
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
    theme_ids: list[str] | None = None,
    entity_type_ids: list[str] | None = None,
) -> TaggedOutput:
    """构建 TaggedOutput，theme_ids / entity_type_ids 由参数直接控制。"""
    hits: list[Hit] = []
    text_parts: list[str] = []
    for tid in theme_ids or []:
        hits.append(_make_hit(tid, kind="theme"))
        text_parts.append(tid)
    for eid in entity_type_ids or []:
        hits.append(_make_hit(eid, kind="entity_type"))
        text_parts.append(eid)
    text = " ".join(text_parts)
    links = build_evidence_links(text, hits, context_window=0)
    return build_tagged_output(_make_event(title=title), text, links)


# ---------------------------------------------------------------------------
# 1. 共享主题聚合
# ---------------------------------------------------------------------------


class TestSharedThemeGrouping:
    """直接共享至少一个 theme_id 的输入应归入同一链。"""

    def test_two_items_sharing_one_theme_form_one_chain(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["ai"])
        chains = group_same_topic([a, b])
        assert len(chains) == 1
        assert len(chains[0].nodes) == 2

    def test_two_items_with_no_shared_theme_form_two_chains(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["gpu"])
        chains = group_same_topic([a, b])
        assert len(chains) == 2

    def test_three_items_sharing_same_theme_form_one_chain(self):
        a = _make_tagged("A", theme_ids=["gpu"])
        b = _make_tagged("B", theme_ids=["gpu"])
        c = _make_tagged("C", theme_ids=["gpu"])
        chains = group_same_topic([a, b, c])
        assert len(chains) == 1
        assert len(chains[0].nodes) == 3

    def test_two_groups_no_overlap(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["ai"])
        c = _make_tagged("C", theme_ids=["chip"])
        d = _make_tagged("D", theme_ids=["chip"])
        chains = group_same_topic([a, b, c, d])
        assert len(chains) == 2
        assert len(chains[0].nodes) == 2
        assert len(chains[1].nodes) == 2

    def test_items_sharing_one_of_multiple_themes_are_grouped(self):
        a = _make_tagged("A", theme_ids=["ai", "robot"])
        b = _make_tagged("B", theme_ids=["robot", "auto"])
        chains = group_same_topic([a, b])
        assert len(chains) == 1


# ---------------------------------------------------------------------------
# 2. 传递性聚合
# ---------------------------------------------------------------------------


class TestTransitiveGrouping:
    """A-B 共享、B-C 共享 ⇒ A、B、C 归入同一组（即使 A、C 不直接共享）。"""

    def test_transitive_three_way(self):
        # A(x,y), B(y,z), C(z) → 一组
        a = _make_tagged("A", theme_ids=["x", "y"])
        b = _make_tagged("B", theme_ids=["y", "z"])
        c = _make_tagged("C", theme_ids=["z"])
        chains = group_same_topic([a, b, c])
        assert len(chains) == 1
        assert len(chains[0].nodes) == 3

    def test_transitive_chain_of_four(self):
        # A(1), B(1,2), C(2,3), D(3) → 一组
        a = _make_tagged("A", theme_ids=["t1"])
        b = _make_tagged("B", theme_ids=["t1", "t2"])
        c = _make_tagged("C", theme_ids=["t2", "t3"])
        d = _make_tagged("D", theme_ids=["t3"])
        chains = group_same_topic([a, b, c, d])
        assert len(chains) == 1
        assert len(chains[0].nodes) == 4

    def test_transitivity_does_not_merge_disconnected_groups(self):
        # A(x,y), B(y,z) 一组；C(w) 另一组
        a = _make_tagged("A", theme_ids=["x", "y"])
        b = _make_tagged("B", theme_ids=["y", "z"])
        c = _make_tagged("C", theme_ids=["w"])
        chains = group_same_topic([a, b, c])
        assert len(chains) == 2

    def test_two_separate_transitive_clusters(self):
        # 组1: A(p,q)-B(q,r); 组2: C(s,t)-D(t,u)
        a = _make_tagged("A", theme_ids=["p", "q"])
        b = _make_tagged("B", theme_ids=["q", "r"])
        c = _make_tagged("C", theme_ids=["s", "t"])
        d = _make_tagged("D", theme_ids=["t", "u"])
        chains = group_same_topic([a, b, c, d])
        assert len(chains) == 2
        assert len(chains[0].nodes) == 2
        assert len(chains[1].nodes) == 2


# ---------------------------------------------------------------------------
# 3. 分组顺序确定性
# ---------------------------------------------------------------------------


class TestDeterministicGroupOrder:
    """各组按组内首个输入的原始索引升序排列。"""

    def test_group_order_follows_first_occurrence(self):
        # 输入顺序：A(ai), B(gpu), C(ai)
        # A 先出现，B 在索引1，C 归入 A 的组
        # 期望：组1=[A,C](首索引0), 组2=[B](首索引1)
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["gpu"])
        c = _make_tagged("C", theme_ids=["ai"])
        chains = group_same_topic([a, b, c])
        assert len(chains) == 2
        assert chains[0].nodes[0].tagged_output is a
        assert chains[1].nodes[0].tagged_output is b

    def test_chain_ids_are_sequential_1based(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["gpu"])
        chains = group_same_topic([a, b])
        assert chains[0].chain_id == "same-topic-0001"
        assert chains[1].chain_id == "same-topic-0002"

    def test_chain_id_format_four_digit_zero_padded(self):
        inputs = [_make_tagged(f"item{i}", theme_ids=[f"t{i}"]) for i in range(9)]
        chains = group_same_topic(inputs)
        assert len(chains) == 9
        assert chains[0].chain_id == "same-topic-0001"
        assert chains[8].chain_id == "same-topic-0009"

    def test_same_input_always_produces_same_chain_ids(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["gpu"])
        c = _make_tagged("C", theme_ids=["ai"])
        chains1 = group_same_topic([a, b, c])
        chains2 = group_same_topic([a, b, c])
        assert [ch.chain_id for ch in chains1] == [ch.chain_id for ch in chains2]

    def test_single_input_gets_chain_id_0001(self):
        a = _make_tagged("A", theme_ids=["ai"])
        chains = group_same_topic([a])
        assert chains[0].chain_id == "same-topic-0001"


# ---------------------------------------------------------------------------
# 4. 组内输入顺序稳定性
# ---------------------------------------------------------------------------


class TestStableInGroupOrder:
    """组内节点应保留原始输入顺序，不按时间或其他字段重排。"""

    def test_nodes_preserve_input_order_within_group(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["ai"])
        c = _make_tagged("C", theme_ids=["ai"])
        chains = group_same_topic([a, b, c])
        nodes = chains[0].nodes
        assert nodes[0].tagged_output is a
        assert nodes[1].tagged_output is b
        assert nodes[2].tagged_output is c

    def test_non_contiguous_members_preserve_original_order(self):
        # 输入：A(ai), B(gpu), C(ai) → 组[A,C]，索引0和2，应为 A 在前 C 在后
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["gpu"])
        c = _make_tagged("C", theme_ids=["ai"])
        chains = group_same_topic([a, b, c])
        ai_chain = next(ch for ch in chains if len(ch.nodes) == 2)
        assert ai_chain.nodes[0].tagged_output is a
        assert ai_chain.nodes[1].tagged_output is c

    def test_position_values_are_zero_based_within_chain(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["ai"])
        c = _make_tagged("C", theme_ids=["ai"])
        chains = group_same_topic([a, b, c])
        positions = [n.position for n in chains[0].nodes]
        assert positions == [0, 1, 2]


# ---------------------------------------------------------------------------
# 5. relation_to_prev 赋值
# ---------------------------------------------------------------------------


class TestRelationToPrevAssignment:
    """首节点 relation_to_prev=None，后续节点 relation_to_prev=SAME_TOPIC。"""

    def test_first_node_relation_is_none(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["ai"])
        chains = group_same_topic([a, b])
        assert chains[0].nodes[0].relation_to_prev is None

    def test_second_node_relation_is_same_topic(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["ai"])
        chains = group_same_topic([a, b])
        assert chains[0].nodes[1].relation_to_prev is RelationType.SAME_TOPIC

    def test_all_non_first_nodes_are_same_topic(self):
        inputs = [_make_tagged(f"item{i}", theme_ids=["shared"]) for i in range(5)]
        chains = group_same_topic(inputs)
        nodes = chains[0].nodes
        assert nodes[0].relation_to_prev is None
        for node in nodes[1:]:
            assert node.relation_to_prev is RelationType.SAME_TOPIC

    def test_singleton_chain_first_node_is_none(self):
        a = _make_tagged("A", theme_ids=[])
        chains = group_same_topic([a])
        assert chains[0].nodes[0].relation_to_prev is None

    def test_relation_value_is_correct_enum_member(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["ai"])
        chains = group_same_topic([a, b])
        rel = chains[0].nodes[1].relation_to_prev
        assert rel == RelationType.SAME_TOPIC
        assert rel == "同主题发酵"


# ---------------------------------------------------------------------------
# 6. 空 theme_ids 处理
# ---------------------------------------------------------------------------


class TestEmptyThemeIdsHandling:
    """theme_ids 为空的输入应形成 singleton 链，不被丢弃。"""

    def test_single_unthemed_item_forms_singleton_chain(self):
        a = _make_tagged("A", theme_ids=[])
        chains = group_same_topic([a])
        assert len(chains) == 1
        assert len(chains[0].nodes) == 1
        assert chains[0].nodes[0].tagged_output is a

    def test_multiple_unthemed_items_each_form_own_chain(self):
        a = _make_tagged("A", theme_ids=[])
        b = _make_tagged("B", theme_ids=[])
        c = _make_tagged("C", theme_ids=[])
        chains = group_same_topic([a, b, c])
        assert len(chains) == 3
        assert all(len(ch.nodes) == 1 for ch in chains)

    def test_unthemed_items_are_not_grouped_together(self):
        # 两个空主题项不应聚合（无共同主题 ID）
        a = _make_tagged("A", theme_ids=[])
        b = _make_tagged("B", theme_ids=[])
        chains = group_same_topic([a, b])
        assert len(chains) == 2

    def test_empty_input_returns_empty_list(self):
        assert group_same_topic([]) == []

    def test_unthemed_chain_theme_ids_is_empty_tuple(self):
        a = _make_tagged("A", theme_ids=[])
        chains = group_same_topic([a])
        assert chains[0].theme_ids == ()


# ---------------------------------------------------------------------------
# 7. 混合有/无主题输入
# ---------------------------------------------------------------------------


class TestMixedThemedUnthemedInputs:
    """同时包含有主题和无主题输入时的聚合行为。"""

    def test_themed_items_grouped_unthemed_singletons(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=[])
        c = _make_tagged("C", theme_ids=["ai"])
        d = _make_tagged("D", theme_ids=[])
        chains = group_same_topic([a, b, c, d])
        # [A,C] 一组，B 一组，D 一组
        assert len(chains) == 3
        sizes = sorted(len(ch.nodes) for ch in chains)
        assert sizes == [1, 1, 2]

    def test_unthemed_item_not_merged_with_themed(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=[])
        chains = group_same_topic([a, b])
        assert len(chains) == 2
        assert any(len(ch.nodes) == 1 and ch.nodes[0].tagged_output is b for ch in chains)

    def test_group_order_interleaves_themed_and_unthemed(self):
        # 输入：X(无), A(ai), Y(无), B(ai)
        # 组1=[X](索引0), 组2=[A,B](索引1), 组3=[Y](索引2)
        x = _make_tagged("X", theme_ids=[])
        a = _make_tagged("A", theme_ids=["ai"])
        y = _make_tagged("Y", theme_ids=[])
        b = _make_tagged("B", theme_ids=["ai"])
        chains = group_same_topic([x, a, y, b])
        assert len(chains) == 3
        assert chains[0].nodes[0].tagged_output is x
        # 第二组应包含 a 和 b
        assert len(chains[1].nodes) == 2
        assert chains[1].nodes[0].tagged_output is a
        assert chains[1].nodes[1].tagged_output is b
        assert chains[2].nodes[0].tagged_output is y

    def test_chain_aggregated_theme_ids_exclude_empty(self):
        a = _make_tagged("A", theme_ids=["ai"])
        b = _make_tagged("B", theme_ids=["ai"])
        chains = group_same_topic([a, b])
        assert "ai" in chains[0].theme_ids

    def test_singleton_from_empty_theme_has_correct_structure(self):
        b = _make_tagged("B", theme_ids=[])
        chains = group_same_topic([b])
        ch = chains[0]
        assert isinstance(ch, InformationChain)
        assert len(ch.nodes) == 1
        assert ch.nodes[0].position == 0
        assert ch.nodes[0].relation_to_prev is None


# ---------------------------------------------------------------------------
# 8. 导入面
# ---------------------------------------------------------------------------


class TestImportSurface:
    """group_same_topic 应可从 app.chains 顶层直接导入。"""

    def test_importable_from_app_chains(self):
        from app.chains import group_same_topic as gst  # noqa: F401
        assert callable(gst)

    def test_importable_from_module_directly(self):
        from app.chains.same_topic_grouping import group_same_topic as gst  # noqa: F401
        assert callable(gst)

    def test_app_chains_all_includes_group_same_topic(self):
        import app.chains as chains_pkg
        assert "group_same_topic" in chains_pkg.__all__

    def test_returns_list_of_information_chain(self):
        a = _make_tagged("A", theme_ids=["ai"])
        result = group_same_topic([a])
        assert isinstance(result, list)
        assert isinstance(result[0], InformationChain)
