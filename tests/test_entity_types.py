"""
tests/test_entity_types.py

实体类型体系完整性测试。
测试目标：ID 唯一性、必选类型存在性、查询行为、结构合法性。
不测试任何抽取算法（尚未实现）。
"""

import pytest

from app.entity.entity_types import (
    ENTITY_TYPE_TAXONOMY,
    EntityTypeDefinition,
    EntityTypeId,
    all_entity_types,
    entity_type_ids,
    find_types_by_mention,
    get_entity_type,
)

# ---------------------------------------------------------------------------
# 必选实体类型 ID（来自 entity-theme-tagging 上下文的硬性要求）
# ---------------------------------------------------------------------------
REQUIRED_ENTITY_TYPE_IDS = {
    EntityTypeId.COMPANY,
    EntityTypeId.PRODUCT,
    EntityTypeId.TECHNOLOGY,
    EntityTypeId.SUPPLY_CHAIN_ROLE,
    EntityTypeId.REGION,
    EntityTypeId.POLICY_BODY,
}


class TestTaxonomyCompleteness:
    """所有必选实体类型均已定义。"""

    def test_required_types_present(self):
        missing = REQUIRED_ENTITY_TYPE_IDS - set(ENTITY_TYPE_TAXONOMY.keys())
        assert not missing, f"缺少必选实体类型: {missing}"

    def test_total_count_at_least_required(self):
        assert len(ENTITY_TYPE_TAXONOMY) >= len(REQUIRED_ENTITY_TYPE_IDS)

    def test_all_enum_members_have_definition(self):
        """EntityTypeId 枚举中的每个成员都必须在 ENTITY_TYPE_TAXONOMY 中存在对应定义。"""
        for tid in EntityTypeId:
            assert tid in ENTITY_TYPE_TAXONOMY, (
                f"EntityTypeId.{tid.name} 在 ENTITY_TYPE_TAXONOMY 中没有定义"
            )

    def test_product_and_technology_are_distinct(self):
        """产品与技术须拆分为独立类型——两者 ID 不同，定义分别存在。"""
        assert EntityTypeId.PRODUCT in ENTITY_TYPE_TAXONOMY
        assert EntityTypeId.TECHNOLOGY in ENTITY_TYPE_TAXONOMY
        assert EntityTypeId.PRODUCT != EntityTypeId.TECHNOLOGY


class TestIdUniqueness:
    """EntityTypeId 值（字符串）必须全局唯一，且与 definition.id 保持一致。"""

    def test_entity_type_id_values_unique(self):
        values = [tid.value for tid in EntityTypeId]
        assert len(values) == len(set(values)), "EntityTypeId 枚举存在重复的字符串值"

    def test_definition_id_matches_key(self):
        for tid, defn in ENTITY_TYPE_TAXONOMY.items():
            assert defn.id == tid, (
                f"键 {tid!r} 对应的 EntityTypeDefinition.id={defn.id!r} 不一致"
            )


class TestDefinitionStructure:
    """每个 EntityTypeDefinition 的字段必须合法。"""

    @pytest.mark.parametrize("defn", list(ENTITY_TYPE_TAXONOMY.values()))
    def test_label_non_empty(self, defn: EntityTypeDefinition):
        assert defn.label.strip(), f"{defn.id}: label 不能为空"

    @pytest.mark.parametrize("defn", list(ENTITY_TYPE_TAXONOMY.values()))
    def test_label_en_non_empty(self, defn: EntityTypeDefinition):
        assert defn.label_en.strip(), f"{defn.id}: label_en 不能为空"

    @pytest.mark.parametrize("defn", list(ENTITY_TYPE_TAXONOMY.values()))
    def test_description_non_empty(self, defn: EntityTypeDefinition):
        assert defn.description.strip(), f"{defn.id}: description 不能为空"

    @pytest.mark.parametrize("defn", list(ENTITY_TYPE_TAXONOMY.values()))
    def test_example_mentions_non_empty(self, defn: EntityTypeDefinition):
        assert len(defn.example_mentions) > 0, (
            f"{defn.id}: example_mentions 不能为空 tuple"
        )

    @pytest.mark.parametrize("defn", list(ENTITY_TYPE_TAXONOMY.values()))
    def test_example_mentions_are_strings(self, defn: EntityTypeDefinition):
        for ex in defn.example_mentions:
            assert isinstance(ex, str) and ex.strip(), (
                f"{defn.id}: example_mention {ex!r} 必须是非空字符串"
            )

    @pytest.mark.parametrize("defn", list(ENTITY_TYPE_TAXONOMY.values()))
    def test_definition_is_frozen(self, defn: EntityTypeDefinition):
        """EntityTypeDefinition 必须是冻结 dataclass（不可变）。"""
        with pytest.raises((AttributeError, TypeError)):
            defn.label = "hacked"  # type: ignore[misc]


class TestLookupAPI:
    """辅助查询函数的行为测试。"""

    def test_get_entity_type_returns_correct_definition(self):
        defn = get_entity_type(EntityTypeId.COMPANY)
        assert defn.id == EntityTypeId.COMPANY
        assert defn.label == "公司"

    def test_get_entity_type_unknown_raises(self):
        with pytest.raises(KeyError):
            get_entity_type("nonexistent_id")  # type: ignore[arg-type]

    def test_all_entity_types_returns_all(self):
        types = all_entity_types()
        assert len(types) == len(EntityTypeId)
        ids_returned = {t.id for t in types}
        assert ids_returned == set(EntityTypeId)

    def test_entity_type_ids_returns_all_enum_members(self):
        ids = entity_type_ids()
        assert set(ids) == set(EntityTypeId)

    def test_find_by_mention_company_nvidia(self):
        results = find_types_by_mention("NVIDIA")
        ids = {r.id for r in results}
        assert EntityTypeId.COMPANY in ids

    def test_find_by_mention_product_h100(self):
        results = find_types_by_mention("H100")
        ids = {r.id for r in results}
        assert EntityTypeId.PRODUCT in ids

    def test_find_by_mention_technology_cowos(self):
        results = find_types_by_mention("CoWoS")
        ids = {r.id for r in results}
        assert EntityTypeId.TECHNOLOGY in ids

    def test_find_by_mention_supply_chain_role_odm(self):
        results = find_types_by_mention("ODM")
        ids = {r.id for r in results}
        assert EntityTypeId.SUPPLY_CHAIN_ROLE in ids

    def test_find_by_mention_region_usa(self):
        results = find_types_by_mention("美国")
        ids = {r.id for r in results}
        assert EntityTypeId.REGION in ids

    def test_find_by_mention_policy_body_bis(self):
        results = find_types_by_mention("BIS")
        ids = {r.id for r in results}
        assert EntityTypeId.POLICY_BODY in ids

    def test_find_by_mention_case_insensitive(self):
        results_lower = find_types_by_mention("nvidia")
        results_upper = find_types_by_mention("NVIDIA")
        assert {r.id for r in results_lower} == {r.id for r in results_upper}

    def test_find_by_mention_no_match_returns_empty(self):
        results = find_types_by_mention("xyzzy_no_match_12345")
        assert results == []

    def test_find_by_mention_tsmc_is_company(self):
        results = find_types_by_mention("TSMC")
        ids = {r.id for r in results}
        assert EntityTypeId.COMPANY in ids

    def test_find_by_mention_hbm_is_technology(self):
        """HBM 在实体类型中归类为技术（区别于主题中的内存赛道）。"""
        results = find_types_by_mention("HBM")
        ids = {r.id for r in results}
        assert EntityTypeId.TECHNOLOGY in ids


class TestEntityTypeIdEnum:
    """EntityTypeId 枚举自身的约束。"""

    def test_entity_type_id_is_str_subclass(self):
        """EntityTypeId 继承 str，可直接当字符串使用（便于 JSON 序列化）。"""
        assert isinstance(EntityTypeId.COMPANY, str)
        assert EntityTypeId.COMPANY == "company"

    def test_entity_type_id_roundtrip(self):
        """可以从字符串值还原 EntityTypeId 枚举。"""
        for tid in EntityTypeId:
            assert EntityTypeId(tid.value) is tid

    def test_all_required_ids_have_stable_string_values(self):
        """验证必选类型的 ID 字符串值稳定，以防重构时意外修改。"""
        assert EntityTypeId.COMPANY.value == "company"
        assert EntityTypeId.PRODUCT.value == "product"
        assert EntityTypeId.TECHNOLOGY.value == "technology"
        assert EntityTypeId.SUPPLY_CHAIN_ROLE.value == "supply_chain_role"
        assert EntityTypeId.REGION.value == "region"
        assert EntityTypeId.POLICY_BODY.value == "policy_body"
