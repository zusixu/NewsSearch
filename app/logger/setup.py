"""
app/logger/setup.py — configure root logger with file (JSON) and console handlers.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from app.config.schema import LoggingConfig
from .formatter import JSONFormatter

_CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
_CONSOLE_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Marker attribute set on handlers we own so we can remove them on re-init.
_MM_HANDLER_ATTR = "_mm_handler"


def setup_logging(cfg: LoggingConfig) -> None:
    """
    Initialise application-wide logging from *cfg*.

    Safe to call multiple times — re-calling replaces previously installed
    handlers without accumulating duplicates.

    Two handlers are attached to the root logger:

    * **File handler** — :class:`~logging.handlers.TimedRotatingFileHandler`
      writing NDJSON to ``<cfg.log_dir>/mm.log``, rotated daily at UTC
      midnight, keeping 30 days of history.
    * **Console handler** — :class:`~logging.StreamHandler` writing a concise
      human-readable line to *stderr*.

    The log directory is created if it does not exist.
    """
    level = _resolve_level(cfg.level)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any handlers we installed in a previous call (idempotent re-init).
    root.handlers = [h for h in root.handlers if not getattr(h, _MM_HANDLER_ATTR, False)]

    # --- file handler (JSON NDJSON, daily rotation) --------------------------
    log_dir = Path(cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "mm.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(level)
    setattr(file_handler, _MM_HANDLER_ATTR, True)
    root.addHandler(file_handler)

    # --- console handler (human-readable) ------------------------------------
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(_CONSOLE_FORMAT, datefmt=_CONSOLE_DATEFMT)
    )
    console_handler.setLevel(level)
    setattr(console_handler, _MM_HANDLER_ATTR, True)
    root.addHandler(console_handler)


def _resolve_level(level_name: str) -> int:
    """Convert a level name string to the corresponding :mod:`logging` integer."""
    numeric = getattr(logging, level_name.upper(), None)
    if not isinstance(numeric, int):
        raise ValueError(
            f"Unknown log level {level_name!r}. "
            f"Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL"
        )
    return numeric
