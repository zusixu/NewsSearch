"""
tests/test_date_filter.py — tests for the date-range filtering pipeline stage.

Covers:
- filter_by_date_range: exact boundaries, inclusive, empty/unparseable dates
- filter_last_n_days: default 7 days, custom n, today override, invalid n
- Metadata annotation on kept items
- Non-mutation of input items
"""

from __future__ import annotations

import datetime

import pytest

from app.models.news_item import NewsItem
from app.models.raw_document import RawDocument
from app.normalize.date_filter import filter_by_date_range, filter_last_n_days


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(published_at: str, title: str = "Test") -> NewsItem:
    raw = RawDocument(
        source="test", provider="test",
        title=title, content="body",
        url=None, date=published_at,
    )
    return NewsItem.from_raw(raw)


def _date(y: int, m: int, d: int) -> datetime.date:
    return datetime.date(y, m, d)


# ---------------------------------------------------------------------------
# filter_by_date_range
# ---------------------------------------------------------------------------

class TestFilterByDateRange:
    def test_keeps_items_within_range(self):
        items = [
            _make_item("2026-04-20"),
            _make_item("2026-04-23"),
            _make_item("2026-04-25"),
        ]
        result = filter_by_date_range(items, _date(2026, 4, 20), _date(2026, 4, 25))
        assert len(result) == 3

    def test_removes_items_before_range(self):
        items = [
            _make_item("2026-04-18"),
            _make_item("2026-04-25"),
        ]
        result = filter_by_date_range(items, _date(2026, 4, 20), _date(2026, 4, 25))
        assert len(result) == 1
        assert result[0].published_at == "2026-04-25"

    def test_removes_items_after_range(self):
        items = [
            _make_item("2026-04-25"),
            _make_item("2026-04-30"),
        ]
        result = filter_by_date_range(items, _date(2026, 4, 20), _date(2026, 4, 25))
        assert len(result) == 1
        assert result[0].published_at == "2026-04-25"

    def test_boundaries_are_inclusive(self):
        items = [
            _make_item("2026-04-19"),
            _make_item("2026-04-20"),
            _make_item("2026-04-25"),
            _make_item("2026-04-26"),
        ]
        result = filter_by_date_range(items, _date(2026, 4, 20), _date(2026, 4, 25))
        assert len(result) == 2
        assert result[0].published_at == "2026-04-20"
        assert result[1].published_at == "2026-04-25"

    def test_drops_empty_date(self):
        item = _make_item("")
        item = NewsItem(
            title="t", content=None, url=None, published_at="",
            source="s", provider="p", raw_refs=[RawDocument(
                source="s", provider="p", title="t", content=None,
                url=None, date="",
            )],
        )
        result = filter_by_date_range([item], _date(2026, 4, 1), _date(2026, 4, 30))
        assert len(result) == 0

    def test_drops_unparseable_date(self):
        item = _make_item("not-a-date")
        result = filter_by_date_range([item], _date(2026, 4, 1), _date(2026, 4, 30))
        assert len(result) == 0

    def test_empty_input_returns_empty(self):
        result = filter_by_date_range([], _date(2026, 4, 1), _date(2026, 4, 30))
        assert result == []

    def test_metadata_annotates_kept_items(self):
        items = [_make_item("2026-04-22")]
        result = filter_by_date_range(items, _date(2026, 4, 20), _date(2026, 4, 25))
        assert len(result) == 1
        assert result[0].metadata["date_filter"]["kept"] is True
        assert result[0].metadata["date_filter"]["start_date"] == "2026-04-20"
        assert result[0].metadata["date_filter"]["end_date"] == "2026-04-25"


# ---------------------------------------------------------------------------
# filter_last_n_days
# ---------------------------------------------------------------------------

class TestFilterLastNDays:
    def test_default_7_days(self):
        today = _date(2026, 4, 25)
        items = [
            _make_item("2026-04-18"),  # day -7: outside (7 days = 4/19-4/25)
            _make_item("2026-04-19"),  # day -6: inside
            _make_item("2026-04-25"),  # today: inside
        ]
        result = filter_last_n_days(items, n=7, today=today)
        assert len(result) == 2
        assert result[0].published_at == "2026-04-19"
        assert result[1].published_at == "2026-04-25"

    def test_custom_n(self):
        today = _date(2026, 4, 25)
        items = [
            _make_item("2026-04-24"),
            _make_item("2026-04-25"),
            _make_item("2026-04-23"),
        ]
        result = filter_last_n_days(items, n=2, today=today)
        assert len(result) == 2
        assert result[0].published_at == "2026-04-24"
        assert result[1].published_at == "2026-04-25"

    def test_n_equals_1_keeps_today_only(self):
        today = _date(2026, 4, 25)
        items = [
            _make_item("2026-04-24"),
            _make_item("2026-04-25"),
        ]
        result = filter_last_n_days(items, n=1, today=today)
        assert len(result) == 1
        assert result[0].published_at == "2026-04-25"

    def test_invalid_n_raises(self):
        with pytest.raises(ValueError, match="n must be >= 1"):
            filter_last_n_days([], n=0)

    def test_today_default_uses_date_today(self):
        # Items from today should always be kept
        today_str = datetime.date.today().isoformat()
        items = [_make_item(today_str)]
        result = filter_last_n_days(items, n=7)
        assert len(result) == 1

    def test_empty_input(self):
        result = filter_last_n_days([], n=7, today=_date(2026, 4, 25))
        assert result == []


# ---------------------------------------------------------------------------
# Non-mutation
# ---------------------------------------------------------------------------

class TestNonMutation:
    def test_does_not_mutate_input_items(self):
        items = [_make_item("2026-04-22")]
        original_metadata = dict(items[0].metadata)
        filter_by_date_range(items, _date(2026, 4, 20), _date(2026, 4, 25))
        assert items[0].metadata == original_metadata
