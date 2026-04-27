"""
app/scheduler/scheduler.py — daily run orchestration, batch detection, and retry logic.

Public API:
    DailyScheduler        — orchestrates daily pipeline runs with batch detection
    determine_batch       — map a run time to batch name / index
    should_run_now        — decide whether a scheduled run is due
    RetryPolicy           — configurable retry behaviour
"""

from __future__ import annotations

import datetime
import subprocess
import sys
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Batch detection
# ---------------------------------------------------------------------------

# The two scheduled run times and their batch identifiers.
_BATCH_MAP: list[tuple[str, str, int]] = [
    # (HH:MM threshold, batch_name, batch_index)
    # Anything before 12:00 → pre-market (batch_index 0)
    # Anything at or after 12:00 → midday   (batch_index 1)
    ("12:00", "midday", 1),
    ("00:00", "pre-market", 0),
]

# Ordered by threshold descending so the first match wins.
_BATCH_MAP.sort(key=lambda t: t[0], reverse=True)


def determine_batch(
    run_time: datetime.time | None = None,
) -> tuple[str, int]:
    """
    Determine the batch name and index for a given local time.

    Parameters
    ----------
    run_time
        The local time of the run.  Defaults to now.

    Returns
    -------
    tuple[str, int]
        (batch_name, batch_index) where batch_name is "pre-market" or "midday".
    """
    if run_time is None:
        run_time = datetime.datetime.now().time()

    time_str = run_time.strftime("%H:%M")

    for threshold, batch_name, batch_index in _BATCH_MAP:
        if time_str >= threshold:
            return batch_name, batch_index

    # Fallback — anything before 12:00 is pre-market
    return "pre-market", 0


# ---------------------------------------------------------------------------
# Run-due check
# ---------------------------------------------------------------------------

def should_run_now(
    scheduled_times: list[str],
    now: datetime.time | None = None,
    tolerance_minutes: int = 5,
) -> bool:
    """
    Check whether a scheduled run is due within *tolerance_minutes* of *now*.

    Parameters
    ----------
    scheduled_times
        List of "HH:MM" strings from config.
    now
        Current local time.  Defaults to now.
    tolerance_minutes
        How many minutes past a scheduled time the run is still considered due.

    Returns
    -------
    bool
    """
    if now is None:
        now = datetime.datetime.now().time()

    now_minutes = now.hour * 60 + now.minute

    for entry in scheduled_times:
        try:
            h, m = entry.split(":")
            scheduled_minutes = int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            continue

        if 0 <= (now_minutes - scheduled_minutes) <= tolerance_minutes:
            return True

    return False


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    """
    Configurable retry behaviour for the daily pipeline.

    Fields
    ------
    max_retries
        Maximum number of retry attempts (0 = no retries).
    delay_seconds
        Base delay between retries in seconds.
    backoff_factor
        Multiplier applied to *delay_seconds* after each attempt
        (exponential backoff).
    """
    max_retries: int = 2
    delay_seconds: int = 60
    backoff_factor: float = 2.0

    def delay_for_attempt(self, attempt: int) -> int:
        """Return the delay in seconds before the *attempt*-th retry (1-based)."""
        return int(self.delay_seconds * (self.backoff_factor ** (attempt - 1)))


# ---------------------------------------------------------------------------
# Daily scheduler
# ---------------------------------------------------------------------------

@dataclass
class DailyScheduler:
    """
    Orchestrates daily pipeline runs with batch detection and retry.

    Usage::

        from app.config import load_config
        from app.scheduler import DailyScheduler, determine_batch

        config = load_config()
        batch_name, batch_index = determine_batch()
        scheduler = DailyScheduler(config=config)
        exit_code = scheduler.run(
            mode="run",
            batch_name=batch_name,
            batch_index=batch_index,
            target_date="2025-01-15",
        )
    """
    config: object  # AppConfig — avoid circular import
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    project_root: Path | None = None

    def _resolve_project_root(self) -> Path:
        if self.project_root is not None:
            return self.project_root
        # Default: parent of app/
        return Path(__file__).resolve().parent.parent.parent

    def _build_python_cmd(
        self,
        mode: str,
        target_date: str | None,
        prompt_profile: str | None,
    ) -> list[str]:
        cmd = [sys.executable, "-m", "app.main", mode]
        if target_date:
            cmd.extend(["--date", target_date])
        if prompt_profile:
            cmd.extend(["--prompt-profile", prompt_profile])
        return cmd

    def _execute_once(
        self,
        mode: str,
        target_date: str | None,
        prompt_profile: str | None,
    ) -> int:
        """Run the pipeline once, returning the exit code."""
        root = self._resolve_project_root()
        cmd = self._build_python_cmd(mode, target_date, prompt_profile)

        result = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=False,
        )
        return result.returncode

    def run(
        self,
        mode: str = "run",
        batch_name: str | None = None,
        batch_index: int | None = None,
        target_date: str | None = None,
        prompt_profile: str | None = None,
    ) -> int:
        """
        Execute the pipeline with retry logic.

        Parameters
        ----------
        mode
            Pipeline mode ("run", "collect-only", "analyze-only", "dry-run").
        batch_name
            Batch name for logging ("pre-market" / "midday").
        batch_index
            0-based batch index.
        target_date
            YYYY-MM-DD for backfill.
        prompt_profile
            Named prompt profile override.

        Returns
        -------
        int
            Final exit code (0 = success).
        """
        from app.logger import get_logger

        logger = get_logger("mm.scheduler")

        if batch_name is None or batch_index is None:
            batch_name, batch_index = determine_batch()

        logger.info(
            "Starting daily run",
            extra={
                "mode": mode,
                "batch_name": batch_name,
                "batch_index": batch_index,
                "target_date": target_date or "today",
            },
        )

        last_exit_code: int = -1

        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                exit_code = self._execute_once(mode, target_date, prompt_profile)
            except Exception as exc:
                logger.error(
                    "Pipeline execution failed with exception",
                    extra={"attempt": attempt, "error": str(exc)},
                )
                exit_code = 1

            if exit_code == 0:
                logger.info(
                    "Daily run completed successfully",
                    extra={
                        "batch_name": batch_name,
                        "attempt": attempt,
                    },
                )
                return 0

            last_exit_code = exit_code
            logger.warning(
                "Pipeline run failed",
                extra={
                    "exit_code": exit_code,
                    "attempt": attempt,
                    "max_retries": self.retry_policy.max_retries,
                },
            )

            # Retry logic
            if attempt < self.retry_policy.max_retries:
                delay = self.retry_policy.delay_for_attempt(attempt + 1)
                logger.info(
                    "Retrying after delay",
                    extra={
                        "delay_seconds": delay,
                        "next_attempt": attempt + 1,
                    },
                )
                _time.sleep(delay)

        logger.error(
            "All retry attempts exhausted",
            extra={
                "batch_name": batch_name,
                "exit_code": last_exit_code,
            },
        )
        return last_exit_code


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def create_scheduler(
    config: object,
    max_retries: int = 2,
    delay_seconds: int = 60,
    backoff_factor: float = 2.0,
) -> DailyScheduler:
    """Create a DailyScheduler with the given config and retry policy."""
    return DailyScheduler(
        config=config,
        retry_policy=RetryPolicy(
            max_retries=max_retries,
            delay_seconds=delay_seconds,
            backoff_factor=backoff_factor,
        ),
    )
