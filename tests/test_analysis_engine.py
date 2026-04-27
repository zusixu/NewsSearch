"""
Tests for the AnalysisEngine and supporting components.
"""

from __future__ import annotations

import pytest
import sqlite3

from app.analysis import (
    AnalysisEngine,
    AnalysisEngineConfig,
    DryRunAnalysisAdapter,
)
from app.analysis.adapters.contracts import (
    AnalysisInput,
    PromptProfile,
    PromptTaskType,
)
from app.chains.chain import InformationChain, build_chain
from app.entity.tagged_output import TaggedOutput
from app.models.event_draft import EventDraft
from app.models.news_item import NewsItem
from app.storage import (
    ChainScoreStore,
    ChainScoreEntry,
    InfoChainStore,
    PromptProfileStore,
    RunLogStore,
    init_db,
)
from app.analysis.prompts import PromptProfileLoader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dummy_tagged_outputs() -> list[TaggedOutput]:
    """Create dummy tagged outputs for testing."""
    from app.models.raw_document import RawDocument
    from app.entity.tagged_output import build_tagged_output

    raw1 = RawDocument(
        source="test",
        provider="test",
        title="AI News 1",
        content="AI is advancing quickly",
        url=None,
        date="2025-01-01",
    )
    news1 = NewsItem.from_raw(raw1)
    event1 = EventDraft.from_news_item(news1)
    tagged1 = build_tagged_output(
        event=event1,
        text="AI is advancing quickly",
        evidence_links=[],
    )

    raw2 = RawDocument(
        source="test",
        provider="test",
        title="GPU News",
        content="GPU demand increases",
        url=None,
        date="2025-01-01",
    )
    news2 = NewsItem.from_raw(raw2)
    event2 = EventDraft.from_news_item(news2)
    tagged2 = build_tagged_output(
        event=event2,
        text="GPU demand increases",
        evidence_links=[],
    )

    return [tagged1, tagged2]


@pytest.fixture
def in_memory_db() -> sqlite3.Connection:
    """Create an in-memory database for testing."""
    return init_db(":memory:")


# ---------------------------------------------------------------------------
# DryRunAnalysisAdapter tests
# ---------------------------------------------------------------------------

class TestDryRunAnalysisAdapter:
    """Tests for DryRunAnalysisAdapter."""

    def test_analyse_empty_input(self, dummy_tagged_outputs: list[TaggedOutput]) -> None:
        """Test analyse with empty chains."""
        adapter = DryRunAnalysisAdapter()
        profile = PromptProfile(
            profile_name="test",
            task_type=PromptTaskType.SUMMARY,
            version="1.0",
            description="test profile"
        )

        input = AnalysisInput(chains=(), evidence_bundles=(), prompt_profile=profile)
        response = adapter.analyse(input)

        assert response is not None
        assert len(response.chain_results) == 0
        assert len(response.ranking.entries) == 0

    def test_analyse_with_chains(self, dummy_tagged_outputs: list[TaggedOutput]) -> None:
        """Test analyse with real chains."""
        from app.chains.evidence_retention import collect_all_evidence

        adapter = DryRunAnalysisAdapter()
        chains = [
            build_chain("chain-1", [dummy_tagged_outputs[0]]),
            build_chain("chain-2", [dummy_tagged_outputs[1]]),
        ]
        bundles = collect_all_evidence(chains)
        profile = PromptProfile(
            profile_name="test",
            task_type=PromptTaskType.SUMMARY,
            version="1.0",
            description="test profile"
        )

        input = AnalysisInput(chains=tuple(chains), evidence_bundles=tuple(bundles), prompt_profile=profile)
        response = adapter.analyse(input)

        assert response is not None
        assert len(response.chain_results) == 2
        assert len(response.ranking.entries) == 2

        # Check results are valid
        for result in response.chain_results:
            assert result.chain_id is not None
            assert 0.0 <= result.confidence <= 1.0

        # Check ranking is valid
        ranks = [e.rank for e in response.ranking.entries]
        assert sorted(ranks) == [1, 2]


# ---------------------------------------------------------------------------
# AnalysisEngine tests
# ---------------------------------------------------------------------------

class TestAnalysisEngine:
    """Tests for AnalysisEngine."""

    def test_create_engine_dry_run(self) -> None:
        """Test creating an engine in dry-run mode."""
        config = AnalysisEngineConfig(
            github_token="dummy",
            templates_dir="app/analysis/prompts/templates",
            profiles_dir="config/prompt_profiles",
            default_profile_name="default",
        )
        engine = AnalysisEngine(config, dry_run=True)

        assert engine is not None
        assert isinstance(engine._adapter, DryRunAnalysisAdapter)

    def test_load_profile(self) -> None:
        """Test loading a prompt profile."""
        config = AnalysisEngineConfig(
            github_token="dummy",
            templates_dir="app/analysis/prompts/templates",
            profiles_dir="config/prompt_profiles",
            default_profile_name="default",
        )
        engine = AnalysisEngine(config, dry_run=True)

        profile = engine.load_profile()

        assert profile is not None
        assert profile.profile_name == "default"

    def test_build_chains(self, dummy_tagged_outputs: list[TaggedOutput]) -> None:
        """Test building chains from tagged outputs."""
        config = AnalysisEngineConfig(github_token="dummy")
        engine = AnalysisEngine(config, dry_run=True)

        chains = engine.build_chains(dummy_tagged_outputs)

        assert chains is not None
        assert len(chains) > 0

    def test_analyse_chains(self, dummy_tagged_outputs: list[TaggedOutput]) -> None:
        """Test analysing chains."""
        config = AnalysisEngineConfig(github_token="dummy")
        engine = AnalysisEngine(config, dry_run=True)

        chains = engine.build_chains(dummy_tagged_outputs)
        profile_config = engine.load_profile()
        response = engine.analyse_chains(chains, profile_config)

        assert response is not None
        assert len(response.chain_results) == len(chains)

    def test_run_full_analysis(self, dummy_tagged_outputs: list[TaggedOutput]) -> None:
        """Test the full analysis pipeline."""
        config = AnalysisEngineConfig(github_token="dummy")
        engine = AnalysisEngine(config, dry_run=True)

        chains, response, profile_config = engine.run_full_analysis(dummy_tagged_outputs)

        assert chains is not None
        assert response is not None
        assert profile_config is not None
        assert len(chains) > 0
        assert len(response.chain_results) > 0


# ---------------------------------------------------------------------------
# Storage tests
# ---------------------------------------------------------------------------

class TestChainScoreStore:
    """Tests for ChainScoreStore."""

    def test_insert_score(self, in_memory_db: sqlite3.Connection) -> None:
        """Test inserting a single score."""
        # First insert a chain and run
        run_store = RunLogStore(in_memory_db)
        run_id = run_store.start_run()

        chain_store = InfoChainStore(in_memory_db)
        chain_id = chain_store.insert_chain(run_id=run_id)

        # Now insert score
        score_store = ChainScoreStore(in_memory_db)
        score_id = score_store.insert_score(
            chain_id=chain_id,
            run_id=run_id,
            novelty=0.8,
            importance=0.9,
            credibility=0.7,
            a_share_relevance=0.6,
            overall=0.75,
            prompt_profile_name="test",
            prompt_profile_version="1.0",
        )

        assert score_id is not None
        assert score_id > 0

    def test_get_scores_for_run(self, in_memory_db: sqlite3.Connection) -> None:
        """Test retrieving scores for a run."""
        run_store = RunLogStore(in_memory_db)
        run_id = run_store.start_run()

        chain_store = InfoChainStore(in_memory_db)
        chain_id1 = chain_store.insert_chain(run_id=run_id)
        chain_id2 = chain_store.insert_chain(run_id=run_id)

        score_store = ChainScoreStore(in_memory_db)
        score_store.insert_score(chain_id1, run_id, overall=0.8)
        score_store.insert_score(chain_id2, run_id, overall=0.9)

        scores = score_store.get_scores_for_run(run_id)

        assert len(scores) == 2
        # Should be sorted by overall descending
        assert scores[0].overall >= scores[1].overall

    def test_get_top_scores(self, in_memory_db: sqlite3.Connection) -> None:
        """Test getting top N scores."""
        run_store = RunLogStore(in_memory_db)
        run_id = run_store.start_run()

        chain_store = InfoChainStore(in_memory_db)
        score_store = ChainScoreStore(in_memory_db)

        for i in range(5):
            chain_id = chain_store.insert_chain(run_id=run_id)
            score_store.insert_score(chain_id, run_id, overall=0.5 + i * 0.1)

        top3 = score_store.get_top_scores(3)

        assert len(top3) == 3
        assert top3[0].overall >= top3[1].overall >= top3[2].overall


class TestPromptProfileStore:
    """Tests for PromptProfileStore."""

    def test_archive_profile(self, in_memory_db: sqlite3.Connection) -> None:
        """Test archiving a prompt profile."""
        from app.analysis.prompts import PromptProfileConfig, TaskTemplateMapping

        # Create a test profile
        tasks = {
            PromptTaskType.SUMMARY: TaskTemplateMapping(template="summary.json"),
        }
        profile_config = PromptProfileConfig(
            profile_name="test-archive",
            version="1.0",
            description="test profile for archiving",
            tasks=tasks,
        )

        store = PromptProfileStore(in_memory_db)
        profile_id = store.archive_profile(profile_config)

        assert profile_id is not None
        assert profile_id > 0

    def test_list_archived_profiles(self, in_memory_db: sqlite3.Connection) -> None:
        """Test listing archived profiles."""
        from app.analysis.prompts import PromptProfileConfig, TaskTemplateMapping

        store = PromptProfileStore(in_memory_db)

        # Insert a profile
        tasks = {PromptTaskType.SUMMARY: TaskTemplateMapping(template="summary.json")}
        profile_config = PromptProfileConfig(
            profile_name="test-list",
            version="1.0",
            description="test",
            tasks=tasks,
        )
        store.archive_profile(profile_config)

        profiles = store.list_archived_profiles()

        assert len(profiles) > 0
        names = [p[0] for p in profiles]
        assert "test-list" in names


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestAnalysisIntegration:
    """Integration tests for the full analysis flow."""

    def test_full_flow_with_storage(
        self,
        in_memory_db: sqlite3.Connection,
        dummy_tagged_outputs: list[TaggedOutput],
    ) -> None:
        """Test the full flow from tagged outputs to stored scores."""
        # Create engine
        config = AnalysisEngineConfig(
            github_token="dummy",
            templates_dir="app/analysis/prompts/templates",
            profiles_dir="config/prompt_profiles",
        )
        engine = AnalysisEngine(config, dry_run=True)

        # Run analysis
        chains, response, profile_config = engine.run_full_analysis(dummy_tagged_outputs)

        # Archive profile
        profile_store = PromptProfileStore(in_memory_db)
        profile_store.archive_profile(profile_config)

        # Start run
        run_store = RunLogStore(in_memory_db)
        run_id = run_store.start_run(
            prompt_profile_name=profile_config.profile_name,
            prompt_profile_version=profile_config.version,
        )

        # Store chains
        chain_store = InfoChainStore(in_memory_db)
        chain_db_ids = {}
        for chain in chains:
            db_id = chain_store.insert_chain(
                run_id=run_id,
                title=f"Chain {chain.chain_id[:8]}",
                chain_type="unknown",
            )
            chain_db_ids[chain.chain_id] = db_id

        # Store scores
        score_store = ChainScoreStore(in_memory_db)
        inserted_ids = score_store.insert_from_analysis_response(
            response,
            chain_db_ids,
            run_id=run_id,
        )

        # Verify
        assert len(inserted_ids) == len(chains)

        # Finish run
        run_store.finish_run(run_id, success=True)

        # Retrieve and verify
        retrieved_scores = score_store.get_scores_for_run(run_id)
        assert len(retrieved_scores) == len(chains)
