"""
tests/test_upstream_downstream.py — apply_upstream_downstream_order 的专项测试套件

覆盖范围
--------
1. 阶段推断：通过 theme_ids 映射供应链阶段（stage mapping by theme_ids）
2. 多阶段优先级：节点命中多个阶段桶时取最上游（precedence with multiple mapped themes）
3. 已知阶段在未知阶段之前（known stages before unknown）
4. 同阶段稳定顺序（stable order within same stage）
5. chain_id 与聚合字段保留（chain_id and aggregate preservation）
6. relation_to_prev 赋值为 UPSTREAM_DOWNSTREAM（relation_to_prev assignment）
7. 单节点与空输入行为（singleton and empty input behavior）
8. 导入面（import surface）
"""

from __future__ import annotations

import pytest

from app.chains.upstream_downstream import apply_upstream_downstream_order
from app.chains import apply_upstream_downstream_order as pkg_fn  # import surface
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


def _make_chain(
    chain_id: str,
    tagged_outputs: list[TaggedOutput],
    theme_ids: tuple[str, ...] = (),
    entity_type_ids: tuple[str, ...] = (),
) -> InformationChain:
    """构建用于测试的 InformationChain（首节点 None，后续 TEMPORAL）。"""
    nodes = tuple(
        ChainNode(
            tagged_output=to,
            position=i,
            relation_to_prev=None if i == 0 else RelationType.TEMPORAL,
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
# 1. 阶段推断：通过 theme_ids 映射供应链阶段（stage mapping by theme_ids）
# ---------------------------------------------------------------------------


class TestStageMappingByThemeIds:
    """每个上游/中游/下游 theme_id 都应产生正确的阶段分组和顺序。"""

    def test_upstream_semiconductor_before_downstream_ai(self):
        downstream = _make_tagged("ai-node", theme_ids=["ai"])
        upstream = _make_tagged("chip-node", theme_ids=["semiconductor"])
        chain = _make_chain("c1", [downstream, upstream])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["chip-node", "ai-node"]

    def test_upstream_memory_placed_first(self):
        down = _make_tagged("cloud-node", theme_ids=["cloud"])
        up = _make_tagged("mem-node", theme_ids=["memory"])
        chain = _make_chain("c2", [down, up])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[0].tagged_output.event.title == "mem-node"

    def test_upstream_gpu_placed_before_midstream(self):
        mid = _make_tagged("compute-node", theme_ids=["compute"])
        up = _make_tagged("gpu-node", theme_ids=["gpu"])
        chain = _make_chain("c3", [mid, up])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["gpu-node", "compute-node"]

    def test_upstream_optical_module_placed_first(self):
        down = _make_tagged("fm-node", theme_ids=["foundation_model"])
        up = _make_tagged("opt-node", theme_ids=["optical_module"])
        chain = _make_chain("c4", [down, up])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[0].tagged_output.event.title == "opt-node"

    def test_upstream_storage_placed_before_downstream(self):
        down = _make_tagged("app-node", theme_ids=["ai_application"])
        up = _make_tagged("stor-node", theme_ids=["storage"])
        chain = _make_chain("c5", [down, up])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[0].tagged_output.event.title == "stor-node"

    def test_midstream_supply_chain_between_up_and_down(self):
        down = _make_tagged("cloud-node", theme_ids=["cloud"])
        mid = _make_tagged("sc-node", theme_ids=["supply_chain"])
        up = _make_tagged("gpu-node", theme_ids=["gpu"])
        chain = _make_chain("c6", [down, mid, up])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["gpu-node", "sc-node", "cloud-node"]

    def test_midstream_compute_between_up_and_down(self):
        down = _make_tagged("ai-node", theme_ids=["ai"])
        mid = _make_tagged("comp-node", theme_ids=["compute"])
        up = _make_tagged("mem-node", theme_ids=["memory"])
        chain = _make_chain("c7", [ai := down, comp := mid, mem := up])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["mem-node", "comp-node", "ai-node"]

    def test_downstream_foundation_model_placed_last_among_knowns(self):
        up = _make_tagged("semi-node", theme_ids=["semiconductor"])
        down = _make_tagged("fm-node", theme_ids=["foundation_model"])
        chain = _make_chain("c8", [down, up])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["semi-node", "fm-node"]

    def test_all_upstream_themes_individually(self):
        """每个 upstream theme 单独使用时，该节点应排在下游节点之前。"""
        upstream_themes = ["semiconductor", "memory", "gpu", "optical_module", "storage"]
        down = _make_tagged("cloud-node", theme_ids=["cloud"])
        for theme in upstream_themes:
            up = _make_tagged(f"{theme}-node", theme_ids=[theme])
            chain = _make_chain(f"single-{theme}", [down, up])
            result = apply_upstream_downstream_order([chain])
            assert result[0].nodes[0].tagged_output.event.title == f"{theme}-node", \
                f"theme '{theme}' should be upstream"

    def test_all_downstream_themes_individually(self):
        """每个 downstream theme 单独使用时，该节点应排在上游节点之后。"""
        downstream_themes = ["cloud", "foundation_model", "ai_application", "ai"]
        up = _make_tagged("semi-node", theme_ids=["semiconductor"])
        for theme in downstream_themes:
            down = _make_tagged(f"{theme}-node", theme_ids=[theme])
            chain = _make_chain(f"down-{theme}", [down, up])
            result = apply_upstream_downstream_order([chain])
            assert result[0].nodes[0].tagged_output.event.title == "semi-node", \
                f"theme '{theme}' should be downstream (after upstream)"


# ---------------------------------------------------------------------------
# 2. 多阶段优先级（precedence with multiple mapped themes）
# ---------------------------------------------------------------------------


class TestMultiThemePrecedence:
    """节点命中多个阶段桶时，取最上游阶段（最小阶段秩）。"""

    def test_upstream_and_downstream_themes_yields_upstream_rank(self):
        # 该节点同时有 upstream 和 downstream theme → 应被视为 upstream
        mixed = _make_tagged("mixed-node", theme_ids=["gpu", "ai"])
        pure_down = _make_tagged("cloud-node", theme_ids=["cloud"])
        chain = _make_chain("prec1", [pure_down, mixed])
        result = apply_upstream_downstream_order([chain])
        # mixed-node 应排在 cloud-node 之前（upstream 优先）
        assert result[0].nodes[0].tagged_output.event.title == "mixed-node"

    def test_upstream_and_midstream_themes_yields_upstream_rank(self):
        # 有 upstream + midstream theme → 应被视为 upstream
        mixed = _make_tagged("mixed-node", theme_ids=["memory", "compute"])
        pure_mid = _make_tagged("sc-node", theme_ids=["supply_chain"])
        chain = _make_chain("prec2", [pure_mid, mixed])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[0].tagged_output.event.title == "mixed-node"

    def test_midstream_and_downstream_themes_yields_midstream_rank(self):
        # 有 midstream + downstream theme → 应被视为 midstream
        mixed = _make_tagged("mixed-node", theme_ids=["supply_chain", "ai"])
        pure_down = _make_tagged("fm-node", theme_ids=["foundation_model"])
        chain = _make_chain("prec3", [pure_down, mixed])
        result = apply_upstream_downstream_order([chain])
        # mixed-node 有 midstream → 在 downstream 之前
        assert result[0].nodes[0].tagged_output.event.title == "mixed-node"

    def test_multiple_upstream_themes_still_upstream(self):
        mixed = _make_tagged("multi-up", theme_ids=["semiconductor", "gpu", "memory"])
        down = _make_tagged("cloud", theme_ids=["cloud"])
        chain = _make_chain("prec4", [down, mixed])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[0].tagged_output.event.title == "multi-up"

    def test_upstream_theme_plus_unknown_yields_upstream_rank(self):
        # 有 upstream theme 和一个未知 theme → 应被视为 upstream
        mixed = _make_tagged("semi-unknown", theme_ids=["semiconductor", "some_unknown_theme"])
        down = _make_tagged("ai-node", theme_ids=["ai"])
        chain = _make_chain("prec5", [down, mixed])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[0].tagged_output.event.title == "semi-unknown"


# ---------------------------------------------------------------------------
# 3. 已知阶段在未知阶段之前（known stages before unknown）
# ---------------------------------------------------------------------------


class TestKnownBeforeUnknown:
    """无法映射阶段的节点（unknown）应排在所有已知阶段节点之后。"""

    def test_unknown_node_after_upstream_node(self):
        unknown = _make_tagged("no-theme", theme_ids=[])
        up = _make_tagged("semi-node", theme_ids=["semiconductor"])
        chain = _make_chain("ku1", [unknown, up])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["semi-node", "no-theme"]

    def test_unknown_node_after_midstream_node(self):
        unknown = _make_tagged("no-theme", theme_ids=[])
        mid = _make_tagged("compute-node", theme_ids=["compute"])
        chain = _make_chain("ku2", [unknown, mid])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["compute-node", "no-theme"]

    def test_unknown_node_after_downstream_node(self):
        unknown = _make_tagged("no-theme", theme_ids=[])
        down = _make_tagged("cloud-node", theme_ids=["cloud"])
        chain = _make_chain("ku3", [unknown, down])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["cloud-node", "no-theme"]

    def test_multiple_unknowns_after_all_knowns(self):
        u1 = _make_tagged("u1", theme_ids=[])
        u2 = _make_tagged("u2", theme_ids=[])
        up = _make_tagged("semi", theme_ids=["semiconductor"])
        down = _make_tagged("ai", theme_ids=["ai"])
        chain = _make_chain("ku4", [u1, u2, down, up])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        # up, down 在前；u1, u2 在后（保持原始相对顺序）
        assert titles[:2] == ["semi", "ai"]
        assert titles[2:] == ["u1", "u2"]

    def test_unknown_with_unmapped_theme_ids_placed_last(self):
        # theme_ids 包含不在映射表中的 ID
        unmapped = _make_tagged("unmapped", theme_ids=["finance", "politics"])
        up = _make_tagged("gpu-node", theme_ids=["gpu"])
        chain = _make_chain("ku5", [unmapped, up])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["gpu-node", "unmapped"]

    def test_all_unknown_nodes_preserve_original_order(self):
        nodes_data = [_make_tagged(f"n{i}", theme_ids=[]) for i in range(4)]
        chain = _make_chain("ku6", nodes_data)
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["n0", "n1", "n2", "n3"]


# ---------------------------------------------------------------------------
# 4. 同阶段稳定顺序（stable order within same stage）
# ---------------------------------------------------------------------------


class TestStableOrderWithinSameStage:
    """相同阶段秩的节点应保持原始相对顺序（稳定排序）。"""

    def test_two_upstream_nodes_preserve_order(self):
        first = _make_tagged("first-up", theme_ids=["gpu"])
        second = _make_tagged("second-up", theme_ids=["memory"])
        chain = _make_chain("stab1", [first, second])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["first-up", "second-up"]

    def test_two_downstream_nodes_preserve_order(self):
        first = _make_tagged("first-down", theme_ids=["ai"])
        second = _make_tagged("second-down", theme_ids=["cloud"])
        chain = _make_chain("stab2", [first, second])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["first-down", "second-down"]

    def test_three_same_stage_nodes_preserve_original_order(self):
        a = _make_tagged("a", theme_ids=["semiconductor"])
        b = _make_tagged("b", theme_ids=["gpu"])
        c = _make_tagged("c", theme_ids=["memory"])
        chain = _make_chain("stab3", [a, b, c])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["a", "b", "c"]

    def test_upstream_group_preserves_order_among_themselves(self):
        # [downstream, up-A, up-B] → [up-A, up-B, downstream]
        down = _make_tagged("down", theme_ids=["ai"])
        up_a = _make_tagged("up-A", theme_ids=["gpu"])
        up_b = _make_tagged("up-B", theme_ids=["storage"])
        chain = _make_chain("stab4", [down, up_a, up_b])
        result = apply_upstream_downstream_order([chain])
        titles = [n.tagged_output.event.title for n in result[0].nodes]
        assert titles == ["up-A", "up-B", "down"]

    def test_positions_are_reassigned_0_based(self):
        down = _make_tagged("down", theme_ids=["cloud"])
        up = _make_tagged("up", theme_ids=["gpu"])
        chain = _make_chain("stab5", [down, up])
        result = apply_upstream_downstream_order([chain])
        positions = [n.position for n in result[0].nodes]
        assert positions == [0, 1]


# ---------------------------------------------------------------------------
# 5. chain_id 与聚合字段保留（chain_id and aggregate preservation）
# ---------------------------------------------------------------------------


class TestChainIdAndAggregatePreservation:
    """chain_id、theme_ids、entity_type_ids 和 tagged_output 引用应原样保留。"""

    def test_chain_id_preserved(self):
        t1 = _make_tagged("A", theme_ids=["ai"])
        chain = _make_chain("my-chain-001", [t1])
        result = apply_upstream_downstream_order([chain])
        assert result[0].chain_id == "my-chain-001"

    def test_chain_id_preserved_across_multiple_chains(self):
        chains = [
            _make_chain(f"chain-{i:03d}", [_make_tagged(f"n{i}", theme_ids=["ai"])])
            for i in range(5)
        ]
        results = apply_upstream_downstream_order(chains)
        for original, output in zip(chains, results):
            assert output.chain_id == original.chain_id

    def test_theme_ids_aggregate_preserved(self):
        t1 = _make_tagged("A", theme_ids=["ai", "gpu"])
        chain = _make_chain("agg1", [t1], theme_ids=("ai", "gpu"))
        result = apply_upstream_downstream_order([chain])
        assert result[0].theme_ids == ("ai", "gpu")

    def test_entity_type_ids_preserved(self):
        t1 = _make_tagged("A", entity_type_ids=["company"])
        chain = _make_chain("agg2", [t1], entity_type_ids=("company",))
        result = apply_upstream_downstream_order([chain])
        assert result[0].entity_type_ids == ("company",)

    def test_empty_aggregates_preserved(self):
        t1 = _make_tagged("A")
        chain = _make_chain("agg3", [t1], theme_ids=(), entity_type_ids=())
        result = apply_upstream_downstream_order([chain])
        assert result[0].theme_ids == ()
        assert result[0].entity_type_ids == ()

    def test_tagged_output_references_preserved(self):
        """重排后节点的 tagged_output 引用应指向原始对象（不拷贝）。"""
        t_down = _make_tagged("down", theme_ids=["cloud"])
        t_up = _make_tagged("up", theme_ids=["gpu"])
        chain = _make_chain("agg4", [t_down, t_up])
        result = apply_upstream_downstream_order([chain])
        # 重排后 position=0 是 t_up（upstream），position=1 是 t_down（downstream）
        assert result[0].nodes[0].tagged_output is t_up
        assert result[0].nodes[1].tagged_output is t_down

    def test_input_chain_not_mutated(self):
        """apply_upstream_downstream_order 不应修改输入链对象。"""
        down = _make_tagged("down", theme_ids=["ai"])
        up = _make_tagged("up", theme_ids=["gpu"])
        chain = _make_chain("immut", [down, up])
        original_titles = [n.tagged_output.event.title for n in chain.nodes]
        apply_upstream_downstream_order([chain])
        titles_after = [n.tagged_output.event.title for n in chain.nodes]
        assert titles_after == original_titles

    def test_output_count_matches_input_count(self):
        chains = [
            _make_chain(f"c{i}", [_make_tagged(f"n{i}", theme_ids=["ai"])])
            for i in range(6)
        ]
        results = apply_upstream_downstream_order(chains)
        assert len(results) == 6


# ---------------------------------------------------------------------------
# 6. relation_to_prev 赋值为 UPSTREAM_DOWNSTREAM
# ---------------------------------------------------------------------------


class TestRelationToPrevAssignment:
    """首节点 relation_to_prev=None，后续节点 relation_to_prev=UPSTREAM_DOWNSTREAM。"""

    def test_first_node_relation_is_none(self):
        t1 = _make_tagged("up", theme_ids=["gpu"])
        t2 = _make_tagged("down", theme_ids=["ai"])
        chain = _make_chain("rel1", [t1, t2])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[0].relation_to_prev is None

    def test_second_node_relation_is_upstream_downstream(self):
        t1 = _make_tagged("up", theme_ids=["gpu"])
        t2 = _make_tagged("down", theme_ids=["ai"])
        chain = _make_chain("rel2", [t1, t2])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[1].relation_to_prev == RelationType.UPSTREAM_DOWNSTREAM

    def test_all_non_first_nodes_get_upstream_downstream_relation(self):
        nodes_data = [
            _make_tagged("up", theme_ids=["semiconductor"]),
            _make_tagged("mid", theme_ids=["compute"]),
            _make_tagged("down", theme_ids=["cloud"]),
            _make_tagged("unknown", theme_ids=[]),
        ]
        chain = _make_chain("rel3", nodes_data)
        result = apply_upstream_downstream_order([chain])
        relations = [n.relation_to_prev for n in result[0].nodes]
        assert relations[0] is None
        assert all(r == RelationType.UPSTREAM_DOWNSTREAM for r in relations[1:])

    def test_upstream_downstream_relation_value_is_correct_string(self):
        """RelationType.UPSTREAM_DOWNSTREAM 的字符串值为"上下游影响"。"""
        t1 = _make_tagged("up", theme_ids=["gpu"])
        t2 = _make_tagged("down", theme_ids=["ai"])
        chain = _make_chain("rel4", [t1, t2])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[1].relation_to_prev == "上下游影响"

    def test_relation_overrides_previous_temporal(self):
        """即使输入节点原 relation_to_prev 为 TEMPORAL，输出应统一为 UPSTREAM_DOWNSTREAM。"""
        t1 = _make_tagged("up", theme_ids=["gpu"])
        t2 = _make_tagged("down", theme_ids=["ai"])
        chain = _make_chain("rel5", [t1, t2])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[1].relation_to_prev == RelationType.UPSTREAM_DOWNSTREAM

    def test_reordered_first_node_relation_is_none(self):
        """重排后新的首节点 relation_to_prev 必须为 None（即使原始节点不是首节点）。"""
        down = _make_tagged("down-first", theme_ids=["cloud"])
        up = _make_tagged("up-second", theme_ids=["gpu"])
        chain = _make_chain("rel6", [down, up])
        result = apply_upstream_downstream_order([chain])
        # 重排后 up 应在首位
        assert result[0].nodes[0].tagged_output.event.title == "up-second"
        assert result[0].nodes[0].relation_to_prev is None


# ---------------------------------------------------------------------------
# 7. 单节点与空输入行为（singleton and empty input behavior）
# ---------------------------------------------------------------------------


class TestSingletonAndEmptyInput:
    """边界条件：单节点链和空输入应正确处理。"""

    def test_empty_input_returns_empty_list(self):
        result = apply_upstream_downstream_order([])
        assert result == []

    def test_singleton_chain_unchanged_structure(self):
        t1 = _make_tagged("only", theme_ids=["gpu"])
        chain = _make_chain("solo", [t1])
        result = apply_upstream_downstream_order([chain])
        assert len(result) == 1
        assert len(result[0].nodes) == 1
        assert result[0].nodes[0].relation_to_prev is None
        assert result[0].nodes[0].position == 0

    def test_singleton_chain_id_preserved(self):
        t1 = _make_tagged("only", theme_ids=["ai"])
        chain = _make_chain("solo-chain", [t1])
        result = apply_upstream_downstream_order([chain])
        assert result[0].chain_id == "solo-chain"

    def test_singleton_with_no_themes(self):
        t1 = _make_tagged("no-themes", theme_ids=[])
        chain = _make_chain("solo-unknown", [t1])
        result = apply_upstream_downstream_order([chain])
        assert len(result[0].nodes) == 1
        assert result[0].nodes[0].relation_to_prev is None

    def test_singleton_tagged_output_reference_preserved(self):
        t1 = _make_tagged("only", theme_ids=["gpu"])
        chain = _make_chain("solo-ref", [t1])
        result = apply_upstream_downstream_order([chain])
        assert result[0].nodes[0].tagged_output is t1


# ---------------------------------------------------------------------------
# 8. 导入面（import surface）
# ---------------------------------------------------------------------------


class TestImportSurface:
    """apply_upstream_downstream_order 应从 app.chains 包直接可导入。"""

    def test_importable_from_package(self):
        assert pkg_fn is apply_upstream_downstream_order

    def test_in_all(self):
        import app.chains as pkg

        assert "apply_upstream_downstream_order" in pkg.__all__

    def test_callable(self):
        assert callable(apply_upstream_downstream_order)
