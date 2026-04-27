"""
app/logger/formatter.py — JSON log formatter for structured, machine-readable output.

Produces NDJSON (one JSON object per line), suitable for log aggregators and
later observability tooling.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

# Attributes that belong to every stdlib LogRecord; we exclude them from the
# "extra fields" merge so callers' custom keys don't collide with internal ones.
_STDLIB_ATTRS: frozenset[str] = frozenset({
    "args", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs", "msg",
    "name", "pathname", "process", "processName", "relativeCreated",
    "stack_info", "taskName", "thread", "threadName",
})


class JSONFormatter(logging.Formatter):
    """
    Format a :class:`logging.LogRecord` as a single-line JSON object.

    Fixed fields emitted on every record:

    =========  ===============================================================
    ``ts``     ISO-8601 timestamp in UTC (e.g. ``2024-01-15T08:30:00.123+00:00``)
    ``level``  Log level name (``INFO``, ``WARNING``, …)
    ``logger`` Logger name (typically the module's ``__name__``)
    ``msg``    Formatted log message
    ``module`` Source module name
    ``func``   Calling function name
    ``line``   Source line number
    =========  ===============================================================

    Optional fields:

    =========  ===============================================================
    ``exc``    Exception traceback string (only present when exc_info is set)
    =========  ===============================================================

    Any keys passed via ``extra={"key": value}`` are merged into the payload
    (keys that collide with fixed fields are silently ignored).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # Merge extra fields passed by the caller (e.g. extra={"run_date": "2024-01-15"})
        for key, value in record.__dict__.items():
            if key not in _STDLIB_ATTRS and not key.startswith("_") and key not in payload:
                payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)
