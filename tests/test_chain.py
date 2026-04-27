"""
tests/test_chain.py — InformationChain / ChainNode / build_chain 的测试套件

覆盖范围
--------
1. 基本构建行为（build_chain）
2. 节点顺序与 position 赋值
3. 链级别 theme_ids / entity_type_ids 聚合
4. 不可变性（frozen dataclass）
5. 校验逻辑（空节点、空 chain_id、position 不连续）
6. 与 TaggedOutput / EventDraft 的集成和溯源
7. 公开 API 导入
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from app.chains.chain import ChainNode, InformationChain, build_chain
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


def _make_news(title: str = "test", date: str = "2025-01-01") -> NewsItem:
    return NewsItem.from_raw(_make_raw(title=title, date=date))


def _make_event(title: str = "测试事件", date: str = "2025-01-01") -> EventDraft:
    return EventDraft.from_news_item(_make_news(title=title, date=date))


def _make_hit(
    matched_text: str,
    start: int,
    end: int,
    kind: str,
    label_id: str,
) -> Hit:
    return Hit(
        matched_text=matched_text,
        start=start,
        end=end,
        matched_seed=matched_text,
        kind=kind,  # type: ignore[arg-type]
        label_id=label_id,
    )


def _make_tagged(
    title: str = "测试事件",
    date: str = "2025-01-01",
    text: str = "",
    hits: list[Hit] | None = None,
) -> TaggedOutput:
    event = _make_event(title=title, date=date)
    links = build_evidence_links(text, hits or [], context_window=0)
    return build_tagged_output(event, text, links)


def _new_chain_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 1. 基本构建行为
# ---------------------------------------------------------------------------


class TestBuildChainBasic:
    """build_chain 的基本构建行为。"""

    def test_returns_information_chain_instance(self):
        to = _make_tagged()
        chain = build_chain(_new_chain_id(), [to])
        assert isinstance(chain, InformationChain)

    def test_chain_id_is_preserved(self):
        cid = _new_chain_id()
        to = _make_tagged()
        chain = build_chain(cid, [to])
        assert chain.chain_id == cid

    def test_single_node_chain(self):
        to = _make_tagged(title="单节点事件")
        chain = build_chain(_new_chain_id(), [to])
        assert len(chain.nodes) == 1

    def test_multi_node_chain_length(self):
        nodes_in = [_make_tagged(title=f"事件{i}") for i in range(4)]
        chain = build_chain(_new_chain_id(), nodes_in)
        assert len(chain.nodes) == 4

    def test_tagged_output_reference_preserved(self):
        """ChainNode 应持有原始 TaggedOutput 引用，不做拷贝。"""
        to = _make_tagged()
        chain = build_chain(_new_chain_id(), [to])
        assert chain.nodes[0].tagged_output is to


# ---------------------------------------------------------------------------
# 2. 节点顺序与 position
# ---------------------------------------------------------------------------


class TestNodeOrdering:
    """节点顺序与 position 赋值。"""

    def test_positions_are_zero_based_consecutive(self):
        tos = [_make_tagged(title=f"事件{i}") for i in range(5)]
        chain = build_chain(_new_chain_id(), tos)
        positions = [n.position for n in chain.nodes]
        assert positions == list(range(5))

    def test_node_order_matches_input_order(self):
        to0 = _make_tagged(title="首个事件", date="2025-01-01")
        to1 = _make_tagged(title="第二事件", date="2025-01-02")
        to2 = _make_tagged(title="第三事件", date="2025-01-03")
        chain = build_chain(_new_chain_id(), [to0, to1, to2])
        assert chain.nodes[0].tagged_output is to0
        assert chain.nodes[1].tagged_output is to1
        assert chain.nodes[2].tagged_output is to2

    def test_position_zero_is_first_node(self):
        to0 = _make_tagged(title="上游事件")
        to1 = _make_tagged(title="下游事件")
        chain = build_chain(_new_chain_id(), [to0, to1])
        assert chain.nodes[0].position == 0
        assert chain.nodes[1].position == 1

    def test_relation_to_prev_is_none_for_all_nodes(self):
        """relation_to_prev 在节点1阶段固定为 None，等待节点2赋值。"""
        tos = [_make_tagged() for _ in range(3)]
        chain = build_chain(_new_chain_id(), tos)
        for node in chain.nodes:
            assert node.relation_to_prev is None


# ---------------------------------------------------------------------------
# 3. 主题与实体类型 ID 聚合
# ---------------------------------------------------------------------------


class TestIdAggregation:
    """链级别 theme_ids / entity_type_ids 应为所有节点标签的并集。"""

    def test_theme_ids_union_across_nodes(self):
        text_a = "GPU 需求旺盛。"
        text_b = "AI 算力竞争。"
        hit_a = _make_hit("GPU", 0, 3, "theme", "gpu")
        hit_b = _make_hit("AI", 0, 2, "theme", "ai")
        to_a = _make_tagged(text=text_a, hits=[hit_a])
        to_b = _make_tagged(text=text_b, hits=[hit_b])

        chain = build_chain(_new_chain_id(), [to_a, to_b])
        assert set(chain.theme_ids) == {"gpu", "ai"}

    def test_entity_type_ids_union_across_nodes(self):
        text_a = "英伟达公司。"
        text_b = "AMD 公司。"
        hit_a = _make_hit("英伟达", 0, 3, "entity_type", "company")
        hit_b = _make_hit("AMD", 0, 3, "entity_type", "company")
        to_a = _make_tagged(text=text_a, hits=[hit_a])
        to_b = _make_tagged(text=text_b, hits=[hit_b])

        chain = build_chain(_new_chain_id(), [to_a, to_b])
        # 两节点均为 company，合并后去重
        assert chain.entity_type_ids == ("company",)

    def test_theme_ids_deduped_across_nodes(self):
        text = "GPU 需求。"
        hit = _make_hit("GPU", 0, 3, "theme", "gpu")
        to_a = _make_tagged(text=text, hits=[hit])
        to_b = _make_tagged(text=text, hits=[hit])

        chain = build_chain(_new_chain_id(), [to_a, to_b])
        assert chain.theme_ids.count("gpu") == 1

    def test_theme_ids_sorted_ascending(self):
        texts_hits = [
            ("半导体。", _make_hit("半导体", 0, 3, "theme", "semiconductor")),
            ("AI 。", _make_hit("AI", 0, 2, "theme", "ai")),
            ("GPU 。", _make_hit("GPU", 0, 3, "theme", "gpu")),
        ]
        tos = [_make_tagged(text=t, hits=[h]) for t, h in texts_hits]
        chain = build_chain(_new_chain_id(), tos)
        assert list(chain.theme_ids) == sorted(chain.theme_ids)

    def test_entity_type_ids_sorted_ascending(self):
        to_company = _make_tagged(
            text="英伟达。",
            hits=[_make_hit("英伟达", 0, 3, "entity_type", "company")],
        )
        to_tech = _make_tagged(
            text="HBM。",
            hits=[_make_hit("HBM", 0, 3, "entity_type", "technology")],
        )
        chain = build_chain(_new_chain_id(), [to_company, to_tech])
        assert list(chain.entity_type_ids) == sorted(chain.entity_type_ids)

    def test_empty_labels_in_all_nodes_gives_empty_aggregates(self):
        tos = [_make_tagged(), _make_tagged()]
        chain = build_chain(_new_chain_id(), tos)
        assert chain.theme_ids == ()
        assert chain.entity_type_ids == ()

    def test_single_node_theme_ids_match_node(self):
        text = "GPU 需求。"
        hit = _make_hit("GPU", 0, 3, "theme", "gpu")
        to = _make_tagged(text=text, hits=[hit])
        chain = build_chain(_new_chain_id(), [to])
        assert chain.theme_ids == to.theme_ids


# ---------------------------------------------------------------------------
# 4. 不可变性（frozen dataclass）
# ---------------------------------------------------------------------------


class TestImmutability:
    """InformationChain 和 ChainNode 均为 frozen dataclass。"""

    def test_chain_cannot_reassign_chain_id(self):
        chain = build_chain(_new_chain_id(), [_make_tagged()])
        with pytest.raises(dataclasses.FrozenInstanceError):
            chain.chain_id = "new-id"  # type: ignore[misc]

    def test_chain_cannot_reassign_nodes(self):
        chain = build_chain(_new_chain_id(), [_make_tagged()])
        with pytest.raises(dataclasses.FrozenInstanceError):
            chain.nodes = ()  # type: ignore[misc]

    def test_chain_cannot_reassign_theme_ids(self):
        chain = build_chain(_new_chain_id(), [_make_tagged()])
        with pytest.raises(dataclasses.FrozenInstanceError):
            chain.theme_ids = ("gpu",)  # type: ignore[misc]

    def test_chain_nodes_field_is_tuple(self):
        chain = build_chain(_new_chain_id(), [_make_tagged()])
        assert isinstance(chain.nodes, tuple)

    def test_chain_theme_ids_is_tuple(self):
        chain = build_chain(_new_chain_id(), [_make_tagged()])
        assert isinstance(chain.theme_ids, tuple)

    def test_chain_entity_type_ids_is_tuple(self):
        chain = build_chain(_new_chain_id(), [_make_tagged()])
        assert isinstance(chain.entity_type_ids, tuple)

    def test_chain_node_cannot_reassign_position(self):
        chain = build_chain(_new_chain_id(), [_make_tagged()])
        node = chain.nodes[0]
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.position = 99  # type: ignore[misc]

    def test_chain_node_cannot_reassign_tagged_output(self):
        chain = build_chain(_new_chain_id(), [_make_tagged()])
        node = chain.nodes[0]
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.tagged_output = _make_tagged()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5. 校验逻辑
# ---------------------------------------------------------------------------


class TestValidation:
    """build_chain 和 InformationChain.__post_init__ 的校验边界。"""

    def test_empty_chain_id_raises(self):
        with pytest.raises(ValueError, match="chain_id"):
            build_chain("", [_make_tagged()])

    def test_empty_tagged_outputs_raises(self):
        with pytest.raises(ValueError):
            build_chain(_new_chain_id(), [])

    def test_direct_construction_empty_chain_id_raises(self):
        node = ChainNode(tagged_output=_make_tagged(), position=0)
        with pytest.raises(ValueError, match="chain_id"):
            InformationChain(
                chain_id="",
                nodes=(node,),
                theme_ids=(),
                entity_type_ids=(),
            )

    def test_direct_construction_empty_nodes_raises(self):
        with pytest.raises(ValueError, match="nodes"):
            InformationChain(
                chain_id=_new_chain_id(),
                nodes=(),
                theme_ids=(),
                entity_type_ids=(),
            )

    def test_direct_construction_non_consecutive_positions_raises(self):
        to = _make_tagged()
        node0 = ChainNode(tagged_output=to, position=0)
        node2 = ChainNode(tagged_output=to, position=2)  # 跳过 1
        with pytest.raises(ValueError, match="position"):
            InformationChain(
                chain_id=_new_chain_id(),
                nodes=(node0, node2),
                theme_ids=(),
                entity_type_ids=(),
            )

    def test_direct_construction_wrong_start_position_raises(self):
        to = _make_tagged()
        node1 = ChainNode(tagged_output=to, position=1)  # 应从 0 开始
        with pytest.raises(ValueError, match="position"):
            InformationChain(
                chain_id=_new_chain_id(),
                nodes=(node1,),
                theme_ids=(),
                entity_type_ids=(),
            )


# ---------------------------------------------------------------------------
# 6. 与 TaggedOutput / EventDraft 集成和溯源
# ---------------------------------------------------------------------------


class TestTraceability:
    """通过 chain → node → tagged_output → event → source_items 完整溯源。"""

    def test_can_access_event_title_via_chain(self):
        to = _make_tagged(title="英伟达 GPU 供货缩减")
        chain = build_chain(_new_chain_id(), [to])
        assert chain.nodes[0].tagged_output.event.title == "英伟达 GPU 供货缩减"

    def test_can_access_occurred_at_via_chain(self):
        to = _make_tagged(date="2025-06-15")
        chain = build_chain(_new_chain_id(), [to])
        assert chain.nodes[0].tagged_output.event.occurred_at == "2025-06-15"

    def test_can_access_evidence_links_via_chain(self):
        text = "GPU 需求激增。"
        hit = _make_hit("GPU", 0, 3, "theme", "gpu")
        to = _make_tagged(text=text, hits=[hit])
        chain = build_chain(_new_chain_id(), [to])
        assert len(chain.nodes[0].tagged_output.evidence_links) == 1

    def test_can_access_source_items_via_chain(self):
        news = _make_news(title="供应链报告")
        event = EventDraft.from_news_item(news)
        to = build_tagged_output(event, "", [])
        chain = build_chain(_new_chain_id(), [to])
        assert chain.nodes[0].tagged_output.event.source_items[0] is news

    def test_multi_node_evidence_independently_accessible(self):
        text_a = "GPU 旺盛。"
        text_b = "AI 爆发。"
        hit_a = _make_hit("GPU", 0, 3, "theme", "gpu")
        hit_b = _make_hit("AI", 0, 2, "theme", "ai")
        to_a = _make_tagged(text=text_a, hits=[hit_a])
        to_b = _make_tagged(text=text_b, hits=[hit_b])
        chain = build_chain(_new_chain_id(), [to_a, to_b])

        # 每个节点的证据彼此独立
        label_a = chain.nodes[0].tagged_output.evidence_links[0].hit.label_id
        label_b = chain.nodes[1].tagged_output.evidence_links[0].hit.label_id
        assert label_a == "gpu"
        assert label_b == "ai"


# ---------------------------------------------------------------------------
# 7. 公开 API 导入
# ---------------------------------------------------------------------------


class TestImportSurface:
    """公开 API 可从 app.chains 顶层导入。"""

    def test_information_chain_importable_from_app_chains(self):
        from app.chains import InformationChain as IC  # noqa: F401
        assert IC is InformationChain

    def test_chain_node_importable_from_app_chains(self):
        from app.chains import ChainNode as CN  # noqa: F401
        assert CN is ChainNode

    def test_build_chain_importable_from_app_chains(self):
        from app.chains import build_chain as bc  # noqa: F401
        assert bc is build_chain

    def test_all_contains_expected_names(self):
        import app.chains as chains_pkg
        for name in ("InformationChain", "ChainNode", "build_chain"):
            assert name in chains_pkg.__all__
