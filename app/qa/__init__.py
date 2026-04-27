"""
app/qa — quality assurance and observability.

Public API:
    ErrorTracker   — track and query runtime errors from pipeline runs
    ErrorSummary   — summary of errors for a given time range
"""

from app.qa.error_tracker import ErrorTracker, ErrorSummary

__all__ = [
    "ErrorTracker",
    "ErrorSummary",
]
