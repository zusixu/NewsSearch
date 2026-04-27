"""
tests/test_react_engine.py

Tests for the ReActAnalysisEngine — grouping logic, multi-step iteration,
finalize, cross-group ranking, and dry-run mode.

Coverage:
- ReActEngineConfig default values
- _dry_run_grouper produces expected grouping
- _dry_run_react_session produces a complete session
- _dry_run_finalize produces a ChainAnalysisResult
- _rank_groups sorts by confidence descending
- _strip_code_fences removes markdown wrapping
- ReActAnalysisEngine.run() in dry_run mode — full flow
- _empty_analysis_response format
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.analysis.react.engine import (
    ReActAnalysisEngine,
    ReActEngineConfig,
    _empty_analysis_response,
    _strip_code_fences,
)
from app.analysis.react.session import ReActSession, ReActStep
from app.analysis.adapters.contracts import (
    AnalysisResponse,
    ChainAnalysisResult,
    PromptProfile,
    PromptTaskType,
    RankingOutput,
    ModelProviderInfo,
)
from app.chains.chain import InformationChain, ChainNode, build_chain
from app.entity.tagged_output import TaggedOutput
from app.models.event_draft import EventDraft
from app.models.news_item import NewsItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dummy_tagged_outputs() -> list[TaggedOutput]:
    """Create dummy tagged outputs for testing."""
    from app.models.raw_document import RawDocument
    from app.entity.tagged_output import build_tagged_output

    raws = [
        RawDocument("s1", "p1", "AI Chip News", "AI chips are advancing", None, "2025-01-01"),
        RawDocument("s2", "p2", "GPU Supply", "GPU supply tightens", None, "2025-01-01"),
        RawDocument("s3", "p3", "Cloud Growth", "Cloud revenue up", None, "2025-01-01"),
    ]
    outputs = []
    for raw in raws:
        news = NewsItem.from_raw(raw)
        event = EventDraft.from_news_item(news)
        event.source_items = [news]
        tagged = build_tagged_output(event=event, text=raw.content, evidence_links=[])
        outputs.append(tagged)
    return outputs


@pytest.fixture
def dummy_chains(dummy_tagged_outputs) -> list[InformationChain]:
    """Build information chains from dummy tagged outputs."""
    from app.chains.candidate_generation import generate_candidate_chains
    return generate_candidate_chains(dummy_tagged_outputs)


@pytest.fixture
def engine_config() -> ReActEngineConfig:
    """Default engine config for tests."""
    return ReActEngineConfig(
        max_steps_per_group=3,
        max_groups=5,
        enable_web_search=True,
        enable_web_fetch=True,
        enable_akshare_query=True,
    )


@pytest.fixture
def engine_dry(engine_config) -> ReActAnalysisEngine:
    """ReActAnalysisEngine in dry_run mode."""
    return ReActAnalysisEngine(
        adapter=MagicMock(),
        renderer=None,
        engine_config=engine_config,
        dry_run=True,
    )


# ---------------------------------------------------------------------------
# ReActEngineConfig tests
# ---------------------------------------------------------------------------


class TestReActEngineConfig:
    """Tests for ReActEngineConfig."""

    def test_default_values(self) -> None:
        """ReActEngineConfig has sensible defaults."""
        config = ReActEngineConfig()
        assert config.max_steps_per_group == 5
        assert config.max_groups == 10
        assert config.enable_web_search is True
        assert config.enable_web_fetch is True
        assert config.enable_akshare_query is True
        assert config.profile_name == "default"
        assert config.profile_version == "1.0.0"

    def test_custom_values(self) -> None:
        """ReActEngineConfig accepts custom values."""
        config = ReActEngineConfig(
            max_steps_per_group=7,
            max_groups=3,
            enable_web_search=False,
            enable_web_fetch=False,
            enable_akshare_query=False,
            profile_name="aggressive",
            profile_version="2.0",
        )
        assert config.max_steps_per_group == 7
        assert config.max_groups == 3
        assert config.enable_web_search is False
        assert config.enable_web_fetch is False
        assert config.enable_akshare_query is False
        assert config.profile_name == "aggressive"
        assert config.profile_version == "2.0"

    def test_config_is_frozen(self) -> None:
        """ReActEngineConfig is a frozen dataclass."""
        config = ReActEngineConfig()
        with pytest.raises(Exception):
            config.max_steps_per_group = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _strip_code_fences tests
# ---------------------------------------------------------------------------


class TestStripCodeFences:
    """Tests for _strip_code_fences()."""

    def test_strips_json_fence(self) -> None:
        """Removes ```json ... ``` wrapper."""
        text = '```json\n{"key": "value"}\n```'
        assert _strip_code_fences(text) == '{"key": "value"}'

    def test_strips_plain_fence(self) -> None:
        """Removes ``` ... ``` wrapper (no language tag)."""
        text = '```\nsome content\n```'
        assert _strip_code_fences(text) == 'some content'

    def test_passthrough_no_fence(self) -> None:
        """Returns text unchanged if no code fences."""
        text = '{"key": "value"}'
        assert _strip_code_fences(text) == text

    def test_handles_newlines(self) -> None:
        """Handles content with multiple newlines inside fences."""
        text = '```json\n\n{"a": 1}\n\n```'
        # The function strips code fences AND strips whitespace from the result
        assert _strip_code_fences(text) == '{"a": 1}'

    def test_trims_whitespace(self) -> None:
        """Input text is stripped before processing."""
        text = '  \n ```json\n{"x":1}\n```\n  '
        assert _strip_code_fences(text) == '{"x":1}'


# ---------------------------------------------------------------------------
# _empty_analysis_response tests
# ---------------------------------------------------------------------------


class TestEmptyAnalysisResponse:
    """Tests for _empty_analysis_response()."""

    def test_returns_analysis_response(self) -> None:
        """_empty_analysis_response returns an AnalysisResponse."""
        config = ReActEngineConfig()
        response = _empty_analysis_response(config)
        assert isinstance(response, AnalysisResponse)

    def test_empty_chain_results(self) -> None:
        """Response has empty chain_results."""
        config = ReActEngineConfig()
        response = _empty_analysis_response(config)
        assert len(response.chain_results) == 0

    def test_empty_ranking_entries(self) -> None:
        """Response has empty ranking entries."""
        config = ReActEngineConfig()
        response = _empty_analysis_response(config)
        assert len(response.ranking.entries) == 0

    def test_uses_profile_from_config(self) -> None:
        """Provider info reflects the config profile name/version."""
        config = ReActEngineConfig(profile_name="my-profile", profile_version="2.0")
        response = _empty_analysis_response(config)
        assert response.provider_info.provider == "react-engine"
        assert response.provider_info.model_id == "react"

    def test_ranking_profile_matches_config(self) -> None:
        """The ranking's prompt_profile uses config values."""
        config = ReActEngineConfig(profile_name="test-p", profile_version="3.0")
        response = _empty_analysis_response(config)
        assert response.ranking.prompt_profile.profile_name == "test-p"
        assert response.ranking.prompt_profile.version == "3.0"


# ---------------------------------------------------------------------------
# _dry_run_grouper tests
# ---------------------------------------------------------------------------


class TestDryRunGrouper:
    """Tests for _dry_run_grouper()."""

    def test_returns_list(self, dummy_chains) -> None:
        """Returns a list of group dicts."""
        groups = ReActAnalysisEngine._dry_run_grouper(dummy_chains)
        assert isinstance(groups, list)

    def test_single_group(self, dummy_chains) -> None:
        """Returns exactly one group in dry_run mode."""
        groups = ReActAnalysisEngine._dry_run_grouper(dummy_chains)
        assert len(groups) == 1

    def test_group_has_expected_keys(self, dummy_chains) -> None:
        """Each group dict has group_id, theme, member_chain_ids, rationale."""
        groups = ReActAnalysisEngine._dry_run_grouper(dummy_chains)
        g = groups[0]
        assert "group_id" in g
        assert "theme" in g
        assert "member_chain_ids" in g
        assert "rationale" in g

    def test_group_contains_all_chain_ids(self, dummy_chains) -> None:
        """The single group contains all chain IDs."""
        groups = ReActAnalysisEngine._dry_run_grouper(dummy_chains)
        all_ids = [ch.chain_id for ch in dummy_chains]
        assert set(groups[0]["member_chain_ids"]) == set(all_ids)

    def test_empty_chains_returns_empty_group_ids(self) -> None:
        """Empty chains produce a group with empty member_chain_ids."""
        groups = ReActAnalysisEngine._dry_run_grouper([])
        assert groups[0]["member_chain_ids"] == []


# ---------------------------------------------------------------------------
# _dry_run_react_session tests
# ---------------------------------------------------------------------------


class TestDryRunReactSession:
    """Tests for _dry_run_react_session()."""

    def test_returns_session(self, engine_dry) -> None:
        """Returns a ReActSession instance."""
        session = ReActSession(group_id="g1")
        group = {"group_id": "g1", "theme": "AI", "member_chain_ids": ["c1"]}
        result = ReActAnalysisEngine._dry_run_react_session(session, group)
        assert isinstance(result, ReActSession)

    def test_returns_same_session_object(self, engine_dry) -> None:
        """Returns the same session object (mutated in place)."""
        session = ReActSession(group_id="g1")
        group = {"group_id": "g1", "theme": "AI", "member_chain_ids": ["c1"]}
        result = ReActAnalysisEngine._dry_run_react_session(session, group)
        assert result is session

    def test_session_has_one_step(self, engine_dry) -> None:
        """The dry-run session has exactly 1 step."""
        session = ReActSession(group_id="g1")
        group = {"group_id": "g1", "theme": "AI", "member_chain_ids": ["c1"]}
        result = ReActAnalysisEngine._dry_run_react_session(session, group)
        assert result.current_step_count == 1

    def test_session_step_is_complete(self, engine_dry) -> None:
        """The dry-run step has is_complete=True."""
        session = ReActSession(group_id="g1")
        group = {"group_id": "g1", "theme": "AI", "member_chain_ids": ["c1"]}
        result = ReActAnalysisEngine._dry_run_react_session(session, group)
        assert result.steps[0].is_complete is True

    def test_session_is_finished(self, engine_dry) -> None:
        """The dry-run session is finished after adding the step."""
        session = ReActSession(group_id="g1")
        group = {"group_id": "g1", "theme": "AI", "member_chain_ids": ["c1"]}
        result = ReActAnalysisEngine._dry_run_react_session(session, group)
        assert result.is_finished is True

    def test_step_thought_contains_theme(self, engine_dry) -> None:
        """The step thought contains the group theme."""
        session = ReActSession(group_id="g1")
        group = {"group_id": "g1", "theme": "Semiconductor", "member_chain_ids": ["c1"]}
        result = ReActAnalysisEngine._dry_run_react_session(session, group)
        assert "Semiconductor" in result.steps[0].thought


# ---------------------------------------------------------------------------
# _dry_run_finalize tests
# ---------------------------------------------------------------------------


class TestDryRunFinalize:
    """Tests for _dry_run_finalize()."""

    def test_returns_chain_analysis_result(self, engine_dry) -> None:
        """Returns a ChainAnalysisResult."""
        session = ReActSession(group_id="g1")
        step = ReActStep(step_index=0, thought="Analysis", is_complete=True)
        session.add_step(step)
        result = ReActAnalysisEngine._dry_run_finalize(session)
        assert isinstance(result, ChainAnalysisResult)

    def test_chain_id_matches_session_group_id(self, engine_dry) -> None:
        """Result chain_id equals session group_id."""
        session = ReActSession(group_id="my-group")
        step = ReActStep(step_index=0, thought="Analysis", is_complete=True)
        session.add_step(step)
        result = ReActAnalysisEngine._dry_run_finalize(session)
        assert result.chain_id == "my-group"

    def test_confidence_in_range(self, engine_dry) -> None:
        """Confidence is within [0.0, 1.0]."""
        session = ReActSession(group_id="g1")
        session.add_step(ReActStep(step_index=0, thought="T", is_complete=True))
        result = ReActAnalysisEngine._dry_run_finalize(session)
        assert 0.0 <= result.confidence <= 1.0

    def test_summary_contains_step_count(self, engine_dry) -> None:
        """Summary mentions the step count."""
        session = ReActSession(group_id="g1")
        session.add_step(ReActStep(step_index=0, thought="First"))
        session.add_step(ReActStep(step_index=1, thought="Second", is_complete=True))
        result = ReActAnalysisEngine._dry_run_finalize(session)
        assert "2 step" in result.summary

    def test_has_key_entities(self, engine_dry) -> None:
        """Result has key_entities tuple."""
        session = ReActSession(group_id="g1")
        session.add_step(ReActStep(step_index=0, thought="T", is_complete=True))
        result = ReActAnalysisEngine._dry_run_finalize(session)
        assert len(result.key_entities) > 0

    def test_has_prompt_profile(self, engine_dry) -> None:
        """Result carries a PromptProfile."""
        session = ReActSession(group_id="g1")
        session.add_step(ReActStep(step_index=0, thought="T", is_complete=True))
        result = ReActAnalysisEngine._dry_run_finalize(session)
        assert isinstance(result.prompt_profile, PromptProfile)
        assert result.prompt_profile.task_type == PromptTaskType.REACT_FINALIZE


# ---------------------------------------------------------------------------
# _rank_groups tests
# ---------------------------------------------------------------------------


class TestRankGroups:
    """Tests for _rank_groups()."""

    def test_returns_analysis_response(self, engine_dry) -> None:
        """Returns an AnalysisResponse."""
        results = [
            ChainAnalysisResult(
                chain_id="c1", summary="S1", completion_notes="",
                key_entities=("AI",), confidence=0.6,
                prompt_profile=PromptProfile(
                    profile_name="p", task_type=PromptTaskType.REACT_FINALIZE, version="1"),
            ),
            ChainAnalysisResult(
                chain_id="c2", summary="S2", completion_notes="",
                key_entities=("GPU",), confidence=0.9,
                prompt_profile=PromptProfile(
                    profile_name="p", task_type=PromptTaskType.REACT_FINALIZE, version="1"),
            ),
        ]
        response = engine_dry._rank_groups(results)
        assert isinstance(response, AnalysisResponse)

    def test_sorts_by_confidence_descending(self, engine_dry) -> None:
        """Higher confidence is ranked first."""
        results = [
            ChainAnalysisResult(
                chain_id="low", summary="L", completion_notes="",
                key_entities=(), confidence=0.3,
                prompt_profile=PromptProfile(
                    profile_name="p", task_type=PromptTaskType.REACT_FINALIZE, version="1"),
            ),
            ChainAnalysisResult(
                chain_id="high", summary="H", completion_notes="",
                key_entities=(), confidence=0.95,
                prompt_profile=PromptProfile(
                    profile_name="p", task_type=PromptTaskType.REACT_FINALIZE, version="1"),
            ),
            ChainAnalysisResult(
                chain_id="mid", summary="M", completion_notes="",
                key_entities=(), confidence=0.5,
                prompt_profile=PromptProfile(
                    profile_name="p", task_type=PromptTaskType.REACT_FINALIZE, version="1"),
            ),
        ]
        response = engine_dry._rank_groups(results)
        entries = response.ranking.entries
        assert entries[0].chain_id == "high"
        assert entries[0].rank == 1
        assert entries[1].chain_id == "mid"
        assert entries[1].rank == 2
        assert entries[2].chain_id == "low"
        assert entries[2].rank == 3

    def test_ranks_are_contiguous(self, engine_dry) -> None:
        """Ranks form a contiguous 1-based sequence."""
        results = [
            ChainAnalysisResult(
                chain_id=f"c{i}", summary="S", completion_notes="",
                key_entities=(), confidence=0.1 * i,
                prompt_profile=PromptProfile(
                    profile_name="p", task_type=PromptTaskType.REACT_FINALIZE, version="1"),
            )
            for i in range(1, 4)
        ]
        response = engine_dry._rank_groups(results)
        ranks = [e.rank for e in response.ranking.entries]
        assert ranks == list(range(1, len(results) + 1))

    def test_empty_results_returns_empty_response(self, engine_dry) -> None:
        """Empty results list produces an empty AnalysisResponse."""
        response = engine_dry._rank_groups([])
        assert len(response.chain_results) == 0
        assert len(response.ranking.entries) == 0

    def test_single_result_ranked_first(self, engine_dry) -> None:
        """A single result is always rank 1."""
        result = ChainAnalysisResult(
            chain_id="only", summary="S", completion_notes="",
            key_entities=(), confidence=0.5,
            prompt_profile=PromptProfile(
                profile_name="p", task_type=PromptTaskType.REACT_FINALIZE, version="1"),
        )
        response = engine_dry._rank_groups([result])
        assert response.ranking.entries[0].rank == 1
        assert response.ranking.entries[0].chain_id == "only"


# ---------------------------------------------------------------------------
# ReActAnalysisEngine.run() — dry-run integration
# ---------------------------------------------------------------------------


class TestReActEngineRunDry:
    """Integration tests for ReActAnalysisEngine.run() in dry_run mode."""

    def test_run_returns_chains_and_response(
        self, engine_dry, dummy_tagged_outputs
    ) -> None:
        """run() returns (chains, analysis_response)."""
        chains, response = engine_dry.run(dummy_tagged_outputs)
        assert isinstance(chains, list)
        assert isinstance(response, AnalysisResponse)
        assert len(chains) > 0

    def test_run_has_chain_results(self, engine_dry, dummy_tagged_outputs) -> None:
        """run() produces non-empty chain_results."""
        chains, response = engine_dry.run(dummy_tagged_outputs)
        assert len(response.chain_results) > 0

    def test_run_has_ranking(self, engine_dry, dummy_tagged_outputs) -> None:
        """run() produces a ranking."""
        chains, response = engine_dry.run(dummy_tagged_outputs)
        assert len(response.ranking.entries) > 0

    def test_run_with_empty_input(self, engine_dry) -> None:
        """run() handles empty tagged_outputs gracefully."""
        chains, response = engine_dry.run([])
        assert chains == []
        assert len(response.chain_results) == 0
        assert len(response.ranking.entries) == 0

    def test_run_chains_and_results_match(
        self, engine_dry, dummy_tagged_outputs
    ) -> None:
        """The number of chain_results equals the number of groups
        (1 in dry_run mode)."""
        chains, response = engine_dry.run(dummy_tagged_outputs)
        # In dry_run, grouper returns 1 group with all chains →
        # 1 ReAct session → 1 finalized result
        assert len(response.chain_results) == 1


# ---------------------------------------------------------------------------
# ReActAnalysisEngine — tool registry construction
# ---------------------------------------------------------------------------


class TestReActEngineToolRegistry:
    """Tests for tool registry construction in ReActAnalysisEngine."""

    def test_tools_enabled_by_default(self, engine_config) -> None:
        """When all tool flags are True, all 3 tools are registered."""
        engine = ReActAnalysisEngine(
            adapter=MagicMock(), renderer=None,
            engine_config=engine_config, dry_run=True,
        )
        tools = engine._tools.list_tools()
        names = {t.name for t in tools}
        assert names == {"web_search", "web_fetch", "akshare_query"}

    def test_tools_respect_config_flags(self) -> None:
        """Only enabled tools appear in the registry."""
        config = ReActEngineConfig(
            enable_web_search=True,
            enable_web_fetch=False,
            enable_akshare_query=False,
        )
        engine = ReActAnalysisEngine(
            adapter=MagicMock(), renderer=None,
            engine_config=config, dry_run=True,
        )
        tools = engine._tools.list_tools()
        names = {t.name for t in tools}
        assert names == {"web_search"}

    def test_all_tools_disabled(self) -> None:
        """When all flags are False, no tools are registered."""
        config = ReActEngineConfig(
            enable_web_search=False,
            enable_web_fetch=False,
            enable_akshare_query=False,
        )
        engine = ReActAnalysisEngine(
            adapter=MagicMock(), renderer=None,
            engine_config=config, dry_run=True,
        )
        assert engine._tools.list_tools() == []

    def test_tool_execution_delegates(self, engine_config) -> None:
        """Engine._execute_tool delegates to the internal registry."""
        engine = ReActAnalysisEngine(
            adapter=MagicMock(), renderer=None,
            engine_config=engine_config, dry_run=True,
        )
        result = engine._execute_tool("web_search", {"query": "test"})
        assert "test" in result

    def test_unknown_tool_returns_error_string(self, engine_dry) -> None:
        """Executing an unknown tool returns an error string (no raise)."""
        result = engine_dry._execute_tool("nonexistent_tool", {})
        assert "error" in result.lower()
