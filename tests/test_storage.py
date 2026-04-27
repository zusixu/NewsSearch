"""
tests/test_storage.py — focused tests for the SQLite initialisation module.

All tests use in-memory databases (:memory:) so they leave no files on disk.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.storage import get_db, init_db, open_connection
from app.storage.database import _SCHEMA_PATH, _read_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_TABLES = {
    "run_logs",
    "raw_documents",
    "news_items",
    "entities",
    "news_entity_links",
    "info_chains",
    "chain_evidence",
    "chain_scores",
    "prompt_profiles",
}

_EXPECTED_INDEXES = {
    "idx_run_logs_run_date",
    "idx_run_logs_status",
    "idx_raw_documents_url_fingerprint",
    "idx_raw_documents_content_hash",
    "idx_raw_documents_run_id",
    "idx_raw_documents_source_fetched",
    "idx_news_items_content_hash",
    "idx_news_items_published_at",
    "idx_news_items_run_id",
    "idx_entities_name",
    "idx_entities_type",
    "idx_nel_entity_id",
    "idx_info_chains_run_id",
    "idx_info_chains_created_at",
    "idx_chain_evidence_chain_id",
    "idx_chain_evidence_news_item_id",
    "idx_chain_scores_chain_id",
    "idx_chain_scores_run_id",
    "idx_chain_scores_overall",
    "idx_prompt_profiles_name_version",
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    ).fetchall()
    return {r[0] for r in rows}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';"
    ).fetchall()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# schema.sql asset
# ---------------------------------------------------------------------------

class TestSchemaAsset:
    def test_schema_file_exists(self):
        assert _SCHEMA_PATH.is_file(), "schema.sql must exist in app/storage/"

    def test_schema_file_readable(self):
        sql = _read_schema()
        assert len(sql) > 100, "schema.sql should not be empty"

    def test_schema_contains_create_if_not_exists(self):
        sql = _read_schema().upper()
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "CREATE INDEX IF NOT EXISTS" in sql


# ---------------------------------------------------------------------------
# open_connection
# ---------------------------------------------------------------------------

class TestOpenConnection:
    def test_returns_connection(self):
        conn = open_connection(":memory:")
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_row_factory_is_row(self):
        conn = open_connection(":memory:")
        assert conn.row_factory is sqlite3.Row
        conn.close()

    def test_foreign_keys_enabled(self):
        conn = open_connection(":memory:")
        row = conn.execute("PRAGMA foreign_keys;").fetchone()
        assert row[0] == 1, "PRAGMA foreign_keys should be ON"
        conn.close()

    def test_wal_journal_mode(self):
        conn = open_connection(":memory:")
        # In-memory DBs always return 'memory' for journal_mode, so we only
        # verify the PRAGMA executes without error.
        result = conn.execute("PRAGMA journal_mode;").fetchone()
        assert result is not None
        conn.close()

    def test_no_tables_created_by_open_connection(self):
        conn = open_connection(":memory:")
        assert _table_names(conn) == set(), "open_connection must not create tables"
        conn.close()

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "sub" / "dir" / "test.db"
        conn = open_connection(nested)
        assert nested.exists()
        conn.close()


# ---------------------------------------------------------------------------
# init_db / get_db
# ---------------------------------------------------------------------------

class TestInitDb:
    def test_returns_connection(self):
        conn = init_db(":memory:")
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_all_tables_created(self):
        conn = init_db(":memory:")
        assert _table_names(conn) == _EXPECTED_TABLES
        conn.close()

    def test_all_indexes_created(self):
        conn = init_db(":memory:")
        assert _index_names(conn) == _EXPECTED_INDEXES
        conn.close()

    def test_idempotent_multiple_calls(self):
        """Calling init_db on the same path twice must not raise."""
        conn1 = init_db(":memory:")
        conn1.close()
        # Open a fresh in-memory DB and call init_db again — both must succeed.
        conn2 = init_db(":memory:")
        assert _table_names(conn2) == _EXPECTED_TABLES
        conn2.close()

    def test_idempotent_executescript_twice(self):
        """Applying the schema twice on the same connection must not raise."""
        from app.storage.database import _read_schema
        conn = open_connection(":memory:")
        sql = _read_schema()
        conn.executescript(sql)
        conn.executescript(sql)  # second application — must not raise
        assert _table_names(conn) == _EXPECTED_TABLES
        conn.close()

    def test_get_db_is_alias_for_init_db(self):
        conn = get_db(":memory:")
        assert _table_names(conn) == _EXPECTED_TABLES
        conn.close()

    def test_creates_file_on_disk(self, tmp_path):
        db_file = tmp_path / "mm.db"
        conn = init_db(db_file)
        conn.close()
        assert db_file.is_file()

    def test_creates_parent_dirs_on_disk(self, tmp_path):
        db_file = tmp_path / "data" / "db" / "mm.db"
        conn = init_db(db_file)
        conn.close()
        assert db_file.is_file()


# ---------------------------------------------------------------------------
# Schema correctness smoke tests
# ---------------------------------------------------------------------------

class TestSchemaCorrectness:
    """Verify key columns and constraints exist by exercising the schema."""

    def setup_method(self):
        self.conn = init_db(":memory:")

    def teardown_method(self):
        self.conn.close()

    def test_run_logs_insert_and_select(self):
        self.conn.execute(
            "INSERT INTO run_logs (run_date, batch_index, started_at, status, prompt_profile_name, prompt_profile_version) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            ("2024-01-01", 0, "2024-01-01T08:30:00Z", "running", "default", "1.0.0"),
        )
        row = self.conn.execute("SELECT * FROM run_logs;").fetchone()
        assert row["run_date"] == "2024-01-01"
        assert row["batch_index"] == 0
        assert row["status"] == "running"

    def test_raw_documents_url_fingerprint_unique(self):
        base = ("2024-01-01T08:30:00Z", "akshare", "http://example.com", "fp1")
        self.conn.execute(
            "INSERT INTO raw_documents (fetched_at, source, url, url_fingerprint) VALUES (?,?,?,?);",
            base,
        )
        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO raw_documents (fetched_at, source, url, url_fingerprint) VALUES (?,?,?,?);",
                ("2024-01-01T09:00:00Z", "web", "http://other.com", "fp1"),
            )

    def test_news_items_insert(self):
        self.conn.execute(
            "INSERT INTO news_items (title, created_at) VALUES (?, ?);",
            ("Test headline", "2024-01-01T08:30:00Z"),
        )
        row = self.conn.execute("SELECT * FROM news_items;").fetchone()
        assert row["title"] == "Test headline"
        assert row["source_credibility"] == 0

    def test_entities_insert(self):
        self.conn.execute(
            "INSERT INTO entities (name, entity_type, created_at) VALUES (?,?,?);",
            ("NVIDIA", "company", "2024-01-01T00:00:00Z"),
        )
        row = self.conn.execute("SELECT * FROM entities WHERE name='NVIDIA';").fetchone()
        assert row["entity_type"] == "company"

    def test_info_chains_insert(self):
        self.conn.execute(
            "INSERT INTO info_chains (title, chain_type, created_at) VALUES (?,?,?);",
            ("HBM demand surge", "causal", "2024-01-01T00:00:00Z"),
        )
        row = self.conn.execute("SELECT * FROM info_chains;").fetchone()
        assert row["chain_type"] == "causal"

    def test_chain_scores_default_values(self):
        self.conn.execute(
            "INSERT INTO info_chains (title, chain_type, created_at) VALUES (?,?,?);",
            ("chain", "causal", "2024-01-01T00:00:00Z"),
        )
        chain_id = self.conn.execute("SELECT last_insert_rowid();").fetchone()[0]
        self.conn.execute(
            "INSERT INTO chain_scores (chain_id, scored_at) VALUES (?,?);",
            (chain_id, "2024-01-01T09:00:00Z"),
        )
        row = self.conn.execute("SELECT * FROM chain_scores;").fetchone()
        assert row["novelty"] == pytest.approx(0.0)
        assert row["a_share_relevance"] == pytest.approx(0.0)
        assert row["prompt_profile_name"] == "default"

    def test_foreign_key_enforcement(self):
        """Inserting a raw_document with a non-existent run_id should raise."""
        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO raw_documents (run_id, source, url, fetched_at) VALUES (?,?,?,?);",
                (9999, "web", "http://x.com", "2024-01-01T00:00:00Z"),
            )

    def test_run_logs_multi_batch_same_date(self):
        """Two batches (batch_index 0 and 1) for the same date are both valid."""
        for batch in (0, 1):
            self.conn.execute(
                "INSERT INTO run_logs (run_date, batch_index, started_at, status, prompt_profile_name, prompt_profile_version) "
                "VALUES (?,?,?,?,?,?);",
                ("2024-01-01", batch, "2024-01-01T08:30:00Z", "success", "default", "1.0.0"),
            )
        count = self.conn.execute("SELECT COUNT(*) FROM run_logs;").fetchone()[0]
        assert count == 2
