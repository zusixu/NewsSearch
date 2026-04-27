"""app/normalize/source_credibility.py — Source credibility grading for NewsItem.

Pipeline stage
--------------
list[NewsItem]  →  grade_credibility  →  list[NewsItem]

Overview
--------
Assigns a deterministic, explainable credibility score (0–5) to each
``NewsItem`` based on its ``source``, ``provider``, and ``url`` fields.
The result is stored in ``metadata["source_credibility"]`` and never
written to the ``source`` / ``provider`` / ``url`` fields themselves.

Score scale (mirrors ``news_items.source_credibility`` in schema.sql)
----------------------------------------------------------------------
  5 — Official / primary government source
      Domains clearly belonging to government and regulatory bodies
      (e.g. ``*.gov.cn``, ``*.people.com.cn``, ``xinhuanet.com``,
      ``mofcom.gov.cn``, ``csrc.gov.cn``, ``ndrc.gov.cn``).
  4 — Established named media / provider with direct rule match
      Well-known financial-news and broadcast media whose names appear
      explicitly in the rule table (e.g. cctv, xinhua, caixin, bloomberg,
      reuters, 21jingji, yicai, thepaper).
  3 — Structured data or curated provider without a stronger primary-signal
      Sources that carry structured/API data or have a known aggregator
      identity but do not satisfy a score-4 or score-5 rule
      (e.g. ``akshare`` adapter, RSS feeds not in score-4 list).
  2 — Generic public web source with a concrete URL / provider but no
      high-confidence match.  The ``web`` source with a resolvable URL
      lands here by default.
  1 — Derived / secondary research transport without a direct source-specific
      rule.  Applies to ``copilot_research`` source and ``web-access``
      provider, which represent secondary synthesis rather than a primary
      publication.
  0 — Insufficient signal: source, provider, and URL are all absent or
      unrecognised.

Rule precedence (applied in order; first match wins)
-----------------------------------------------------
Rule 1 — Official domain pattern (URL-based, governs score 5)
    Triggered when the URL host or path contains one of the explicit
    official-domain patterns listed in ``_OFFICIAL_DOMAIN_PATTERNS``.
Rule 2 — Official provider keyword (provider-field-based, governs score 5)
    Triggered when ``provider`` (case-insensitive) exactly matches or
    contains one of the tokens in ``_OFFICIAL_PROVIDER_TOKENS``.
Rule 3 — Established media provider (provider-field-based, governs score 4)
    Triggered when ``provider`` (case-insensitive) exactly matches or
    contains one of the tokens in ``_ESTABLISHED_MEDIA_TOKENS``.
Rule 4 — Established media URL keyword (URL-based, governs score 4)
    Triggered when the URL host contains one of the patterns in
    ``_ESTABLISHED_MEDIA_URL_PATTERNS``.
Rule 5 — Copilot research / web-access transport (source/provider, governs score 1)
    Triggered when ``source == "copilot_research"`` or
    ``provider`` contains ``"web-access"`` (case-insensitive).
    Checked *before* the generic web/akshare rules so that a
    copilot_research item is never promoted above score 1 by accident.
Rule 6 — AkShare structured data source (source-field-based, governs score 3)
    Triggered when ``source == "akshare"``.
Rule 7 — Generic web source (source-field-based, governs score 2)
    Triggered when ``source == "web"`` (and no higher rule matched).
Rule 8 — Default: unknown / insufficient signal → score 0.

Autonomous-decision record
--------------------------
The user was unavailable; the following choices were made conservatively
and are documented here for review:

* Provider matching is case-insensitive substring search (not exact match)
  so that compound labels like ``"cctv-news"`` or ``"xinhuanet"`` still match
  the ``"cctv"`` / ``"xinhua"`` tokens.
* URL domain matching uses ``urllib.parse.urlparse`` on the stored URL; if
  the URL is None, empty, or unparseable, the URL-based rules are skipped
  and only field-based rules are evaluated.
* ``copilot_research`` is checked *before* generic-web rules (Rule 5 fires
  before Rules 6–7) so that a research transport is never accidentally
  promoted to score 2 or 3.
* AkShare is graded 3 (structured / curated) rather than 4 (established media)
  because it is an API aggregator rather than a named editorial outlet.
* ``web-access`` in the ``provider`` field is treated the same as
  ``copilot_research`` in ``source`` (both score 1) because both represent
  a secondary transport / synthesis layer.
* All string comparisons are performed after ``.strip().casefold()``.
* Original ``NewsItem`` instances are never modified; the function always
  returns new ``NewsItem`` instances.

Output metadata
---------------
Every output item gains ``metadata["source_credibility"]``::

    {
        "score":        int,           # 0–5
        "label":        str,           # human-readable label
        "matched_rule": str,           # rule identifier, e.g. "rule1_official_domain"
        "reason":       str,           # short human-readable explanation
    }
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any
from urllib.parse import urlparse

from app.models.news_item import NewsItem

# ---------------------------------------------------------------------------
# Score labels
# ---------------------------------------------------------------------------

_LABELS: dict[int, str] = {
    5: "official",
    4: "high_confidence_media",
    3: "structured_data",
    2: "generic_web",
    1: "research_transport",
    0: "unknown",
}

# ---------------------------------------------------------------------------
# Rule tables
# ---------------------------------------------------------------------------

# Rule 1 — official domain patterns (checked against the URL host)
# Each entry is a substring to search for in the lowercased hostname.
_OFFICIAL_DOMAIN_PATTERNS: tuple[str, ...] = (
    ".gov.cn",
    "gov.cn",
    "xinhuanet.com",
    "people.com.cn",
    "csrc.gov.cn",
    "ndrc.gov.cn",
    "mofcom.gov.cn",
    "pbc.gov.cn",         # People's Bank of China
    "safe.gov.cn",        # State Administration of Foreign Exchange
    "stats.gov.cn",       # National Bureau of Statistics
    "miit.gov.cn",        # Ministry of Industry and Information Technology
    "sc.gov.cn",          # State Council
    "nea.gov.cn",         # National Energy Administration
    "samr.gov.cn",        # State Administration for Market Regulation
    "sse.com.cn",         # Shanghai Stock Exchange
    "szse.cn",            # Shenzhen Stock Exchange
    "cninfo.com.cn",      # CSRC-authorized disclosure platform
)

# Rule 2 — official provider keywords (checked against provider field)
_OFFICIAL_PROVIDER_TOKENS: tuple[str, ...] = (
    "xinhuanet",
    "xinhua",
    "people",          # people.com.cn / 人民网
    "csrc",
    "ndrc",
    "mofcom",
    "pbc",
    "sse",
    "szse",
    "cninfo",
    "gov",
)

# Rule 3 — established named media tokens (checked against provider field)
_ESTABLISHED_MEDIA_TOKENS: tuple[str, ...] = (
    "cctv",
    "caixin",
    "bloomberg",
    "reuters",
    "21jingji",      # 21世纪经济报道
    "yicai",         # 第一财经
    "thepaper",      # 澎湃新闻
    "chinadaily",
    "globaltimes",
    "ifeng",         # 凤凰新闻
    "sina",
    "sohu",
    "netease",
    "tencent",
    "eastmoney",     # 东方财富
    "hexun",         # 和讯
    "jrj",           # 金融界
    "cls",           # 财联社
    "stcn",          # 证券时报网
    "cnstock",       # 中国证券网
    "cnr",           # 中国之声
    "chinanews",
)

# Rule 4 — established media URL host substrings (checked against URL hostname)
_ESTABLISHED_MEDIA_URL_PATTERNS: tuple[str, ...] = (
    "cctv.com",
    "caixin.com",
    "bloomberg.com",
    "reuters.com",
    "21jingji.com",
    "yicai.com",
    "thepaper.cn",
    "chinadaily.com.cn",
    "globaltimes.cn",
    "ifeng.com",
    "sina.com.cn",
    "sohu.com",
    "163.com",         # NetEase news
    "qq.com",          # Tencent
    "eastmoney.com",
    "hexun.com",
    "jrj.com.cn",
    "cls.cn",
    "stcn.com",
    "cnstock.com",
    "cnr.cn",
    "chinanews.com.cn",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_hostname(url: str | None) -> str:
    """Return the lowercased hostname from *url*, or empty string on failure."""
    if not url:
        return ""
    try:
        return urlparse(url.strip()).hostname or ""
    except Exception:
        return ""


def _cf(text: str | None) -> str:
    """Case-fold and strip *text*; return empty string for None."""
    if not text:
        return ""
    return text.strip().casefold()


def _score_item(item: NewsItem) -> dict[str, Any]:
    """Compute and return the credibility metadata dict for *item*.

    Returns a dict with keys: ``score``, ``label``, ``matched_rule``, ``reason``.
    """
    source = _cf(item.source)
    provider = _cf(item.provider)
    hostname = _extract_hostname(item.url)

    # ------------------------------------------------------------------
    # Rule 1 — official domain (URL-based) → score 5
    # ------------------------------------------------------------------
    for pattern in _OFFICIAL_DOMAIN_PATTERNS:
        if pattern in hostname:
            return _make(
                5,
                "rule1_official_domain",
                f"URL hostname '{hostname}' matches official domain pattern '{pattern}'",
            )

    # ------------------------------------------------------------------
    # Rule 2 — official provider keyword (field-based) → score 5
    # ------------------------------------------------------------------
    for token in _OFFICIAL_PROVIDER_TOKENS:
        if token in provider:
            return _make(
                5,
                "rule2_official_provider",
                f"provider '{provider}' contains official token '{token}'",
            )

    # ------------------------------------------------------------------
    # Rule 3 — established media provider keyword (field-based) → score 4
    # ------------------------------------------------------------------
    for token in _ESTABLISHED_MEDIA_TOKENS:
        if token in provider:
            return _make(
                4,
                "rule3_established_media_provider",
                f"provider '{provider}' contains established-media token '{token}'",
            )

    # ------------------------------------------------------------------
    # Rule 4 — established media URL hostname (URL-based) → score 4
    # ------------------------------------------------------------------
    for pattern in _ESTABLISHED_MEDIA_URL_PATTERNS:
        if pattern in hostname:
            return _make(
                4,
                "rule4_established_media_url",
                f"URL hostname '{hostname}' matches established-media pattern '{pattern}'",
            )

    # ------------------------------------------------------------------
    # Rule 5 — copilot research / web-access transport → score 1
    # Checked *before* akshare and generic-web rules so that a research
    # transport is never accidentally promoted.
    # ------------------------------------------------------------------
    if source == "copilot_research" or "web-access" in provider:
        return _make(
            1,
            "rule5_research_transport",
            f"source='{source}', provider='{provider}' identified as research/synthesis transport",
        )

    # ------------------------------------------------------------------
    # Rule 6 — AkShare structured data → score 3
    # ------------------------------------------------------------------
    if source == "akshare":
        return _make(
            3,
            "rule6_akshare_structured",
            "source='akshare' is a structured-data API aggregator",
        )

    # ------------------------------------------------------------------
    # Rule 7 — generic web source → score 2
    # ------------------------------------------------------------------
    if source == "web":
        return _make(
            2,
            "rule7_generic_web",
            "source='web' with no high-confidence domain or provider match",
        )

    # ------------------------------------------------------------------
    # Rule 8 — unknown / insufficient signal → score 0
    # ------------------------------------------------------------------
    return _make(
        0,
        "rule8_unknown",
        f"no matching rule for source='{source}', provider='{provider}', hostname='{hostname}'",
    )


def _make(score: int, matched_rule: str, reason: str) -> dict[str, Any]:
    return {
        "score": score,
        "label": _LABELS[score],
        "matched_rule": matched_rule,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def grade_item_credibility(item: NewsItem) -> NewsItem:
    """Grade the source credibility of a single ``NewsItem``.

    Returns a *new* ``NewsItem`` identical to *item* except that
    ``metadata["source_credibility"]`` is set to the credibility-grading
    result dict.  The original *item* is never modified.

    Args:
        item: The ``NewsItem`` to grade.

    Returns:
        A new ``NewsItem`` with ``metadata["source_credibility"]`` populated.
    """
    cred = _score_item(item)
    new_metadata = copy.copy(item.metadata)
    new_metadata["source_credibility"] = cred
    return replace(item, metadata=new_metadata)


def grade_credibility(items: list[NewsItem]) -> list[NewsItem]:
    """Grade source credibility for every item in *items*.

    Applies :func:`grade_item_credibility` to each item, preserving the
    input order and count.  No items are merged, dropped, or reordered.

    Args:
        items: List of ``NewsItem`` objects to grade.

    Returns:
        A new list of ``NewsItem`` objects with ``metadata["source_credibility"]``
        populated on every item.
    """
    return [grade_item_credibility(item) for item in items]
