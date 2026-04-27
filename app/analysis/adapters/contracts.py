"""
Analysis adapter contracts — interface/contract definitions only.

No provider calls are made here.  This module defines the stable typed surface
that *all* future analysis-adapter implementations must satisfy, covering:

- Prompt profile / version-selection metadata  (``PromptProfile``)
- Structured adapter input  (``AnalysisInput``)
- Per-chain analysis output  (``ChainAnalysisResult``)
- Investment ranking output  (``ChainRankingEntry``, ``RankingOutput``)
- Model/provider metadata  (``ModelProviderInfo``)
- Full response envelope  (``AnalysisResponse``)
- Provider-agnostic Protocol  (``AnalysisAdapter``)

All value objects are ``frozen=True`` dataclasses; the adapter entry-point is a
``@runtime_checkable`` ``Protocol`` so that duck-typed implementations work
alongside explicit subclassing.

三种分析任务（来自 llm-analysis-plan.md）
------------------------------------------
- **摘要归纳**  (``PromptTaskType.SUMMARY``)
- **链路补全**  (``PromptTaskType.CHAIN_COMPLETION``)
- **投资排序**  (``PromptTaskType.INVESTMENT_RANKING``)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from app.chains.chain import InformationChain
from app.chains.evidence_retention import ChainEvidenceBundle


# ---------------------------------------------------------------------------
# PromptTaskType — enumeration of supported analysis tasks
# ---------------------------------------------------------------------------


class PromptTaskType(str, Enum):
    """The analysis tasks supported by the adapter layer."""

    SUMMARY = "summary"
    """摘要归纳 — narrative summary of chain events."""

    CHAIN_COMPLETION = "chain_completion"
    """链路补全 — infer or complete missing causal links in a chain."""

    INVESTMENT_RANKING = "investment_ranking"
    """投资排序 — rank chains by investment relevance."""

    GROUPER = "grouper"
    """分组策略 — determine optimal grouping of tagged outputs."""

    REACT_STEP = "react_step"
    """ReAct 单步迭代 — single reasoning+acting iteration."""

    REACT_FINALIZE = "react_finalize"
    """ReAct 最终输出 — synthesise steps into final analysis."""


# ---------------------------------------------------------------------------
# PromptProfile — prompt template / version selection metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptProfile:
    """
    Identifies **which** prompt template and version to use for a task.

    Fields
    ------
    profile_name
        Human-readable profile identifier, e.g. ``"default"``, ``"aggressive"``,
        ``"conservative"``.  Must be non-empty.
    task_type
        The :class:`PromptTaskType` this profile is designed for.
    version
        Semantic version or date tag, e.g. ``"1.0.0"`` or ``"2024-01"``.
        Must be non-empty.
    description
        Optional human-readable description kept for audit / logging purposes.
    """

    profile_name: str
    task_type: PromptTaskType
    version: str
    description: str = ""

    def __post_init__(self) -> None:
        if not self.profile_name:
            raise ValueError("PromptProfile.profile_name must not be empty.")
        if not self.version:
            raise ValueError("PromptProfile.version must not be empty.")


# ---------------------------------------------------------------------------
# AnalysisInput — structured adapter input bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisInput:
    """
    Input bundle fed to an :class:`AnalysisAdapter` call.

    Fields
    ------
    chains
        Candidate :class:`~app.chains.chain.InformationChain` objects to analyse.
    evidence_bundles
        Per-chain :class:`~app.chains.evidence_retention.ChainEvidenceBundle`
        objects; **must have the same length as** ``chains`` and be ordered
        identically (``chains[i]`` corresponds to ``evidence_bundles[i]``).
    prompt_profile
        The :class:`PromptProfile` selecting the prompt template/version for
        this call.
    extra_context
        Optional dict of extra placeholder values to inject into the prompt
        render context.  Used by the ReAct engine to pass dynamic data
        (e.g. react_history_json, group_json, available_tools_json) through
        the standard AnalysisAdapter pipeline without modifying the renderer.
    """

    chains: tuple[InformationChain, ...]
    evidence_bundles: tuple[ChainEvidenceBundle, ...]
    prompt_profile: PromptProfile
    extra_context: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.chains) != len(self.evidence_bundles):
            raise ValueError(
                "AnalysisInput.chains and evidence_bundles must have the same length; "
                f"got {len(self.chains)} chains and {len(self.evidence_bundles)} bundles."
            )


# ---------------------------------------------------------------------------
# ChainAnalysisResult — per-chain structured analysis output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainAnalysisResult:
    """
    Structured analysis result for a single :class:`~app.chains.chain.InformationChain`.

    Fields
    ------
    chain_id
        Matches :attr:`InformationChain.chain_id` of the analysed chain.
    summary
        LLM-generated narrative summary of the chain events (摘要归纳).
    completion_notes
        Inferred or completed causal links / missing steps (链路补全).
        Empty string when no completion was requested or possible.
    key_entities
        Salient entity names extracted from the analysis, already de-duplicated.
    confidence
        Provider-reported or model-estimated confidence in ``[0.0, 1.0]``.
    prompt_profile
        The :class:`PromptProfile` used to produce this result (for audit).
    """

    chain_id: str
    summary: str
    completion_notes: str
    key_entities: tuple[str, ...]
    confidence: float
    prompt_profile: PromptProfile

    def __post_init__(self) -> None:
        if not self.chain_id:
            raise ValueError("ChainAnalysisResult.chain_id must not be empty.")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                "ChainAnalysisResult.confidence must be in [0.0, 1.0]; "
                f"got {self.confidence}."
            )


# ---------------------------------------------------------------------------
# ChainRankingEntry — per-chain investment ranking entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainRankingEntry:
    """
    Investment-relevance ranking entry for a single chain (投资排序).

    Fields
    ------
    chain_id
        Matches :attr:`InformationChain.chain_id` of the ranked chain.
    rank
        1-based rank (``1`` = most investment-relevant).  Must be ``>= 1``.
    score
        Numeric relevance score; higher values indicate greater relevance.
        Scale is implementation-defined (providers may use different ranges).
    rationale
        LLM-generated explanation of why this chain received its rank.
    """

    chain_id: str
    rank: int
    score: float
    rationale: str

    def __post_init__(self) -> None:
        if not self.chain_id:
            raise ValueError("ChainRankingEntry.chain_id must not be empty.")
        if self.rank < 1:
            raise ValueError(
                f"ChainRankingEntry.rank must be >= 1; got {self.rank}."
            )


# ---------------------------------------------------------------------------
# RankingOutput — full investment ranking result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RankingOutput:
    """
    Ordered investment ranking for a set of candidate chains.

    Fields
    ------
    entries
        :class:`ChainRankingEntry` objects sorted by ``rank`` (ascending, 1-based).
        Ranks must form a contiguous sequence ``[1, 2, …, N]`` with no gaps or
        duplicates (enforced by ``__post_init__``).
    prompt_profile
        The :class:`PromptProfile` used for the ranking call.
    """

    entries: tuple[ChainRankingEntry, ...]
    prompt_profile: PromptProfile

    def __post_init__(self) -> None:
        if self.entries:
            ranks = [e.rank for e in self.entries]
            expected = list(range(1, len(ranks) + 1))
            if sorted(ranks) != expected:
                raise ValueError(
                    "RankingOutput.entries ranks must be a contiguous 1-based sequence "
                    f"[1 … {len(ranks)}]; got {ranks}."
                )


# ---------------------------------------------------------------------------
# ModelProviderInfo — model / provider metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelProviderInfo:
    """
    Metadata about the model and provider used for an analysis call.

    Fields
    ------
    provider
        Provider identifier, e.g. ``"github_models"``, ``"openai"``,
        ``"anthropic"``.  Must be non-empty.
    model_id
        Model identifier, e.g. ``"gpt-4o"``, ``"gpt-4o-mini"``.
        Must be non-empty.
    model_version
        Model version string, e.g. ``"2024-11-20"``, ``"latest"``.
    endpoint
        Base API endpoint URL; empty string when the provider uses a default
        or when the information is not exposed.
    """

    provider: str
    model_id: str
    model_version: str
    endpoint: str = ""

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("ModelProviderInfo.provider must not be empty.")
        if not self.model_id:
            raise ValueError("ModelProviderInfo.model_id must not be empty.")


# ---------------------------------------------------------------------------
# AnalysisResponse — complete adapter response envelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisResponse:
    """
    Complete response envelope returned by an :class:`AnalysisAdapter`.

    Fields
    ------
    chain_results
        Per-chain :class:`ChainAnalysisResult` objects in the same order as
        the input chains.
    ranking
        :class:`RankingOutput` with investment-relevance ranking across all
        analysed chains.
    provider_info
        :class:`ModelProviderInfo` for the model/provider used in this call.
    """

    chain_results: tuple[ChainAnalysisResult, ...]
    ranking: RankingOutput
    provider_info: ModelProviderInfo


# ---------------------------------------------------------------------------
# AnalysisAdapter — provider-agnostic Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AnalysisAdapter(Protocol):
    """
    Provider-agnostic interface for LLM-backed chain analysis.

    Any class that implements ``analyse(AnalysisInput) -> AnalysisResponse``
    satisfies this Protocol (structural sub-typing via ``@runtime_checkable``).

    Contract
    --------
    - Accept an :class:`AnalysisInput` (frozen; do **not** mutate it).
    - Return an :class:`AnalysisResponse` covering summary, completion, and ranking.
    - Prompt template selection, HTTP calls, retries, and authentication are
      implementation concerns; they must **not** leak into this contract.

    The ``prompt_profile`` field inside :class:`AnalysisInput` is the single
    human-adjustable entry-point that implementations must honour for selecting
    the active prompt template and version.
    """

    def analyse(self, analysis_input: AnalysisInput) -> AnalysisResponse:
        """
        Run the full analysis pipeline for *analysis_input* and return a
        structured :class:`AnalysisResponse`.

        Implementations must cover all three task types:
        ``SUMMARY``, ``CHAIN_COMPLETION``, and ``INVESTMENT_RANKING``.
        """
        ...
