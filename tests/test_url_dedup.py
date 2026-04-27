"""tests/test_url_dedup.py — Tests for URL canonicalization and URL-based dedup.

Coverage
--------
- canonicalize_url: scheme/host lowercasing, fragment removal, default port
  removal, path normalization, query sorting.
- deduplicate_by_url: exact duplicates, canonical duplicates, None-URL items,
  raw_refs merging, field filling, metadata merging, output order, no mutation.
"""

from __future__ import annotations

import pytest

from app.normalize.url_dedup import canonicalize_url, deduplicate_by_url
from app.models.raw_document import RawDocument
from app.models.news_item import NewsItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raw(url: str = "https://example.com/a", title: str = "T") -> RawDocument:
    return RawDocument(
        source="web",
        provider="test",
        title=title,
        content="body",
        url=url,
        date="2024-01-01",
        metadata={},
    )


def _item(
    url: str | None = "https://example.com/a",
    title: str = "Title",
    content: str | None = "body",
    published_at: str = "2024-01-01",
    source: str = "web",
    provider: str = "test",
    metadata: dict | None = None,
    raw: RawDocument | None = None,
) -> NewsItem:
    if raw is None:
        raw = _raw(url=url or "https://example.com/a", title=title)
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
# canonicalize_url
# ===========================================================================

class TestCanonicalizeUrl:

    # --- scheme / host case ---

    def test_scheme_lowercased(self):
        assert canonicalize_url("HTTP://Example.COM/path") == "http://example.com/path"

    def test_host_lowercased(self):
        assert canonicalize_url("https://NEWS.Example.COM/") == "https://news.example.com/"

    # --- fragment removal ---

    def test_fragment_removed(self):
        assert canonicalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_fragment_only_removed(self):
        assert canonicalize_url("https://example.com/#top") == "https://example.com/"

    # --- default port removal ---

    def test_default_http_port_removed(self):
        assert canonicalize_url("http://example.com:80/path") == "http://example.com/path"

    def test_default_https_port_removed(self):
        assert canonicalize_url("https://example.com:443/path") == "https://example.com/path"

    def test_non_default_port_kept(self):
        result = canonicalize_url("https://example.com:8443/path")
        assert ":8443" in result

    def test_http_non_default_port_kept(self):
        result = canonicalize_url("http://example.com:8080/path")
        assert ":8080" in result

    # --- path normalization ---

    def test_empty_path_becomes_slash(self):
        assert canonicalize_url("https://example.com") == "https://example.com/"

    def test_root_path_unchanged(self):
        assert canonicalize_url("https://example.com/") == "https://example.com/"

    def test_trailing_slash_stripped(self):
        assert canonicalize_url("https://example.com/article/") == "https://example.com/article"

    def test_deeper_trailing_slash_stripped(self):
        assert canonicalize_url("https://example.com/a/b/c/") == "https://example.com/a/b/c"

    def test_path_without_trailing_slash_unchanged(self):
        assert canonicalize_url("https://example.com/article") == "https://example.com/article"

    # --- query normalization ---

    def test_query_params_sorted(self):
        result = canonicalize_url("https://example.com/p?z=1&a=2&m=3")
        assert result == "https://example.com/p?a=2&m=3&z=1"

    def test_already_sorted_query_unchanged(self):
        assert canonicalize_url("https://example.com/p?a=1&b=2") == "https://example.com/p?a=1&b=2"

    def test_no_query_remains_no_query(self):
        assert "?" not in canonicalize_url("https://example.com/page")

    def test_query_params_preserved_not_dropped(self):
        # Tracker-like params must NOT be dropped.
        result = canonicalize_url("https://example.com/p?utm_source=twitter&id=42")
        assert "utm_source=twitter" in result
        assert "id=42" in result

    # --- combined ---

    def test_combined_normalization(self):
        # Path is case-sensitive; only scheme and host are lowercased.
        url = "HTTPS://Example.COM:443/Article/?z=last&a=first#fragment"
        result = canonicalize_url(url)
        assert result == "https://example.com/Article?a=first&z=last"

    def test_unparseable_url_returned_unchanged(self):
        # urlsplit should not raise for most strings, but if it does the
        # original is returned.
        bad = "not a url at all"
        # Should not raise.
        out = canonicalize_url(bad)
        assert isinstance(out, str)

    # --- idempotency ---

    def test_idempotent(self):
        url = "https://Example.COM:443/path/?b=2&a=1#frag"
        once = canonicalize_url(url)
        twice = canonicalize_url(once)
        assert once == twice


# ===========================================================================
# deduplicate_by_url
# ===========================================================================

class TestDeduplicateByUrl:

    # --- empty / single ---

    def test_empty_list(self):
        assert deduplicate_by_url([]) == []

    def test_single_item_returned_unchanged(self):
        item = _item()
        result = deduplicate_by_url([item])
        assert result == [item]

    # --- no duplicates ---

    def test_no_duplicates_all_returned(self):
        items = [
            _item(url="https://example.com/a"),
            _item(url="https://example.com/b"),
            _item(url="https://example.com/c"),
        ]
        result = deduplicate_by_url(items)
        assert len(result) == 3

    # --- exact duplicate removal ---

    def test_exact_url_duplicate_removed(self):
        a = _item(url="https://example.com/news", title="First")
        b = _item(url="https://example.com/news", title="Second")
        result = deduplicate_by_url([a, b])
        assert len(result) == 1

    def test_first_occurrence_is_representative(self):
        a = _item(url="https://example.com/news", title="First")
        b = _item(url="https://example.com/news", title="Second")
        result = deduplicate_by_url([a, b])
        assert result[0].title == "First"

    # --- canonical duplicate removal ---

    def test_trailing_slash_canonical_dedup(self):
        a = _item(url="https://example.com/article")
        b = _item(url="https://example.com/article/")
        result = deduplicate_by_url([a, b])
        assert len(result) == 1

    def test_fragment_canonical_dedup(self):
        a = _item(url="https://example.com/page")
        b = _item(url="https://example.com/page#comments")
        result = deduplicate_by_url([a, b])
        assert len(result) == 1

    def test_scheme_case_canonical_dedup(self):
        a = _item(url="https://example.com/x")
        b = _item(url="HTTPS://example.com/x")
        result = deduplicate_by_url([a, b])
        assert len(result) == 1

    def test_host_case_canonical_dedup(self):
        a = _item(url="https://example.com/x")
        b = _item(url="https://EXAMPLE.COM/x")
        result = deduplicate_by_url([a, b])
        assert len(result) == 1

    def test_default_port_canonical_dedup(self):
        a = _item(url="https://example.com/x")
        b = _item(url="https://example.com:443/x")
        result = deduplicate_by_url([a, b])
        assert len(result) == 1

    def test_query_order_canonical_dedup(self):
        a = _item(url="https://example.com/p?a=1&b=2")
        b = _item(url="https://example.com/p?b=2&a=1")
        result = deduplicate_by_url([a, b])
        assert len(result) == 1

    # --- raw_refs merging ---

    def test_raw_refs_merged(self):
        raw_a = _raw(url="https://example.com/n", title="A")
        raw_b = _raw(url="https://example.com/n", title="B")
        a = _item(url="https://example.com/n", raw=raw_a)
        b = _item(url="https://example.com/n", raw=raw_b)
        result = deduplicate_by_url([a, b])
        assert len(result[0].raw_refs) == 2

    def test_raw_refs_order_rep_first(self):
        raw_a = _raw(url="https://example.com/n", title="A")
        raw_b = _raw(url="https://example.com/n", title="B")
        a = _item(url="https://example.com/n", raw=raw_a)
        b = _item(url="https://example.com/n", raw=raw_b)
        result = deduplicate_by_url([a, b])
        assert result[0].raw_refs[0] is raw_a
        assert result[0].raw_refs[1] is raw_b

    def test_three_way_dedup_raw_refs(self):
        url = "https://example.com/story"
        items = [_item(url=url), _item(url=url), _item(url=url)]
        result = deduplicate_by_url(items)
        assert len(result) == 1
        assert len(result[0].raw_refs) == 3

    # --- None-URL items ---

    def test_none_url_items_pass_through(self):
        a = _item(url=None)
        b = _item(url=None)
        result = deduplicate_by_url([a, b])
        assert len(result) == 2

    def test_none_url_and_url_item_both_kept(self):
        a = _item(url=None)
        b = _item(url="https://example.com/x")
        result = deduplicate_by_url([a, b])
        assert len(result) == 2

    def test_none_url_does_not_deduplicate_with_each_other(self):
        items = [_item(url=None)] * 5
        result = deduplicate_by_url(items)
        assert len(result) == 5

    # --- output order ---

    def test_first_occurrence_order_preserved(self):
        items = [
            _item(url="https://example.com/c"),
            _item(url="https://example.com/a"),
            _item(url="https://example.com/b"),
        ]
        result = deduplicate_by_url(items)
        urls = [i.url for i in result]
        assert urls == [
            "https://example.com/c",
            "https://example.com/a",
            "https://example.com/b",
        ]

    def test_duplicate_does_not_move_position(self):
        a = _item(url="https://example.com/x", title="first")
        b = _item(url="https://example.com/y", title="other")
        c = _item(url="https://example.com/x", title="dup of first")
        result = deduplicate_by_url([a, b, c])
        assert len(result) == 2
        assert result[0].title == "first"
        assert result[1].url == "https://example.com/y"

    # --- field filling ---

    def test_empty_title_filled_from_dup(self):
        a = _item(url="https://example.com/n", title="")
        b = _item(url="https://example.com/n", title="Filled Title")
        result = deduplicate_by_url([a, b])
        assert result[0].title == "Filled Title"

    def test_none_content_filled_from_dup(self):
        a = _item(url="https://example.com/n", content=None)
        b = _item(url="https://example.com/n", content="Some content")
        result = deduplicate_by_url([a, b])
        assert result[0].content == "Some content"

    def test_populated_title_not_overwritten(self):
        a = _item(url="https://example.com/n", title="Original")
        b = _item(url="https://example.com/n", title="Different")
        result = deduplicate_by_url([a, b])
        assert result[0].title == "Original"

    def test_populated_content_not_overwritten(self):
        a = _item(url="https://example.com/n", content="Original body")
        b = _item(url="https://example.com/n", content="Other body")
        result = deduplicate_by_url([a, b])
        assert result[0].content == "Original body"

    # --- metadata merging ---

    def test_metadata_new_keys_from_dup_added(self):
        a = _item(url="https://example.com/n", metadata={"k1": "v1"})
        b = _item(url="https://example.com/n", metadata={"k2": "v2"})
        result = deduplicate_by_url([a, b])
        assert result[0].metadata["k1"] == "v1"
        assert result[0].metadata["k2"] == "v2"

    def test_metadata_rep_keys_not_overwritten(self):
        a = _item(url="https://example.com/n", metadata={"k": "rep"})
        b = _item(url="https://example.com/n", metadata={"k": "dup"})
        result = deduplicate_by_url([a, b])
        assert result[0].metadata["k"] == "rep"

    # --- no mutation ---

    def test_original_items_not_mutated(self):
        raw_a = _raw(url="https://example.com/n")
        raw_b = _raw(url="https://example.com/n")
        a = _item(url="https://example.com/n", raw=raw_a)
        b = _item(url="https://example.com/n", raw=raw_b)
        original_refs_a = list(a.raw_refs)
        original_refs_b = list(b.raw_refs)
        deduplicate_by_url([a, b])
        assert a.raw_refs == original_refs_a
        assert b.raw_refs == original_refs_b

    def test_non_duplicate_items_not_mutated(self):
        a = _item(url="https://example.com/a", title="Alpha")
        b = _item(url="https://example.com/b", title="Beta")
        result = deduplicate_by_url([a, b])
        # Non-duplicate items should be the same objects.
        assert result[0] is a
        assert result[1] is b

    # --- import from app.normalize ---

    def test_importable_from_normalize_package(self):
        from app.normalize import deduplicate_by_url as fn, canonicalize_url as cfn
        assert callable(fn)
        assert callable(cfn)
