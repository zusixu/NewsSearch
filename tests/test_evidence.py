"""
tests/test_evidence.py — 实体证据关联模块测试

覆盖：
- 合法 Hit 创建 EvidenceLink（主题 / 实体类型）
- snippet / context 行为（含边界截断、context_window=0）
- 非法偏移显式拒绝（负数、越界、end≤start、零长度）
- Hit 身份与数据在 EvidenceLink 中的保留
- 空输入行为
- 导入/导出接口
"""

import pytest

from app.entity.evidence import (
    EvidenceLink,
    EvidenceLinkError,
    EvidenceSpan,
    build_evidence_links,
)
from app.entity.rules.extractor import Hit

# ── 顶层导入路径（app.entity）也要能访问 ────────────────────────────────────
from app.entity import (
    EvidenceLink as EvidenceLinkAlias,
    EvidenceLinkError as EvidenceLinkErrorAlias,
    EvidenceSpan as EvidenceSpanAlias,
    build_evidence_links as build_evidence_links_alias,
)


# ---------------------------------------------------------------------------
# 导入 / 导出接口
# ---------------------------------------------------------------------------


class TestImportSurface:
    def test_direct_imports_available(self):
        assert EvidenceLink is not None
        assert EvidenceSpan is not None
        assert EvidenceLinkError is not None
        assert build_evidence_links is not None

    def test_package_re_exports_match(self):
        assert EvidenceLinkAlias is EvidenceLink
        assert EvidenceSpanAlias is EvidenceSpan
        assert EvidenceLinkErrorAlias is EvidenceLinkError
        assert build_evidence_links_alias is build_evidence_links

    def test_evidence_link_error_is_value_error_subclass(self):
        """EvidenceLinkError 必须继承 ValueError，方便调用方统一捕获。"""
        assert issubclass(EvidenceLinkError, ValueError)


# ---------------------------------------------------------------------------
# EvidenceSpan / EvidenceLink 结构测试
# ---------------------------------------------------------------------------


class TestEvidenceSpanStructure:
    def test_frozen(self):
        span = EvidenceSpan(
            snippet="GPU",
            context_before="最新 ",
            context_after=" 芯片",
            start=3,
            end=6,
        )
        with pytest.raises((AttributeError, TypeError)):
            span.snippet = "CPU"  # type: ignore[misc]

    def test_fields_accessible(self):
        span = EvidenceSpan(
            snippet="GPU",
            context_before="前",
            context_after="后",
            start=1,
            end=4,
        )
        assert span.snippet == "GPU"
        assert span.context_before == "前"
        assert span.context_after == "后"
        assert span.start == 1
        assert span.end == 4


class TestEvidenceLinkStructure:
    def _make_hit(self) -> Hit:
        return Hit(
            matched_text="GPU",
            start=3,
            end=6,
            matched_seed="GPU",
            kind="theme",
            label_id="gpu",
        )

    def test_frozen(self):
        hit = self._make_hit()
        span = EvidenceSpan(snippet="GPU", context_before="", context_after="", start=3, end=6)
        link = EvidenceLink(hit=hit, span=span)
        with pytest.raises((AttributeError, TypeError)):
            link.hit = hit  # type: ignore[misc]

    def test_hit_and_span_preserved(self):
        hit = self._make_hit()
        span = EvidenceSpan(snippet="GPU", context_before="a", context_after="b", start=3, end=6)
        link = EvidenceLink(hit=hit, span=span)
        assert link.hit is hit
        assert link.span is span


# ---------------------------------------------------------------------------
# 合法 Hit → EvidenceLink 创建
# ---------------------------------------------------------------------------

TEXT_EN = "The latest GPU chip is powering AI models worldwide."
# indices:  0123456789...
#  "GPU" starts at index 11, ends at 14

TEXT_ZH = "英伟达发布最新GPU芯片，AI行业高度关注。"
# "GPU" starts at 8, ends at 11 (bytes differ, but Python str is Unicode)


def _hit(text: str, seed: str, kind="theme", label_id="gpu") -> Hit:
    idx = text.find(seed)
    assert idx != -1, f"seed {seed!r} not found in text"
    return Hit(
        matched_text=seed,
        start=idx,
        end=idx + len(seed),
        matched_seed=seed,
        kind=kind,
        label_id=label_id,
    )


class TestValidLinkCreation:
    def test_single_theme_hit_english(self):
        hit = _hit(TEXT_EN, "GPU")
        links = build_evidence_links(TEXT_EN, [hit])
        assert len(links) == 1
        link = links[0]
        assert isinstance(link, EvidenceLink)
        assert isinstance(link.span, EvidenceSpan)

    def test_single_entity_type_hit(self):
        hit = _hit(TEXT_EN, "GPU", kind="entity_type", label_id="product")
        links = build_evidence_links(TEXT_EN, [hit])
        assert len(links) == 1
        assert links[0].hit.kind == "entity_type"

    def test_multiple_hits_returns_same_count(self):
        hit1 = _hit(TEXT_EN, "GPU")
        hit2 = _hit(TEXT_EN, "AI")
        links = build_evidence_links(TEXT_EN, [hit1, hit2])
        assert len(links) == 2

    def test_order_preserved(self):
        hit1 = _hit(TEXT_EN, "GPU")
        hit2 = _hit(TEXT_EN, "AI")
        links = build_evidence_links(TEXT_EN, [hit1, hit2])
        assert links[0].hit is hit1
        assert links[1].hit is hit2

    def test_chinese_text_hit(self):
        hit = _hit(TEXT_ZH, "GPU")
        links = build_evidence_links(TEXT_ZH, [hit])
        assert len(links) == 1
        assert links[0].span.snippet == "GPU"

    def test_hit_at_text_start(self):
        text = "GPU powers everything."
        hit = Hit(matched_text="GPU", start=0, end=3, matched_seed="GPU", kind="theme", label_id="gpu")
        links = build_evidence_links(text, [hit])
        assert links[0].span.snippet == "GPU"
        assert links[0].span.context_before == ""

    def test_hit_at_text_end(self):
        text = "Powered by GPU"
        hit = Hit(matched_text="GPU", start=11, end=14, matched_seed="GPU", kind="theme", label_id="gpu")
        links = build_evidence_links(text, [hit])
        assert links[0].span.snippet == "GPU"
        assert links[0].span.context_after == ""


# ---------------------------------------------------------------------------
# snippet / context 行为
# ---------------------------------------------------------------------------


class TestSnippetAndContext:
    def test_snippet_equals_matched_text(self):
        hit = _hit(TEXT_EN, "GPU")
        links = build_evidence_links(TEXT_EN, [hit])
        assert links[0].span.snippet == hit.matched_text

    def test_span_start_end_match_hit(self):
        hit = _hit(TEXT_EN, "GPU")
        links = build_evidence_links(TEXT_EN, [hit])
        span = links[0].span
        assert span.start == hit.start
        assert span.end == hit.end

    def test_context_before_is_substring_before_snippet(self):
        hit = _hit(TEXT_EN, "GPU")
        links = build_evidence_links(TEXT_EN, [hit], context_window=50)
        span = links[0].span
        # context_before should end exactly where snippet begins
        assert TEXT_EN[hit.start - len(span.context_before) : hit.start] == span.context_before

    def test_context_after_is_substring_after_snippet(self):
        hit = _hit(TEXT_EN, "GPU")
        links = build_evidence_links(TEXT_EN, [hit], context_window=50)
        span = links[0].span
        assert TEXT_EN[hit.end : hit.end + len(span.context_after)] == span.context_after

    def test_context_window_zero_gives_empty_context(self):
        hit = _hit(TEXT_EN, "GPU")
        links = build_evidence_links(TEXT_EN, [hit], context_window=0)
        span = links[0].span
        assert span.context_before == ""
        assert span.context_after == ""
        assert span.snippet == "GPU"

    def test_context_window_truncated_at_text_boundary(self):
        text = "GPU"
        hit = Hit(matched_text="GPU", start=0, end=3, matched_seed="GPU", kind="theme", label_id="gpu")
        links = build_evidence_links(text, [hit], context_window=100)
        span = links[0].span
        assert span.context_before == ""
        assert span.context_after == ""

    def test_context_window_one(self):
        text = "XGPUY"
        # "GPU" at index 1..4
        hit = Hit(matched_text="GPU", start=1, end=4, matched_seed="GPU", kind="theme", label_id="gpu")
        links = build_evidence_links(text, [hit], context_window=1)
        span = links[0].span
        assert span.context_before == "X"
        assert span.context_after == "Y"

    def test_large_context_window_does_not_overflow(self):
        text = "Short GPU text"
        hit = _hit(text, "GPU")
        links = build_evidence_links(text, [hit], context_window=9999)
        span = links[0].span
        assert span.context_before == text[: hit.start]
        assert span.context_after == text[hit.end :]

    def test_default_context_window_is_50(self):
        # Build a text where we can verify window=50 behavior
        prefix = "A" * 60
        suffix = "B" * 60
        text = prefix + "GPU" + suffix
        hit = Hit(
            matched_text="GPU",
            start=60,
            end=63,
            matched_seed="GPU",
            kind="theme",
            label_id="gpu",
        )
        links = build_evidence_links(text, [hit])  # default window=50
        span = links[0].span
        assert len(span.context_before) == 50
        assert len(span.context_after) == 50


# ---------------------------------------------------------------------------
# Hit 身份与数据保留
# ---------------------------------------------------------------------------


class TestHitIdentityPreservation:
    def test_hit_object_identity_preserved(self):
        hit = _hit(TEXT_EN, "GPU")
        links = build_evidence_links(TEXT_EN, [hit])
        assert links[0].hit is hit  # same object, not a copy

    def test_hit_all_fields_accessible_through_link(self):
        hit = Hit(
            matched_text="NVIDIA",
            start=4,
            end=10,
            matched_seed="NVIDIA",
            kind="entity_type",
            label_id="company",
        )
        text = "The NVIDIA chip..."
        links = build_evidence_links(text, [hit])
        lh = links[0].hit
        assert lh.matched_text == "NVIDIA"
        assert lh.start == 4
        assert lh.end == 10
        assert lh.matched_seed == "NVIDIA"
        assert lh.kind == "entity_type"
        assert lh.label_id == "company"

    def test_multiple_hits_each_link_references_correct_hit(self):
        text = "GPU and AI are trending."
        hit_gpu = _hit(text, "GPU")
        hit_ai = _hit(text, "AI")
        links = build_evidence_links(text, [hit_gpu, hit_ai])
        assert links[0].hit is hit_gpu
        assert links[1].hit is hit_ai


# ---------------------------------------------------------------------------
# 空输入行为
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_hits_list_returns_empty(self):
        result = build_evidence_links("some text", [])
        assert result == []

    def test_empty_hits_with_empty_text_returns_empty(self):
        result = build_evidence_links("", [])
        assert result == []

    def test_non_empty_hits_with_empty_text_raises(self):
        hit = Hit(matched_text="x", start=0, end=1, matched_seed="x", kind="theme", label_id="ai")
        with pytest.raises(EvidenceLinkError):
            build_evidence_links("", [hit])


# ---------------------------------------------------------------------------
# 非法偏移显式拒绝
# ---------------------------------------------------------------------------


class TestInvalidOffsetsRejected:
    TEXT = "Hello GPU world"

    def _hit(self, start: int, end: int) -> Hit:
        # matched_text does not matter for offset validation tests
        return Hit(
            matched_text="x",
            start=start,
            end=end,
            matched_seed="x",
            kind="theme",
            label_id="gpu",
        )

    def test_negative_start_raises(self):
        with pytest.raises(EvidenceLinkError, match="start"):
            build_evidence_links(self.TEXT, [self._hit(-1, 3)])

    def test_negative_end_raises(self):
        with pytest.raises(EvidenceLinkError, match="end"):
            build_evidence_links(self.TEXT, [self._hit(0, -1)])

    def test_end_equals_start_raises(self):
        with pytest.raises(EvidenceLinkError):
            build_evidence_links(self.TEXT, [self._hit(3, 3)])

    def test_end_less_than_start_raises(self):
        with pytest.raises(EvidenceLinkError):
            build_evidence_links(self.TEXT, [self._hit(5, 2)])

    def test_start_beyond_text_length_raises(self):
        with pytest.raises(EvidenceLinkError, match="start"):
            build_evidence_links(self.TEXT, [self._hit(len(self.TEXT), len(self.TEXT) + 1)])

    def test_end_beyond_text_length_raises(self):
        with pytest.raises(EvidenceLinkError, match="end"):
            build_evidence_links(self.TEXT, [self._hit(0, len(self.TEXT) + 1)])

    def test_valid_span_exactly_at_last_char(self):
        # end == len(text) is valid (exclusive end)
        text = "GPU"
        hit = Hit(matched_text="GPU", start=0, end=3, matched_seed="GPU", kind="theme", label_id="gpu")
        links = build_evidence_links(text, [hit])
        assert len(links) == 1

    def test_first_hit_valid_second_invalid_raises(self):
        """验证即使第一个 Hit 合法，遇到非法 Hit 也必须抛出异常。"""
        text = "GPU"
        good = Hit(matched_text="GPU", start=0, end=3, matched_seed="GPU", kind="theme", label_id="gpu")
        bad = Hit(matched_text="x", start=0, end=99, matched_seed="x", kind="theme", label_id="gpu")
        with pytest.raises(EvidenceLinkError):
            build_evidence_links(text, [good, bad])

    def test_negative_context_window_raises_value_error(self):
        hit = _hit(TEXT_EN, "GPU")
        with pytest.raises(ValueError):
            build_evidence_links(TEXT_EN, [hit], context_window=-1)
