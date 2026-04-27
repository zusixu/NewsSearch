"""
tests/test_scheduler.py — tests for app/scheduler.

Covers: determine_batch, should_run_now, RetryPolicy, DailyScheduler.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.scheduler.scheduler import (
    DailyScheduler,
    RetryPolicy,
    determine_batch,
    should_run_now,
    create_scheduler,
)


# ============================================================================
# determine_batch
# ============================================================================

class TestDetermineBatch:

    def test_morning_before_noon(self):
        t = datetime.time(8, 30)
        name, idx = determine_batch(t)
        assert name == "pre-market"
        assert idx == 0

    def test_early_morning(self):
        t = datetime.time(6, 0)
        name, idx = determine_batch(t)
        assert name == "pre-market"
        assert idx == 0

    def test_midnight(self):
        t = datetime.time(0, 0)
        name, idx = determine_batch(t)
        assert name == "pre-market"
        assert idx == 0

    def test_afternoon(self):
        t = datetime.time(14, 0)
        name, idx = determine_batch(t)
        assert name == "midday"
        assert idx == 1

    def test_evening(self):
        t = datetime.time(20, 0)
        name, idx = determine_batch(t)
        assert name == "midday"
        assert idx == 1

    def test_exactly_noon(self):
        t = datetime.time(12, 0)
        name, idx = determine_batch(t)
        assert name == "midday"
        assert idx == 1

    def test_just_before_noon(self):
        t = datetime.time(11, 59)
        name, idx = determine_batch(t)
        assert name == "pre-market"
        assert idx == 0

    def test_default_is_now(self):
        """Calling without argument should not raise."""
        name, idx = determine_batch()
        assert name in ("pre-market", "midday")
        assert idx in (0, 1)


# ============================================================================
# should_run_now
# ============================================================================

class TestShouldRunNow:

    def test_exact_match(self):
        now = datetime.time(8, 30)
        assert should_run_now(["08:30"], now) is True

    def test_within_tolerance(self):
        now = datetime.time(8, 33)
        assert should_run_now(["08:30"], now, tolerance_minutes=5) is True

    def test_outside_tolerance(self):
        now = datetime.time(8, 36)
        assert should_run_now(["08:30"], now, tolerance_minutes=5) is False

    def test_before_scheduled(self):
        now = datetime.time(8, 29)
        assert should_run_now(["08:30"], now, tolerance_minutes=5) is False

    def test_multiple_schedules_first_match(self):
        now = datetime.time(8, 32)
        assert should_run_now(["08:30", "14:00"], now, tolerance_minutes=5) is True

    def test_multiple_schedules_second_match(self):
        now = datetime.time(14, 2)
        assert should_run_now(["08:30", "14:00"], now, tolerance_minutes=5) is True

    def test_no_match(self):
        now = datetime.time(10, 0)
        assert should_run_now(["08:30", "14:00"], now, tolerance_minutes=5) is False

    def test_invalid_schedule_entry_skipped(self):
        now = datetime.time(8, 31)
        assert should_run_now(["invalid", "08:30"], now, tolerance_minutes=5) is True

    def test_default_now(self):
        """Calling without now should not raise."""
        result = should_run_now(["08:30", "14:00"])
        assert isinstance(result, bool)


# ============================================================================
# RetryPolicy
# ============================================================================

class TestRetryPolicy:

    def test_defaults(self):
        policy = RetryPolicy()
        assert policy.max_retries == 2
        assert policy.delay_seconds == 60
        assert policy.backoff_factor == 2.0

    def test_custom(self):
        policy = RetryPolicy(max_retries=5, delay_seconds=30, backoff_factor=1.5)
        assert policy.max_retries == 5
        assert policy.delay_seconds == 30
        assert policy.backoff_factor == 1.5

    def test_delay_for_attempt_1(self):
        policy = RetryPolicy(delay_seconds=60, backoff_factor=2.0)
        assert policy.delay_for_attempt(1) == 60

    def test_delay_for_attempt_2(self):
        policy = RetryPolicy(delay_seconds=60, backoff_factor=2.0)
        assert policy.delay_for_attempt(2) == 120

    def test_delay_for_attempt_3(self):
        policy = RetryPolicy(delay_seconds=60, backoff_factor=2.0)
        assert policy.delay_for_attempt(3) == 240

    def test_no_retries(self):
        policy = RetryPolicy(max_retries=0)
        assert policy.max_retries == 0

    def test_frozen(self):
        policy = RetryPolicy()
        with pytest.raises(AttributeError):
            policy.max_retries = 10


# ============================================================================
# DailyScheduler
# ============================================================================

class TestDailyScheduler:

    def test_default_batch_detection(self):
        config = MagicMock()
        scheduler = DailyScheduler(config=config)
        # Should not raise
        assert scheduler.config is config

    def test_custom_retry_policy(self):
        config = MagicMock()
        policy = RetryPolicy(max_retries=3, delay_seconds=30)
        scheduler = DailyScheduler(config=config, retry_policy=policy)
        assert scheduler.retry_policy.max_retries == 3
        assert scheduler.retry_policy.delay_seconds == 30

    def test_resolve_project_root_explicit(self, tmp_path):
        config = MagicMock()
        scheduler = DailyScheduler(config=config, project_root=tmp_path)
        assert scheduler._resolve_project_root() == tmp_path

    def test_resolve_project_root_default(self):
        config = MagicMock()
        scheduler = DailyScheduler(config=config)
        root = scheduler._resolve_project_root()
        assert root.exists()
        assert (root / "app").is_dir()

    def test_build_python_cmd(self):
        config = MagicMock()
        scheduler = DailyScheduler(config=config)
        cmd = scheduler._build_python_cmd("run", "2025-01-15", "aggressive-v1")
        assert "app.main" in cmd
        assert "run" in cmd
        assert "--date" in cmd
        assert "2025-01-15" in cmd
        assert "--prompt-profile" in cmd
        assert "aggressive-v1" in cmd

    def test_build_python_cmd_no_extras(self):
        config = MagicMock()
        scheduler = DailyScheduler(config=config)
        cmd = scheduler._build_python_cmd("dry-run", None, None)
        assert cmd[-2:] == ["app.main", "dry-run"] or cmd[-1] == "dry-run"

    @patch("app.scheduler.scheduler.DailyScheduler._execute_once")
    def test_run_success_first_try(self, mock_exec):
        mock_exec.return_value = 0
        config = MagicMock()
        scheduler = DailyScheduler(
            config=config,
            retry_policy=RetryPolicy(max_retries=2),
        )
        result = scheduler.run(mode="run", batch_name="pre-market", batch_index=0)
        assert result == 0
        assert mock_exec.call_count == 1

    @patch("app.scheduler.scheduler._time.sleep")
    @patch("app.scheduler.scheduler.DailyScheduler._execute_once")
    def test_run_success_after_retry(self, mock_exec, mock_sleep):
        mock_exec.side_effect = [1, 0]  # Fail first, succeed second
        config = MagicMock()
        scheduler = DailyScheduler(
            config=config,
            retry_policy=RetryPolicy(max_retries=2, delay_seconds=10, backoff_factor=2.0),
        )
        result = scheduler.run(mode="run", batch_name="midday", batch_index=1)
        assert result == 0
        assert mock_exec.call_count == 2
        mock_sleep.assert_called_once_with(10)

    @patch("app.scheduler.scheduler._time.sleep")
    @patch("app.scheduler.scheduler.DailyScheduler._execute_once")
    def test_run_all_retries_exhausted(self, mock_exec, mock_sleep):
        mock_exec.return_value = 1
        config = MagicMock()
        scheduler = DailyScheduler(
            config=config,
            retry_policy=RetryPolicy(max_retries=2, delay_seconds=10),
        )
        result = scheduler.run(mode="run")
        assert result == 1
        assert mock_exec.call_count == 3  # initial + 2 retries

    @patch("app.scheduler.scheduler._time.sleep")
    @patch("app.scheduler.scheduler.DailyScheduler._execute_once")
    def test_retry_backoff(self, mock_exec, mock_sleep):
        mock_exec.side_effect = [1, 1, 0]
        config = MagicMock()
        scheduler = DailyScheduler(
            config=config,
            retry_policy=RetryPolicy(max_retries=2, delay_seconds=60, backoff_factor=2.0),
        )
        result = scheduler.run(mode="run")
        assert result == 0
        assert mock_sleep.call_count == 2
        # First retry: 60s, second retry: 120s
        mock_sleep.assert_any_call(60)
        mock_sleep.assert_any_call(120)

    @patch("app.scheduler.scheduler.DailyScheduler._execute_once")
    def test_no_retries(self, mock_exec):
        mock_exec.return_value = 1
        config = MagicMock()
        scheduler = DailyScheduler(
            config=config,
            retry_policy=RetryPolicy(max_retries=0),
        )
        result = scheduler.run(mode="run")
        assert result == 1
        assert mock_exec.call_count == 1

    @patch("app.scheduler.scheduler._time.sleep")
    @patch("app.scheduler.scheduler.DailyScheduler._execute_once")
    def test_exception_treated_as_failure(self, mock_exec, mock_sleep):
        mock_exec.side_effect = [RuntimeError("boom"), 0]
        config = MagicMock()
        scheduler = DailyScheduler(
            config=config,
            retry_policy=RetryPolicy(max_retries=1, delay_seconds=5),
        )
        result = scheduler.run(mode="run")
        assert result == 0
        assert mock_exec.call_count == 2


# ============================================================================
# create_scheduler
# ============================================================================

class TestCreateScheduler:

    def test_defaults(self):
        config = MagicMock()
        scheduler = create_scheduler(config)
        assert isinstance(scheduler, DailyScheduler)
        assert scheduler.retry_policy.max_retries == 2
        assert scheduler.retry_policy.delay_seconds == 60

    def test_custom_policy(self):
        config = MagicMock()
        scheduler = create_scheduler(
            config,
            max_retries=5,
            delay_seconds=30,
            backoff_factor=1.5,
        )
        assert scheduler.retry_policy.max_retries == 5
        assert scheduler.retry_policy.delay_seconds == 30
        assert scheduler.retry_policy.backoff_factor == 1.5
