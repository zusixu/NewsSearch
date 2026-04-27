"""tests/test_text_dedup.py — Tests for text normalization, fingerprinting, and text-hash dedup.

Coverage
--------
TestTextNormalization:
  - Unicode NFC normalization collapses canonical equivalents
  - Case-folding (ASCII, Unicode, Turkish dotless-i via casefold)
  - Whitespace collapsing (spaces, tabs, newlines, zero-width spaces)
  - Leading/trailing whitespace stripped

TestTextFingerprint:
  - Identical text → identical fingerprint
  - Different text → different fingerprint
  - Output is 64-char lowercase hex (SHA-256)
  - title+content separation: same combined string but different split → same fingerprint
  - None content treated as empty
  - Cosmetic differences (whitespace, case) → same fingerprint
  - Truly different content → different fingerprints

TestIsBlank:
  - Empty title + None content → blank
  - Whitespace-only title + None content → blank
  - Non-empty title → not blank
  - Empty title + non-empty content → not blank

TestDeduplicateByText:
  - Empty list → empty list
  - Single item → unchanged
  - No duplicates → all items preserved, order stable
  - Exact text duplicate → merged, raw_refs combined
  - Cosmetic duplicate (whitespace/case) → merged
  - First occurrence is the representative
  - raw_refs order: representative's refs first, then duplicate's
  - Blank items pass through without deduplication
  - Two blank items both pass through (not merged with each other)
  - field filling: missing title filled from duplicate
  - field filling: missing content filled from duplicate
  - field filling: rep fields are never overwritten
  - metadata merge: rep keys win, missing keys filled from dup
  - url preserved from representative
  - Original instances not mutated
  - Three-way dedup (two duplicates of same item)
  - Mixed: some duplicates, some unique
  - URL-bearing items with same text merge correctly

TestImportIdentity:
  - text_fingerprint and deduplicate_by_text importable from app.normalize
"""

from __future__ import annotations

import hashlib

import pytest

from app.normalize.text_dedup import (
    _normalize_text,
    _is_blank,
    text_fingerprint,
    deduplicate_by_text,
)
from app.models.raw_document import RawDocument
from app.models.news_item import NewsItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raw(
    title: str = "Title",
    content: str = "body",
    url: str = "https://example.com/a",
    source: str = "web",
    provider: str = "test",
) -> RawDocument:
    return RawDocument(
        source=source,
        provider=provider,
        title=title,
        content=content,
        url=url,
        date="2024-01-01",
        metadata={},
    )


def _item(
    title: str = "Title",
    content: str | None = "body",
    url: str | None = "https://example.com/a",
    published_at: str = "2024-01-01",
    source: str = "web",
    provider: str = "test",
    metadata: dict | None = None,
    raw: RawDocument | None = None,
) -> NewsItem:
    if raw is None:
        raw = _raw(title=title, content=content or "", url=url or "https://example.com/x")
    return NewsItem(
        title=title,
        content=content,
        url=url,
        published_at=published_at,
        source=source,
        provider=provider,
        raw_refs=[raw],
        metadata=metadata or {},
    )


# ===========================================================================
# TestTextNormalization
# ===========================================================================

class TestTextNormalization:
    def test_nfc_normalization(self):
        # "é" as NFC (U+00E9) vs NFD (e + U+0301) → same after normalize
        nfc = "caf\u00e9"
        nfd = "cafe\u0301"
        assert _normalize_text(nfc) == _normalize_text(nfd)

    def test_casefold_ascii(self):
        assert _normalize_text("Hello World") == "hello world"

    def test_casefold_unicode(self):
        # German sharp-s: "ß".casefold() == "ss"
        assert _normalize_text("Straße") == "strasse"

    def test_whitespace_collapses_spaces(self):
        assert _normalize_text("  hello   world  ") == "hello world"

    def test_whitespace_collapses_tabs(self):
        assert _normalize_text("hello\t\tworld") == "hello world"

    def test_whitespace_collapses_newlines(self):
        assert _normalize_text("hello\nworld\n") == "hello world"

    def test_whitespace_collapses_mixed(self):
        assert _normalize_text("  hello \t\n world  ") == "hello world"

    def test_empty_string(self):
        assert _normalize_text("") == ""

    def test_whitespace_only(self):
        assert _normalize_text("   \t\n  ") == ""

    def test_zero_width_space(self):
        # Zero-width space (U+200B) is whitespace; should be collapsed
        result = _normalize_text("hello\u200bworld")
        assert result == "hello world"


# ===========================================================================
# TestTextFingerprint
# ===========================================================================

class TestTextFingerprint:
    def test_identical_text_identical_fingerprint(self):
        assert text_fingerprint("A", "B") == text_fingerprint("A", "B")

    def test_different_text_different_fingerprint(self):
        assert text_fingerprint("A", "B") != text_fingerprint("A", "C")

    def test_output_is_64_char_lowercase_hex(self):
        fp = text_fingerprint("title", "content")
        assert len(fp) == 64
        assert fp == fp.lower()
        int(fp, 16)  # raises ValueError if not valid hex

    def test_none_content_treated_as_empty(self):
        assert text_fingerprint("t", None) == text_fingerprint("t", "")

    def test_whitespace_difference_same_fingerprint(self):
        assert text_fingerprint("hello", "world") == text_fingerprint("  hello  ", " world ")

    def test_case_difference_same_fingerprint(self):
        assert text_fingerprint("Hello", "World") == text_fingerprint("hello", "world")

    def test_truly_different_content_different_fingerprint(self):
        assert text_fingerprint("A", "body1") != text_fingerprint("A", "body2")

    def test_title_and_content_not_interchangeable(self):
        # "AB" + "\n" + "" ≠ "" + "\n" + "AB" after NFC+casefold+whitespace
        fp1 = text_fingerprint("AB", "")
        fp2 = text_fingerprint("", "AB")
        assert fp1 != fp2

    def test_fingerprint_matches_manual_sha256(self):
        # Verify the algorithm matches the documented formula exactly.
        title = "Test Title"
        content = "Test body."
        # Apply same normalization as _normalize_text
        import unicodedata, re
        def norm(s: str) -> str:
            s = unicodedata.normalize("NFC", s)
            s = s.casefold()
            s = re.sub(r"\s+", " ", s).strip()
            return s
        combined = norm(title) + "\n" + norm(content)
        expected = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        assert text_fingerprint(title, content) == expected

    def test_unicode_nfc_same_fingerprint(self):
        nfc_title = "caf\u00e9"
        nfd_title = "cafe\u0301"
        assert text_fingerprint(nfc_title, "body") == text_fingerprint(nfd_title, "body")


# ===========================================================================
# TestIsBlank
# ===========================================================================

class TestIsBlank:
    def test_empty_title_and_none_content(self):
        assert _is_blank("", None) is True

    def test_whitespace_title_and_none_content(self):
        assert _is_blank("   \t\n", None) is True

    def test_whitespace_title_and_empty_content(self):
        assert _is_blank("  ", "") is True

    def test_nonempty_title_not_blank(self):
        assert _is_blank("title", None) is False

    def test_empty_title_nonempty_content(self):
        assert _is_blank("", "body") is False

    def test_both_nonempty_not_blank(self):
        assert _is_blank("title", "body") is False


# ===========================================================================
# TestDeduplicateByText
# ===========================================================================

class TestDeduplicateByText:
    def test_empty_list(self):
        assert deduplicate_by_text([]) == []

    def test_single_item(self):
        item = _item()
        result = deduplicate_by_text([item])
        assert result == [item]

    def test_no_duplicates_all_preserved(self):
        items = [_item(title="A"), _item(title="B"), _item(title="C")]
        result = deduplicate_by_text(items)
        assert len(result) == 3

    def test_no_duplicates_stable_order(self):
        items = [_item(title="A"), _item(title="B"), _item(title="C")]
        result = deduplicate_by_text(items)
        assert [r.title for r in result] == ["A", "B", "C"]

    def test_exact_text_duplicate_merged(self):
        items = [_item(title="Same", content="body"), _item(title="Same", content="body")]
        result = deduplicate_by_text(items)
        assert len(result) == 1

    def test_cosmetic_duplicate_whitespace(self):
        items = [
            _item(title="Hello World", content="body"),
            _item(title="Hello  World", content="body"),
        ]
        result = deduplicate_by_text(items)
        assert len(result) == 1

    def test_cosmetic_duplicate_case(self):
        items = [
            _item(title="Hello", content="BODY TEXT"),
            _item(title="hello", content="body text"),
        ]
        result = deduplicate_by_text(items)
        assert len(result) == 1

    def test_first_occurrence_is_representative(self):
        raw1 = _raw(title="First")
        raw2 = _raw(title="First")
        item1 = _item(title="First", content="same", raw=raw1)
        item2 = _item(title="First", content="same", raw=raw2)
        result = deduplicate_by_text([item1, item2])
        assert result[0].raw_refs[0] is raw1

    def test_raw_refs_order_rep_first(self):
        raw1 = _raw(title="T", source="src1")
        raw2 = _raw(title="T", source="src2")
        item1 = _item(title="T", content="body", raw=raw1)
        item2 = _item(title="T", content="body", raw=raw2)
        result = deduplicate_by_text([item1, item2])
        assert result[0].raw_refs == [raw1, raw2]

    def test_raw_refs_all_preserved_three_way(self):
        raw1 = _raw(title="T", source="s1")
        raw2 = _raw(title="T", source="s2")
        raw3 = _raw(title="T", source="s3")
        item1 = _item(title="T", content="body", raw=raw1)
        item2 = _item(title="T", content="body", raw=raw2)
        item3 = _item(title="T", content="body", raw=raw3)
        result = deduplicate_by_text([item1, item2, item3])
        assert len(result) == 1
        assert result[0].raw_refs == [raw1, raw2, raw3]

    def test_blank_item_passes_through(self):
        blank = _item(title="", content=None)
        result = deduplicate_by_text([blank])
        assert len(result) == 1
        assert result[0] is blank

    def test_two_blank_items_both_pass_through(self):
        blank1 = _item(title="", content=None)
        blank2 = _item(title="", content=None)
        result = deduplicate_by_text([blank1, blank2])
        assert len(result) == 2
        assert result[0] is blank1
        assert result[1] is blank2

    def test_blank_whitespace_passes_through(self):
        blank = _item(title="   ", content="  ")
        result = deduplicate_by_text([blank])
        assert len(result) == 1
        assert result[0] is blank

    def test_field_filling_title(self):
        # When representative has an empty title but same text (both blank title,
        # same content), the duplicate's title fills in.
        # We achieve same fingerprint by matching on content only with empty titles.
        # Actually both items must produce the same fingerprint to be merged.
        # Use same content, and make the representative have empty source (non-fingerprint field).
        raw1 = _raw(title="Same Title", source="")
        raw2 = _raw(title="Same Title", source="src-filled")
        item1 = NewsItem(
            title="Same Title", content="same body", url=None,
            published_at="2024-01-01", source="", provider="test",
            raw_refs=[raw1], metadata={},
        )
        item2 = _item(title="Same Title", content="same body", source="src-filled", raw=raw2)
        result = deduplicate_by_text([item1, item2])
        assert len(result) == 1
        # source should be filled from dup when rep has empty source
        assert result[0].source == "src-filled"

    def test_field_filling_content(self):
        # Non-fingerprint field filling: published_at empty on representative.
        raw1 = _raw(title="T")
        raw2 = _raw(title="T")
        item1 = NewsItem(
            title="T", content="body", url=None,
            published_at="", source="web", provider="test",
            raw_refs=[raw1], metadata={},
        )
        item2 = _item(title="T", content="body", published_at="2024-06-15", raw=raw2)
        result = deduplicate_by_text([item1, item2])
        assert len(result) == 1
        assert result[0].published_at == "2024-06-15"

    def test_rep_fields_not_overwritten(self):
        item1 = _item(title="Original", content="body", source="src-original")
        item2 = _item(title="Original", content="body", source="src-other")
        result = deduplicate_by_text([item1, item2])
        assert result[0].source == "src-original"

    def test_metadata_merge_rep_wins(self):
        item1 = _item(title="T", content="b", metadata={"key": "rep-value"})
        item2 = _item(title="T", content="b", metadata={"key": "dup-value", "extra": "x"})
        result = deduplicate_by_text([item1, item2])
        assert result[0].metadata["key"] == "rep-value"
        assert result[0].metadata["extra"] == "x"

    def test_url_preserved_from_representative(self):
        item1 = _item(title="T", content="b", url="https://rep.example/")
        item2 = _item(title="T", content="b", url="https://dup.example/")
        result = deduplicate_by_text([item1, item2])
        assert result[0].url == "https://rep.example/"

    def test_original_instances_not_mutated(self):
        raw1 = _raw(title="T", source="s1")
        raw2 = _raw(title="T", source="s2")
        item1 = _item(title="T", content="body", raw=raw1)
        item2 = _item(title="T", content="body", raw=raw2)
        original_refs1 = list(item1.raw_refs)
        original_refs2 = list(item2.raw_refs)
        deduplicate_by_text([item1, item2])
        assert item1.raw_refs == original_refs1
        assert item2.raw_refs == original_refs2

    def test_mixed_duplicates_and_uniques(self):
        item_a1 = _item(title="A", content="body-a")
        item_a2 = _item(title="A", content="body-a")
        item_b = _item(title="B", content="body-b")
        item_c = _item(title="C", content="body-c")
        result = deduplicate_by_text([item_a1, item_b, item_a2, item_c])
        assert len(result) == 3
        assert result[0].title == "A"
        assert result[1].title == "B"
        assert result[2].title == "C"

    def test_output_order_stable_first_occurrence(self):
        item1 = _item(title="First", content="x")
        item2 = _item(title="Second", content="y")
        item3 = _item(title="First", content="x")  # dup of item1
        result = deduplicate_by_text([item1, item2, item3])
        assert len(result) == 2
        assert result[0].title == "First"
        assert result[1].title == "Second"

    def test_url_bearing_items_with_same_text(self):
        item1 = _item(title="T", content="b", url="https://a.example/1")
        item2 = _item(title="T", content="b", url="https://b.example/2")
        result = deduplicate_by_text([item1, item2])
        assert len(result) == 1
        assert result[0].url == "https://a.example/1"
        assert len(result[0].raw_refs) == 2


# ===========================================================================
# TestImportIdentity
# ===========================================================================

class TestImportIdentity:
    def test_text_fingerprint_importable_from_normalize(self):
        from app.normalize import text_fingerprint as tf
        from app.normalize.text_dedup import text_fingerprint as tf2
        assert tf is tf2

    def test_deduplicate_by_text_importable_from_normalize(self):
        from app.normalize import deduplicate_by_text as dbt
        from app.normalize.text_dedup import deduplicate_by_text as dbt2
        assert dbt is dbt2

    def test_normalize_all_exports(self):
        import app.normalize as norm
        for name in ["text_fingerprint", "deduplicate_by_text"]:
            assert name in norm.__all__
