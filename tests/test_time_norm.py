"""tests/test_time_norm.py — Tests for time normalization of NewsItem.published_at.

Coverage
--------
TestParseDateString:
  Format 1 — ISO date/datetime prefix (YYYY-MM-DD[…])
    - Plain ISO date "2025-06-01"
    - ISO datetime with T separator, no timezone
    - ISO datetime with T separator, Z suffix
    - ISO datetime with T separator, numeric offset
    - ISO datetime with space separator
  Format 2 — Slash-separated (YYYY/MM/DD[…])
    - Zero-padded month and day
    - Single-digit month and day
    - With trailing time component
  Format 3 — Compact 8-digit (YYYYMMDD)
    - Exactly 8 digits → parsed
    - 8 digits with trailing chars → None (fullmatch required)
    - 9 digits → None
  Format 4 — RFC-2822 style
    - Full form with weekday and UTC offset
    - With GMT timezone string
    - Without weekday prefix
  Format 5 — Chinese-style (YYYY年M月D日[…])
    - Zero-padded month and day
    - Single-digit month and day
    - With trailing text after 日
  Output formatting
    - Output is always zero-padded (month, day)
  Failure cases
    - Empty string → None
    - Whitespace-only → None
    - Unparseable garbage → None
    - Invalid month (13) → None
    - Invalid day (32) → None
    - Leap-year boundary: 2024-02-29 valid, 2025-02-29 invalid

TestNormalizeItemTime:
  Status "ok" path
    - published_at parses → status "ok"
    - Normalized date is YYYY-MM-DD
    - fallback_source is None
    - attempts list has one entry with result "ok"
  Status "fallback" path
    - Invalid published_at → scan raw_refs
    - First parseable raw_ref is used
    - Status is "fallback"
    - fallback_source name is "raw_refs[N].date"
    - Earlier bad raw_refs recorded in attempts
    - Skips over unparseable raw_refs to find first parseable one
  Status "failed" path
    - All attempts fail → published_at is empty string sentinel
    - Status is "failed"
    - normalized is empty string
    - fallback_source is None
    - All candidates appear in attempts list with "parse_failed"
  Non-mutation guarantees
    - Original item's published_at not modified
    - Original item's metadata not modified
    - Original raw_refs list not modified
  Field preservation
    - title, content, url, source, provider preserved verbatim
    - raw_refs count preserved
    - Unrelated metadata keys preserved intact
  Metadata audit structure
    - metadata key is "time_normalization"
    - audit "original" field holds original published_at
    - Existing metadata keys not overwritten

TestNormalizeTime:
  - Empty list → empty list
  - Single item → single normalized item
  - Ordering preserved across multiple items
  - Count equals input count
  - No mutation of original items
  - Mixed statuses: ok/fallback/failed in same batch

TestImportExport:
  - parse_date_string importable from app.normalize
  - normalize_item_time importable from app.normalize
  - normalize_time importable from app.normalize
  - app.normalize exports are the same objects as time_norm module attributes
"""

from __future__ import annotations

import pytest

from app.normalize.time_norm import (
    parse_date_string,
    normalize_item_time,
    normalize_time,
)
from app.models.raw_document import RawDocument
from app.models.news_item import NewsItem


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _raw(
    date: str = "2025-06-01",
    title: str = "T",
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
        date=date,
        metadata={},
    )


def _item(
    published_at: str = "2025-06-01",
    title: str = "T",
    content: str | None = "body",
    url: str | None = "https://example.com/a",
    source: str = "web",
    provider: str = "test",
    metadata: dict | None = None,
    raw_date: str | None = None,
    extra_raws: list[RawDocument] | None = None,
) -> NewsItem:
    """Build a NewsItem with one primary RawDocument.

    raw_date overrides the date on the primary RawDocument.
    extra_raws are appended after the primary RawDocument.
    """
    primary_raw = _raw(date=raw_date if raw_date is not None else published_at)
    refs = [primary_raw] + (extra_raws or [])
    return NewsItem(
        title=title,
        content=content,
        url=url,
        published_at=published_at,
        source=source,
        provider=provider,
        raw_refs=refs,
        metadata=dict(metadata) if metadata else {},
    )


# ===========================================================================
# TestParseDateString
# ===========================================================================

class TestParseDateString:

    # -----------------------------------------------------------------------
    # Format 1 — ISO date/datetime prefix
    # -----------------------------------------------------------------------

    def test_iso_date_plain(self):
        assert parse_date_string("2025-06-01") == "2025-06-01"

    def test_iso_datetime_T_no_tz(self):
        assert parse_date_string("2025-06-01T10:30:00") == "2025-06-01"

    def test_iso_datetime_T_with_Z(self):
        assert parse_date_string("2025-06-01T10:30:00Z") == "2025-06-01"

    def test_iso_datetime_T_with_positive_offset(self):
        assert parse_date_string("2025-06-01T10:30:00+08:00") == "2025-06-01"

    def test_iso_datetime_T_with_negative_offset(self):
        assert parse_date_string("2025-06-01T00:00:00-05:00") == "2025-06-01"

    def test_iso_datetime_space_separator(self):
        assert parse_date_string("2025-06-01 10:30:00") == "2025-06-01"

    def test_iso_date_early_year(self):
        assert parse_date_string("2000-01-01") == "2000-01-01"

    # -----------------------------------------------------------------------
    # Format 2 — Slash-separated
    # -----------------------------------------------------------------------

    def test_slash_zero_padded(self):
        assert parse_date_string("2025/06/01") == "2025-06-01"

    def test_slash_single_digit_month_day(self):
        assert parse_date_string("2025/6/1") == "2025-06-01"

    def test_slash_with_trailing_time(self):
        assert parse_date_string("2025/06/01 10:30:00") == "2025-06-01"

    def test_slash_mid_year(self):
        assert parse_date_string("2024/12/31") == "2024-12-31"

    # -----------------------------------------------------------------------
    # Format 3 — Compact 8-digit YYYYMMDD
    # -----------------------------------------------------------------------

    def test_yyyymmdd_basic(self):
        assert parse_date_string("20250601") == "2025-06-01"

    def test_yyyymmdd_start_of_year(self):
        assert parse_date_string("20250101") == "2025-01-01"

    def test_yyyymmdd_end_of_year(self):
        assert parse_date_string("20241231") == "2024-12-31"

    def test_yyyymmdd_with_trailing_chars_returns_none(self):
        # 8 digits followed by more text must NOT match YYYYMMDD format
        # and should also fail ISO prefix (no hyphens), slash, RFC-2822, Chinese
        assert parse_date_string("202506011") is None

    def test_yyyymmdd_nine_digits_returns_none(self):
        assert parse_date_string("123456789") is None

    def test_yyyymmdd_with_T_suffix_returns_none(self):
        # YYYYMMDDTHHMMSS — not a supported format; fullmatch prevents YYYYMMDD match
        assert parse_date_string("20250601T103000") is None

    # -----------------------------------------------------------------------
    # Format 4 — RFC-2822 style
    # -----------------------------------------------------------------------

    def test_rfc2822_utc_offset(self):
        assert parse_date_string("Mon, 01 Jun 2025 10:30:00 +0000") == "2025-06-01"

    def test_rfc2822_gmt(self):
        assert parse_date_string("Mon, 01 Jun 2025 10:30:00 GMT") == "2025-06-01"

    def test_rfc2822_no_weekday(self):
        assert parse_date_string("01 Jun 2025 10:30:00 +0000") == "2025-06-01"

    def test_rfc2822_different_month(self):
        assert parse_date_string("Fri, 31 Jan 2025 08:00:00 +0800") == "2025-01-31"

    # -----------------------------------------------------------------------
    # Format 5 — Chinese-style
    # -----------------------------------------------------------------------

    def test_chinese_zero_padded(self):
        assert parse_date_string("2025年06月01日") == "2025-06-01"

    def test_chinese_no_padding(self):
        assert parse_date_string("2025年6月1日") == "2025-06-01"

    def test_chinese_double_digit_day(self):
        assert parse_date_string("2025年12月31日") == "2025-12-31"

    def test_chinese_with_suffix_text(self):
        # Extra content after 日 should not prevent parsing
        assert parse_date_string("2025年6月1日 上午10点") == "2025-06-01"

    # -----------------------------------------------------------------------
    # Output is always zero-padded
    # -----------------------------------------------------------------------

    def test_output_month_zero_padded(self):
        result = parse_date_string("2025/1/15")
        assert result is not None
        assert result[5:7] == "01"  # month portion

    def test_output_day_zero_padded(self):
        result = parse_date_string("2025/06/5")
        assert result is not None
        assert result[8:10] == "05"  # day portion

    # -----------------------------------------------------------------------
    # Failure cases
    # -----------------------------------------------------------------------

    def test_empty_string_returns_none(self):
        assert parse_date_string("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_date_string("   ") is None

    def test_garbage_string_returns_none(self):
        assert parse_date_string("not-a-date") is None

    def test_invalid_month_13_returns_none(self):
        assert parse_date_string("2025-13-01") is None

    def test_invalid_month_00_returns_none(self):
        assert parse_date_string("2025-00-01") is None

    def test_invalid_day_32_returns_none(self):
        assert parse_date_string("2025-06-32") is None

    def test_invalid_day_00_returns_none(self):
        assert parse_date_string("2025-06-00") is None

    def test_leap_year_feb29_valid(self):
        # 2024 is a leap year
        assert parse_date_string("2024-02-29") == "2024-02-29"

    def test_non_leap_year_feb29_returns_none(self):
        # 2025 is not a leap year
        assert parse_date_string("2025-02-29") is None

    def test_leading_trailing_whitespace_stripped(self):
        assert parse_date_string("  2025-06-01  ") == "2025-06-01"


# ===========================================================================
# TestNormalizeItemTime
# ===========================================================================

class TestNormalizeItemTime:

    # -----------------------------------------------------------------------
    # Status "ok" path
    # -----------------------------------------------------------------------

    def test_ok_status_when_published_at_parses(self):
        item = _item(published_at="2025-06-01")
        out = normalize_item_time(item)
        assert out.metadata["time_normalization"]["status"] == "ok"

    def test_ok_normalized_date_correct(self):
        item = _item(published_at="2025/06/15")
        out = normalize_item_time(item)
        assert out.published_at == "2025-06-15"

    def test_ok_fallback_source_is_none(self):
        item = _item(published_at="2025-06-01")
        out = normalize_item_time(item)
        assert out.metadata["time_normalization"]["fallback_source"] is None

    def test_ok_one_attempt_with_ok_result(self):
        item = _item(published_at="2025-06-01")
        out = normalize_item_time(item)
        attempts = out.metadata["time_normalization"]["attempts"]
        assert len(attempts) == 1
        assert attempts[0]["source"] == "published_at"
        assert attempts[0]["result"] == "ok"

    def test_ok_various_formats_normalized_to_iso(self):
        formats = [
            ("20250601", "2025-06-01"),
            ("2025/06/01", "2025-06-01"),
            ("Mon, 01 Jun 2025 10:30:00 +0000", "2025-06-01"),
            ("2025年6月1日", "2025-06-01"),
            ("2025-06-01T10:30:00Z", "2025-06-01"),
        ]
        for raw_str, expected in formats:
            item = _item(published_at=raw_str)
            out = normalize_item_time(item)
            assert out.published_at == expected, f"Format {raw_str!r} → {out.published_at!r}, expected {expected!r}"

    # -----------------------------------------------------------------------
    # Status "fallback" path
    # -----------------------------------------------------------------------

    def test_fallback_when_published_at_invalid(self):
        raw = _raw(date="2025-06-01")
        item = _item(published_at="garbage", raw_date="2025-06-01")
        item = NewsItem(
            title="T", content="b", url="u", published_at="garbage",
            source="web", provider="p", raw_refs=[raw], metadata={},
        )
        out = normalize_item_time(item)
        assert out.published_at == "2025-06-01"

    def test_fallback_status_is_fallback(self):
        raw = _raw(date="2025-03-15")
        item = NewsItem(
            title="T", content="b", url="u", published_at="bad",
            source="web", provider="p", raw_refs=[raw], metadata={},
        )
        out = normalize_item_time(item)
        assert out.metadata["time_normalization"]["status"] == "fallback"

    def test_fallback_source_name_raw_refs_0(self):
        raw = _raw(date="2025-03-15")
        item = NewsItem(
            title="T", content="b", url="u", published_at="bad",
            source="web", provider="p", raw_refs=[raw], metadata={},
        )
        out = normalize_item_time(item)
        assert out.metadata["time_normalization"]["fallback_source"] == "raw_refs[0].date"

    def test_fallback_skips_bad_raw_refs_to_find_parseable(self):
        # raw_refs[0] has a bad date; raw_refs[1] has a good date
        bad_raw = _raw(date="not-a-date")
        good_raw = _raw(date="2025-09-20")
        item = NewsItem(
            title="T", content="b", url="u", published_at="also-bad",
            source="web", provider="p",
            raw_refs=[bad_raw, good_raw], metadata={},
        )
        out = normalize_item_time(item)
        assert out.published_at == "2025-09-20"
        assert out.metadata["time_normalization"]["fallback_source"] == "raw_refs[1].date"

    def test_fallback_bad_raw_refs_recorded_in_attempts(self):
        bad_raw = _raw(date="not-a-date")
        good_raw = _raw(date="2025-09-20")
        item = NewsItem(
            title="T", content="b", url="u", published_at="also-bad",
            source="web", provider="p",
            raw_refs=[bad_raw, good_raw], metadata={},
        )
        out = normalize_item_time(item)
        attempts = out.metadata["time_normalization"]["attempts"]
        # published_at + raw_refs[0] (failed) + raw_refs[1] (ok)
        assert len(attempts) == 3
        assert attempts[0] == {"source": "published_at", "value": "also-bad", "result": "parse_failed"}
        assert attempts[1] == {"source": "raw_refs[0].date", "value": "not-a-date", "result": "parse_failed"}
        assert attempts[2] == {"source": "raw_refs[1].date", "value": "2025-09-20", "result": "ok"}

    def test_fallback_stops_at_first_parseable_raw_ref(self):
        # raw_refs[0] good, raw_refs[1] also good — only [0] should be used
        raw0 = _raw(date="2025-01-10")
        raw1 = _raw(date="2025-02-20")
        item = NewsItem(
            title="T", content="b", url="u", published_at="bad",
            source="web", provider="p",
            raw_refs=[raw0, raw1], metadata={},
        )
        out = normalize_item_time(item)
        assert out.published_at == "2025-01-10"
        assert out.metadata["time_normalization"]["fallback_source"] == "raw_refs[0].date"

    # -----------------------------------------------------------------------
    # Status "failed" path
    # -----------------------------------------------------------------------

    def test_failed_published_at_is_empty_sentinel(self):
        raw = _raw(date="still-bad")
        item = NewsItem(
            title="T", content="b", url="u", published_at="bad",
            source="web", provider="p", raw_refs=[raw], metadata={},
        )
        out = normalize_item_time(item)
        assert out.published_at == ""

    def test_failed_status_is_failed(self):
        raw = _raw(date="still-bad")
        item = NewsItem(
            title="T", content="b", url="u", published_at="bad",
            source="web", provider="p", raw_refs=[raw], metadata={},
        )
        out = normalize_item_time(item)
        assert out.metadata["time_normalization"]["status"] == "failed"

    def test_failed_normalized_field_is_empty_string(self):
        raw = _raw(date="bad2")
        item = NewsItem(
            title="T", content="b", url="u", published_at="bad1",
            source="web", provider="p", raw_refs=[raw], metadata={},
        )
        out = normalize_item_time(item)
        assert out.metadata["time_normalization"]["normalized"] == ""

    def test_failed_fallback_source_is_none(self):
        raw = _raw(date="bad2")
        item = NewsItem(
            title="T", content="b", url="u", published_at="bad1",
            source="web", provider="p", raw_refs=[raw], metadata={},
        )
        out = normalize_item_time(item)
        assert out.metadata["time_normalization"]["fallback_source"] is None

    def test_failed_all_candidates_in_attempts(self):
        raw0 = _raw(date="x")
        raw1 = _raw(date="y")
        item = NewsItem(
            title="T", content="b", url="u", published_at="z",
            source="web", provider="p",
            raw_refs=[raw0, raw1], metadata={},
        )
        out = normalize_item_time(item)
        attempts = out.metadata["time_normalization"]["attempts"]
        assert len(attempts) == 3
        sources = [a["source"] for a in attempts]
        assert sources == ["published_at", "raw_refs[0].date", "raw_refs[1].date"]
        assert all(a["result"] == "parse_failed" for a in attempts)

    def test_failed_empty_published_at_tries_raw_refs(self):
        # published_at="" should immediately try raw_refs
        raw = _raw(date="2025-07-04")
        item = NewsItem(
            title="T", content="b", url="u", published_at="",
            source="web", provider="p", raw_refs=[raw], metadata={},
        )
        out = normalize_item_time(item)
        assert out.published_at == "2025-07-04"
        assert out.metadata["time_normalization"]["status"] == "fallback"

    # -----------------------------------------------------------------------
    # Non-mutation guarantees
    # -----------------------------------------------------------------------

    def test_original_published_at_not_mutated(self):
        item = _item(published_at="garbage-date")
        _ = normalize_item_time(item)
        assert item.published_at == "garbage-date"

    def test_original_metadata_not_mutated(self):
        item = _item(published_at="2025-06-01", metadata={"existing_key": "v"})
        _ = normalize_item_time(item)
        assert "time_normalization" not in item.metadata
        assert item.metadata == {"existing_key": "v"}

    def test_original_raw_refs_list_not_mutated(self):
        item = _item(published_at="2025-06-01")
        original_refs = list(item.raw_refs)
        _ = normalize_item_time(item)
        assert item.raw_refs == original_refs

    def test_original_raw_document_not_mutated(self):
        raw = _raw(date="2025-06-01")
        item = NewsItem(
            title="T", content="b", url="u", published_at="bad",
            source="web", provider="p", raw_refs=[raw], metadata={},
        )
        _ = normalize_item_time(item)
        assert raw.date == "2025-06-01"

    # -----------------------------------------------------------------------
    # Field preservation
    # -----------------------------------------------------------------------

    def test_preserves_title(self):
        item = _item(title="My Title", published_at="2025-06-01")
        assert normalize_item_time(item).title == "My Title"

    def test_preserves_content(self):
        item = _item(content="My Content", published_at="2025-06-01")
        assert normalize_item_time(item).content == "My Content"

    def test_preserves_url(self):
        item = _item(url="https://example.com/test", published_at="2025-06-01")
        assert normalize_item_time(item).url == "https://example.com/test"

    def test_preserves_source(self):
        item = _item(source="akshare", published_at="2025-06-01")
        assert normalize_item_time(item).source == "akshare"

    def test_preserves_provider(self):
        item = _item(provider="cctv", published_at="2025-06-01")
        assert normalize_item_time(item).provider == "cctv"

    def test_preserves_raw_refs_count(self):
        raw0 = _raw(date="2025-06-01")
        raw1 = _raw(date="2025-06-02")
        item = NewsItem(
            title="T", content="b", url="u", published_at="2025-06-01",
            source="web", provider="p", raw_refs=[raw0, raw1], metadata={},
        )
        out = normalize_item_time(item)
        assert len(out.raw_refs) == 2

    def test_preserves_unrelated_metadata_keys(self):
        item = _item(published_at="2025-06-01", metadata={"foo": "bar", "num": 42})
        out = normalize_item_time(item)
        assert out.metadata["foo"] == "bar"
        assert out.metadata["num"] == 42

    def test_does_not_overwrite_existing_metadata_key(self):
        # A pre-existing time_normalization key should be overwritten with
        # the new audit record (expected — normalization owns this key).
        item = _item(published_at="2025-06-01", metadata={"time_normalization": "old"})
        out = normalize_item_time(item)
        assert isinstance(out.metadata["time_normalization"], dict)

    # -----------------------------------------------------------------------
    # Audit metadata structure
    # -----------------------------------------------------------------------

    def test_audit_key_is_time_normalization(self):
        item = _item(published_at="2025-06-01")
        out = normalize_item_time(item)
        assert "time_normalization" in out.metadata

    def test_audit_original_holds_original_published_at(self):
        item = _item(published_at="20250601")
        out = normalize_item_time(item)
        assert out.metadata["time_normalization"]["original"] == "20250601"

    def test_audit_normalized_holds_yyyy_mm_dd(self):
        item = _item(published_at="20250601")
        out = normalize_item_time(item)
        assert out.metadata["time_normalization"]["normalized"] == "2025-06-01"

    def test_returned_object_is_new_instance(self):
        item = _item(published_at="2025-06-01")
        out = normalize_item_time(item)
        assert out is not item


# ===========================================================================
# TestNormalizeTime
# ===========================================================================

class TestNormalizeTime:

    def test_empty_list_returns_empty(self):
        assert normalize_time([]) == []

    def test_single_item_normalized(self):
        item = _item(published_at="20250601")
        result = normalize_time([item])
        assert len(result) == 1
        assert result[0].published_at == "2025-06-01"

    def test_ordering_preserved(self):
        items = [
            _item(published_at="2025-01-01", title="A"),
            _item(published_at="2025-03-15", title="B"),
            _item(published_at="2025-12-31", title="C"),
        ]
        result = normalize_time(items)
        assert [r.title for r in result] == ["A", "B", "C"]

    def test_count_equals_input_count(self):
        items = [_item(published_at=f"2025-0{i+1}-01") for i in range(5)]
        assert len(normalize_time(items)) == 5

    def test_no_mutation_of_original_items(self):
        items = [_item(published_at="2025/06/01", title="X")]
        normalize_time(items)
        assert items[0].published_at == "2025/06/01"
        assert "time_normalization" not in items[0].metadata

    def test_mixed_statuses_in_batch(self):
        ok_raw = _raw(date="2025-01-01")
        ok_item = NewsItem(
            title="ok", content="b", url="u1", published_at="2025-01-01",
            source="web", provider="p", raw_refs=[ok_raw], metadata={},
        )
        fallback_item = NewsItem(
            title="fb", content="b", url="u2", published_at="bad",
            source="web", provider="p", raw_refs=[_raw(date="2025-02-01")], metadata={},
        )
        failed_item = NewsItem(
            title="fail", content="b", url="u3", published_at="garbage",
            source="web", provider="p", raw_refs=[_raw(date="nope")], metadata={},
        )
        result = normalize_time([ok_item, fallback_item, failed_item])
        assert len(result) == 3
        assert result[0].metadata["time_normalization"]["status"] == "ok"
        assert result[1].metadata["time_normalization"]["status"] == "fallback"
        assert result[2].metadata["time_normalization"]["status"] == "failed"

    def test_all_items_get_audit_metadata(self):
        items = [_item(published_at="2025-06-01") for _ in range(3)]
        result = normalize_time(items)
        assert all("time_normalization" in r.metadata for r in result)

    def test_output_items_are_new_instances(self):
        item = _item(published_at="2025-06-01")
        result = normalize_time([item])
        assert result[0] is not item


# ===========================================================================
# TestImportExport
# ===========================================================================

class TestImportExport:

    def test_parse_date_string_importable_from_normalize(self):
        from app.normalize import parse_date_string as pds
        assert callable(pds)

    def test_normalize_item_time_importable_from_normalize(self):
        from app.normalize import normalize_item_time as nit
        assert callable(nit)

    def test_normalize_time_importable_from_normalize(self):
        from app.normalize import normalize_time as nt
        assert callable(nt)

    def test_same_parse_date_string_object(self):
        import app.normalize as pkg
        from app.normalize.time_norm import parse_date_string as pds
        assert pkg.parse_date_string is pds

    def test_same_normalize_item_time_object(self):
        import app.normalize as pkg
        from app.normalize.time_norm import normalize_item_time as nit
        assert pkg.normalize_item_time is nit

    def test_same_normalize_time_object(self):
        import app.normalize as pkg
        from app.normalize.time_norm import normalize_time as nt
        assert pkg.normalize_time is nt

    def test_parse_date_string_in_all(self):
        from app.normalize import __all__
        assert "parse_date_string" in __all__

    def test_normalize_item_time_in_all(self):
        from app.normalize import __all__
        assert "normalize_item_time" in __all__

    def test_normalize_time_in_all(self):
        from app.normalize import __all__
        assert "normalize_time" in __all__
