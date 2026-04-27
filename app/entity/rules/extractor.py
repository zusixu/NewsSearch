"""
基础规则抽取引擎（Rule-based Extractor）

匹配策略
--------
- **含 CJK 字符的种子词**（如"人工智能"、"SK 海力士"）：
  大小写不敏感的子串匹配。CJK 文本中不存在词边界概念，直接子串查找即可。
- **纯 ASCII / 数字种子词**（如 ``AI``、``GPU``、``LLM``）：
  使用正则 ``\b…\b`` 词边界匹配（re.IGNORECASE），防止短 ASCII token 在
  无关词内误命中（例如 ``AI`` 不应在 ``PAID`` 或 ``BRAIN`` 中触发）。

输出
----
返回按 ``(start, end, label_id)`` 升序排列的 :class:`Hit` 列表，保证稳定顺序。
同一位置同一标签只保留一条记录（去重）。

注意：本模块不实现模型辅助抽取，也不涉及最终标签化输出结构；
这两部分分别由 task.md 第四项和第六项负责。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Literal, Tuple

from app.entity.entity_types import ENTITY_TYPE_TAXONOMY
from app.entity.themes import THEME_TAXONOMY

# ---------------------------------------------------------------------------
# CJK Unicode 范围检测（U+4E00-U+9FFF CJK 统一汉字核心区，
# 兼顾扩展 A 区 U+3400-U+4DBF、平假名/片假名 U+3040-U+30FF、韩文音节 U+AC00-U+D7AF）
# ---------------------------------------------------------------------------
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff"
    r"\u3400-\u4dbf"
    r"\u3040-\u30ff"
    r"\uac00-\ud7af]"
)


def _has_cjk(s: str) -> bool:
    """判断字符串中是否含有 CJK 字符。"""
    return bool(_CJK_RE.search(s))


def _find_occurrences(seed: str, text: str) -> List[Tuple[int, int]]:
    """
    返回 *seed* 在 *text* 中所有（非重叠）出现的 ``(start, end)`` 偏移列表。

    - 含 CJK 字符：直接大小写不敏感子串搜索
    - 纯 ASCII/数字：正则词边界匹配（re.IGNORECASE）
    """
    if not seed or not text:
        return []

    if _has_cjk(seed):
        # CJK 路径：直接子串查找（先折叠大小写处理夹杂的 ASCII 部分）
        seed_lower = seed.lower()
        text_lower = text.lower()
        results: List[Tuple[int, int]] = []
        pos = 0
        while True:
            idx = text_lower.find(seed_lower, pos)
            if idx == -1:
                break
            results.append((idx, idx + len(seed)))
            pos = idx + len(seed)  # 非重叠：跳过已匹配片段
        return results
    else:
        # ASCII 路径：词边界正则，防止短 token 在无关词内误命中
        pattern = re.compile(r"\b" + re.escape(seed) + r"\b", re.IGNORECASE)
        return [(m.start(), m.end()) for m in pattern.finditer(text)]


# ---------------------------------------------------------------------------
# Hit — 单次命中记录
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    """
    一次规则命中的结构化记录，为后续证据关联（节点 5）和输出结构（节点 6）提供基础。

    字段
    ----
    matched_text
        原始文本中实际命中的字符片段（``text[start:end]``）。
    start
        命中起始字符偏移（inclusive，以 Unicode 码点计）。
    end
        命中结束字符偏移（exclusive）。
    matched_seed
        触发本次命中的种子关键词或示例提及字符串。
    kind
        命中来源类型：``"theme"`` 或 ``"entity_type"``。
    label_id
        对应的 :class:`~app.entity.themes.ThemeId` 值或
        :class:`~app.entity.entity_types.EntityTypeId` 值（字符串）。
    """

    matched_text: str
    start: int
    end: int
    matched_seed: str
    kind: Literal["theme", "entity_type"]
    label_id: str


# ---------------------------------------------------------------------------
# RuleExtractor
# ---------------------------------------------------------------------------


class RuleExtractor:
    """
    基于 themes.py 关键词和 entity_types.py example_mentions 的确定性规则抽取器。

    用法::

        extractor = RuleExtractor()
        hits = extractor.extract("英伟达发布最新 GPU 芯片，AI 行业高度关注。")
        for hit in hits:
            print(hit.kind, hit.label_id, hit.matched_text, hit.start, hit.end)

    实例可以反复调用 :meth:`extract`，无内部状态。
    """

    def extract(self, text: str) -> List[Hit]:
        """
        对 *text* 执行全量规则扫描，返回命中列表。

        返回值按 ``(start, end, label_id)`` 升序排列；相同位置相同标签只保留一条。
        """
        if not text or not text.strip():
            return []

        hits: List[Hit] = []
        # 用 (start, end, label_id) 去重，防止同一种子因大小写折叠重复计数
        seen: set[tuple[int, int, str]] = set()

        # ── 主题关键词扫描 ───────────────────────────────────────────────
        for theme_def in THEME_TAXONOMY.values():
            for seed in theme_def.keywords:
                for start, end in _find_occurrences(seed, text):
                    key = (start, end, theme_def.id.value)
                    if key not in seen:
                        seen.add(key)
                        hits.append(
                            Hit(
                                matched_text=text[start:end],
                                start=start,
                                end=end,
                                matched_seed=seed,
                                kind="theme",
                                label_id=theme_def.id.value,
                            )
                        )

        # ── 实体类型示例提及扫描 ─────────────────────────────────────────
        for type_def in ENTITY_TYPE_TAXONOMY.values():
            for example in type_def.example_mentions:
                for start, end in _find_occurrences(example, text):
                    key = (start, end, type_def.id.value)
                    if key not in seen:
                        seen.add(key)
                        hits.append(
                            Hit(
                                matched_text=text[start:end],
                                start=start,
                                end=end,
                                matched_seed=example,
                                kind="entity_type",
                                label_id=type_def.id.value,
                            )
                        )

        # 按位置升序排列，相同位置再按 label_id 字典序，保证确定性输出
        hits.sort(key=lambda h: (h.start, h.end, h.label_id))
        return hits
