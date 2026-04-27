"""
app/scheduler — daily run orchestration.

Public API:
    DailyScheduler   — orchestrates daily pipeline runs with batch detection and retry
    RetryPolicy      — configurable retry behaviour
    determine_batch  — map a run time to batch name / index
    should_run_now   — decide whether a scheduled run is due
    create_scheduler — factory for DailyScheduler
"""

from app.scheduler.scheduler import (
    DailyScheduler,
    RetryPolicy,
    determine_batch,
    should_run_now,
    create_scheduler,
)

__all__ = [
    "DailyScheduler",
    "RetryPolicy",
    "determine_batch",
    "should_run_now",
    "create_scheduler",
]
