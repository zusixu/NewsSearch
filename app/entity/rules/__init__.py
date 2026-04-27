"""app.entity.rules — 基础规则抽取子包。

公开 API
--------
Hit
    单次命中记录（frozen dataclass）。
RuleExtractor
    基于种子关键词和示例提及的确定性规则抽取器。
"""

from app.entity.rules.extractor import Hit, RuleExtractor

__all__ = ["Hit", "RuleExtractor"]
