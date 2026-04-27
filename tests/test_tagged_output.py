"""
tests/test_tagged_output.py — TaggedOutput 和 build_tagged_output 的测试套件

覆盖范围
--------
- 从命中/证据关联构建 TaggedOutput
- theme_ids / entity_type_ids 的稳定排序与去重
- 与 EventDraft 的集成
- 空命中场景
- 导入/导出接口
"""

from __future__ import annotations

import dataclasses
import pytest

from app.entity.rules.extractor import Hit
from app.entity.evidence import EvidenceLink, EvidenceSpan, build_evidence_links
from app.entity.tagged_output import TaggedOutput, build_tagged_output
from app.models.raw_document import RawDocument
from app.models.news_item import NewsItem
from app.models.event_draft import EventDraft


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
    seed: str = "",
) -> Hit:
    return Hit(
        matched_text=matched_text,
        start=start,
        end=end,
        matched_seed=seed or matched_text,
        kind=kind,  # type: ignore[arg-type]
        label_id=label_id,
    )


def _make_link(hit: Hit, text: str) -> EvidenceLink:
    """用最简单方式包装 Hit → EvidenceLink（context_window=0）。"""
    links = build_evidence_links(text, [hit], context_window=0)
    return links[0]


# ---------------------------------------------------------------------------
# 1. 从证据关联构建基本 TaggedOutput
# ---------------------------------------------------------------------------


class TestBuildFromEvidenceLinks:
    """基本构建行为。"""

    def test_returns_tagged_output_instance(self):
        event = _make_event()
        text = "英伟达发布新 GPU，AI 行业关注。"
        hit = _make_hit("GPU", 8, 11, "theme", "gpu")
        link = _make_link(hit, text)

        result = build_tagged_output(event, text, [link])
        assert isinstance(result, TaggedOutput)

    def test_event_is_preserved(self):
        event = _make_event(title="GPU 需求上升")
        text = "GPU 需求大幅上升。"
        hit = _make_hit("GPU", 0, 3, "theme", "gpu")
        link = _make_link(hit, text)

        result = build_tagged_output(event, text, [link])
        assert result.event is event

    def test_text_is_preserved(self):
        event = _make_event()
        text = "英伟达 H100 需求上升。"
        result = build_tagged_output(event, text, [])

        assert result.text == text

    def test_theme_id_extracted_from_theme_hit(self):
        event = _make_event()
        text = "GPU 市场扩大。"
        hit = _make_hit("GPU", 0, 3, "theme", "gpu")
        link = _make_link(hit, text)

        result = build_tagged_output(event, text, [link])
        assert "gpu" in result.theme_ids

    def test_entity_type_id_extracted_from_entity_hit(self):
        event = _make_event()
        text = "英伟达公司发布。"
        hit = _make_hit("英伟达", 0, 3, "entity_type", "company")
        link = _make_link(hit, text)

        result = build_tagged_output(event, text, [link])
        assert "company" in result.entity_type_ids

    def test_theme_hit_does_not_leak_into_entity_type_ids(self):
        event = _make_event()
        text = "GPU 市场扩大。"
        hit = _make_hit("GPU", 0, 3, "theme", "gpu")
        link = _make_link(hit, text)

        result = build_tagged_output(event, text, [link])
        assert result.entity_type_ids == ()

    def test_entity_hit_does_not_leak_into_theme_ids(self):
        event = _make_event()
        text = "英伟达公司发布。"
        hit = _make_hit("英伟达", 0, 3, "entity_type", "company")
        link = _make_link(hit, text)

        result = build_tagged_output(event, text, [link])
        assert result.theme_ids == ()


# ---------------------------------------------------------------------------
# 2. 稳定排序与去重
# ---------------------------------------------------------------------------


class TestSortingAndDeduplication:
    """theme_ids 和 entity_type_ids 应去重并按字母升序排列。"""

    def test_theme_ids_deduped(self):
        event = _make_event()
        text = "GPU 与 GPU 供应链影响半导体行业。"
        # 两条 kind="theme", label_id="gpu" 的命中
        hit1 = _make_hit("GPU", 0, 3, "theme", "gpu")
        hit2 = _make_hit("GPU", 5, 8, "theme", "gpu")
        links = build_evidence_links(text, [hit1, hit2], context_window=0)

        result = build_tagged_output(event, text, links)
        assert result.theme_ids.count("gpu") == 1

    def test_entity_type_ids_deduped(self):
        event = _make_event()
        text = "英伟达与英伟达合并报告。"
        hit1 = _make_hit("英伟达", 0, 3, "entity_type", "company")
        hit2 = _make_hit("英伟达", 4, 7, "entity_type", "company")
        links = build_evidence_links(text, [hit1, hit2], context_window=0)

        result = build_tagged_output(event, text, links)
        assert result.entity_type_ids.count("company") == 1

    def test_theme_ids_sorted_ascending(self):
        event = _make_event()
        text = "半导体和 AI 供应链都涉及 GPU。"
        hits = [
            _make_hit("半导体", 0, 3, "theme", "semiconductor"),
            _make_hit("AI", 4, 6, "theme", "ai"),
            _make_hit("GPU", 14, 17, "theme", "gpu"),
        ]
        links = build_evidence_links(text, hits, context_window=0)

        result = build_tagged_output(event, text, links)
        assert list(result.theme_ids) == sorted(result.theme_ids)

    def test_entity_type_ids_sorted_ascending(self):
        event = _make_event()
        text = "公司与供应链角色协作。"
        hits = [
            _make_hit("公司", 0, 2, "entity_type", "company"),
            _make_hit("角色", 6, 8, "entity_type", "supply_chain_role"),
        ]
        links = build_evidence_links(text, hits, context_window=0)

        result = build_tagged_output(event, text, links)
        assert list(result.entity_type_ids) == sorted(result.entity_type_ids)

    def test_multiple_different_theme_ids_all_present(self):
        event = _make_event()
        text = "GPU 和 AI 同时涉及。"
        hits = [
            _make_hit("GPU", 0, 3, "theme", "gpu"),
            _make_hit("AI", 5, 7, "theme", "ai"),
        ]
        links = build_evidence_links(text, hits, context_window=0)

        result = build_tagged_output(event, text, links)
        assert set(result.theme_ids) == {"gpu", "ai"}

    def test_deterministic_output_same_input(self):
        """相同输入，多次调用结果完全一致。"""
        event = _make_event()
        text = "GPU 和 AI 行业增长，半导体需求旺盛。"
        hits = [
            _make_hit("GPU", 0, 3, "theme", "gpu"),
            _make_hit("AI", 5, 7, "theme", "ai"),
            _make_hit("半导体", 13, 16, "theme", "semiconductor"),
        ]
        links = build_evidence_links(text, hits, context_window=0)

        r1 = build_tagged_output(event, text, links)
        r2 = build_tagged_output(event, text, links)
        assert r1.theme_ids == r2.theme_ids
        assert r1.entity_type_ids == r2.entity_type_ids
        assert r1.evidence_links == r2.evidence_links


# ---------------------------------------------------------------------------
# 3. 证据关联排序
# ---------------------------------------------------------------------------


class TestEvidenceLinksOrdering:
    """evidence_links 应按 (start, end, label_id) 升序排列。"""

    def test_evidence_links_ordered_by_start(self):
        event = _make_event()
        text = "AI 行业需要 GPU 芯片。"
        # 故意逆序传入
        hit_gpu = _make_hit("GPU", 8, 11, "theme", "gpu")
        hit_ai = _make_hit("AI", 0, 2, "theme", "ai")
        links = build_evidence_links(text, [hit_gpu, hit_ai], context_window=0)

        result = build_tagged_output(event, text, links)
        starts = [lnk.hit.start for lnk in result.evidence_links]
        assert starts == sorted(starts)

    def test_evidence_links_ordered_by_label_id_when_same_position(self):
        event = _make_event()
        text = "GPU 相关。"
        # 相同位置，不同 label_id
        hit_b = _make_hit("GPU", 0, 3, "theme", "gpu")
        hit_a = _make_hit("GPU", 0, 3, "theme", "ai")
        links = build_evidence_links(text, [hit_b, hit_a], context_window=0)

        result = build_tagged_output(event, text, links)
        label_ids = [lnk.hit.label_id for lnk in result.evidence_links]
        assert label_ids == sorted(label_ids)

    def test_evidence_links_all_included(self):
        event = _make_event()
        text = "AI 行业需要 GPU 芯片，半导体产能有限。"
        hits = [
            _make_hit("AI", 0, 2, "theme", "ai"),
            _make_hit("GPU", 8, 11, "theme", "gpu"),
            _make_hit("半导体", 14, 17, "theme", "semiconductor"),
        ]
        links = build_evidence_links(text, hits, context_window=0)

        result = build_tagged_output(event, text, links)
        assert len(result.evidence_links) == 3


# ---------------------------------------------------------------------------
# 4. 与 EventDraft 的集成
# ---------------------------------------------------------------------------


class TestEventDraftIntegration:
    """TaggedOutput 应完整保留 EventDraft 的所有字段。"""

    def test_event_title_accessible(self):
        title = "英伟达 GPU 供货缩减"
        event = _make_event(title=title)
        result = build_tagged_output(event, "GPU", [])
        assert result.event.title == title

    def test_event_occurred_at_accessible(self):
        event = _make_event(date="2025-06-15")
        result = build_tagged_output(event, "", [])
        assert result.event.occurred_at == "2025-06-15"

    def test_event_source_items_accessible(self):
        news = _make_news(title="新闻标题")
        event = EventDraft.from_news_item(news)
        result = build_tagged_output(event, "", [])
        assert result.event.source_items[0] is news

    def test_event_metadata_accessible(self):
        news = _make_news()
        event = EventDraft(
            title="test",
            summary=None,
            occurred_at="2025-01-01",
            source_items=[news],
            metadata={"priority": 1},
        )
        result = build_tagged_output(event, "", [])
        assert result.event.metadata["priority"] == 1

    def test_event_summary_accessible(self):
        news = _make_news()
        event = EventDraft(
            title="test",
            summary="英伟达削减 GPU 出货量，AI 行业受影响。",
            occurred_at="2025-01-01",
            source_items=[news],
        )
        result = build_tagged_output(event, "", [])
        assert result.event.summary is not None


# ---------------------------------------------------------------------------
# 5. 空命中场景
# ---------------------------------------------------------------------------


class TestEmptyHits:
    """空证据关联时，TaggedOutput 应返回空元组而非报错。"""

    def test_empty_evidence_links_gives_empty_theme_ids(self):
        event = _make_event()
        result = build_tagged_output(event, "无命中文本", [])
        assert result.theme_ids == ()

    def test_empty_evidence_links_gives_empty_entity_type_ids(self):
        event = _make_event()
        result = build_tagged_output(event, "无命中文本", [])
        assert result.entity_type_ids == ()

    def test_empty_evidence_links_gives_empty_evidence_links(self):
        event = _make_event()
        result = build_tagged_output(event, "无命中文本", [])
        assert result.evidence_links == ()

    def test_empty_text_with_empty_links(self):
        event = _make_event()
        result = build_tagged_output(event, "", [])
        assert result.theme_ids == ()
        assert result.entity_type_ids == ()
        assert result.evidence_links == ()


# ---------------------------------------------------------------------------
# 6. 不可变性（frozen dataclass）
# ---------------------------------------------------------------------------


class TestImmutability:
    """TaggedOutput 为 frozen dataclass，字段赋值应抛出 FrozenInstanceError。"""

    def test_cannot_reassign_event(self):
        event = _make_event()
        result = build_tagged_output(event, "", [])
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.event = _make_event()  # type: ignore[misc]

    def test_cannot_reassign_theme_ids(self):
        event = _make_event()
        result = build_tagged_output(event, "", [])
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.theme_ids = ("gpu",)  # type: ignore[misc]

    def test_cannot_reassign_evidence_links(self):
        event = _make_event()
        result = build_tagged_output(event, "", [])
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.evidence_links = ()  # type: ignore[misc]

    def test_fields_are_tuples_not_lists(self):
        event = _make_event()
        text = "GPU 相关。"
        hit = _make_hit("GPU", 0, 3, "theme", "gpu")
        link = _make_link(hit, text)
        result = build_tagged_output(event, text, [link])

        assert isinstance(result.theme_ids, tuple)
        assert isinstance(result.entity_type_ids, tuple)
        assert isinstance(result.evidence_links, tuple)


# ---------------------------------------------------------------------------
# 7. 与 RuleExtractor 的端到端集成
# ---------------------------------------------------------------------------


class TestEndToEndWithRuleExtractor:
    """通过 RuleExtractor → build_evidence_links → build_tagged_output 的完整流程。"""

    def test_full_pipeline_with_real_extractor(self):
        from app.entity.rules import RuleExtractor

        extractor = RuleExtractor()
        event = _make_event(title="GPU 与 AI 市场分析")
        text = "英伟达 GPU 需求旺盛，AI 和半导体行业共同受益。"

        hits = extractor.extract(text)
        links = build_evidence_links(text, hits)
        result = build_tagged_output(event, text, links)

        assert isinstance(result, TaggedOutput)
        assert result.event is event
        assert result.text == text
        # 至少应命中 gpu、ai、semiconductor 之一
        assert len(result.theme_ids) >= 1
        # evidence_links 数量与 hits 一致
        assert len(result.evidence_links) == len(hits)

    def test_full_pipeline_hit_ids_match_evidence_label_ids(self):
        from app.entity.rules import RuleExtractor

        extractor = RuleExtractor()
        event = _make_event()
        text = "AI 算力需求增加，GPU 产能吃紧。"

        hits = extractor.extract(text)
        links = build_evidence_links(text, hits)
        result = build_tagged_output(event, text, links)

        # evidence_links 中的 theme label_id 集合 == result.theme_ids 集合
        from_links = {lnk.hit.label_id for lnk in result.evidence_links if lnk.hit.kind == "theme"}
        assert from_links == set(result.theme_ids)

    def test_full_pipeline_entity_ids_match_evidence_entity_label_ids(self):
        from app.entity.rules import RuleExtractor

        extractor = RuleExtractor()
        event = _make_event()
        text = "AMD 和英伟达在 GPU 领域竞争激烈。"

        hits = extractor.extract(text)
        links = build_evidence_links(text, hits)
        result = build_tagged_output(event, text, links)

        from_links = {lnk.hit.label_id for lnk in result.evidence_links if lnk.hit.kind == "entity_type"}
        assert from_links == set(result.entity_type_ids)


# ---------------------------------------------------------------------------
# 8. 导入/导出接口
# ---------------------------------------------------------------------------


class TestImportExportSurface:
    """验证公开 API 可以从顶层 app.entity 导入。"""

    def test_tagged_output_importable_from_app_entity(self):
        from app.entity import TaggedOutput as TO  # noqa: F401
        assert TO is TaggedOutput

    def test_build_tagged_output_importable_from_app_entity(self):
        from app.entity import build_tagged_output as bto  # noqa: F401
        assert bto is build_tagged_output

    def test_tagged_output_in_all(self):
        import app.entity as entity_pkg
        assert "TaggedOutput" in entity_pkg.__all__

    def test_build_tagged_output_in_all(self):
        import app.entity as entity_pkg
        assert "build_tagged_output" in entity_pkg.__all__

    def test_direct_module_import(self):
        from app.entity.tagged_output import TaggedOutput as TO, build_tagged_output as bto  # noqa: F401
        assert TO is TaggedOutput
        assert bto is build_tagged_output
