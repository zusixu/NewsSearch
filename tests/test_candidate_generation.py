"""
tests/test_candidate_generation.py — generate_candidate_chains 的专项测试套件

覆盖范围
--------
1. 空输入（empty input）
2. 流水线组合等价性（pipeline composition equivalence）
3. 确定性：链数量与顺序（deterministic chain count and order）
4. 链 ID 来源于 same-topic 阶段（chain id preservation from same-topic stage）
5. 候选链保留 tagged_output 与证据可达性（tagged_output/evidence accessibility）
6. singleton/无主题输入存活（singleton and unthemed inputs survive）
7. 导入面（import surface）
"""

from __future__ import annotations

import pytest

from app.chains.candidate_generation import generate_candidate_chains
from app.chains import generate_candidate_chains as pkg_fn  # import surface
from app.chains.chain import InformationChain
from app.chains.same_topic_grouping import group_same_topic
from app.chains.temporal_connection import apply_temporal_order
from app.chains.upstream_downstream import apply_upstream_downstream_order
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
    """构建带指定 theme_ids 的 TaggedOutput。"""
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


# ---------------------------------------------------------------------------
# 1. 空输入（empty input）
# ---------------------------------------------------------------------------


class TestEmptyInput:
    """空输入应立即返回空列表，不抛出任何异常。"""

    def test_empty_list_returns_empty(self):
        result = generate_candidate_chains([])
        assert result == []

    def test_empty_list_returns_list_type(self):
        result = generate_candidate_chains([])
        assert isinstance(result, list)

    def test_empty_tuple_returns_empty(self):
        result = generate_candidate_chains(())
        assert result == []


# ---------------------------------------------------------------------------
# 2. 流水线组合等价性（pipeline composition equivalence to manual chaining）
# ---------------------------------------------------------------------------


class TestPipelineCompositionEquivalence:
    """generate_candidate_chains 的结果应与手动串联三阶段完全一致。"""

    def _manual_pipeline(self, tagged_outputs: list[TaggedOutput]) -> list[InformationChain]:
        chains = group_same_topic(tagged_outputs)
        chains = apply_temporal_order(chains)
        chains = apply_upstream_downstream_order(chains)
        return chains

    def test_single_tagged_output_equivalence(self):
        to = _make_tagged("A", theme_ids=["gpu"])
        expected = self._manual_pipeline([to])
        result = generate_candidate_chains([to])
        assert len(result) == len(expected)
        assert result[0].chain_id == expected[0].chain_id
        assert len(result[0].nodes) == len(expected[0].nodes)

    def test_two_same_theme_equivalence(self):
        to1 = _make_tagged("A", date="2025-03-01", theme_ids=["gpu"])
        to2 = _make_tagged("B", date="2025-01-01", theme_ids=["gpu"])
        expected = self._manual_pipeline([to1, to2])
        result = generate_candidate_chains([to1, to2])
        assert len(result) == len(expected)
        for r, e in zip(result, expected):
            assert r.chain_id == e.chain_id
            node_titles_r = [n.tagged_output.event.title for n in r.nodes]
            node_titles_e = [n.tagged_output.event.title for n in e.nodes]
            assert node_titles_r == node_titles_e

    def test_multiple_groups_equivalence(self):
        to1 = _make_tagged("chip", date="2025-03-01", theme_ids=["semiconductor"])
        to2 = _make_tagged("cloud", date="2025-01-01", theme_ids=["cloud"])
        to3 = _make_tagged("chip2", date="2025-02-01", theme_ids=["semiconductor"])
        expected = self._manual_pipeline([to1, to2, to3])
        result = generate_candidate_chains([to1, to2, to3])
        assert len(result) == len(expected)
        for r, e in zip(result, expected):
            assert r.chain_id == e.chain_id

    def test_mixed_themed_and_unthemed_equivalence(self):
        to1 = _make_tagged("with-theme", theme_ids=["ai"])
        to2 = _make_tagged("no-theme", theme_ids=[])
        expected = self._manual_pipeline([to1, to2])
        result = generate_candidate_chains([to1, to2])
        assert len(result) == len(expected)
        chain_ids_r = [c.chain_id for c in result]
        chain_ids_e = [c.chain_id for c in expected]
        assert chain_ids_r == chain_ids_e

    def test_node_positions_match_manual_pipeline(self):
        to1 = _make_tagged("A", date="2025-05-01", theme_ids=["gpu", "cloud"])
        to2 = _make_tagged("B", date="2025-01-01", theme_ids=["cloud"])
        expected = self._manual_pipeline([to1, to2])
        result = generate_candidate_chains([to1, to2])
        for r, e in zip(result, expected):
            r_pos = [n.position for n in r.nodes]
            e_pos = [n.position for n in e.nodes]
            assert r_pos == e_pos


# ---------------------------------------------------------------------------
# 3. 确定性：链数量与顺序（deterministic chain count and order）
# ---------------------------------------------------------------------------


class TestDeterministicChainCountAndOrder:
    """相同输入多次调用应产生完全相同的链数量和顺序。"""

    def test_repeated_calls_same_chain_count(self):
        inputs = [
            _make_tagged("X", theme_ids=["gpu"]),
            _make_tagged("Y", theme_ids=["cloud"]),
            _make_tagged("Z", theme_ids=["gpu"]),
        ]
        r1 = generate_candidate_chains(inputs)
        r2 = generate_candidate_chains(inputs)
        assert len(r1) == len(r2)

    def test_repeated_calls_same_chain_ids(self):
        inputs = [
            _make_tagged("A", theme_ids=["semiconductor"]),
            _make_tagged("B", theme_ids=["ai"]),
        ]
        r1 = generate_candidate_chains(inputs)
        r2 = generate_candidate_chains(inputs)
        assert [c.chain_id for c in r1] == [c.chain_id for c in r2]

    def test_repeated_calls_same_node_order(self):
        inputs = [
            _make_tagged("late", date="2025-12-01", theme_ids=["gpu"]),
            _make_tagged("early", date="2025-01-01", theme_ids=["gpu"]),
        ]
        r1 = generate_candidate_chains(inputs)
        r2 = generate_candidate_chains(inputs)
        titles_r1 = [n.tagged_output.event.title for n in r1[0].nodes]
        titles_r2 = [n.tagged_output.event.title for n in r2[0].nodes]
        assert titles_r1 == titles_r2

    def test_chain_count_equals_expected_groups(self):
        """3 种不同主题 → 3 条链。"""
        inputs = [
            _make_tagged("A", theme_ids=["gpu"]),
            _make_tagged("B", theme_ids=["cloud"]),
            _make_tagged("C", theme_ids=["memory"]),
        ]
        result = generate_candidate_chains(inputs)
        assert len(result) == 3

    def test_shared_theme_merges_into_single_chain(self):
        """两个共享主题的节点合并为 1 条链。"""
        inputs = [
            _make_tagged("A", theme_ids=["gpu"]),
            _make_tagged("B", theme_ids=["gpu"]),
        ]
        result = generate_candidate_chains(inputs)
        assert len(result) == 1
        assert len(result[0].nodes) == 2


# ---------------------------------------------------------------------------
# 4. 链 ID 来源于 same-topic 阶段（chain id preservation from same-topic stage）
# ---------------------------------------------------------------------------


class TestChainIdPreservation:
    """链 ID 必须保留 same-topic 阶段生成的格式（same-topic-NNNN）。"""

    def test_chain_id_format_single(self):
        to = _make_tagged("A", theme_ids=["ai"])
        result = generate_candidate_chains([to])
        assert result[0].chain_id == "same-topic-0001"

    def test_chain_id_format_multiple(self):
        inputs = [
            _make_tagged("A", theme_ids=["gpu"]),
            _make_tagged("B", theme_ids=["cloud"]),
        ]
        result = generate_candidate_chains(inputs)
        ids = [c.chain_id for c in result]
        assert ids == ["same-topic-0001", "same-topic-0002"]

    def test_chain_id_unchanged_after_temporal_stage(self):
        """时序阶段不应修改链 ID。"""
        to1 = _make_tagged("late", date="2025-12-01", theme_ids=["gpu"])
        to2 = _make_tagged("early", date="2025-01-01", theme_ids=["gpu"])
        result = generate_candidate_chains([to1, to2])
        assert result[0].chain_id == "same-topic-0001"

    def test_chain_id_unchanged_after_upstream_downstream_stage(self):
        """上下游阶段不应修改链 ID。"""
        to1 = _make_tagged("down", theme_ids=["cloud"])
        to2 = _make_tagged("up", theme_ids=["semiconductor"])
        result = generate_candidate_chains([to1, to2])
        assert result[0].chain_id == "same-topic-0001"

    def test_chain_ids_are_sequential_one_based(self):
        """4 个独立主题 → 链 ID 为 0001~0004。"""
        inputs = [
            _make_tagged("A", theme_ids=["gpu"]),
            _make_tagged("B", theme_ids=["cloud"]),
            _make_tagged("C", theme_ids=["memory"]),
            _make_tagged("D", theme_ids=["ai"]),
        ]
        result = generate_candidate_chains(inputs)
        ids = [c.chain_id for c in result]
        assert ids == [
            "same-topic-0001",
            "same-topic-0002",
            "same-topic-0003",
            "same-topic-0004",
        ]


# ---------------------------------------------------------------------------
# 5. 候选链保留 tagged_output 与证据可达性（tagged_output/evidence accessibility）
# ---------------------------------------------------------------------------


class TestEvidenceAccessibility:
    """每个节点的 tagged_output 引用不变，证据字段可正常访问。"""

    def test_tagged_output_identity_preserved(self):
        to = _make_tagged("chip", theme_ids=["semiconductor"])
        result = generate_candidate_chains([to])
        assert result[0].nodes[0].tagged_output is to

    def test_evidence_links_accessible(self):
        to = _make_tagged("event", theme_ids=["gpu"])
        result = generate_candidate_chains([to])
        node = result[0].nodes[0]
        assert hasattr(node.tagged_output, "evidence_links")
        assert isinstance(node.tagged_output.evidence_links, tuple)

    def test_event_source_accessible(self):
        to = _make_tagged("event-src", theme_ids=["cloud"])
        result = generate_candidate_chains([to])
        node = result[0].nodes[0]
        assert hasattr(node.tagged_output, "event")
        assert node.tagged_output.event.title == "event-src"

    def test_multiple_nodes_all_tagged_outputs_accessible(self):
        to1 = _make_tagged("first", date="2025-01-01", theme_ids=["gpu"])
        to2 = _make_tagged("second", date="2025-06-01", theme_ids=["gpu"])
        result = generate_candidate_chains([to1, to2])
        tos = [n.tagged_output for n in result[0].nodes]
        assert any(t is to1 for t in tos)
        assert any(t is to2 for t in tos)

    def test_theme_ids_and_entity_type_ids_accessible(self):
        to = _make_tagged("e", theme_ids=["ai"], entity_type_ids=["company"])
        result = generate_candidate_chains([to])
        chain = result[0]
        assert "ai" in chain.theme_ids
        assert "company" in chain.entity_type_ids


# ---------------------------------------------------------------------------
# 6. singleton/无主题输入存活（singleton and unthemed inputs survive）
# ---------------------------------------------------------------------------


class TestSingletonAndUnthemedSurvival:
    """theme_ids 为空的节点不应被丢弃，各自形成 singleton 链。"""

    def test_unthemed_single_input_forms_one_chain(self):
        to = _make_tagged("no-theme", theme_ids=[])
        result = generate_candidate_chains([to])
        assert len(result) == 1
        assert len(result[0].nodes) == 1

    def test_unthemed_tagged_output_preserved(self):
        to = _make_tagged("orphan", theme_ids=[])
        result = generate_candidate_chains([to])
        assert result[0].nodes[0].tagged_output is to

    def test_multiple_unthemed_form_separate_chains(self):
        to1 = _make_tagged("orphan-1", theme_ids=[])
        to2 = _make_tagged("orphan-2", theme_ids=[])
        result = generate_candidate_chains([to1, to2])
        assert len(result) == 2

    def test_mixed_themed_and_unthemed_both_present(self):
        themed = _make_tagged("with-theme", theme_ids=["ai"])
        unthemed = _make_tagged("no-theme", theme_ids=[])
        result = generate_candidate_chains([themed, unthemed])
        # 总共 2 条链，主题链 + singleton
        assert len(result) == 2

    def test_unthemed_chain_has_empty_theme_ids(self):
        to = _make_tagged("orphan", theme_ids=[])
        result = generate_candidate_chains([to])
        assert result[0].theme_ids == ()

    def test_singleton_chain_position_is_zero(self):
        to = _make_tagged("single", theme_ids=[])
        result = generate_candidate_chains([to])
        assert result[0].nodes[0].position == 0

    def test_singleton_chain_relation_to_prev_is_none(self):
        to = _make_tagged("single", theme_ids=[])
        result = generate_candidate_chains([to])
        assert result[0].nodes[0].relation_to_prev is None


# ---------------------------------------------------------------------------
# 7. 导入面（import surface）
# ---------------------------------------------------------------------------


class TestImportSurface:
    """generate_candidate_chains 必须同时可从模块路径和包路径导入。"""

    def test_direct_module_import_is_callable(self):
        assert callable(generate_candidate_chains)

    def test_package_import_is_same_object(self):
        assert pkg_fn is generate_candidate_chains

    def test_generate_candidate_chains_in_all(self):
        import app.chains as chains_pkg
        assert "generate_candidate_chains" in chains_pkg.__all__

    def test_returns_list(self):
        to = _make_tagged("A", theme_ids=["gpu"])
        result = generate_candidate_chains([to])
        assert isinstance(result, list)

    def test_each_element_is_information_chain(self):
        to = _make_tagged("A", theme_ids=["gpu"])
        result = generate_candidate_chains([to])
        assert all(isinstance(c, InformationChain) for c in result)
