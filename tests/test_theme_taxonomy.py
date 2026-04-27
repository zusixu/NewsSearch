"""
tests/test_theme_taxonomy.py

主题标签体系完整性测试。
测试目标：ID 唯一性、必选分类存在性、查询行为、结构合法性。
不测试任何抽取算法（尚未实现）。
"""

import pytest

from app.entity.themes import (
    THEME_TAXONOMY,
    ThemeDefinition,
    ThemeId,
    all_themes,
    find_themes_by_keyword,
    get_theme,
    theme_ids,
)

# ---------------------------------------------------------------------------
# 必选主题 ID（来自 plan.md / entity-theme-tagging 上下文的硬性要求）
# ---------------------------------------------------------------------------
REQUIRED_THEME_IDS = {
    ThemeId.AI,
    ThemeId.FOUNDATION_MODEL,
    ThemeId.COMPUTE,
    ThemeId.MEMORY,
    ThemeId.GPU,
    ThemeId.SEMICONDUCTOR,
    ThemeId.CLOUD,
    ThemeId.AI_APPLICATION,
    ThemeId.SUPPLY_CHAIN,
}


class TestTaxonomyCompleteness:
    """所有必选主题均已定义。"""

    def test_required_themes_present(self):
        missing = REQUIRED_THEME_IDS - set(THEME_TAXONOMY.keys())
        assert not missing, f"缺少必选主题: {missing}"

    def test_total_count_at_least_required(self):
        assert len(THEME_TAXONOMY) >= len(REQUIRED_THEME_IDS)

    def test_all_enum_members_have_definition(self):
        """ThemeId 枚举中的每个成员都必须在 THEME_TAXONOMY 中存在对应定义。"""
        for tid in ThemeId:
            assert tid in THEME_TAXONOMY, f"ThemeId.{tid.name} 在 THEME_TAXONOMY 中没有定义"


class TestIdUniqueness:
    """ThemeId 值（字符串）必须全局唯一，且与 definition.id 保持一致。"""

    def test_theme_id_values_unique(self):
        values = [tid.value for tid in ThemeId]
        assert len(values) == len(set(values)), "ThemeId 枚举存在重复的字符串值"

    def test_definition_id_matches_key(self):
        for tid, defn in THEME_TAXONOMY.items():
            assert defn.id == tid, (
                f"键 {tid!r} 对应的 ThemeDefinition.id={defn.id!r} 不一致"
            )


class TestDefinitionStructure:
    """每个 ThemeDefinition 的字段必须合法。"""

    @pytest.mark.parametrize("defn", list(THEME_TAXONOMY.values()))
    def test_label_non_empty(self, defn: ThemeDefinition):
        assert defn.label.strip(), f"{defn.id}: label 不能为空"

    @pytest.mark.parametrize("defn", list(THEME_TAXONOMY.values()))
    def test_label_en_non_empty(self, defn: ThemeDefinition):
        assert defn.label_en.strip(), f"{defn.id}: label_en 不能为空"

    @pytest.mark.parametrize("defn", list(THEME_TAXONOMY.values()))
    def test_description_non_empty(self, defn: ThemeDefinition):
        assert defn.description.strip(), f"{defn.id}: description 不能为空"

    @pytest.mark.parametrize("defn", list(THEME_TAXONOMY.values()))
    def test_keywords_non_empty(self, defn: ThemeDefinition):
        assert len(defn.keywords) > 0, f"{defn.id}: keywords 不能为空 tuple"

    @pytest.mark.parametrize("defn", list(THEME_TAXONOMY.values()))
    def test_keywords_are_strings(self, defn: ThemeDefinition):
        for kw in defn.keywords:
            assert isinstance(kw, str) and kw.strip(), (
                f"{defn.id}: keyword {kw!r} 必须是非空字符串"
            )

    @pytest.mark.parametrize("defn", list(THEME_TAXONOMY.values()))
    def test_definition_is_frozen(self, defn: ThemeDefinition):
        """ThemeDefinition 必须是冻结 dataclass（不可变）。"""
        with pytest.raises((AttributeError, TypeError)):
            defn.label = "hacked"  # type: ignore[misc]


class TestLookupAPI:
    """辅助查询函数的行为测试。"""

    def test_get_theme_returns_correct_definition(self):
        defn = get_theme(ThemeId.AI)
        assert defn.id == ThemeId.AI
        assert defn.label == "人工智能"

    def test_get_theme_unknown_raises(self):
        with pytest.raises(KeyError):
            get_theme("nonexistent_id")  # type: ignore[arg-type]

    def test_all_themes_returns_all(self):
        themes = all_themes()
        assert len(themes) == len(ThemeId)
        ids_returned = {t.id for t in themes}
        assert ids_returned == set(ThemeId)

    def test_theme_ids_returns_all_enum_members(self):
        ids = theme_ids()
        assert set(ids) == set(ThemeId)

    def test_find_by_keyword_hit(self):
        results = find_themes_by_keyword("GPU")
        ids = {r.id for r in results}
        assert ThemeId.GPU in ids

    def test_find_by_keyword_case_insensitive(self):
        results_lower = find_themes_by_keyword("gpu")
        results_upper = find_themes_by_keyword("GPU")
        assert {r.id for r in results_lower} == {r.id for r in results_upper}

    def test_find_by_keyword_no_match_returns_empty(self):
        results = find_themes_by_keyword("xyzzy_no_match_12345")
        assert results == []

    def test_find_by_keyword_hbm_hits_memory(self):
        results = find_themes_by_keyword("HBM")
        ids = {r.id for r in results}
        assert ThemeId.MEMORY in ids

    def test_find_by_keyword_cloud_hits_cloud(self):
        results = find_themes_by_keyword("阿里云")
        ids = {r.id for r in results}
        assert ThemeId.CLOUD in ids

    def test_find_by_keyword_optical_module(self):
        results = find_themes_by_keyword("光模块")
        ids = {r.id for r in results}
        assert ThemeId.OPTICAL_MODULE in ids

    def test_find_by_keyword_storage(self):
        results = find_themes_by_keyword("NAND")
        ids = {r.id for r in results}
        assert ThemeId.STORAGE in ids


class TestThemeIdEnum:
    """ThemeId 枚举自身的约束。"""

    def test_theme_id_is_str_subclass(self):
        """ThemeId 继承 str，可直接当字符串使用（便于 JSON 序列化）。"""
        assert isinstance(ThemeId.AI, str)
        assert ThemeId.AI == "ai"

    def test_theme_id_roundtrip(self):
        """可以从字符串值还原 ThemeId 枚举。"""
        for tid in ThemeId:
            assert ThemeId(tid.value) is tid
