"""tests/test_source_credibility.py — Tests for source credibility grading.

Coverage
--------
TestRulesPrecedence:
  - Official domain beats generic web source (rule1 > rule7)
  - Official domain beats established media provider (rule1 > rule3)
  - Official provider token beats established media token (rule2 > rule3)
  - Established media provider beats generic web (rule3 > rule7)
  - Established media URL beats generic web (rule4 > rule7)
  - Copilot research beats generic web / not graded as score 2 (rule5 < rule7)
  - AkShare beats generic web (rule6 > rule7)
  - Unknown beats nothing — is always 0 (rule8)

TestOfficialSources:
  - gov.cn domain → score 5
  - xinhuanet.com domain → score 5
  - people.com.cn domain → score 5
  - sse.com.cn (Shanghai Stock Exchange) → score 5
  - szse.cn (Shenzhen Stock Exchange) → score 5
  - cninfo.com.cn → score 5
  - provider "xinhua" → score 5
  - provider "gov" → score 5
  - label is "official" for score 5

TestEstablishedMedia:
  - provider "cctv" → score 4
  - provider "cctv-news" (compound) → score 4 (substring match)
  - provider "xinhua" → score 5 (NOT 4: xinhua is official)
  - provider "caixin" → score 4
  - provider "bloomberg" → score 4
  - provider "reuters" → score 4
  - provider "21jingji" → score 4
  - provider "yicai" → score 4
  - provider "thepaper" → score 4
  - URL cctv.com → score 4
  - URL caixin.com → score 4
  - URL bloomberg.com → score 4
  - URL reuters.com → score 4
  - label is "high_confidence_media" for score 4

TestResearchTransport:
  - source "copilot_research" → score 1, not 0/2
  - provider "web-access" → score 1
  - provider "WEB-ACCESS" (uppercase) → score 1
  - copilot_research with official-looking URL still → score ≤ 1? No: URL rule fires first.
    Actually: official domain URL should still win (rule1 > rule5). Verified here.
  - copilot_research with no URL → score 1
  - label is "research_transport" for score 1

TestAkShare:
  - source "akshare" → score 3
  - label is "structured_data" for score 3

TestGenericWeb:
  - source "web", no strong URL/provider → score 2
  - label is "generic_web" for score 2

TestUnknown:
  - empty/missing source and provider and URL → score 0
  - label is "unknown" for score 0
  - unrecognised source string → score 0

TestMetadata:
  - metadata key is "source_credibility"
  - metadata contains "score", "label", "matched_rule", "reason"
  - score is int 0–5
  - label is non-empty string
  - matched_rule is non-empty string
  - reason is non-empty string
  - original item not mutated (no shared metadata dict)
  - raw_refs preserved in output item
  - output metadata has all pre-existing keys intact

TestBatchGradeCredibility:
  - output count equals input count
  - output order preserved (same titles in same order)
  - all items gain "source_credibility" key
  - empty input list → empty output list

TestImportExportSurface:
  - grade_item_credibility importable from app.normalize
  - grade_credibility importable from app.normalize
  - grade_item_credibility importable directly from app.normalize.source_credibility
  - grade_credibility importable directly from app.normalize.source_credibility
  - both names present in app.normalize.__all__
"""

from __future__ import annotations

import pytest

from app.models.raw_document import RawDocument
from app.models.news_item import NewsItem


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _raw(source: str = "web", provider: str = "test", url: str | None = None) -> RawDocument:
    return RawDocument(
        source=source,
        provider=provider,
        title="Test title",
        content="Test content",
        url=url or "",
        date="2025-01-01",
        metadata={},
    )


def _item(
    source: str = "web",
    provider: str = "test",
    url: str | None = None,
    extra_meta: dict | None = None,
) -> NewsItem:
    raw = _raw(source=source, provider=provider, url=url or "")
    item = NewsItem(
        title="Test title",
        content="Test content",
        url=url,
        published_at="2025-01-01",
        source=source,
        provider=provider,
        raw_refs=[raw],
        metadata=dict(extra_meta or {}),
    )
    return item


# ---------------------------------------------------------------------------
# TestRulesPrecedence
# ---------------------------------------------------------------------------

class TestRulesPrecedence:
    """Verify that rule ordering is deterministic and higher rules win."""

    def test_official_domain_beats_generic_web(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="unknown", url="https://www.mofcom.gov.cn/article/1.html")
        result = grade_item_credibility(item)
        cred = result.metadata["source_credibility"]
        assert cred["score"] == 5, f"expected 5, got {cred}"
        assert "rule1" in cred["matched_rule"]

    def test_official_domain_beats_established_media_provider(self):
        from app.normalize import grade_item_credibility
        # Even though provider matches cctv (score-4 rule), gov.cn URL should win.
        item = _item(source="web", provider="cctv", url="https://www.gov.cn/news/1.html")
        result = grade_item_credibility(item)
        cred = result.metadata["source_credibility"]
        assert cred["score"] == 5

    def test_official_provider_beats_established_media(self):
        from app.normalize import grade_item_credibility
        # provider "xinhua" is in both official and established lists;
        # rule2 (official provider) fires before rule3.
        item = _item(source="web", provider="xinhua")
        result = grade_item_credibility(item)
        cred = result.metadata["source_credibility"]
        assert cred["score"] == 5
        assert "rule2" in cred["matched_rule"]

    def test_established_media_provider_beats_generic_web(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="caixin")
        result = grade_item_credibility(item)
        cred = result.metadata["source_credibility"]
        assert cred["score"] == 4
        assert "rule3" in cred["matched_rule"]

    def test_established_media_url_beats_generic_web(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="unknown_provider", url="https://www.caixin.com/story/1.html")
        result = grade_item_credibility(item)
        cred = result.metadata["source_credibility"]
        assert cred["score"] == 4
        assert "rule4" in cred["matched_rule"]

    def test_copilot_research_not_promoted_to_generic_web(self):
        from app.normalize import grade_item_credibility
        item = _item(source="copilot_research", provider="web-access")
        result = grade_item_credibility(item)
        cred = result.metadata["source_credibility"]
        assert cred["score"] == 1
        assert cred["score"] != 2

    def test_akshare_beats_generic_web(self):
        from app.normalize import grade_item_credibility
        item = _item(source="akshare", provider="akshare")
        result = grade_item_credibility(item)
        cred = result.metadata["source_credibility"]
        assert cred["score"] == 3
        assert cred["score"] > 2

    def test_unknown_is_lowest(self):
        from app.normalize import grade_item_credibility
        item = _item(source="unknown_source_xyz", provider="nobody", url=None)
        result = grade_item_credibility(item)
        cred = result.metadata["source_credibility"]
        assert cred["score"] == 0

    def test_generic_web_outranks_unknown(self):
        from app.normalize import grade_item_credibility
        web_item = _item(source="web", provider="nobody")
        unknown_item = _item(source="xyz", provider="nobody")
        web_score = grade_item_credibility(web_item).metadata["source_credibility"]["score"]
        unknown_score = grade_item_credibility(unknown_item).metadata["source_credibility"]["score"]
        assert web_score > unknown_score


# ---------------------------------------------------------------------------
# TestOfficialSources
# ---------------------------------------------------------------------------

class TestOfficialSources:
    def test_gov_cn_domain(self):
        from app.normalize import grade_item_credibility
        item = _item(url="https://www.ndrc.gov.cn/fzggw/jgsj/1.htm")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 5

    def test_xinhuanet_domain(self):
        from app.normalize import grade_item_credibility
        item = _item(url="http://www.xinhuanet.com/english/2025-01/01/c_1.htm")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 5

    def test_people_com_cn_domain(self):
        from app.normalize import grade_item_credibility
        item = _item(url="https://finance.people.com.cn/n1/2025/0601/c1004-1.html")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 5

    def test_sse_domain(self):
        from app.normalize import grade_item_credibility
        item = _item(url="http://www.sse.com.cn/disclosure/bond/1.htm")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 5

    def test_szse_domain(self):
        from app.normalize import grade_item_credibility
        item = _item(url="https://www.szse.cn/disclosure/listed/notice/1.htm")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 5

    def test_cninfo_domain(self):
        from app.normalize import grade_item_credibility
        item = _item(url="http://www.cninfo.com.cn/new/announcement/1.html")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 5

    def test_provider_xinhua(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="xinhua")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 5

    def test_provider_gov(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="gov")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 5

    def test_label_is_official(self):
        from app.normalize import grade_item_credibility
        item = _item(url="https://www.csrc.gov.cn/notice/1.html")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["label"] == "official"


# ---------------------------------------------------------------------------
# TestEstablishedMedia
# ---------------------------------------------------------------------------

class TestEstablishedMedia:
    def test_provider_cctv(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="cctv")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_provider_cctv_compound(self):
        from app.normalize import grade_item_credibility
        # Compound label "cctv-news" should still match via substring.
        item = _item(provider="cctv-news")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_provider_xinhua_is_official_not_media(self):
        from app.normalize import grade_item_credibility
        # xinhua is also in official-provider tokens; should be score 5.
        item = _item(provider="xinhua")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 5

    def test_provider_caixin(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="caixin")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_provider_bloomberg(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="bloomberg")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_provider_reuters(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="reuters")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_provider_21jingji(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="21jingji")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_provider_yicai(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="yicai")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_provider_thepaper(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="thepaper")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_url_cctv_com(self):
        from app.normalize import grade_item_credibility
        item = _item(url="https://news.cctv.com/2025/06/01/ARTI123.shtml")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_url_caixin_com(self):
        from app.normalize import grade_item_credibility
        item = _item(url="https://www.caixin.com/2025-06-01/100000001.html")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_url_bloomberg_com(self):
        from app.normalize import grade_item_credibility
        item = _item(url="https://www.bloomberg.com/news/articles/2025-06-01/story")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_url_reuters_com(self):
        from app.normalize import grade_item_credibility
        item = _item(url="https://www.reuters.com/technology/story-2025-06-01/")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 4

    def test_label_is_high_confidence_media(self):
        from app.normalize import grade_item_credibility
        item = _item(provider="cctv")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["label"] == "high_confidence_media"

    def test_generic_web_lower_than_established_media(self):
        from app.normalize import grade_item_credibility
        generic = _item(source="web", provider="nobody")
        media = _item(source="web", provider="caixin")
        generic_score = grade_item_credibility(generic).metadata["source_credibility"]["score"]
        media_score = grade_item_credibility(media).metadata["source_credibility"]["score"]
        assert media_score > generic_score


# ---------------------------------------------------------------------------
# TestResearchTransport
# ---------------------------------------------------------------------------

class TestResearchTransport:
    def test_copilot_research_source_is_score_1(self):
        from app.normalize import grade_item_credibility
        item = _item(source="copilot_research", provider="web-access")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 1

    def test_copilot_research_not_unknown(self):
        from app.normalize import grade_item_credibility
        item = _item(source="copilot_research", provider="web-access")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] != 0

    def test_copilot_research_not_high(self):
        from app.normalize import grade_item_credibility
        item = _item(source="copilot_research", provider="web-access")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] < 2

    def test_provider_web_access_is_score_1(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="web-access")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 1

    def test_provider_web_access_uppercase(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="WEB-ACCESS")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 1

    def test_official_url_overrides_copilot_research_source(self):
        # Rule 1 (official domain) fires before rule 5 (copilot_research)
        from app.normalize import grade_item_credibility
        item = _item(source="copilot_research", provider="web-access",
                     url="https://www.gov.cn/news/1.html")
        result = grade_item_credibility(item)
        # Official URL should still win
        assert result.metadata["source_credibility"]["score"] == 5

    def test_copilot_research_no_url_is_score_1(self):
        from app.normalize import grade_item_credibility
        item = _item(source="copilot_research", provider="web-access", url=None)
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 1

    def test_label_is_research_transport(self):
        from app.normalize import grade_item_credibility
        item = _item(source="copilot_research", provider="web-access")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["label"] == "research_transport"

    def test_matched_rule_is_rule5(self):
        from app.normalize import grade_item_credibility
        item = _item(source="copilot_research", provider="web-access")
        result = grade_item_credibility(item)
        assert "rule5" in result.metadata["source_credibility"]["matched_rule"]


# ---------------------------------------------------------------------------
# TestAkShare
# ---------------------------------------------------------------------------

class TestAkShare:
    def test_akshare_score_3(self):
        from app.normalize import grade_item_credibility
        item = _item(source="akshare", provider="akshare")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 3

    def test_akshare_label(self):
        from app.normalize import grade_item_credibility
        item = _item(source="akshare", provider="akshare")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["label"] == "structured_data"

    def test_akshare_matched_rule(self):
        from app.normalize import grade_item_credibility
        item = _item(source="akshare", provider="akshare")
        result = grade_item_credibility(item)
        assert "rule6" in result.metadata["source_credibility"]["matched_rule"]

    def test_akshare_outranks_generic_web(self):
        from app.normalize import grade_item_credibility
        akshare = _item(source="akshare")
        web = _item(source="web")
        assert (grade_item_credibility(akshare).metadata["source_credibility"]["score"] >
                grade_item_credibility(web).metadata["source_credibility"]["score"])


# ---------------------------------------------------------------------------
# TestGenericWeb
# ---------------------------------------------------------------------------

class TestGenericWeb:
    def test_generic_web_score_2(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="some_blog", url="https://some-blog.com/post/1")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 2

    def test_generic_web_label(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="nobody")
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["label"] == "generic_web"

    def test_generic_web_matched_rule(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="nobody")
        result = grade_item_credibility(item)
        assert "rule7" in result.metadata["source_credibility"]["matched_rule"]


# ---------------------------------------------------------------------------
# TestUnknown
# ---------------------------------------------------------------------------

class TestUnknown:
    def test_empty_source_and_provider(self):
        from app.normalize import grade_item_credibility
        item = _item(source="", provider="", url=None)
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 0

    def test_unrecognised_source(self):
        from app.normalize import grade_item_credibility
        item = _item(source="mystery_source_xyz", provider="nobody_special", url=None)
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["score"] == 0

    def test_unknown_label(self):
        from app.normalize import grade_item_credibility
        item = _item(source="mystery", provider="mystery", url=None)
        result = grade_item_credibility(item)
        assert result.metadata["source_credibility"]["label"] == "unknown"

    def test_matched_rule_is_rule8(self):
        from app.normalize import grade_item_credibility
        item = _item(source="mystery", provider="mystery", url=None)
        result = grade_item_credibility(item)
        assert "rule8" in result.metadata["source_credibility"]["matched_rule"]


# ---------------------------------------------------------------------------
# TestMetadata
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_metadata_key_name(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="caixin")
        result = grade_item_credibility(item)
        assert "source_credibility" in result.metadata

    def test_metadata_has_score(self):
        from app.normalize import grade_item_credibility
        cred = grade_item_credibility(_item()).metadata["source_credibility"]
        assert "score" in cred

    def test_metadata_has_label(self):
        from app.normalize import grade_item_credibility
        cred = grade_item_credibility(_item()).metadata["source_credibility"]
        assert "label" in cred

    def test_metadata_has_matched_rule(self):
        from app.normalize import grade_item_credibility
        cred = grade_item_credibility(_item()).metadata["source_credibility"]
        assert "matched_rule" in cred

    def test_metadata_has_reason(self):
        from app.normalize import grade_item_credibility
        cred = grade_item_credibility(_item()).metadata["source_credibility"]
        assert "reason" in cred

    def test_score_is_int(self):
        from app.normalize import grade_item_credibility
        cred = grade_item_credibility(_item()).metadata["source_credibility"]
        assert isinstance(cred["score"], int)

    def test_score_in_range(self):
        from app.normalize import grade_item_credibility
        for source, provider, url in [
            ("web", "caixin", None),
            ("akshare", "akshare", None),
            ("copilot_research", "web-access", None),
            ("web", "nobody", None),
            ("", "", None),
            ("web", "nobody", "https://www.gov.cn/news/1.html"),
        ]:
            item = _item(source=source, provider=provider, url=url)
            cred = grade_item_credibility(item).metadata["source_credibility"]
            assert 0 <= cred["score"] <= 5, f"score out of range: {cred}"

    def test_label_is_string(self):
        from app.normalize import grade_item_credibility
        cred = grade_item_credibility(_item()).metadata["source_credibility"]
        assert isinstance(cred["label"], str) and cred["label"]

    def test_matched_rule_is_string(self):
        from app.normalize import grade_item_credibility
        cred = grade_item_credibility(_item()).metadata["source_credibility"]
        assert isinstance(cred["matched_rule"], str) and cred["matched_rule"]

    def test_reason_is_string(self):
        from app.normalize import grade_item_credibility
        cred = grade_item_credibility(_item()).metadata["source_credibility"]
        assert isinstance(cred["reason"], str) and cred["reason"]

    def test_original_item_not_mutated(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="caixin")
        original_meta = dict(item.metadata)
        _ = grade_item_credibility(item)
        assert item.metadata == original_meta

    def test_original_metadata_dict_not_shared(self):
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="caixin")
        result = grade_item_credibility(item)
        # Modifying result metadata should not affect original
        result.metadata["source_credibility"]["score"] = 999
        assert "source_credibility" not in item.metadata

    def test_raw_refs_preserved(self):
        from app.normalize import grade_item_credibility
        raw = _raw()
        item = NewsItem(
            title="t", content="c", url=None,
            published_at="2025-01-01",
            source="web", provider="nobody",
            raw_refs=[raw],
            metadata={},
        )
        result = grade_item_credibility(item)
        assert result.raw_refs == [raw]

    def test_pre_existing_metadata_keys_preserved(self):
        from app.normalize import grade_item_credibility
        item = _item(extra_meta={"existing_key": "existing_value"})
        result = grade_item_credibility(item)
        assert result.metadata["existing_key"] == "existing_value"
        assert "source_credibility" in result.metadata

    def test_repeated_call_overwrites_previous_score(self):
        # Calling grade_item_credibility twice should overwrite old score.
        from app.normalize import grade_item_credibility
        item = _item(source="web", provider="nobody")
        once = grade_item_credibility(item)
        twice = grade_item_credibility(once)
        # Score should be stable (same item, same rule)
        assert (once.metadata["source_credibility"]["score"] ==
                twice.metadata["source_credibility"]["score"])


# ---------------------------------------------------------------------------
# TestBatchGradeCredibility
# ---------------------------------------------------------------------------

class TestBatchGradeCredibility:
    def test_output_count_equals_input_count(self):
        from app.normalize import grade_credibility
        items = [_item(source="web"), _item(source="akshare"), _item(source="copilot_research", provider="web-access")]
        result = grade_credibility(items)
        assert len(result) == 3

    def test_output_order_preserved(self):
        from app.normalize import grade_credibility
        items = [
            _item(source="web"),
            _item(source="akshare"),
            _item(source="copilot_research", provider="web-access"),
        ]
        # Use titles to track order
        items[0] = NewsItem(title="first", content=None, url=None,
                            published_at="", source="web", provider="nobody", raw_refs=[_raw()])
        items[1] = NewsItem(title="second", content=None, url=None,
                            published_at="", source="akshare", provider="akshare", raw_refs=[_raw()])
        items[2] = NewsItem(title="third", content=None, url=None,
                            published_at="", source="copilot_research", provider="web-access",
                            raw_refs=[_raw()])
        result = grade_credibility(items)
        assert [r.title for r in result] == ["first", "second", "third"]

    def test_all_items_have_source_credibility_key(self):
        from app.normalize import grade_credibility
        items = [_item(source="web"), _item(source="akshare")]
        result = grade_credibility(items)
        for r in result:
            assert "source_credibility" in r.metadata

    def test_empty_input(self):
        from app.normalize import grade_credibility
        assert grade_credibility([]) == []

    def test_batch_scores_independent(self):
        from app.normalize import grade_credibility
        items = [
            _item(source="web", provider="caixin"),        # should be 4
            _item(source="copilot_research", provider="web-access"),  # should be 1
            _item(source="", provider="", url=None),       # should be 0
        ]
        result = grade_credibility(items)
        assert result[0].metadata["source_credibility"]["score"] == 4
        assert result[1].metadata["source_credibility"]["score"] == 1
        assert result[2].metadata["source_credibility"]["score"] == 0


# ---------------------------------------------------------------------------
# TestImportExportSurface
# ---------------------------------------------------------------------------

class TestImportExportSurface:
    def test_grade_item_credibility_from_app_normalize(self):
        from app.normalize import grade_item_credibility
        assert callable(grade_item_credibility)

    def test_grade_credibility_from_app_normalize(self):
        from app.normalize import grade_credibility
        assert callable(grade_credibility)

    def test_grade_item_credibility_from_module(self):
        from app.normalize.source_credibility import grade_item_credibility
        assert callable(grade_item_credibility)

    def test_grade_credibility_from_module(self):
        from app.normalize.source_credibility import grade_credibility
        assert callable(grade_credibility)

    def test_both_names_in_all(self):
        import app.normalize as pkg
        assert "grade_item_credibility" in pkg.__all__
        assert "grade_credibility" in pkg.__all__

    def test_same_object_via_both_paths(self):
        from app.normalize import grade_item_credibility as a
        from app.normalize.source_credibility import grade_item_credibility as b
        assert a is b

    def test_batch_same_object_via_both_paths(self):
        from app.normalize import grade_credibility as a
        from app.normalize.source_credibility import grade_credibility as b
        assert a is b
