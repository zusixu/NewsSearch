"""
tests/test_akshare_collector.py — Focused unit tests for AkShareCollector.

All tests use mocks/fakes.  No live network calls are made.

Coverage areas
--------------
* Both providers succeed       → CollectResult.ok
* One provider fails           → CollectResult.partial  (partial-failure policy)
* Both providers fail          → CollectResult.failed
* Import failure               → CollectorUnavailableError propagates
* Empty DataFrames             → no items, no errors
* Normalisation of CCTV rows  → correct dict fields
* Normalisation of Caixin rows → correct dict fields, tag/summary fallback
* is_enabled() contract
* metadata populated correctly
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.collectors.akshare_collector import AkShareCollector
from app.collectors.base import (
    CollectResult,
    CollectorError,
    CollectorUnavailableError,
    RunContext,
)
from app.collectors.raw_document import RawDocument

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_DATE = datetime.date(2025, 1, 15)
_CTX = RunContext.for_date(_DATE)
_DATE_STR = "20250115"

_PATCH = "app.collectors.akshare_collector._import_akshare"


def _cctv_df(rows: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [_DATE.isoformat()] * rows,
            "title": [f"CCTV title {i}" for i in range(rows)],
            "content": [f"CCTV content {i}" for i in range(rows)],
        }
    )


def _caixin_df(rows: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "tag": [f"tag{i}" for i in range(rows)],
            "summary": [f"Caixin summary {i}" for i in range(rows)],
            "url": [f"https://example.com/{i}" for i in range(rows)],
        }
    )


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame()


def _mock_ak(cctv=None, caixin=None, cctv_err=None, caixin_err=None) -> MagicMock:
    """Build a mock akshare module with configurable return values / side-effects."""
    ak = MagicMock()
    if cctv_err:
        ak.news_cctv.side_effect = cctv_err
    else:
        ak.news_cctv.return_value = cctv if cctv is not None else _cctv_df()
    if caixin_err:
        ak.stock_news_main_cx.side_effect = caixin_err
    else:
        ak.stock_news_main_cx.return_value = caixin if caixin is not None else _caixin_df()
    return ak


# ---------------------------------------------------------------------------
# Happy-path: both providers return data
# ---------------------------------------------------------------------------

class TestBothProvidersSucceed:
    def _run(self) -> CollectResult:
        with patch(_PATCH, return_value=_mock_ak()):
            return AkShareCollector().collect(_CTX)

    def test_result_is_ok(self):
        assert self._run().ok

    def test_item_count(self):
        # 2 CCTV rows + 2 Caixin rows
        assert len(self._run().items) == 4

    def test_no_errors(self):
        assert self._run().errors == []

    def test_source_id_in_all_items(self):
        for item in self._run().items:
            assert item.source == "akshare"

    def test_both_providers_represented(self):
        providers = {item.provider for item in self._run().items}
        assert providers == {"cctv", "caixin"}

    def test_result_target_date(self):
        assert self._run().target_date == _DATE

    def test_result_source_id(self):
        assert self._run().source_id == "akshare"

    def test_metadata_date_str(self):
        assert self._run().metadata["date_str"] == _DATE_STR

    def test_metadata_provider_counts(self):
        counts = self._run().metadata["provider_counts"]
        assert counts["cctv"] == 2
        assert counts["caixin"] == 2


# ---------------------------------------------------------------------------
# Partial failure: one provider fails
# ---------------------------------------------------------------------------

class TestPartialFailure:
    def test_cctv_fails_caixin_succeeds(self):
        ak = _mock_ak(cctv_err=RuntimeError("CCTV API down"))
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert result.partial
        assert len(result.items) == 2
        assert len(result.errors) == 1
        assert all(item.provider == "caixin" for item in result.items)

    def test_caixin_fails_cctv_succeeds(self):
        ak = _mock_ak(caixin_err=RuntimeError("Caixin API down"))
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert result.partial
        assert len(result.items) == 2
        assert len(result.errors) == 1
        assert all(item.provider == "cctv" for item in result.items)

    def test_error_is_collector_error_subclass(self):
        ak = _mock_ak(cctv_err=RuntimeError("down"))
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert isinstance(result.errors[0], CollectorError)

    def test_error_source_id_is_akshare(self):
        ak = _mock_ak(cctv_err=RuntimeError("down"))
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert result.errors[0].source_id == "akshare"

    def test_provider_count_zero_for_failed_provider(self):
        ak = _mock_ak(cctv_err=RuntimeError("down"))
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert result.metadata["provider_counts"]["cctv"] == 0
        assert result.metadata["provider_counts"]["caixin"] == 2


# ---------------------------------------------------------------------------
# Both providers fail
# ---------------------------------------------------------------------------

class TestBothFail:
    def _run(self) -> CollectResult:
        ak = _mock_ak(
            cctv_err=RuntimeError("CCTV down"),
            caixin_err=RuntimeError("Caixin down"),
        )
        with patch(_PATCH, return_value=ak):
            return AkShareCollector().collect(_CTX)

    def test_result_is_failed(self):
        assert self._run().failed

    def test_two_errors_recorded(self):
        assert len(self._run().errors) == 2

    def test_no_items(self):
        assert self._run().items == []


# ---------------------------------------------------------------------------
# Import failure
# ---------------------------------------------------------------------------

class TestImportFailure:
    def test_raises_unavailable_error(self):
        err = CollectorUnavailableError(
            "akshare not installed", source_id="akshare"
        )
        with patch(_PATCH, side_effect=err):
            with pytest.raises(CollectorUnavailableError):
                AkShareCollector().collect(_CTX)

    def test_error_is_collector_error(self):
        err = CollectorUnavailableError(
            "akshare not installed", source_id="akshare"
        )
        with patch(_PATCH, side_effect=err):
            with pytest.raises(CollectorError):
                AkShareCollector().collect(_CTX)


# ---------------------------------------------------------------------------
# Empty DataFrames — should produce no items and no errors
# ---------------------------------------------------------------------------

class TestEmptyDataFrames:
    def test_empty_cctv_no_cctv_items(self):
        ak = _mock_ak(cctv=_empty_df())
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert all(item.provider == "caixin" for item in result.items)
        assert result.errors == []

    def test_empty_caixin_no_caixin_items(self):
        ak = _mock_ak(caixin=_empty_df())
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert all(item.provider == "cctv" for item in result.items)
        assert result.errors == []

    def test_both_empty_failed_no_errors(self):
        ak = _mock_ak(cctv=_empty_df(), caixin=_empty_df())
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert result.failed
        assert result.errors == []


# ---------------------------------------------------------------------------
# Normalisation — CCTV
# ---------------------------------------------------------------------------

class TestCctvNormalisation:
    def _single_item(self, **row_override) -> RawDocument:
        row = {"date": "2025-01-15", "title": "Test Title", "content": "Test body."}
        row.update(row_override)
        ak = _mock_ak(cctv=pd.DataFrame([row]), caixin=_empty_df())
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert len(result.items) == 1
        return result.items[0]

    def test_source_field(self):
        assert self._single_item().source == "akshare"

    def test_provider_field(self):
        assert self._single_item().provider == "cctv"

    def test_title_field(self):
        assert self._single_item().title == "Test Title"

    def test_content_field(self):
        assert self._single_item().content == "Test body."

    def test_url_is_none(self):
        assert self._single_item().url is None

    def test_date_field(self):
        assert self._single_item().date == "2025-01-15"

    def test_empty_content_becomes_none(self):
        item = self._single_item(content="")
        assert item.content is None

    def test_nan_title_becomes_empty_string(self):
        import math
        item = self._single_item(title=float("nan"))
        assert item.title == ""

    def test_missing_date_falls_back_to_target_date(self):
        ak = _mock_ak(
            cctv=pd.DataFrame([{"title": "T", "content": "C"}]),
            caixin=_empty_df(),
        )
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert result.items[0].date == _DATE.isoformat()


# ---------------------------------------------------------------------------
# Normalisation — Caixin
# ---------------------------------------------------------------------------

class TestCaixinNormalisation:
    def _single_item(self, **row_override) -> RawDocument:
        row = {"tag": "金融", "summary": "Market update.", "url": "https://example.com/n"}
        row.update(row_override)
        ak = _mock_ak(cctv=_empty_df(), caixin=pd.DataFrame([row]))
        with patch(_PATCH, return_value=ak):
            result = AkShareCollector().collect(_CTX)
        assert len(result.items) == 1
        return result.items[0]

    def test_source_field(self):
        assert self._single_item().source == "akshare"

    def test_provider_field(self):
        assert self._single_item().provider == "caixin"

    def test_title_from_tag(self):
        assert self._single_item().title == "金融"

    def test_content_from_summary(self):
        assert self._single_item().content == "Market update."

    def test_url_field(self):
        assert self._single_item().url == "https://example.com/n"

    def test_date_is_target_date(self):
        assert self._single_item().date == _DATE.isoformat()

    def test_empty_tag_falls_back_to_summary_as_title(self):
        item = self._single_item(tag="")
        assert "Market update" in item.title

    def test_empty_url_becomes_none(self):
        item = self._single_item(url="")
        assert item.url is None

    def test_empty_summary_becomes_none(self):
        item = self._single_item(summary="")
        assert item.content is None

    def test_long_summary_title_truncated_to_60(self):
        long_summary = "A" * 80
        item = self._single_item(tag="", summary=long_summary)
        assert len(item.title) == 60


# ---------------------------------------------------------------------------
# is_enabled()
# ---------------------------------------------------------------------------

class TestIsEnabled:
    def test_true_when_config_akshare_true(self):
        class Cfg:
            akshare = True
        assert AkShareCollector().is_enabled(Cfg()) is True

    def test_false_when_config_akshare_false(self):
        class Cfg:
            akshare = False
        assert AkShareCollector().is_enabled(Cfg()) is False

    def test_true_when_no_akshare_attr(self):
        # Default to enabled when the config object has no akshare flag
        assert AkShareCollector().is_enabled(object()) is True

    def test_true_when_config_is_none(self):
        assert AkShareCollector().is_enabled(None) is True
