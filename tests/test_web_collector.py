"""
tests/test_web_collector.py — Focused unit tests for WebCollector.

All tests use local fixtures and mocks.  No live network calls are made.

Coverage areas
--------------
* parse_feed() — RSS 2.0 items, including pubDate, content:encoded, missing
  pubDate fallback, malformed XML, empty feed, unknown root tag
* parse_feed() — Atom entries, including published/updated, no-namespace Atom
* parse_html() — heading-based item extraction, skip tags, no headings
* _HeadingExtractor — nested skip tags, void elements, multiple headings
* _parse_rfc2822_date() — valid RFC-2822, bad month, no match
* _parse_iso_date() — ISO datetime, date-only, empty string
* fetch_url() — HTTP error, URLError, OS error (via mock)
* WebCollector.collect() — all sources succeed, partial failure,
  all fail, empty source list, missing url key, per-source timeout
* WebCollector.is_enabled() contract
* metadata populated correctly
"""

from __future__ import annotations

import datetime
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.collectors.base import (
    CollectResult,
    CollectorError,
    CollectorUnavailableError,
    RunContext,
)
from app.collectors.raw_document import RawDocument
from app.collectors.web_collector import (
    WebCollector,
    _HeadingExtractor,
    _parse_iso_date,
    _parse_rfc2822_date,
    fetch_url,
    parse_feed,
    parse_html,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_DATE = datetime.date(2025, 1, 15)
_CTX = RunContext.for_date(_DATE)
_FALLBACK = _DATE.isoformat()  # "2025-01-15"

_PATCH_FETCH = "app.collectors.web_collector.fetch_url"

# ---------------------------------------------------------------------------
# Local XML / HTML fixtures
# ---------------------------------------------------------------------------

RSS_FEED = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <item>
      <title>Item One</title>
      <link>https://example.com/1</link>
      <description>Short description one.</description>
      <pubDate>Mon, 15 Jan 2025 08:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Item Two</title>
      <link>https://example.com/2</link>
      <content:encoded>&lt;p&gt;Full content two.&lt;/p&gt;</content:encoded>
      <pubDate>Tue, 14 Jan 2025 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>No Date Item</title>
      <link>https://example.com/3</link>
      <description>No pubDate.</description>
    </item>
  </channel>
</rss>
"""

RSS_EMPTY = """\
<?xml version="1.0"?>
<rss version="2.0"><channel><title>Empty</title></channel></rss>
"""

ATOM_FEED = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Test Feed</title>
  <entry>
    <title>Atom Entry One</title>
    <link href="https://atom.example.com/e1"/>
    <summary>Summary of entry one.</summary>
    <published>2025-01-15T07:30:00Z</published>
  </entry>
  <entry>
    <title>Atom Entry Two</title>
    <link href="https://atom.example.com/e2"/>
    <updated>2025-01-14T09:00:00Z</updated>
  </entry>
  <entry>
    <title>  </title>
  </entry>
</feed>
"""

ATOM_NO_NS = """\
<?xml version="1.0"?>
<feed>
  <entry>
    <title>Plain Atom</title>
    <link href="https://plain.example.com/a"/>
    <summary>Plain atom summary.</summary>
    <published>2025-01-15T00:00:00Z</published>
  </entry>
</feed>
"""

HTML_PAGE = """\
<!DOCTYPE html>
<html>
<head><title>Page Title</title></head>
<body>
  <nav><a href="/">Home</a></nav>
  <h2>Section Alpha</h2>
  <p>Alpha paragraph one. Alpha paragraph two.</p>
  <h2>Section Beta</h2>
  <p>Beta content here.</p>
  <h3>Sub-section</h3>
  <p>Sub paragraph.</p>
  <script>var x = 1;</script>
  <footer>Footer text</footer>
</body>
</html>
"""

HTML_NO_HEADINGS = """\
<html><body><p>Just a paragraph.</p><p>Another one.</p></body></html>
"""

# ---------------------------------------------------------------------------
# _parse_rfc2822_date
# ---------------------------------------------------------------------------

class TestParseRfc2822Date:
    def test_standard_format(self):
        assert _parse_rfc2822_date("Mon, 15 Jan 2025 08:00:00 +0000") == "2025-01-15"

    def test_without_day_of_week(self):
        assert _parse_rfc2822_date("15 Jan 2025 08:00:00 +0000") == "2025-01-15"

    def test_december(self):
        assert _parse_rfc2822_date("Wed, 31 Dec 2025 23:59:59 +0000") == "2025-12-31"

    def test_bad_month_abbreviation(self):
        assert _parse_rfc2822_date("15 Xyz 2025 08:00:00 +0000") is None

    def test_no_match(self):
        assert _parse_rfc2822_date("not a date") is None

    def test_empty_string(self):
        assert _parse_rfc2822_date("") is None


# ---------------------------------------------------------------------------
# _parse_iso_date
# ---------------------------------------------------------------------------

class TestParseIsoDate:
    def test_full_datetime(self):
        assert _parse_iso_date("2025-01-15T07:30:00Z") == "2025-01-15"

    def test_date_only(self):
        assert _parse_iso_date("2025-01-15") == "2025-01-15"

    def test_empty_string(self):
        assert _parse_iso_date("") is None

    def test_none_like_string(self):
        assert _parse_iso_date("   ") is None


# ---------------------------------------------------------------------------
# parse_feed — RSS 2.0
# ---------------------------------------------------------------------------

class TestParseFeedRss:
    def _parse(self, xml: str = RSS_FEED) -> list[RawDocument]:
        return parse_feed(xml, provider="testfeed", fallback_date=_DATE)

    def test_item_count(self):
        assert len(self._parse()) == 3

    def test_source_field(self):
        for item in self._parse():
            assert item.source == "web"

    def test_provider_field(self):
        for item in self._parse():
            assert item.provider == "testfeed"

    def test_first_item_title(self):
        assert self._parse()[0].title == "Item One"

    def test_first_item_url(self):
        assert self._parse()[0].url == "https://example.com/1"

    def test_first_item_content(self):
        assert self._parse()[0].content == "Short description one."

    def test_first_item_date(self):
        assert self._parse()[0].date == "2025-01-15"

    def test_second_item_date(self):
        # pubDate = 14 Jan 2025
        assert self._parse()[1].date == "2025-01-14"

    def test_content_encoded_over_description(self):
        # Item Two has content:encoded; description is absent; content should be the encoded body
        assert "Full content two" in self._parse()[1].content

    def test_no_pubdate_falls_back_to_target_date(self):
        # Item Three has no pubDate
        assert self._parse()[2].date == _FALLBACK

    def test_empty_feed_returns_empty_list(self):
        assert parse_feed(RSS_EMPTY, provider="x", fallback_date=_DATE) == []

    def test_malformed_xml_returns_empty_list(self):
        assert parse_feed("not xml at all", provider="x", fallback_date=_DATE) == []

    def test_unknown_root_tag_returns_empty_list(self):
        xml = "<opml><body><outline text='a'/></body></opml>"
        assert parse_feed(xml, provider="x", fallback_date=_DATE) == []


# ---------------------------------------------------------------------------
# parse_feed — Atom
# ---------------------------------------------------------------------------

class TestParseFeedAtom:
    def _parse(self, xml: str = ATOM_FEED) -> list[RawDocument]:
        return parse_feed(xml, provider="atomfeed", fallback_date=_DATE)

    def test_item_count_skips_blank_title_entry(self):
        # Entry with only whitespace title and no summary is skipped
        assert len(self._parse()) == 2

    def test_source_field(self):
        for item in self._parse():
            assert item.source == "web"

    def test_provider_field(self):
        for item in self._parse():
            assert item.provider == "atomfeed"

    def test_first_entry_title(self):
        assert self._parse()[0].title == "Atom Entry One"

    def test_first_entry_url(self):
        assert self._parse()[0].url == "https://atom.example.com/e1"

    def test_first_entry_summary(self):
        assert self._parse()[0].content == "Summary of entry one."

    def test_first_entry_date_from_published(self):
        assert self._parse()[0].date == "2025-01-15"

    def test_second_entry_date_from_updated(self):
        assert self._parse()[1].date == "2025-01-14"

    def test_second_entry_no_summary_content_is_none(self):
        assert self._parse()[1].content is None

    def test_atom_without_namespace(self):
        items = parse_feed(ATOM_NO_NS, provider="plain", fallback_date=_DATE)
        assert len(items) == 1
        assert items[0].title == "Plain Atom"
        assert items[0].content == "Plain atom summary."
        assert items[0].date == "2025-01-15"


# ---------------------------------------------------------------------------
# parse_html
# ---------------------------------------------------------------------------

class TestParseHtml:
    def _parse(self, html: str = HTML_PAGE) -> list[RawDocument]:
        return parse_html(
            html, provider="htmlsrc", url="https://example.com/news", fallback_date=_DATE
        )

    def test_heading_count(self):
        # Section Alpha, Section Beta, Sub-section
        assert len(self._parse()) == 3

    def test_source_field(self):
        for item in self._parse():
            assert item.source == "web"

    def test_provider_field(self):
        for item in self._parse():
            assert item.provider == "htmlsrc"

    def test_url_preserved(self):
        for item in self._parse():
            assert item.url == "https://example.com/news"

    def test_date_is_fallback(self):
        for item in self._parse():
            assert item.date == _FALLBACK

    def test_first_heading_title(self):
        assert self._parse()[0].title == "Section Alpha"

    def test_first_heading_content(self):
        assert "Alpha paragraph" in self._parse()[0].content

    def test_second_heading(self):
        assert self._parse()[1].title == "Section Beta"
        assert "Beta content" in self._parse()[1].content

    def test_h3_sub_section(self):
        assert self._parse()[2].title == "Sub-section"
        assert "Sub paragraph" in self._parse()[2].content

    def test_nav_text_excluded(self):
        for item in self._parse():
            assert "Home" not in (item.title + (item.content or ""))

    def test_script_text_excluded(self):
        for item in self._parse():
            assert "var x" not in (item.content or "")

    def test_footer_text_excluded(self):
        for item in self._parse():
            assert "Footer text" not in (item.title + (item.content or ""))

    def test_no_headings_returns_empty(self):
        assert parse_html(HTML_NO_HEADINGS, provider="x", url=None, fallback_date=_DATE) == []

    def test_url_none_preserved(self):
        items = parse_html(HTML_PAGE, provider="x", url=None, fallback_date=_DATE)
        for item in items:
            assert item.url is None

    def test_heading_only_no_body_content_is_none(self):
        html = "<html><body><h2>Lonely heading</h2></body></html>"
        items = parse_html(html, provider="x", url=None, fallback_date=_DATE)
        assert len(items) == 1
        assert items[0].title == "Lonely heading"
        assert items[0].content is None


# ---------------------------------------------------------------------------
# _HeadingExtractor edge cases
# ---------------------------------------------------------------------------

class TestHeadingExtractor:
    def _extract(self, html: str) -> list[tuple[str, str]]:
        ex = _HeadingExtractor()
        ex.feed(html)
        ex.close()
        return ex.items

    def test_nested_skip_tag(self):
        html = "<h2>Title</h2><nav><div><p>skip me</p></div></nav><p>keep me</p>"
        items = self._extract(html)
        assert len(items) == 1
        assert "skip me" not in items[0][1]
        assert "keep me" in items[0][1]

    def test_script_inside_body_skipped(self):
        html = "<h2>Alpha</h2><p>Good text</p><script>evil()</script><p>More text</p>"
        items = self._extract(html)
        assert "evil" not in items[0][1]
        assert "Good text" in items[0][1]
        assert "More text" in items[0][1]

    def test_void_element_no_depth_effect(self):
        # <br/> should not corrupt skip depth
        html = "<nav><br/></nav><h2>After</h2><p>OK</p>"
        items = self._extract(html)
        assert len(items) == 1
        assert items[0][0] == "After"

    def test_multiple_paragraphs_joined(self):
        html = "<h2>Multi</h2><p>First.</p><p>Second.</p>"
        items = self._extract(html)
        body = items[0][1]
        assert "First" in body
        assert "Second" in body

    def test_html_entities_decoded(self):
        # convert_charrefs=True handles entity decoding automatically
        html = "<h2>AT&amp;T</h2><p>Q&amp;A</p>"
        items = self._extract(html)
        assert items[0][0] == "AT&T"
        assert "Q&A" in items[0][1]


# ---------------------------------------------------------------------------
# fetch_url (network layer — mocked)
# ---------------------------------------------------------------------------

class TestFetchUrl:
    _PATCH = "app.collectors.web_collector.urllib.request.urlopen"

    def _make_mock_response(self, body: str = "hello", charset: str = "utf-8") -> MagicMock:
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = body.encode(charset)
        resp.headers.get_content_charset.return_value = charset
        return resp

    def test_returns_decoded_body(self):
        with patch(self._PATCH, return_value=self._make_mock_response("content")) as m:
            result = fetch_url("https://example.com/feed")
        assert result == "content"

    def test_http_error_raises_unavailable(self):
        http_err = urllib.error.HTTPError(
            url="https://x.com", code=404, msg="Not Found", hdrs=None, fp=None
        )
        with patch(self._PATCH, side_effect=http_err):
            with pytest.raises(CollectorUnavailableError) as exc_info:
                fetch_url("https://x.com/missing")
        assert "404" in str(exc_info.value)

    def test_url_error_raises_unavailable(self):
        url_err = urllib.error.URLError(reason="Name or service not known")
        with patch(self._PATCH, side_effect=url_err):
            with pytest.raises(CollectorUnavailableError):
                fetch_url("https://nonexistent.invalid/")

    def test_os_error_raises_unavailable(self):
        with patch(self._PATCH, side_effect=OSError("connection reset")):
            with pytest.raises(CollectorUnavailableError):
                fetch_url("https://x.com/")

    def test_unavailable_error_is_collector_error(self):
        with patch(self._PATCH, side_effect=urllib.error.URLError("fail")):
            with pytest.raises(CollectorError):
                fetch_url("https://x.com/")


# ---------------------------------------------------------------------------
# WebCollector.collect — happy path
# ---------------------------------------------------------------------------

_RSS_SOURCE = {"url": "https://rss.example.com/feed", "type": "rss", "provider": "rsssrc"}
_HTML_SOURCE = {"url": "https://html.example.com/news", "type": "html", "provider": "htmlsrc"}


class TestWebCollectorBothSucceed:
    def _run(self) -> CollectResult:
        with patch(_PATCH_FETCH, side_effect=[RSS_FEED, HTML_PAGE]):
            return WebCollector(sources=[_RSS_SOURCE, _HTML_SOURCE]).collect(_CTX)

    def test_no_errors(self):
        assert self._run().errors == []

    def test_source_id(self):
        assert self._run().source_id == "web"

    def test_target_date(self):
        assert self._run().target_date == _DATE

    def test_items_from_both_sources(self):
        result = self._run()
        providers = {item.provider for item in result.items}
        assert "rsssrc" in providers
        assert "htmlsrc" in providers

    def test_total_item_count(self):
        # RSS_FEED has 3 items; HTML_PAGE has 3 headings
        assert len(self._run().items) == 6

    def test_result_is_ok(self):
        assert self._run().ok

    def test_metadata_source_counts(self):
        counts = self._run().metadata["source_counts"]
        assert counts["rsssrc"] == 3
        assert counts["htmlsrc"] == 3


# ---------------------------------------------------------------------------
# WebCollector.collect — partial failure
# ---------------------------------------------------------------------------

class TestWebCollectorPartialFailure:
    def test_first_source_fails_second_succeeds(self):
        err = CollectorUnavailableError("rss down", source_id="web")
        # max_attempts=3 (default): RSS source is retried 3 times, then HTML runs.
        with patch(_PATCH_FETCH, side_effect=[err, err, err, HTML_PAGE]):
            result = WebCollector(sources=[_RSS_SOURCE, _HTML_SOURCE]).collect(_CTX)
        assert result.partial
        assert len(result.errors) == 1
        assert all(item.provider == "htmlsrc" for item in result.items)

    def test_second_source_fails_first_succeeds(self):
        err = CollectorUnavailableError("html down", source_id="web")
        # RSS succeeds immediately; HTML is retried 3 times before failing.
        with patch(_PATCH_FETCH, side_effect=[RSS_FEED, err, err, err]):
            result = WebCollector(sources=[_RSS_SOURCE, _HTML_SOURCE]).collect(_CTX)
        assert result.partial
        assert len(result.errors) == 1
        assert all(item.provider == "rsssrc" for item in result.items)

    def test_error_is_collector_error_subclass(self):
        err = CollectorUnavailableError("down", source_id="web")
        with patch(_PATCH_FETCH, side_effect=[err, err, err, HTML_PAGE]):
            result = WebCollector(sources=[_RSS_SOURCE, _HTML_SOURCE]).collect(_CTX)
        assert isinstance(result.errors[0], CollectorError)

    def test_source_count_zero_for_failed_source(self):
        err = CollectorUnavailableError("rss down", source_id="web")
        with patch(_PATCH_FETCH, side_effect=[err, err, err, HTML_PAGE]):
            result = WebCollector(sources=[_RSS_SOURCE, _HTML_SOURCE]).collect(_CTX)
        assert result.metadata["source_counts"]["rsssrc"] == 0
        assert result.metadata["source_counts"]["htmlsrc"] == 3

    def test_unexpected_exception_is_wrapped(self):
        # RuntimeError is not a CollectorError → propagates immediately through
        # with_retry without retrying; caught by the outer except Exception handler.
        with patch(_PATCH_FETCH, side_effect=[RuntimeError("boom"), HTML_PAGE]):
            result = WebCollector(sources=[_RSS_SOURCE, _HTML_SOURCE]).collect(_CTX)
        assert result.partial
        assert isinstance(result.errors[0], CollectorUnavailableError)


# ---------------------------------------------------------------------------
# WebCollector.collect — all fail
# ---------------------------------------------------------------------------

class TestWebCollectorAllFail:
    def _run(self) -> CollectResult:
        err = CollectorUnavailableError("down", source_id="web")
        with patch(_PATCH_FETCH, side_effect=[err, err]):
            return WebCollector(sources=[_RSS_SOURCE, _HTML_SOURCE]).collect(_CTX)

    def test_result_is_failed(self):
        assert self._run().failed

    def test_two_errors_recorded(self):
        assert len(self._run().errors) == 2

    def test_no_items(self):
        assert self._run().items == []


# ---------------------------------------------------------------------------
# WebCollector.collect — edge cases
# ---------------------------------------------------------------------------

class TestWebCollectorEdgeCases:
    def test_empty_sources_returns_failed_no_errors(self):
        result = WebCollector(sources=[]).collect(_CTX)
        assert result.failed
        assert result.errors == []

    def test_no_sources_arg_returns_failed(self):
        result = WebCollector().collect(_CTX)
        assert result.failed

    def test_missing_url_records_error(self):
        bad_src = {"type": "rss", "provider": "nourl"}  # no url key
        result = WebCollector(sources=[bad_src]).collect(_CTX)
        assert result.failed
        assert len(result.errors) == 1

    def test_per_source_timeout_passed_to_fetch(self):
        src = {"url": "https://x.com/feed", "type": "rss", "provider": "x", "timeout": 5}
        captured: list[int] = []

        def fake_fetch(url: str, timeout: int = 15) -> str:
            captured.append(timeout)
            return RSS_FEED

        with patch(_PATCH_FETCH, side_effect=fake_fetch):
            WebCollector(sources=[src]).collect(_CTX)
        assert captured == [5]

    def test_default_type_treated_as_rss(self):
        # source without "type" key should default to RSS
        src = {"url": "https://x.com/feed", "provider": "x"}
        with patch(_PATCH_FETCH, return_value=RSS_FEED):
            result = WebCollector(sources=[src]).collect(_CTX)
        assert result.items  # RSS parsed successfully

    def test_metadata_key_present(self):
        result = WebCollector(sources=[]).collect(_CTX)
        assert "source_counts" in result.metadata


# ---------------------------------------------------------------------------
# WebCollector.is_enabled()
# ---------------------------------------------------------------------------

class TestWebCollectorIsEnabled:
    def test_true_when_config_web_true(self):
        class Cfg:
            web = True
        assert WebCollector().is_enabled(Cfg()) is True

    def test_false_when_config_web_false(self):
        class Cfg:
            web = False
        assert WebCollector().is_enabled(Cfg()) is False

    def test_true_when_no_web_attr(self):
        assert WebCollector().is_enabled(object()) is True

    def test_true_when_config_is_none(self):
        assert WebCollector().is_enabled(None) is True
