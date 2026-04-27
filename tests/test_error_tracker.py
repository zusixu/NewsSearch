"""
tests/test_error_tracker.py — tests for app/qa.error_tracker.
"""

from __future__ import annotations

import pytest

from app.storage import init_db, RunLogStore
from app.qa.error_tracker import ErrorTracker, ErrorSummary


class TestErrorSummary:

    def test_frozen(self):
        summary = ErrorSummary(
            total_runs=10,
            failed_runs=2,
            success_rate=0.8,
            error_messages=["err1", "err2"],
        )
        with pytest.raises(AttributeError):
            summary.total_runs = 20

    def test_fields(self):
        summary = ErrorSummary(
            total_runs=10,
            failed_runs=2,
            success_rate=0.8,
            error_messages=["err1"],
        )
        assert summary.total_runs == 10
        assert summary.failed_runs == 2
        assert summary.success_rate == 0.8
        assert len(summary.error_messages) == 1


class TestErrorTracker:

    def _make_tracker(self) -> tuple:
        conn = init_db(":memory:")
        run_store = RunLogStore(conn)
        tracker = ErrorTracker(conn)
        return tracker, run_store

    def test_empty_database(self):
        tracker, _ = self._make_tracker()
        summary = tracker.get_error_summary(start_date="2025-01-01", end_date="2025-12-31")
        assert summary.total_runs == 0
        assert summary.failed_runs == 0
        assert summary.success_rate == 1.0
        assert summary.error_messages == []

    def test_all_successes(self):
        tracker, run_store = self._make_tracker()
        for i in range(5):
            rid = run_store.start_run(run_date="2025-03-18", batch_index=i)
            run_store.finish_run(rid, success=True)

        summary = tracker.get_error_summary(start_date="2025-03-01", end_date="2025-03-31")
        assert summary.total_runs == 5
        assert summary.failed_runs == 0
        assert summary.success_rate == 1.0

    def test_all_failures(self):
        tracker, run_store = self._make_tracker()
        for i in range(3):
            rid = run_store.start_run(run_date="2025-03-18", batch_index=i)
            run_store.finish_run(rid, success=False, error_text=f"Error {i}")

        summary = tracker.get_error_summary(start_date="2025-03-01", end_date="2025-03-31")
        assert summary.total_runs == 3
        assert summary.failed_runs == 3
        assert summary.success_rate == 0.0
        assert len(summary.error_messages) == 3

    def test_mixed_success_failure(self):
        tracker, run_store = self._make_tracker()
        rid1 = run_store.start_run(run_date="2025-03-18", batch_index=0)
        run_store.finish_run(rid1, success=True)
        rid2 = run_store.start_run(run_date="2025-03-18", batch_index=1)
        run_store.finish_run(rid2, success=False, error_text="Timeout")
        rid3 = run_store.start_run(run_date="2025-03-18", batch_index=2)
        run_store.finish_run(rid3, success=True)

        summary = tracker.get_error_summary(start_date="2025-03-01", end_date="2025-03-31")
        assert summary.total_runs == 3
        assert summary.failed_runs == 1
        assert abs(summary.success_rate - 2 / 3) < 0.01
        assert summary.error_messages == ["Timeout"]

    def test_date_filtering(self):
        tracker, run_store = self._make_tracker()
        rid1 = run_store.start_run(run_date="2025-03-10")
        run_store.finish_run(rid1, success=True)
        rid2 = run_store.start_run(run_date="2025-03-20")
        run_store.finish_run(rid2, success=False, error_text="Late error")

        # Only March 10
        summary = tracker.get_error_summary(start_date="2025-03-10", end_date="2025-03-10")
        assert summary.total_runs == 1
        assert summary.failed_runs == 0

        # Only March 20
        summary = tracker.get_error_summary(start_date="2025-03-20", end_date="2025-03-20")
        assert summary.total_runs == 1
        assert summary.failed_runs == 1

    def test_recent_failures_empty(self):
        tracker, _ = self._make_tracker()
        failures = tracker.get_recent_failures()
        assert failures == []

    def test_recent_failures(self):
        tracker, run_store = self._make_tracker()
        rid1 = run_store.start_run(run_date="2025-03-18", batch_index=0)
        run_store.finish_run(rid1, success=False, error_text="Error A")
        rid2 = run_store.start_run(run_date="2025-03-18", batch_index=1)
        run_store.finish_run(rid2, success=True)
        rid3 = run_store.start_run(run_date="2025-03-18", batch_index=2)
        run_store.finish_run(rid3, success=False, error_text="Error B")

        failures = tracker.get_recent_failures(limit=10)
        assert len(failures) == 2
        # Both errors should be present (order depends on started_at)
        error_texts = {f["error_text"] for f in failures}
        assert error_texts == {"Error A", "Error B"}

    def test_recent_failures_limit(self):
        tracker, run_store = self._make_tracker()
        for i in range(5):
            rid = run_store.start_run(run_date="2025-03-18", batch_index=i)
            run_store.finish_run(rid, success=False, error_text=f"Error {i}")

        failures = tracker.get_recent_failures(limit=2)
        assert len(failures) == 2

    def test_run_duration_stats_empty(self):
        tracker, _ = self._make_tracker()
        stats = tracker.get_run_duration_stats(start_date="2025-01-01", end_date="2025-12-31")
        assert stats["count"] == 0
        assert stats["avg_seconds"] == 0

    def test_run_duration_stats(self):
        tracker, run_store = self._make_tracker()
        # We can't easily control the time in RunLogStore.finish_run,
        # but we can verify the query doesn't crash and returns proper structure.
        rid = run_store.start_run(run_date="2025-03-18")
        run_store.finish_run(rid, success=True)

        stats = tracker.get_run_duration_stats(start_date="2025-03-01", end_date="2025-03-31")
        assert stats["count"] == 1
        assert stats["avg_seconds"] >= 0
        assert stats["min_seconds"] >= 0
        assert stats["max_seconds"] >= 0

    def test_default_date_range(self):
        """Default date range should not raise."""
        tracker, run_store = self._make_tracker()
        rid = run_store.start_run(run_date="2025-03-18")
        run_store.finish_run(rid, success=True)

        # Should not raise even with default dates
        summary = tracker.get_error_summary()
        assert isinstance(summary, ErrorSummary)
