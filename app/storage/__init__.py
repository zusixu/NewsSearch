"""
app/storage — SQLite storage layer.

Public API:
    open_connection(db_path)  -> sqlite3.Connection
    init_db(db_path)          -> sqlite3.Connection
    get_db(db_path)           -> sqlite3.Connection
    RunLogEntry               — data class for run_logs entries
    RunLogStore               — manage run_logs entries
    PromptProfileStore        — archive and retrieve prompt profiles
    ChainScoreEntry           — data class for chain_scores entries
    ChainScoreStore           — manage chain_scores entries
    InfoChainStore            — manage info_chains entries
"""

from app.storage.database import (
    ChainScoreEntry,
    ChainScoreStore,
    InfoChainStore,
    PromptProfileStore,
    RunLogEntry,
    RunLogStore,
    get_db,
    init_db,
    open_connection,
)

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

