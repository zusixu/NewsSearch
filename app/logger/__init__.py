"""
app/logger — structured logging for the daily AI investment pipeline.

Naming note
-----------
This package is named ``logger`` (not ``logging``) to avoid shadowing the
Python standard-library ``logging`` module.

Public API
----------
setup_logging(cfg: LoggingConfig) -> None
    Initialise application-wide logging from a :class:`~app.config.LoggingConfig`.
    Call **once** at startup (e.g. in ``app/main.py``) before any other module
    emits log records.  Safe to call again — re-calling replaces handlers
    without accumulating duplicates.

get_logger(name: str) -> logging.Logger
    Return a named :class:`logging.Logger`.  Cheap to call; create one per
    module at import time::

        from app.logger import get_logger
        logger = get_logger(__name__)
"""

import logging

from app.config.schema import LoggingConfig
from .setup import setup_logging

__all__ = ["setup_logging", "get_logger", "LoggingConfig"]


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.  Intended to be called at module level."""
    return logging.getLogger(name)
