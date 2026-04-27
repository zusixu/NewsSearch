"""app.entity — 实体与主题标签体系包。"""

from app.entity.tagged_output import TaggedOutput, build_tagged_output
from app.entity.evidence import (
    EvidenceLink,
    EvidenceLinkError,
    EvidenceSpan,
    build_evidence_links,
)
from app.entity.model_extractor import (
    ModelExtractionRequest,
    ModelExtractionResponse,
    ModelExtractor,
)
from app.entity.rules import Hit, RuleExtractor
from app.entity.entity_types import (
    ENTITY_TYPE_TAXONOMY,
    EntityTypeDefinition,
    EntityTypeId,
    all_entity_types,
    entity_type_ids,
    find_types_by_mention,
    get_entity_type,
)
from app.entity.themes import (
    THEME_TAXONOMY,
    ThemeDefinition,
    ThemeId,
    all_themes,
    find_themes_by_keyword,
    get_theme,
    theme_ids,
)

__all__ = [
    # tagged output
    "TaggedOutput",
    "build_tagged_output",
    # evidence linking
    "EvidenceSpan",
    "EvidenceLink",
    "EvidenceLinkError",
    "build_evidence_links",
    # model extractor contract
    "ModelExtractionRequest",
    "ModelExtractionResponse",
    "ModelExtractor",
    # rule extractor
    "Hit",
    "RuleExtractor",
    # theme taxonomy
    "ThemeId",
    "ThemeDefinition",
    "THEME_TAXONOMY",
    "get_theme",
    "all_themes",
    "theme_ids",
    "find_themes_by_keyword",
    # entity type taxonomy
    "EntityTypeId",
    "EntityTypeDefinition",
    "ENTITY_TYPE_TAXONOMY",
    "get_entity_type",
    "all_entity_types",
    "entity_type_ids",
    "find_types_by_mention",
]
