"""
tests/test_rule_extractor.py — 基础规则抽取引擎测试

覆盖：
- 中文关键词命中
- 英文关键词大小写不敏感命中
- 短 ASCII token 的假阳性规避
- 实体类型 example_mentions 命中
- 命中结果的稳定排序
- 空文本 / 无命中场景
- 包导入 / 导出接口
"""

from __future__ import annotations

import pytest

from app.entity.rules import Hit, RuleExtractor
from app.entity.themes import ThemeId
from app.entity.entity_types import EntityTypeId


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def extractor() -> RuleExtractor:
    return RuleExtractor()


# ---------------------------------------------------------------------------
# 1. 主题关键词命中
# ---------------------------------------------------------------------------


class TestThemeHits:
    def test_chinese_keyword_hit_returns_hit(self, extractor: RuleExtractor) -> None:
        """中文关键词"人工智能"应命中 AI 主题。"""
        hits = extractor.extract("人工智能正在改变世界。")
        theme_hits = [h for h in hits if h.label_id == ThemeId.AI.value]
        assert len(theme_hits) >= 1
        hit = theme_hits[0]
        assert hit.kind == "theme"
        assert hit.matched_text == "人工智能"

    def test_chinese_keyword_hit_correct_offsets(self, extractor: RuleExtractor) -> None:
        """命中的 start/end 偏移应与原始文本一致。"""
        text = "这是关于人工智能的报道。"
        hits = extractor.extract(text)
        theme_hits = [h for h in hits if h.label_id == ThemeId.AI.value]
        assert theme_hits, "Expected at least one AI theme hit"
        for hit in theme_hits:
            assert text[hit.start : hit.end] == hit.matched_text

    def test_english_keyword_case_insensitive_lowercase(
        self, extractor: RuleExtractor
    ) -> None:
        """英文关键词小写形式"nvidia"应命中。"""
        hits = extractor.extract("nvidia released new chips today.")
        gpu_hits = [h for h in hits if h.label_id == ThemeId.GPU.value]
        assert gpu_hits, "Expected GPU theme hit for 'nvidia'"

    def test_english_keyword_case_insensitive_uppercase(
        self, extractor: RuleExtractor
    ) -> None:
        """英文关键词大写形式"NVIDIA"应命中。"""
        hits = extractor.extract("NVIDIA stock rose sharply.")
        gpu_hits = [h for h in hits if h.label_id == ThemeId.GPU.value]
        assert gpu_hits, "Expected GPU theme hit for 'NVIDIA'"

    def test_multiple_themes_in_one_text(self, extractor: RuleExtractor) -> None:
        """同一段文本应可命中多个不同主题。"""
        text = "英伟达 GPU 供应紧张，云计算服务商纷纷扩容。"
        hits = extractor.extract(text)
        label_ids = {h.label_id for h in hits}
        assert ThemeId.GPU.value in label_ids
        assert ThemeId.CLOUD.value in label_ids

    def test_hit_fields_are_all_populated(self, extractor: RuleExtractor) -> None:
        """Hit 对象所有字段均应填充。"""
        hits = extractor.extract("GPU 算力需求旺盛。")
        assert hits
        hit = hits[0]
        assert hit.matched_text
        assert isinstance(hit.start, int)
        assert isinstance(hit.end, int)
        assert hit.end > hit.start
        assert hit.matched_seed
        assert hit.kind in ("theme", "entity_type")
        assert hit.label_id


# ---------------------------------------------------------------------------
# 2. 假阳性规避（短 ASCII token 词边界保护）
# ---------------------------------------------------------------------------


class TestFalsePositiveAvoidance:
    def test_ai_not_inside_paid(self, extractor: RuleExtractor) -> None:
        """'PAID' 不应触发 AI 主题命中。"""
        hits = extractor.extract("The vendor PAID for the invoice.")
        ai_hits = [h for h in hits if h.label_id == ThemeId.AI.value]
        assert not ai_hits, f"Unexpected AI hits: {ai_hits}"

    def test_ai_not_inside_brain(self, extractor: RuleExtractor) -> None:
        """'BRAIN' 不应触发 AI 主题命中。"""
        hits = extractor.extract("BRAIN research is fascinating.")
        ai_hits = [h for h in hits if h.label_id == ThemeId.AI.value]
        assert not ai_hits, f"Unexpected AI hits: {ai_hits}"

    def test_ai_not_inside_chain(self, extractor: RuleExtractor) -> None:
        """'CHAIN' 单词内的 AI 字母序列不应触发 AI 主题命中。"""
        hits = extractor.extract("The food CHAIN expanded globally.")
        ai_hits = [h for h in hits if h.label_id == ThemeId.AI.value]
        assert not ai_hits, f"Unexpected AI hits: {ai_hits}"

    def test_ai_standalone_matches(self, extractor: RuleExtractor) -> None:
        """独立词'AI'（前后有词边界）应命中 AI 主题。"""
        hits = extractor.extract("The AI sector is booming.")
        ai_hits = [h for h in hits if h.label_id == ThemeId.AI.value]
        assert ai_hits, "Expected AI theme hit for standalone 'AI'"

    def test_ai_at_punctuation_boundary(self, extractor: RuleExtractor) -> None:
        """AI 紧跟标点符号时（词边界存在）应命中。"""
        hits = extractor.extract("Next-gen AI.")
        ai_hits = [h for h in hits if h.label_id == ThemeId.AI.value]
        assert ai_hits, "Expected AI theme hit at punctuation boundary"

    def test_gpu_not_inside_longer_ascii_word(self, extractor: RuleExtractor) -> None:
        """'GPU' 嵌在纯 ASCII 长词内不应命中（保守策略）。"""
        hits = extractor.extract("XGPUX is a fictional word.")
        gpu_hits = [h for h in hits if h.label_id == ThemeId.GPU.value]
        assert not gpu_hits, f"Unexpected GPU hits inside longer word: {gpu_hits}"


# ---------------------------------------------------------------------------
# 3. 实体类型 example_mentions 命中
# ---------------------------------------------------------------------------


class TestEntityTypeHits:
    def test_company_example_hit(self, extractor: RuleExtractor) -> None:
        """'NVIDIA' 应命中 COMPANY 实体类型。"""
        hits = extractor.extract("NVIDIA dominates the AI chip market.")
        company_hits = [
            h for h in hits if h.label_id == EntityTypeId.COMPANY.value
        ]
        assert company_hits, "Expected COMPANY entity hit for 'NVIDIA'"

    def test_product_example_hit(self, extractor: RuleExtractor) -> None:
        """'H100' 应命中 PRODUCT 实体类型。"""
        hits = extractor.extract("The H100 GPU is in short supply.")
        product_hits = [
            h for h in hits if h.label_id == EntityTypeId.PRODUCT.value
        ]
        assert product_hits, "Expected PRODUCT entity hit for 'H100'"

    def test_technology_example_hit(self, extractor: RuleExtractor) -> None:
        """'CoWoS' 应命中 TECHNOLOGY 实体类型。"""
        hits = extractor.extract("台积电的 CoWoS 封装产能受限。")
        tech_hits = [
            h for h in hits if h.label_id == EntityTypeId.TECHNOLOGY.value
        ]
        assert tech_hits, "Expected TECHNOLOGY entity hit for 'CoWoS'"

    def test_entity_hit_kind_is_entity_type(self, extractor: RuleExtractor) -> None:
        """实体类型命中的 kind 字段应为 'entity_type'。"""
        hits = extractor.extract("NVIDIA launched H100.")
        entity_hits = [h for h in hits if h.kind == "entity_type"]
        assert entity_hits

    def test_chinese_entity_example_hit(self, extractor: RuleExtractor) -> None:
        """中文示例提及'英伟达'应命中 COMPANY 实体类型。"""
        hits = extractor.extract("英伟达发布了新一代芯片。")
        company_hits = [
            h for h in hits if h.label_id == EntityTypeId.COMPANY.value
        ]
        assert company_hits, "Expected COMPANY entity hit for '英伟达'"


# ---------------------------------------------------------------------------
# 4. 排序与去重
# ---------------------------------------------------------------------------


class TestOrderingAndDedup:
    def test_hits_sorted_by_start_offset(self, extractor: RuleExtractor) -> None:
        """命中列表应按 start 偏移升序排列。"""
        text = "GPU 需求旺盛，AI 应用广泛，HBM 供应紧张。"
        hits = extractor.extract(text)
        starts = [h.start for h in hits]
        assert starts == sorted(starts), "Hits are not sorted by start offset"

    def test_stable_order_is_deterministic(self, extractor: RuleExtractor) -> None:
        """多次调用同一文本，结果应完全一致。"""
        text = "人工智能与半导体产业协同发展。"
        hits1 = extractor.extract(text)
        hits2 = extractor.extract(text)
        assert hits1 == hits2

    def test_no_duplicate_hits_same_position_same_label(
        self, extractor: RuleExtractor
    ) -> None:
        """同一位置同一标签不应出现重复命中。"""
        text = "GPU 芯片性能大幅提升。"
        hits = extractor.extract(text)
        keys = [(h.start, h.end, h.label_id) for h in hits]
        assert len(keys) == len(set(keys)), "Duplicate hits detected"

    def test_multiple_occurrences_of_same_keyword(
        self, extractor: RuleExtractor
    ) -> None:
        """关键词在文本中出现两次，应产生两条命中记录。"""
        text = "AI 应用广泛，下一代 AI 芯片已发布。"
        hits = extractor.extract(text)
        ai_hits = [h for h in hits if h.matched_text == "AI"]
        assert len(ai_hits) >= 2, f"Expected ≥2 AI hits, got {len(ai_hits)}"
        # 确认两次出现位置不同
        starts = [h.start for h in ai_hits]
        assert len(set(starts)) >= 2


# ---------------------------------------------------------------------------
# 5. 边界与空输入
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_string_returns_empty(self, extractor: RuleExtractor) -> None:
        assert extractor.extract("") == []

    def test_whitespace_only_returns_empty(self, extractor: RuleExtractor) -> None:
        assert extractor.extract("   \t\n  ") == []

    def test_no_match_text_returns_empty(self, extractor: RuleExtractor) -> None:
        """与任何种子词无关的文本应返回空列表。"""
        assert extractor.extract("banana cherry orange") == []

    def test_keyword_at_start_of_text(self, extractor: RuleExtractor) -> None:
        """关键词位于文本开头时 start 偏移应为 0。"""
        hits = extractor.extract("GPU supply is tight this quarter.")
        gpu_hits = [h for h in hits if h.label_id == ThemeId.GPU.value]
        assert gpu_hits
        assert gpu_hits[0].start == 0

    def test_keyword_at_end_of_text(self, extractor: RuleExtractor) -> None:
        """关键词位于文本末尾时 end 偏移应等于文本长度。"""
        text = "全球最先进的 GPU"
        hits = extractor.extract(text)
        gpu_hits = [h for h in hits if h.label_id == ThemeId.GPU.value]
        assert gpu_hits
        assert gpu_hits[0].end == len(text)

    def test_hit_is_frozen_dataclass(self, extractor: RuleExtractor) -> None:
        """Hit 是冻结 dataclass，不允许修改字段。"""
        hits = extractor.extract("AI 行业高速增长。")
        assert hits
        with pytest.raises((AttributeError, TypeError)):
            hits[0].label_id = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 6. 导入 / 导出接口
# ---------------------------------------------------------------------------


class TestImportExports:
    def test_hit_importable_from_rules_package(self) -> None:
        """Hit 可直接从 app.entity.rules 导入。"""
        from app.entity.rules import Hit as _Hit

        assert _Hit is Hit

    def test_rule_extractor_importable_from_rules_package(self) -> None:
        """RuleExtractor 可直接从 app.entity.rules 导入。"""
        from app.entity.rules import RuleExtractor as _RE

        assert _RE is RuleExtractor

    def test_rules_all_exports(self) -> None:
        """app.entity.rules.__all__ 应包含 Hit 和 RuleExtractor。"""
        import app.entity.rules as rules_pkg

        assert "Hit" in rules_pkg.__all__
        assert "RuleExtractor" in rules_pkg.__all__

    def test_hit_and_extractor_importable_from_entity_package(self) -> None:
        """Hit 和 RuleExtractor 可从顶层 app.entity 包导入。"""
        import app.entity as entity_pkg

        assert hasattr(entity_pkg, "Hit")
        assert hasattr(entity_pkg, "RuleExtractor")

    def test_entity_package_all_includes_rules(self) -> None:
        """app.entity.__all__ 应包含 Hit 和 RuleExtractor。"""
        import app.entity as entity_pkg

        assert "Hit" in entity_pkg.__all__
        assert "RuleExtractor" in entity_pkg.__all__
