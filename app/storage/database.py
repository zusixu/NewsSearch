"""
app/storage/database.py — SQLite connection and initialisation helpers.

Public API (re-exported from app.storage):
    open_connection(db_path)  -> sqlite3.Connection
    init_db(db_path)          -> sqlite3.Connection
    get_db(db_path)           -> sqlite3.Connection   (alias for init_db)
    RunLogStore               — manage run_logs entries
    PromptProfileStore        — archive and retrieve prompt profiles

Design choices:
- Uses stdlib sqlite3 only — no third-party ORM or driver.
- open_connection() creates a plain connection with recommended pragmas.
- init_db() calls open_connection() then applies schema.sql idempotently.
- All helpers are safe to call repeatedly; CREATE IF NOT EXISTS guards the schema.
- Foreign key enforcement is enabled on every connection.
- WAL journal mode is used for better concurrent read performance.
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.analysis.adapters.contracts import PromptTaskType
from app.analysis.prompts import PromptProfileConfig, PromptProfileLoader
from app.analysis.prompts.profile import TaskTemplateMapping

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _read_schema() -> str:
    """Return the contents of schema.sql."""
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply recommended pragmas to a freshly opened connection."""
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")


def _utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _date_only_iso(dt: datetime.datetime | None = None) -> str:
    """Return date-only ISO-8601 string (YYYY-MM-DD)."""
    if dt is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    return dt.date().isoformat()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def open_connection(db_path: str | os.PathLike) -> sqlite3.Connection:
    """
    Open (or create) a SQLite database at *db_path* and return the connection.

    - Parent directories are created automatically.
    - Foreign keys and WAL journal mode are enabled.
    - The schema is NOT applied; call :func:`init_db` for a fully initialised DB.

    Parameters
    ----------
    db_path:
        File-system path to the ``.db`` file.  An in-memory database can be
        requested by passing ``":memory:"``.

    Returns
    -------
    sqlite3.Connection
        The opened connection with ``row_factory = sqlite3.Row`` so callers
        can access columns by name.
    """
    db_path = str(db_path)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    return conn


def init_db(db_path: str | os.PathLike) -> sqlite3.Connection:
    """
    Open (or create) the database at *db_path*, apply the baseline schema, and
    return the connection.

    Safe to call repeatedly — all DDL statements use ``IF NOT EXISTS``.

    Parameters
    ----------
    db_path:
        File-system path to the ``.db`` file, or ``":memory:"`` for an
        in-memory database (useful in tests).

    Returns
    -------
    sqlite3.Connection
        The opened, schema-initialised connection.
    """
    conn = open_connection(db_path)
    schema_sql = _read_schema()
    conn.executescript(schema_sql)
    conn.commit()
    return conn


# Convenience alias so callers don't have to pick between the two helpers in
# the common case where they just want a ready-to-use connection.
get_db = init_db


# ---------------------------------------------------------------------------
# RunLog data class
# ---------------------------------------------------------------------------

@dataclass
class RunLogEntry:
    """A single entry in the run_logs table."""
    id: int | None = None
    run_date: str = ""
    batch_index: int = 0
    started_at: str = ""
    finished_at: str | None = None
    status: str = "running"
    error_text: str | None = None
    prompt_profile_name: str = "default"
    prompt_profile_version: str = "unknown"
    prompt_profile_desc: str = ""


# ---------------------------------------------------------------------------
# RunLogStore — manage run_logs entries
# ---------------------------------------------------------------------------

class RunLogStore:
    """Manage entries in the run_logs table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        Initialize the store with a database connection.

        Parameters
        ----------
        conn
            Open SQLite connection (not closed by this store).
        """
        self._conn = conn

    def start_run(
        self,
        prompt_profile_name: str = "default",
        prompt_profile_version: str = "unknown",
        prompt_profile_desc: str = "",
        run_date: str | None = None,
        batch_index: int = 0,
    ) -> int:
        """
        Start a new run and insert a row into run_logs.

        Parameters
        ----------
        prompt_profile_name
            Name of the prompt profile used for this run.
        prompt_profile_version
            Version of the prompt profile used for this run.
        prompt_profile_desc
            Optional description of the prompt profile.
        run_date
            YYYY-MM-DD run date (default: today UTC).
        batch_index
            0-based batch index for same-day multiple runs.

        Returns
        -------
        int
            The newly inserted run_logs.id.
        """
        if run_date is None:
            run_date = _date_only_iso()

        started_at = _utc_now_iso()

        cursor = self._conn.execute(
            """
            INSERT INTO run_logs
            (run_date, batch_index, started_at, status,
             prompt_profile_name, prompt_profile_version, prompt_profile_desc)
            VALUES (?, ?, ?, 'running', ?, ?, ?)
            """,
            (
                run_date,
                batch_index,
                started_at,
                prompt_profile_name,
                prompt_profile_version,
                prompt_profile_desc,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def finish_run(
        self,
        run_id: int,
        success: bool = True,
        error_text: str | None = None,
    ) -> None:
        """
        Mark a run as finished (success or failed).

        Parameters
        ----------
        run_id
            The run_logs.id to update.
        success
            Whether the run succeeded (True) or failed (False).
        error_text
            Optional error text when success=False.
        """
        finished_at = _utc_now_iso()
        status = "success" if success else "failed"

        self._conn.execute(
            """
            UPDATE run_logs
            SET finished_at = ?, status = ?, error_text = ?
            WHERE id = ?
            """,
            (finished_at, status, error_text, run_id),
        )
        self._conn.commit()

    def get_run(self, run_id: int) -> RunLogEntry | None:
        """
        Get a run log entry by ID.

        Parameters
        ----------
        run_id
            The run_logs.id to retrieve.

        Returns
        -------
        RunLogEntry or None
            The entry if found, otherwise None.
        """
        cursor = self._conn.execute(
            "SELECT * FROM run_logs WHERE id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return RunLogEntry(
            id=row["id"],
            run_date=row["run_date"],
            batch_index=row["batch_index"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            status=row["status"],
            error_text=row["error_text"],
            prompt_profile_name=row["prompt_profile_name"],
            prompt_profile_version=row["prompt_profile_version"],
            prompt_profile_desc=row["prompt_profile_desc"],
        )

    def get_latest_run(self) -> RunLogEntry | None:
        """
        Get the most recently started run.

        Returns
        -------
        RunLogEntry or None
            The latest entry if any exist, otherwise None.
        """
        cursor = self._conn.execute(
            "SELECT * FROM run_logs ORDER BY started_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return RunLogEntry(
            id=row["id"],
            run_date=row["run_date"],
            batch_index=row["batch_index"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            status=row["status"],
            error_text=row["error_text"],
            prompt_profile_name=row["prompt_profile_name"],
            prompt_profile_version=row["prompt_profile_version"],
            prompt_profile_desc=row["prompt_profile_desc"],
        )


# ---------------------------------------------------------------------------
# PromptProfileStore — archive and retrieve prompt profiles
# ---------------------------------------------------------------------------

class PromptProfileStore:
    """Archive and retrieve prompt profiles for reproducibility."""

    def __init__(self, conn: sqlite3.Connection, templates_dir: str | Path | None = None) -> None:
        """
        Initialize the store with a database connection and optional templates directory.

        Parameters
        ----------
        conn
            Open SQLite connection (not closed by this store).
        templates_dir
            Directory containing prompt template JSON files (optional).
        """
        self._conn = conn
        self._templates_dir = Path(templates_dir) if templates_dir else None

    def archive_profile(
        self,
        profile_config: PromptProfileConfig,
        templates_dir: str | Path | None = None,
    ) -> int:
        """
        Archive a prompt profile (including all template content) into the database.

        If the profile (name + version) already exists, it is NOT overwritten.

        Parameters
        ----------
        profile_config
            The prompt profile configuration to archive.
        templates_dir
            Directory containing template files (overrides __init__ value).

        Returns
        -------
        int
            The prompt_profiles.id (existing or newly inserted).
        """
        # Check if profile already exists
        cursor = self._conn.execute(
            "SELECT id FROM prompt_profiles WHERE profile_name = ? AND version = ?",
            (profile_config.profile_name, profile_config.version),
        )
        row = cursor.fetchone()
        if row is not None:
            return row["id"]

        # Build config JSON (convert to dict first)
        config_dict = {
            "profile_name": profile_config.profile_name,
            "version": profile_config.version,
            "description": profile_config.description,
            "tasks": {
                task_type.value: {
                    "template": mapping.template,
                    "overrides": mapping.overrides,
                }
                for task_type, mapping in profile_config.tasks.items()
            },
        }
        config_json = json.dumps(config_dict, ensure_ascii=False)

        # Load and archive all template files
        template_files: dict[str, str] = {}
        templates_path = Path(templates_dir) if templates_dir else self._templates_dir

        if templates_path and templates_path.is_dir():
            for task_type, mapping in profile_config.tasks.items():
                template_path = templates_path / mapping.template
                if template_path.is_file():
                    template_files[task_type.value] = template_path.read_text(encoding="utf-8")

        template_files_json = json.dumps(template_files, ensure_ascii=False)
        archived_at = _utc_now_iso()

        cursor = self._conn.execute(
            """
            INSERT INTO prompt_profiles
            (profile_name, version, description, config_json, template_files, archived_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                profile_config.profile_name,
                profile_config.version,
                profile_config.description,
                config_json,
                template_files_json,
                archived_at,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_profile(
        self,
        profile_name: str,
        version: str,
    ) -> PromptProfileConfig | None:
        """
        Retrieve an archived prompt profile by name and version.

        Parameters
        ----------
        profile_name
            Name of the profile to retrieve.
        version
            Version of the profile to retrieve.

        Returns
        -------
        PromptProfileConfig or None
            The archived profile if found, otherwise None.
        """
        cursor = self._conn.execute(
            "SELECT config_json FROM prompt_profiles WHERE profile_name = ? AND version = ?",
            (profile_name, version),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        config_dict = json.loads(row["config_json"])
        return PromptProfileConfig.from_dict(config_dict)

    def list_archived_profiles(self) -> list[tuple[str, str, str, str]]:
        """
        List all archived profiles.

        Returns
        -------
        list[tuple]
            List of (profile_name, version, description, archived_at) tuples.
        """
        cursor = self._conn.execute(
            """
            SELECT profile_name, version, description, archived_at
            FROM prompt_profiles
            ORDER BY profile_name, archived_at DESC
            """
        )
        return [
            (row["profile_name"], row["version"], row["description"], row["archived_at"])
            for row in cursor.fetchall()
        ]


# ---------------------------------------------------------------------------
# ChainScore data class
# ---------------------------------------------------------------------------


@dataclass
class ChainScoreEntry:
    """A single entry in the chain_scores table."""
    id: int | None = None
    chain_id: int = 0  # info_chains.id
    run_id: int | None = None
    novelty: float = 0.0
    importance: float = 0.0
    credibility: float = 0.0
    a_share_relevance: float = 0.0
    overall: float = 0.0
    scored_at: str = ""
    prompt_profile_name: str = "default"
    prompt_profile_version: str = "unknown"


# ---------------------------------------------------------------------------
# ChainScoreStore — manage chain_scores entries
# ---------------------------------------------------------------------------


class ChainScoreStore:
    """Manage entries in the chain_scores table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        Initialize the store with a database connection.

        Parameters
        ----------
        conn
            Open SQLite connection (not closed by this store).
        """
        self._conn = conn

    def insert_score(
        self,
        chain_id: int,
        run_id: int | None,
        novelty: float = 0.0,
        importance: float = 0.0,
        credibility: float = 0.0,
        a_share_relevance: float = 0.0,
        overall: float = 0.0,
        prompt_profile_name: str = "default",
        prompt_profile_version: str = "unknown",
    ) -> int:
        """
        Insert a new chain score entry.

        Parameters
        ----------
        chain_id
            info_chains.id this score belongs to.
        run_id
            Optional run_logs.id.
        novelty
            Novelty score (0.0-1.0).
        importance
            Importance score (0.0-1.0).
        credibility
            Credibility score (0.0-1.0).
        a_share_relevance
            A-share relevance score (0.0-1.0).
        overall
            Overall composite score (0.0-1.0).
        prompt_profile_name
            Name of prompt profile used.
        prompt_profile_version
            Version of prompt profile used.

        Returns
        -------
        int
            The newly inserted chain_scores.id.
        """
        scored_at = _utc_now_iso()
        cursor = self._conn.execute(
            """
            INSERT INTO chain_scores
            (chain_id, run_id, novelty, importance, credibility, a_share_relevance,
             overall, scored_at, prompt_profile_name, prompt_profile_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chain_id,
                run_id,
                float(novelty),
                float(importance),
                float(credibility),
                float(a_share_relevance),
                float(overall),
                scored_at,
                prompt_profile_name,
                prompt_profile_version,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def insert_from_analysis_response(
        self,
        analysis_response: Any,  # Will take AnalysisResponse
        chain_db_ids: dict[str, int],  # Maps chain.uuid -> info_chains.id
        run_id: int | None = None,
    ) -> list[int]:
        """
        Insert scores from an AnalysisResponse.

        Parameters
        ----------
        analysis_response
            The AnalysisResponse from the LLM analysis.
        chain_db_ids
            Dictionary mapping chain UUID (string) to database info_chains.id (int).
        run_id
            Optional run_logs.id to associate with these scores.

        Returns
        -------
        list[int]
            List of newly inserted chain_scores.id.
        """
        inserted_ids: list[int] = []

        # Build rank/score mapping from ranking
        rank_map: dict[str, tuple[int, float, str]] = {}
        if hasattr(analysis_response, "ranking") and hasattr(analysis_response.ranking, "entries"):
            for entry in analysis_response.ranking.entries:
                rank_map[entry.chain_id] = (entry.rank, entry.score, entry.rationale)

        # Process each chain result
        if hasattr(analysis_response, "chain_results"):
            for result in analysis_response.chain_results:
                chain_uuid = result.chain_id
                db_chain_id = chain_db_ids.get(chain_uuid)
                if db_chain_id is None:
                    continue

                # Extract scores from result
                confidence = getattr(result, "confidence", 0.5)
                rank_info = rank_map.get(chain_uuid)
                rank, score, rationale = rank_info if rank_info else (0, confidence, "")

                # Map to our score dimensions (simple heuristic for now)
                # These can be refined later with more sophisticated mapping from LLM output
                novelty = min(1.0, confidence + 0.1)
                importance = min(1.0, (score if score != 0 else confidence))
                credibility = confidence
                a_share_relevance = 0.5  # Default middle value
                overall = (novelty + importance + credibility + a_share_relevance) / 4

                # Get profile info
                profile_name = getattr(result.prompt_profile, "profile_name", "default")
                profile_version = getattr(result.prompt_profile, "version", "unknown")

                inserted_id = self.insert_score(
                    chain_id=db_chain_id,
                    run_id=run_id,
                    novelty=novelty,
                    importance=importance,
                    credibility=credibility,
                    a_share_relevance=a_share_relevance,
                    overall=overall,
                    prompt_profile_name=profile_name,
                    prompt_profile_version=profile_version,
                )
                inserted_ids.append(inserted_id)

        return inserted_ids

    def get_scores_for_run(self, run_id: int) -> list[ChainScoreEntry]:
        """
        Get all chain scores for a given run.

        Parameters
        ----------
        run_id
            run_logs.id to get scores for.

        Returns
        -------
        list[ChainScoreEntry]
            List of ChainScoreEntry objects, sorted by overall score descending.
        """
        cursor = self._conn.execute(
            """
            SELECT * FROM chain_scores
            WHERE run_id = ?
            ORDER BY overall DESC
            """,
            (run_id,),
        )
        return [
            ChainScoreEntry(
                id=row["id"],
                chain_id=row["chain_id"],
                run_id=row["run_id"],
                novelty=row["novelty"],
                importance=row["importance"],
                credibility=row["credibility"],
                a_share_relevance=row["a_share_relevance"],
                overall=row["overall"],
                scored_at=row["scored_at"],
                prompt_profile_name=row["prompt_profile_name"],
                prompt_profile_version=row["prompt_profile_version"],
            )
            for row in cursor.fetchall()
        ]

    def get_top_scores(self, limit: int = 10) -> list[ChainScoreEntry]:
        """
        Get the top N chain scores by overall score.

        Parameters
        ----------
        limit
            Maximum number of scores to return.

        Returns
        -------
        list[ChainScoreEntry]
            List of top ChainScoreEntry objects.
        """
        cursor = self._conn.execute(
            """
            SELECT * FROM chain_scores
            ORDER BY overall DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            ChainScoreEntry(
                id=row["id"],
                chain_id=row["chain_id"],
                run_id=row["run_id"],
                novelty=row["novelty"],
                importance=row["importance"],
                credibility=row["credibility"],
                a_share_relevance=row["a_share_relevance"],
                overall=row["overall"],
                scored_at=row["scored_at"],
                prompt_profile_name=row["prompt_profile_name"],
                prompt_profile_version=row["prompt_profile_version"],
            )
            for row in cursor.fetchall()
        ]


# ---------------------------------------------------------------------------
# InfoChainStore — basic storage for info_chains
# ---------------------------------------------------------------------------


class InfoChainStore:
    """Basic storage for info_chains table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_chain(
        self,
        run_id: int | None,
        title: str = "",
        summary: str = "",
        chain_type: str = "unknown",
    ) -> int:
        """
        Insert a new information chain.

        Returns
        -------
        int
            The newly inserted info_chains.id.
        """
        created_at = _utc_now_iso()
        cursor = self._conn.execute(
            """
            INSERT INTO info_chains (run_id, title, summary, chain_type, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, title, summary, chain_type, created_at),
        )
        self._conn.commit()
        return cursor.lastrowid


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "open_connection",
    "init_db",
    "get_db",
    "RunLogEntry",
    "RunLogStore",
    "PromptProfileStore",
    "ChainScoreEntry",
    "ChainScoreStore",
    "InfoChainStore",
]
