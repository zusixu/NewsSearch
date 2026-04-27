"""
tests/test_relation_type.py — RelationType 枚举的测试套件

覆盖范围
--------
1. 枚举完整性（required members 全部存在，成员总数正确）
2. 必要成员的字符串值稳定性（序列化值不漂移）
3. 从字符串值反向构造（round-trip）
4. str() 语义与 == 比较
5. JSON 序列化兼容性
6. 公开 API 导入（从 app.chains 顶层可用）
7. 与 ChainNode 的集成（relation_to_prev 可接受 RelationType）
8. 与 InformationChain / build_chain 的集成
"""

from __future__ import annotations

import json
import uuid
from enum import Enum

import pytest

from app.chains.relation_type import RelationType


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------

_REQUIRED_MEMBERS = {
    "CAUSAL": "因果",
    "TEMPORAL": "时间延续",
    "UPSTREAM_DOWNSTREAM": "上下游影响",
    "SAME_TOPIC": "同主题发酵",
}


def _new_cid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 1. 枚举完整性
# ---------------------------------------------------------------------------


class TestEnumIntegrity:
    """枚举成员集合必须覆盖全部 4 种关系类型，且不得缺漏。"""

    def test_causal_member_exists(self):
        assert hasattr(RelationType, "CAUSAL")

    def test_temporal_member_exists(self):
        assert hasattr(RelationType, "TEMPORAL")

    def test_upstream_downstream_member_exists(self):
        assert hasattr(RelationType, "UPSTREAM_DOWNSTREAM")

    def test_same_topic_member_exists(self):
        assert hasattr(RelationType, "SAME_TOPIC")

    def test_minimum_member_count(self):
        """至少需要 4 个成员；允许将来扩展但不允许收缩。"""
        assert len(RelationType) >= 4

    def test_is_enum_subclass(self):
        assert issubclass(RelationType, Enum)

    def test_is_str_subclass(self):
        """RelationType 必须是 str 的子类，确保序列化兼容。"""
        assert issubclass(RelationType, str)


# ---------------------------------------------------------------------------
# 2. 字符串值稳定性
# ---------------------------------------------------------------------------


class TestStringStability:
    """枚举值（.value）必须与文档约定完全一致，不允许改动。"""

    @pytest.mark.parametrize("name,expected_value", list(_REQUIRED_MEMBERS.items()))
    def test_member_value_matches_spec(self, name: str, expected_value: str):
        member = RelationType[name]
        assert member.value == expected_value

    def test_causal_value_is_chinese(self):
        assert RelationType.CAUSAL.value == "因果"

    def test_temporal_value_is_chinese(self):
        assert RelationType.TEMPORAL.value == "时间延续"

    def test_upstream_downstream_value_is_chinese(self):
        assert RelationType.UPSTREAM_DOWNSTREAM.value == "上下游影响"

    def test_same_topic_value_is_chinese(self):
        assert RelationType.SAME_TOPIC.value == "同主题发酵"


# ---------------------------------------------------------------------------
# 3. Round-trip（从字符串反向构造）
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """可通过 RelationType(value) 从字符串值重新构造枚举成员。"""

    @pytest.mark.parametrize("name,value", list(_REQUIRED_MEMBERS.items()))
    def test_construct_from_string_value(self, name: str, value: str):
        member = RelationType(value)
        assert member is RelationType[name]

    def test_unknown_value_raises(self):
        with pytest.raises(ValueError):
            RelationType("未知关系")


# ---------------------------------------------------------------------------
# 4. str() 语义与 == 比较
# ---------------------------------------------------------------------------


class TestStrSemantics:
    """作为 str 子类，成员可直接当字符串用，比较行为正确。"""

    def test_str_conversion_equals_value(self):
        # In Python ≥ 3.11, str(member) yields "RelationType.CAUSAL" etc.
        # The serialization-relevant behaviour is that the member *is* a str
        # whose underlying value equals the Chinese label — verified by ==.
        for member in RelationType:
            assert member == member.value  # str-subclass equality

    def test_equality_with_plain_string(self):
        assert RelationType.CAUSAL == "因果"
        assert RelationType.TEMPORAL == "时间延续"
        assert RelationType.UPSTREAM_DOWNSTREAM == "上下游影响"
        assert RelationType.SAME_TOPIC == "同主题发酵"

    def test_inequality_between_members(self):
        assert RelationType.CAUSAL != RelationType.TEMPORAL
        assert RelationType.UPSTREAM_DOWNSTREAM != RelationType.SAME_TOPIC

    def test_members_are_distinct(self):
        values = [m.value for m in RelationType]
        assert len(values) == len(set(values)), "每个成员的字符串值必须唯一"


# ---------------------------------------------------------------------------
# 5. JSON 序列化兼容性
# ---------------------------------------------------------------------------


class TestJsonSerialization:
    """RelationType 可直接嵌入 JSON 负载，无需自定义编码器。"""

    def test_member_serializable_in_dict(self):
        payload = {"relation": RelationType.CAUSAL}
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "因果" in serialized

    def test_all_members_serializable(self):
        for member in RelationType:
            result = json.dumps(member, ensure_ascii=False)
            assert member.value in result

    def test_deserialized_value_reconstructable(self):
        payload = {"relation": RelationType.SAME_TOPIC}
        raw = json.dumps(payload, ensure_ascii=False)
        loaded = json.loads(raw)
        reconstructed = RelationType(loaded["relation"])
        assert reconstructed is RelationType.SAME_TOPIC


# ---------------------------------------------------------------------------
# 6. 公开 API 导入
# ---------------------------------------------------------------------------


class TestImportSurface:
    """RelationType 必须可从 app.chains 顶层导入。"""

    def test_importable_from_app_chains(self):
        from app.chains import RelationType as RT  # noqa: F401
        assert RT is RelationType

    def test_in_all_list(self):
        import app.chains as chains_pkg
        assert "RelationType" in chains_pkg.__all__

    def test_importable_directly_from_module(self):
        from app.chains.relation_type import RelationType as RT  # noqa: F401
        assert RT is RelationType


# ---------------------------------------------------------------------------
# 7. 与 ChainNode 的集成
# ---------------------------------------------------------------------------


class TestChainNodeIntegration:
    """ChainNode.relation_to_prev 可接受 RelationType 或 None。"""

    def _make_node(self, relation: RelationType | None = None):
        from app.chains.chain import ChainNode
        from tests.test_chain import _make_tagged  # reuse existing helper
        return ChainNode(tagged_output=_make_tagged(), position=0, relation_to_prev=relation)

    def test_relation_to_prev_default_is_none(self):
        from app.chains.chain import ChainNode
        from tests.test_chain import _make_tagged
        node = ChainNode(tagged_output=_make_tagged(), position=0)
        assert node.relation_to_prev is None

    def test_relation_to_prev_accepts_causal(self):
        node = self._make_node(RelationType.CAUSAL)
        assert node.relation_to_prev is RelationType.CAUSAL

    def test_relation_to_prev_accepts_temporal(self):
        node = self._make_node(RelationType.TEMPORAL)
        assert node.relation_to_prev is RelationType.TEMPORAL

    def test_relation_to_prev_accepts_upstream_downstream(self):
        node = self._make_node(RelationType.UPSTREAM_DOWNSTREAM)
        assert node.relation_to_prev is RelationType.UPSTREAM_DOWNSTREAM

    def test_relation_to_prev_accepts_same_topic(self):
        node = self._make_node(RelationType.SAME_TOPIC)
        assert node.relation_to_prev is RelationType.SAME_TOPIC

    def test_relation_stored_on_frozen_node(self):
        """frozen dataclass 中的关系值可读，不可写。"""
        import dataclasses
        node = self._make_node(RelationType.CAUSAL)
        assert node.relation_to_prev == RelationType.CAUSAL
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.relation_to_prev = RelationType.TEMPORAL  # type: ignore[misc]

    def test_relation_value_is_str(self):
        """relation_to_prev 的值同时也是字符串（str 子类）。"""
        node = self._make_node(RelationType.CAUSAL)
        assert isinstance(node.relation_to_prev, str)


# ---------------------------------------------------------------------------
# 8. 与 InformationChain / build_chain 的集成
# ---------------------------------------------------------------------------


class TestInformationChainIntegration:
    """链节点可携带 RelationType；build_chain 保持默认 None。"""

    def test_build_chain_leaves_relation_none(self):
        from app.chains import build_chain
        from tests.test_chain import _make_tagged
        chain = build_chain(_new_cid(), [_make_tagged(), _make_tagged()])
        for node in chain.nodes:
            assert node.relation_to_prev is None

    def test_manual_chain_with_typed_relations(self):
        """手动构建带关系的节点，装入 InformationChain，验证可读。"""
        from app.chains.chain import ChainNode, InformationChain
        from tests.test_chain import _make_tagged

        n0 = ChainNode(tagged_output=_make_tagged(), position=0)
        n1 = ChainNode(
            tagged_output=_make_tagged(),
            position=1,
            relation_to_prev=RelationType.CAUSAL,
        )
        n2 = ChainNode(
            tagged_output=_make_tagged(),
            position=2,
            relation_to_prev=RelationType.SAME_TOPIC,
        )
        chain = InformationChain(
            chain_id=_new_cid(),
            nodes=(n0, n1, n2),
            theme_ids=(),
            entity_type_ids=(),
        )
        assert chain.nodes[0].relation_to_prev is None
        assert chain.nodes[1].relation_to_prev is RelationType.CAUSAL
        assert chain.nodes[2].relation_to_prev is RelationType.SAME_TOPIC

    def test_relation_value_readable_as_string_in_chain(self):
        from app.chains.chain import ChainNode, InformationChain
        from tests.test_chain import _make_tagged

        n0 = ChainNode(tagged_output=_make_tagged(), position=0)
        n1 = ChainNode(
            tagged_output=_make_tagged(),
            position=1,
            relation_to_prev=RelationType.UPSTREAM_DOWNSTREAM,
        )
        chain = InformationChain(
            chain_id=_new_cid(),
            nodes=(n0, n1),
            theme_ids=(),
            entity_type_ids=(),
        )
        assert chain.nodes[1].relation_to_prev == "上下游影响"
