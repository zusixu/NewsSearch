"""
tests/test_analysis_adapter_contracts.py

Focused tests for app.analysis.adapters contracts (interface / contract only).

Coverage
--------
 1. Import surface — app.analysis.adapters
 2. Import surface — app.analysis (re-export)
 3. PromptTaskType values and str behaviour
 4. PromptProfile — valid construction
 5. PromptProfile — frozen (immutability)
 6. PromptProfile — rejects empty profile_name
 7. PromptProfile — rejects empty version
 8. AnalysisInput — valid construction (non-empty)
 9. AnalysisInput — valid construction (empty chains)
10. AnalysisInput — frozen (immutability)
11. AnalysisInput — rejects mismatched chains/bundles lengths
12. ChainAnalysisResult — valid construction
13. ChainAnalysisResult — frozen (immutability)
14. ChainAnalysisResult — rejects empty chain_id
15. ChainAnalysisResult — rejects confidence below 0.0
16. ChainAnalysisResult — rejects confidence above 1.0
17. ChainAnalysisResult — accepts confidence boundary values 0.0 and 1.0
18. ChainRankingEntry — valid construction
19. ChainRankingEntry — frozen (immutability)
20. ChainRankingEntry — rejects empty chain_id
21. ChainRankingEntry — rejects rank < 1
22. RankingOutput — valid construction (ordered entries)
23. RankingOutput — valid construction (empty entries)
24. RankingOutput — frozen (immutability)
25. RankingOutput — rejects non-contiguous ranks
26. ModelProviderInfo — valid construction
27. ModelProviderInfo — frozen (immutability)
28. ModelProviderInfo — rejects empty provider
29. ModelProviderInfo — rejects empty model_id
30. AnalysisResponse — valid construction
31. AnalysisResponse — frozen (immutability)
32. AnalysisAdapter Protocol — structural compatibility (duck-typed implementor)
33. AnalysisAdapter Protocol — non-compatible class fails isinstance check
34. Compatibility — AnalysisInput accepts InformationChain + ChainEvidenceBundle
"""

from __future__ import annotations

import dataclasses

import pytest

# ---------------------------------------------------------------------------
# Import surface tests are inline — we do the imports here so that failures
# produce clear ImportError messages tied to specific test IDs.
# ---------------------------------------------------------------------------

from app.analysis.adapters import (
    AnalysisAdapter,
    AnalysisInput,
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    ModelProviderInfo,
    PromptProfile,
    PromptTaskType,
    RankingOutput,
)

# Re-export surface
import app.analysis as _analysis_top

# information-chain models (compatibility)
from app.chains.chain import ChainNode, InformationChain, build_chain
from app.chains.evidence_retention import ChainEvidenceBundle, collect_chain_evidence
from app.entity.evidence import EvidenceLink, EvidenceSpan, build_evidence_links
from app.entity.rules.extractor import Hit
from app.entity.tagged_output import build_tagged_output
from app.models.event_draft import EventDraft
from app.models.news_item import NewsItem
from app.models.raw_document import RawDocument


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------


def _make_raw(title: str = "raw", date: str = "2025-01-01") -> RawDocument:
    return RawDocument(
        source="web",
        provider="test",
        title=title,
        content=None,
        url=None,
        date=date,
    )


def _make_news(title: str = "news", date: str = "2025-01-01") -> NewsItem:
    return NewsItem.from_raw(_make_raw(title=title, date=date))


def _make_event(title: str = "事件") -> EventDraft:
    news = _make_news(title=title)
    return EventDraft(title=title, summary=None, occurred_at="2025-01-01", source_items=[news])


def _make_hit(label_id: str = "ai", kind: str = "theme") -> Hit:
    return Hit(matched_text="AI", start=0, end=2, matched_seed="AI", kind=kind, label_id=label_id)  # type: ignore[arg-type]


def _make_chain(chain_id: str = "chain-001") -> InformationChain:
    hit = _make_hit()
    to = build_tagged_output(
        event=_make_event(),
        text="AI算力",
        evidence_links=build_evidence_links("AI算力", [hit]),
    )
    return build_chain(chain_id, [to])


def _make_bundle(chain: InformationChain) -> ChainEvidenceBundle:
    return collect_chain_evidence(chain)


def _make_profile(
    name: str = "default",
    task: PromptTaskType = PromptTaskType.SUMMARY,
    version: str = "1.0.0",
) -> PromptProfile:
    return PromptProfile(profile_name=name, task_type=task, version=version)


def _make_chain_result(
    chain_id: str = "chain-001",
    confidence: float = 0.8,
) -> ChainAnalysisResult:
    return ChainAnalysisResult(
        chain_id=chain_id,
        summary="这是摘要。",
        completion_notes="补全说明。",
        key_entities=("公司A", "公司B"),
        confidence=confidence,
        prompt_profile=_make_profile(),
    )


def _make_ranking_entry(chain_id: str, rank: int, score: float = 0.9) -> ChainRankingEntry:
    return ChainRankingEntry(
        chain_id=chain_id,
        rank=rank,
        score=score,
        rationale="排序理由。",
    )


def _make_provider_info() -> ModelProviderInfo:
    return ModelProviderInfo(
        provider="github_models",
        model_id="gpt-4o",
        model_version="2024-11-20",
        endpoint="https://models.inference.ai.azure.com",
    )


# ---------------------------------------------------------------------------
# 1. Import surface — app.analysis.adapters
# ---------------------------------------------------------------------------


def test_import_surface_adapters_module() -> None:
    """All public names are importable from app.analysis.adapters."""
    expected = {
        "AnalysisAdapter",
        "AnalysisInput",
        "AnalysisResponse",
        "ChainAnalysisResult",
        "ChainRankingEntry",
        "ModelProviderInfo",
        "PromptProfile",
        "PromptTaskType",
        "RankingOutput",
    }
    from app.analysis import adapters as _adapters_pkg
    exported = set(_adapters_pkg.__all__)
    assert expected <= exported


# ---------------------------------------------------------------------------
# 2. Import surface — app.analysis top-level re-export
# ---------------------------------------------------------------------------


def test_import_surface_analysis_top_level() -> None:
    """All adapter names are re-exported from app.analysis."""
    expected = {
        "AnalysisAdapter",
        "AnalysisInput",
        "AnalysisResponse",
        "ChainAnalysisResult",
        "ChainRankingEntry",
        "ModelProviderInfo",
        "PromptProfile",
        "PromptTaskType",
        "RankingOutput",
    }
    assert expected <= set(_analysis_top.__all__)


# ---------------------------------------------------------------------------
# 3. PromptTaskType values and str behaviour
# ---------------------------------------------------------------------------


def test_prompt_task_type_values() -> None:
    assert PromptTaskType.SUMMARY == "summary"
    assert PromptTaskType.CHAIN_COMPLETION == "chain_completion"
    assert PromptTaskType.INVESTMENT_RANKING == "investment_ranking"


def test_prompt_task_type_str_subclass() -> None:
    assert isinstance(PromptTaskType.SUMMARY, str)


# ---------------------------------------------------------------------------
# 4. PromptProfile — valid construction
# ---------------------------------------------------------------------------


def test_prompt_profile_construction() -> None:
    p = _make_profile(name="conservative", task=PromptTaskType.INVESTMENT_RANKING, version="2.0")
    assert p.profile_name == "conservative"
    assert p.task_type is PromptTaskType.INVESTMENT_RANKING
    assert p.version == "2.0"
    assert p.description == ""


def test_prompt_profile_with_description() -> None:
    p = PromptProfile(
        profile_name="test",
        task_type=PromptTaskType.CHAIN_COMPLETION,
        version="0.1",
        description="用于单元测试的 profile。",
    )
    assert p.description == "用于单元测试的 profile。"


# ---------------------------------------------------------------------------
# 5. PromptProfile — frozen
# ---------------------------------------------------------------------------


def test_prompt_profile_is_frozen() -> None:
    p = _make_profile()
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        p.profile_name = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 6 & 7. PromptProfile — validation guards
# ---------------------------------------------------------------------------


def test_prompt_profile_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="profile_name"):
        PromptProfile(profile_name="", task_type=PromptTaskType.SUMMARY, version="1.0")


def test_prompt_profile_rejects_empty_version() -> None:
    with pytest.raises(ValueError, match="version"):
        PromptProfile(profile_name="ok", task_type=PromptTaskType.SUMMARY, version="")


# ---------------------------------------------------------------------------
# 8 & 9. AnalysisInput — valid construction
# ---------------------------------------------------------------------------


def test_analysis_input_construction_non_empty() -> None:
    chain = _make_chain()
    bundle = _make_bundle(chain)
    profile = _make_profile()
    ai = AnalysisInput(
        chains=(chain,),
        evidence_bundles=(bundle,),
        prompt_profile=profile,
    )
    assert len(ai.chains) == 1
    assert len(ai.evidence_bundles) == 1
    assert ai.prompt_profile is profile


def test_analysis_input_construction_empty() -> None:
    ai = AnalysisInput(
        chains=(),
        evidence_bundles=(),
        prompt_profile=_make_profile(),
    )
    assert ai.chains == ()
    assert ai.evidence_bundles == ()


# ---------------------------------------------------------------------------
# 10. AnalysisInput — frozen
# ---------------------------------------------------------------------------


def test_analysis_input_is_frozen() -> None:
    ai = AnalysisInput(chains=(), evidence_bundles=(), prompt_profile=_make_profile())
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        ai.chains = (None,)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 11. AnalysisInput — mismatched chains/bundles
# ---------------------------------------------------------------------------


def test_analysis_input_rejects_length_mismatch() -> None:
    chain = _make_chain()
    bundle = _make_bundle(chain)
    with pytest.raises(ValueError, match="same length"):
        AnalysisInput(
            chains=(chain, chain),
            evidence_bundles=(bundle,),  # one fewer bundle
            prompt_profile=_make_profile(),
        )


# ---------------------------------------------------------------------------
# 12. ChainAnalysisResult — valid construction
# ---------------------------------------------------------------------------


def test_chain_analysis_result_construction() -> None:
    r = _make_chain_result(chain_id="c-1", confidence=0.75)
    assert r.chain_id == "c-1"
    assert r.confidence == 0.75
    assert "公司A" in r.key_entities


# ---------------------------------------------------------------------------
# 13. ChainAnalysisResult — frozen
# ---------------------------------------------------------------------------


def test_chain_analysis_result_is_frozen() -> None:
    r = _make_chain_result()
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        r.summary = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 14. ChainAnalysisResult — rejects empty chain_id
# ---------------------------------------------------------------------------


def test_chain_analysis_result_rejects_empty_chain_id() -> None:
    with pytest.raises(ValueError, match="chain_id"):
        ChainAnalysisResult(
            chain_id="",
            summary="摘要",
            completion_notes="",
            key_entities=(),
            confidence=0.5,
            prompt_profile=_make_profile(),
        )


# ---------------------------------------------------------------------------
# 15 & 16. ChainAnalysisResult — confidence range validation
# ---------------------------------------------------------------------------


def test_chain_analysis_result_rejects_confidence_below_zero() -> None:
    with pytest.raises(ValueError, match="confidence"):
        _make_chain_result(confidence=-0.01)


def test_chain_analysis_result_rejects_confidence_above_one() -> None:
    with pytest.raises(ValueError, match="confidence"):
        _make_chain_result(confidence=1.01)


# ---------------------------------------------------------------------------
# 17. ChainAnalysisResult — boundary confidence values accepted
# ---------------------------------------------------------------------------


def test_chain_analysis_result_accepts_confidence_boundaries() -> None:
    r0 = _make_chain_result(confidence=0.0)
    r1 = _make_chain_result(confidence=1.0)
    assert r0.confidence == 0.0
    assert r1.confidence == 1.0


# ---------------------------------------------------------------------------
# 18. ChainRankingEntry — valid construction
# ---------------------------------------------------------------------------


def test_chain_ranking_entry_construction() -> None:
    e = _make_ranking_entry("c-1", rank=1, score=0.95)
    assert e.chain_id == "c-1"
    assert e.rank == 1
    assert e.score == 0.95


# ---------------------------------------------------------------------------
# 19. ChainRankingEntry — frozen
# ---------------------------------------------------------------------------


def test_chain_ranking_entry_is_frozen() -> None:
    e = _make_ranking_entry("c-1", rank=1)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        e.rank = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 20. ChainRankingEntry — rejects empty chain_id
# ---------------------------------------------------------------------------


def test_chain_ranking_entry_rejects_empty_chain_id() -> None:
    with pytest.raises(ValueError, match="chain_id"):
        ChainRankingEntry(chain_id="", rank=1, score=0.5, rationale="理由")


# ---------------------------------------------------------------------------
# 21. ChainRankingEntry — rejects rank < 1
# ---------------------------------------------------------------------------


def test_chain_ranking_entry_rejects_rank_zero() -> None:
    with pytest.raises(ValueError, match="rank"):
        ChainRankingEntry(chain_id="c-1", rank=0, score=0.5, rationale="理由")


def test_chain_ranking_entry_rejects_negative_rank() -> None:
    with pytest.raises(ValueError, match="rank"):
        ChainRankingEntry(chain_id="c-1", rank=-1, score=0.5, rationale="理由")


# ---------------------------------------------------------------------------
# 22 & 23. RankingOutput — valid construction
# ---------------------------------------------------------------------------


def test_ranking_output_construction_ordered() -> None:
    entries = (
        _make_ranking_entry("c-1", rank=1, score=0.9),
        _make_ranking_entry("c-2", rank=2, score=0.7),
        _make_ranking_entry("c-3", rank=3, score=0.5),
    )
    ro = RankingOutput(entries=entries, prompt_profile=_make_profile(task=PromptTaskType.INVESTMENT_RANKING))
    assert ro.entries[0].rank == 1
    assert ro.entries[2].chain_id == "c-3"


def test_ranking_output_construction_empty() -> None:
    ro = RankingOutput(entries=(), prompt_profile=_make_profile())
    assert ro.entries == ()


# ---------------------------------------------------------------------------
# 24. RankingOutput — frozen
# ---------------------------------------------------------------------------


def test_ranking_output_is_frozen() -> None:
    ro = RankingOutput(entries=(), prompt_profile=_make_profile())
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        ro.entries = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 25. RankingOutput — rejects non-contiguous / duplicate ranks
# ---------------------------------------------------------------------------


def test_ranking_output_rejects_gap_in_ranks() -> None:
    entries = (
        _make_ranking_entry("c-1", rank=1),
        _make_ranking_entry("c-2", rank=3),  # gap: no rank 2
    )
    with pytest.raises(ValueError, match="contiguous"):
        RankingOutput(entries=entries, prompt_profile=_make_profile())


def test_ranking_output_rejects_duplicate_ranks() -> None:
    entries = (
        _make_ranking_entry("c-1", rank=1),
        _make_ranking_entry("c-2", rank=1),  # duplicate rank
    )
    with pytest.raises(ValueError, match="contiguous"):
        RankingOutput(entries=entries, prompt_profile=_make_profile())


# ---------------------------------------------------------------------------
# 26. ModelProviderInfo — valid construction
# ---------------------------------------------------------------------------


def test_model_provider_info_construction() -> None:
    m = _make_provider_info()
    assert m.provider == "github_models"
    assert m.model_id == "gpt-4o"
    assert m.model_version == "2024-11-20"
    assert m.endpoint == "https://models.inference.ai.azure.com"


def test_model_provider_info_default_endpoint() -> None:
    m = ModelProviderInfo(provider="openai", model_id="gpt-4o-mini", model_version="latest")
    assert m.endpoint == ""


# ---------------------------------------------------------------------------
# 27. ModelProviderInfo — frozen
# ---------------------------------------------------------------------------


def test_model_provider_info_is_frozen() -> None:
    m = _make_provider_info()
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        m.provider = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 28 & 29. ModelProviderInfo — validation guards
# ---------------------------------------------------------------------------


def test_model_provider_info_rejects_empty_provider() -> None:
    with pytest.raises(ValueError, match="provider"):
        ModelProviderInfo(provider="", model_id="gpt-4o", model_version="latest")


def test_model_provider_info_rejects_empty_model_id() -> None:
    with pytest.raises(ValueError, match="model_id"):
        ModelProviderInfo(provider="openai", model_id="", model_version="latest")


# ---------------------------------------------------------------------------
# 30. AnalysisResponse — valid construction
# ---------------------------------------------------------------------------


def test_analysis_response_construction() -> None:
    chain = _make_chain("chain-42")
    bundle = _make_bundle(chain)
    result = _make_chain_result("chain-42")
    entry = _make_ranking_entry("chain-42", rank=1)
    ranking = RankingOutput(entries=(entry,), prompt_profile=_make_profile(task=PromptTaskType.INVESTMENT_RANKING))
    provider = _make_provider_info()

    resp = AnalysisResponse(
        chain_results=(result,),
        ranking=ranking,
        provider_info=provider,
    )
    assert resp.chain_results[0].chain_id == "chain-42"
    assert resp.ranking.entries[0].rank == 1
    assert resp.provider_info.model_id == "gpt-4o"


# ---------------------------------------------------------------------------
# 31. AnalysisResponse — frozen
# ---------------------------------------------------------------------------


def test_analysis_response_is_frozen() -> None:
    chain = _make_chain()
    result = _make_chain_result()
    entry = _make_ranking_entry("chain-001", rank=1)
    ranking = RankingOutput(entries=(entry,), prompt_profile=_make_profile())
    resp = AnalysisResponse(
        chain_results=(result,),
        ranking=ranking,
        provider_info=_make_provider_info(),
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        resp.chain_results = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 32. AnalysisAdapter Protocol — structural compatibility
# ---------------------------------------------------------------------------


def test_analysis_adapter_protocol_compatible_implementor() -> None:
    """A class with analyse() satisfies the Protocol at runtime."""

    class _StubAdapter:
        def analyse(self, analysis_input: AnalysisInput) -> AnalysisResponse:
            raise NotImplementedError

    assert isinstance(_StubAdapter(), AnalysisAdapter)


# ---------------------------------------------------------------------------
# 33. AnalysisAdapter Protocol — non-compatible class fails isinstance check
# ---------------------------------------------------------------------------


def test_analysis_adapter_protocol_incompatible_class() -> None:
    """A class without analyse() does NOT satisfy the Protocol."""

    class _NoopClass:
        def process(self) -> None:
            pass

    assert not isinstance(_NoopClass(), AnalysisAdapter)


# ---------------------------------------------------------------------------
# 34. Compatibility with information-chain models
# ---------------------------------------------------------------------------


def test_analysis_input_accepts_information_chain_and_bundle() -> None:
    """AnalysisInput integrates cleanly with InformationChain + ChainEvidenceBundle."""
    chain = _make_chain("compat-chain")
    bundle = _make_bundle(chain)
    assert bundle.chain_id == "compat-chain"

    ai = AnalysisInput(
        chains=(chain,),
        evidence_bundles=(bundle,),
        prompt_profile=_make_profile(),
    )
    assert ai.chains[0].chain_id == "compat-chain"
    assert ai.evidence_bundles[0].chain_id == "compat-chain"
