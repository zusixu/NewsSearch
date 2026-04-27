"""
Test prompt version tracking functionality.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.analysis.adapters.contracts import PromptTaskType
from app.analysis.prompts import PromptProfileConfig, PromptProfileLoader
from app.storage import (
    RunLogEntry,
    RunLogStore,
    PromptProfileStore,
    get_db,
    init_db,
    open_connection,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path) -> sqlite3.Connection:
    """Initialized database connection."""
    return init_db(db_path)


@pytest.fixture
def sample_profile_config() -> PromptProfileConfig:
    """Sample prompt profile config for testing."""
    return PromptProfileConfig.from_dict({
        "profile_name": "test-profile",
        "version": "1.0.0",
        "description": "Test profile for unit tests",
        "tasks": {
            "summary": {"template": "summary.json"},
            "chain_completion": {"template": "chain_completion.json"},
            "investment_ranking": {"template": "investment_ranking.json"},
        },
    })


@pytest.fixture
def default_profile_config() -> PromptProfileConfig:
    """Load the actual default profile for integration testing."""
    profiles_dir = Path(__file__).parent.parent / "config" / "prompt_profiles"
    if not profiles_dir.exists():
        pytest.skip("Default prompt profile not available")

    loader = PromptProfileLoader(profiles_dir)
    return loader.load_profile("default")


# ---------------------------------------------------------------------------
# RunLogStore tests
# ---------------------------------------------------------------------------

class TestRunLogStore:
    """Tests for RunLogStore."""

    def test_start_run(self, conn: sqlite3.Connection) -> None:
        """Test starting a new run creates a valid entry."""
        store = RunLogStore(conn)
        run_id = store.start_run(
            prompt_profile_name="test-profile",
            prompt_profile_version="1.0.0",
            prompt_profile_desc="Test description",
            run_date="2025-01-15",
            batch_index=1,
        )

        assert run_id > 0

        entry = store.get_run(run_id)
        assert entry is not None
        assert entry.id == run_id
        assert entry.run_date == "2025-01-15"
        assert entry.batch_index == 1
        assert entry.status == "running"
        assert entry.prompt_profile_name == "test-profile"
        assert entry.prompt_profile_version == "1.0.0"
        assert entry.prompt_profile_desc == "Test description"
        assert entry.started_at is not None
        assert entry.finished_at is None

    def test_start_run_defaults(self, conn: sqlite3.Connection) -> None:
        """Test starting a run with default values."""
        store = RunLogStore(conn)
        run_id = store.start_run()

        entry = store.get_run(run_id)
        assert entry is not None
        assert entry.prompt_profile_name == "default"
        assert entry.prompt_profile_version == "unknown"
        assert entry.batch_index == 0
        assert entry.run_date is not None  # today's date

    def test_finish_run_success(self, conn: sqlite3.Connection) -> None:
        """Test finishing a run successfully."""
        store = RunLogStore(conn)
        run_id = store.start_run()

        store.finish_run(run_id, success=True)

        entry = store.get_run(run_id)
        assert entry is not None
        assert entry.status == "success"
        assert entry.finished_at is not None
        assert entry.error_text is None

    def test_finish_run_failure(self, conn: sqlite3.Connection) -> None:
        """Test finishing a run with failure."""
        store = RunLogStore(conn)
        run_id = store.start_run()

        store.finish_run(run_id, success=False, error_text="Something went wrong")

        entry = store.get_run(run_id)
        assert entry is not None
        assert entry.status == "failed"
        assert entry.finished_at is not None
        assert entry.error_text == "Something went wrong"

    def test_get_latest_run(self, conn: sqlite3.Connection) -> None:
        """Test retrieving the latest run."""
        store = RunLogStore(conn)

        # Create first run
        run_id_1 = store.start_run(prompt_profile_name="profile-v1")

        # Create second (later) run
        import time
        time.sleep(0.01)  # Ensure different timestamps
        run_id_2 = store.start_run(prompt_profile_name="profile-v2")

        latest = store.get_latest_run()
        assert latest is not None
        assert latest.id == run_id_2
        assert latest.prompt_profile_name == "profile-v2"

    def test_get_nonexistent_run(self, conn: sqlite3.Connection) -> None:
        """Test getting a run that doesn't exist returns None."""
        store = RunLogStore(conn)
        assert store.get_run(9999) is None

    def test_get_latest_run_when_none_exist(self, conn: sqlite3.Connection) -> None:
        """Test getting latest run when table is empty returns None."""
        store = RunLogStore(conn)
        assert store.get_latest_run() is None


# ---------------------------------------------------------------------------
# PromptProfileStore tests
# ---------------------------------------------------------------------------

class TestPromptProfileStore:
    """Tests for PromptProfileStore."""

    def test_archive_profile(self, conn: sqlite3.Connection, default_profile_config: PromptProfileConfig) -> None:
        """Test archiving a profile stores it correctly."""
        store = PromptProfileStore(conn)
        profile_id = store.archive_profile(default_profile_config)

        assert profile_id > 0

        # Should not insert duplicate
        profile_id_2 = store.archive_profile(default_profile_config)
        assert profile_id_2 == profile_id

    def test_get_archived_profile(self, conn: sqlite3.Connection, default_profile_config: PromptProfileConfig) -> None:
        """Test retrieving an archived profile."""
        store = PromptProfileStore(conn)
        store.archive_profile(default_profile_config)

        retrieved = store.get_profile(default_profile_config.profile_name, default_profile_config.version)

        assert retrieved is not None
        assert retrieved.profile_name == default_profile_config.profile_name
        assert retrieved.version == default_profile_config.version
        assert retrieved.description == default_profile_config.description
        assert set(retrieved.tasks.keys()) == set(default_profile_config.tasks.keys())

    def test_get_nonexistent_profile(self, conn: sqlite3.Connection) -> None:
        """Test getting a profile that doesn't exist returns None."""
        store = PromptProfileStore(conn)
        assert store.get_profile("nonexistent", "0.0.0") is None

    def test_list_archived_profiles(self, conn: sqlite3.Connection, default_profile_config: PromptProfileConfig) -> None:
        """Test listing archived profiles."""
        store = PromptProfileStore(conn)

        # Empty initially
        assert store.list_archived_profiles() == []

        # After archiving
        store.archive_profile(default_profile_config)
        profiles = store.list_archived_profiles()

        assert len(profiles) == 1
        name, version, desc, archived_at = profiles[0]
        assert name == default_profile_config.profile_name
        assert version == default_profile_config.version
        assert desc == default_profile_config.description
        assert archived_at is not None


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestPromptVersionTrackingIntegration:
    """Integration tests for prompt version tracking."""

    def test_full_workflow(self, conn: sqlite3.Connection, default_profile_config: PromptProfileConfig) -> None:
        """Test the full workflow: archive profile -> start run -> finish run."""
        # Archive the profile
        profile_store = PromptProfileStore(conn)
        profile_store.archive_profile(default_profile_config)

        # Start a run with the profile
        run_store = RunLogStore(conn)
        run_id = run_store.start_run(
            prompt_profile_name=default_profile_config.profile_name,
            prompt_profile_version=default_profile_config.version,
            prompt_profile_desc=default_profile_config.description,
        )

        # Verify run was created
        run = run_store.get_run(run_id)
        assert run is not None
        assert run.prompt_profile_name == default_profile_config.profile_name
        assert run.prompt_profile_version == default_profile_config.version

        # Finish the run
        run_store.finish_run(run_id, success=True)

        # Verify run is marked as finished
        run = run_store.get_run(run_id)
        assert run is not None
        assert run.status == "success"

        # Verify profile can still be retrieved
        retrieved_profile = profile_store.get_profile(
            default_profile_config.profile_name,
            default_profile_config.version,
        )
        assert retrieved_profile is not None

    def test_schema_backward_compatibility(self, db_path: Path) -> None:
        """Test that the new schema doesn't break basic initialization."""
        # Init DB with new schema
        conn = init_db(db_path)

        # Verify tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row["name"] for row in cursor.fetchall()]

        expected_tables = [
            "chain_evidence",
            "chain_scores",
            "entities",
            "info_chains",
            "news_entity_links",
            "news_items",
            "prompt_profiles",
            "raw_documents",
            "run_logs",
        ]

        for table in expected_tables:
            assert table in tables, f"Expected table {table} not found"

        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
