"""app/normalize/text_dedup.py — text-hash deduplication for NewsItem lists.

Pipeline stage
--------------
list[NewsItem]  →  deduplicate_by_text  →  list[NewsItem]

Deduplication basis
-------------------
Two ``NewsItem`` records are considered duplicates when their **text
fingerprint** collides.  The fingerprint is a SHA-256 digest computed over
the concatenation of the normalized title and body:

    fingerprint = SHA-256( normalize(title) + "\\n" + normalize(content) )

where ``normalize`` applies (in order):

1. Unicode NFC normalization — ensures canonically-equivalent code-point
   sequences map to the same bytes.
2. Lower-casing (``str.casefold``).
3. Whitespace collapsing — all runs of whitespace (including newlines, tabs,
   zero-width spaces) are replaced by a single ASCII space, then leading/
   trailing whitespace is stripped.

These transformations are conservative and deterministic: no information is
lost from a dedup perspective, and the same logical text will always produce
the same fingerprint regardless of cosmetic encoding differences.

Blank-text pass-through
-----------------------
If the combined normalized text (title + content) is empty or consists solely
of whitespace *before* collapsing, the item is considered "effectively blank"
and is **always passed through without participating in deduplication**.  This
prevents items that carry no textual content from being incorrectly merged.

Assumption (autonomous decision)
---------------------------------
The text scope used for hashing is ``title + body`` together.  This was
chosen autonomously because the user was unavailable; the decision is
recorded in ``dev/normalization-pipeline/normalization-pipeline-context.md``.

Merge semantics
---------------
Identical to URL dedup (shared helper ``_item_merge.merge_news_items``):
- First occurrence is the representative; its position in the output is stable.
- All ``raw_refs`` from later duplicates are appended to the representative's
  ``raw_refs`` (representative's refs first).
- Missing scalar fields on the representative may be filled from the first
  duplicate that supplies a non-empty value.
- ``metadata`` is shallow-merged; representative keys win.
- Original ``NewsItem`` instances are never mutated.

Public API
----------
``text_fingerprint(title, content) -> str``
    Compute the SHA-256 text fingerprint for a title/content pair.
    Exported for testing and external reuse.

``deduplicate_by_text(items) -> list[NewsItem]``
    Deduplicate a list of ``NewsItem`` by text fingerprint.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from app.models.news_item import NewsItem
from app.normalize._item_merge import merge_news_items


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Apply conservative, deterministic normalizations for fingerprinting.

    Steps
    -----
    1. Unicode NFC normalization.
    2. Case-folding (lower-case in a Unicode-aware way).
    3. Whitespace collapsing: all whitespace runs → single space, strip ends.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.casefold()
    text = re.sub(r"[\s\u200b\u200c\u200d\ufeff]+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def text_fingerprint(title: str, content: str | None) -> str:
    """Return the SHA-256 text fingerprint for *title* + *content*.

    The fingerprint is suitable for deduplication: two items with logically
    identical text (same casing, encoding, whitespace differences) will
    produce the same fingerprint.

    Parameters
    ----------
    title:
        The item's headline text.  May be empty but never ``None``.
    content:
        The item's body text.  ``None`` is treated as empty.

    Returns
    -------
    str
        64-character lowercase hex digest (SHA-256).
    """
    norm_title = _normalize_text(title)
    norm_content = _normalize_text(content or "")
    combined = norm_title + "\n" + norm_content
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _is_blank(title: str, content: str | None) -> bool:
    """Return ``True`` when the combined text is effectively empty.

    An item is considered blank when ``normalize(title) + normalize(content)``
    yields an empty string after whitespace collapsing.  Such items are passed
    through the dedup stage without participating in fingerprint matching.
    """
    return (_normalize_text(title) + _normalize_text(content or "")) == ""


# ---------------------------------------------------------------------------
# Public dedup stage
# ---------------------------------------------------------------------------

def deduplicate_by_text(items: list[NewsItem]) -> list[NewsItem]:
    """Deduplicate *items* by text fingerprint, merging ``raw_refs`` on collisions.

    Items whose combined title+content is effectively blank are **never**
    considered duplicates of each other or of content-bearing items; each
    such item passes through unchanged.

    Ordering guarantee
    ------------------
    The first occurrence of each fingerprint determines both the
    representative item and its position in the output list.  Subsequent
    duplicates are merged into the representative (their ``raw_refs`` are
    appended) but do not affect output order.

    Field filling
    -------------
    Same conservative rules as URL dedup — see
    ``app.normalize._item_merge.merge_news_items`` for details.

    Parameters
    ----------
    items:
        Input list of ``NewsItem`` objects, possibly containing text duplicates.

    Returns
    -------
    list[NewsItem]
        Deduplicated list preserving first-occurrence order.  No input
        instance is mutated; merged items are new objects.
    """
    seen: dict[str, int] = {}  # fingerprint → index in `result`
    result: list[NewsItem] = []

    for item in items:
        if _is_blank(item.title, item.content):
            # Blank items always pass through without participating in dedup.
            result.append(item)
            continue

        key = text_fingerprint(item.title, item.content)

        if key not in seen:
            seen[key] = len(result)
            result.append(item)
        else:
            idx = seen[key]
            rep = result[idx]
            result[idx] = merge_news_items(rep, item)

    return result
