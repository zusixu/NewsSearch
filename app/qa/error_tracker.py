"""
app/qa/error_tracker.py — runtime error tracking and reporting.

Public API:
    ErrorTracker        — track and query runtime errors from pipeline runs
    ErrorSummary        — summary of errors for a given time range
"""

from __future__ import annotations

import datetime
import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ErrorSummary:
    """
    Summary of errors for a given time range.

    Fields
    ------
    total_runs
        Total number of runs in the period.
    failed_runs
        Number of failed runs.
    success_rate
        Fraction of runs that succeeded (0.0–1.0).
    error_messages
        List of error messages from failed runs.
    """
    total_runs: int
    failed_runs: int
    success_rate: float
    error_messages: list[str]


class ErrorTracker:
    """
    Track and query runtime errors from pipeline runs.

    Reads from the run_logs table managed by RunLogStore.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_error_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> ErrorSummary:
        """
        Get error summary for a date range.

        Parameters
        ----------
        start_date
            Start date (YYYY-MM-DD), defaults to 7 days ago.
        end_date
            End date (YYYY-MM-DD), defaults to today.

        Returns
        -------
        ErrorSummary
        """
        if end_date is None:
            end_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        if start_date is None:
            start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
            start_date = start.strftime("%Y-%m-%d")

        # Total runs
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM run_logs WHERE run_date >= ? AND run_date <= ?",
            (start_date, end_date),
        )
        total = cursor.fetchone()[0]

        # Failed runs
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM run_logs WHERE run_date >= ? AND run_date <= ? AND status = 'failed'",
            (start_date, end_date),
        )
        failed = cursor.fetchone()[0]

        # Error messages
        cursor = self._conn.execute(
            "SELECT error_text FROM run_logs WHERE run_date >= ? AND run_date <= ? AND status = 'failed' AND error_text IS NOT NULL",
            (start_date, end_date),
        )
        error_messages = [row[0] for row in cursor.fetchall() if row[0]]

        success_rate = (total - failed) / total if total > 0 else 1.0

        return ErrorSummary(
            total_runs=total,
            failed_runs=failed,
            success_rate=success_rate,
            error_messages=error_messages,
        )

    def get_recent_failures(self, limit: int = 10) -> list[dict]:
        """
        Get recent failed runs.

        Parameters
        ----------
        limit
            Maximum number of entries to return.

        Returns
        -------
        list[dict]
            List of dicts with keys: id, run_date, batch_index, started_at, error_text.
        """
        cursor = self._conn.execute(
            """
            SELECT id, run_date, batch_index, started_at, error_text
            FROM run_logs
            WHERE status = 'failed'
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "id": row[0],
                "run_date": row[1],
                "batch_index": row[2],
                "started_at": row[3],
                "error_text": row[4],
            }
            for row in cursor.fetchall()
        ]

    def get_run_duration_stats(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """
        Get run duration statistics.

        Returns
        -------
        dict
            Keys: avg_seconds, min_seconds, max_seconds, count.
        """
        if end_date is None:
            end_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        if start_date is None:
            start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
            start_date = start.strftime("%Y-%m-%d")

        cursor = self._conn.execute(
            """
            SELECT
                AVG(CAST((julianday(finished_at) - julianday(started_at)) * 86400 AS REAL)) as avg_seconds,
                MIN(CAST((julianday(finished_at) - julianday(started_at)) * 86400 AS REAL)) as min_seconds,
                MAX(CAST((julianday(finished_at) - julianday(started_at)) * 86400 AS REAL)) as max_seconds,
                COUNT(*) as count
            FROM run_logs
            WHERE run_date >= ? AND run_date <= ?
              AND status = 'success'
              AND finished_at IS NOT NULL
            """,
            (start_date, end_date),
        )
        row = cursor.fetchone()
        if row is None or row[3] == 0:
            return {"avg_seconds": 0, "min_seconds": 0, "max_seconds": 0, "count": 0}

        return {
            "avg_seconds": round(row[0] or 0, 1),
            "min_seconds": round(row[1] or 0, 1),
            "max_seconds": round(row[2] or 0, 1),
            "count": row[3],
        }
