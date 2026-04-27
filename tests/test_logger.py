"""
tests/test_logger.py — focused tests for the app.logger module.

Covers:
- JSONFormatter produces valid JSON with all required fields
- JSONFormatter merges extra fields from the caller
- JSONFormatter includes exc field when exc_info is set
- setup_logging creates log directory and attaches handlers
- setup_logging is idempotent (no duplicate handlers on repeated calls)
- setup_logging respects level from LoggingConfig
- get_logger returns a logging.Logger instance
- Invalid log level is rejected at config validation
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import textwrap
from pathlib import Path

import pytest

from app.config.schema import AppConfig, ConfigError, LoggingConfig
from app.logger import get_logger, setup_logging
from app.logger.formatter import JSONFormatter
from app.logger.setup import _MM_HANDLER_ATTR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    msg: str = "hello",
    level: int = logging.INFO,
    name: str = "test.logger",
    extra: dict | None = None,
) -> logging.LogRecord:
    """Build a minimal LogRecord for formatter tests."""
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=42,
        msg=msg,
        args=(),
        exc_info=None,
    )
    if extra:
        for key, value in extra.items():
            setattr(record, key, value)
    return record


def _mm_handlers(root: logging.Logger) -> list[logging.Handler]:
    """Return only the handlers installed by setup_logging."""
    return [h for h in root.handlers if getattr(h, _MM_HANDLER_ATTR, False)]


@pytest.fixture(autouse=True)
def _clean_root_handlers():
    """Remove any mm handlers before and after each test to avoid leakage."""
    root = logging.getLogger()
    before = [h for h in root.handlers if not getattr(h, _MM_HANDLER_ATTR, False)]
    yield
    # Tear down: close mm handlers and restore root to pre-test state.
    for h in _mm_handlers(root):
        h.close()
    root.handlers = before
    root.setLevel(logging.WARNING)  # pytest default


# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------

class TestJSONFormatter:
    def test_produces_valid_json(self):
        record = _make_record("hello world")
        line = JSONFormatter().format(record)
        payload = json.loads(line)
        assert isinstance(payload, dict)

    def test_required_fields_present(self):
        record = _make_record("test message", level=logging.WARNING, name="app.foo")
        payload = json.loads(JSONFormatter().format(record))
        assert payload["level"] == "WARNING"
        assert payload["logger"] == "app.foo"
        assert payload["msg"] == "test message"
        assert "ts" in payload
        assert "module" in payload
        assert "func" in payload
        assert "line" in payload

    def test_ts_is_utc_iso8601(self):
        record = _make_record()
        payload = json.loads(JSONFormatter().format(record))
        ts = payload["ts"]
        # Should end with +00:00 for UTC
        assert ts.endswith("+00:00"), f"Expected UTC timestamp, got {ts!r}"

    def test_extra_fields_merged(self):
        record = _make_record(extra={"run_date": "2024-01-15", "batch": 1})
        payload = json.loads(JSONFormatter().format(record))
        assert payload["run_date"] == "2024-01-15"
        assert payload["batch"] == 1

    def test_exc_field_included_when_exc_info_set(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="oops",
                args=(),
                exc_info=sys.exc_info(),
            )
        payload = json.loads(JSONFormatter().format(record))
        assert "exc" in payload
        assert "ValueError" in payload["exc"]

    def test_no_exc_field_when_no_exception(self):
        record = _make_record()
        payload = json.loads(JSONFormatter().format(record))
        assert "exc" not in payload

    def test_single_line_output(self):
        record = _make_record("line\nwith\nnewlines")
        line = JSONFormatter().format(record)
        # json.dumps encodes newlines — result must be a single line
        assert "\n" not in line


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

class TestSetupLogging:
    def test_creates_log_directory(self, tmp_path: Path):
        log_dir = tmp_path / "logs" / "nested"
        cfg = LoggingConfig(log_dir=str(log_dir), level="INFO")
        setup_logging(cfg)
        assert log_dir.is_dir()

    def test_file_handler_attached(self, tmp_path: Path):
        cfg = LoggingConfig(log_dir=str(tmp_path / "logs"), level="INFO")
        setup_logging(cfg)
        handlers = _mm_handlers(logging.getLogger())
        file_handlers = [h for h in handlers if isinstance(h, logging.handlers.TimedRotatingFileHandler)]
        assert len(file_handlers) == 1

    def test_console_handler_attached(self, tmp_path: Path):
        cfg = LoggingConfig(log_dir=str(tmp_path / "logs"), level="INFO")
        setup_logging(cfg)
        handlers = _mm_handlers(logging.getLogger())
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) == 1

    def test_idempotent_no_duplicate_handlers(self, tmp_path: Path):
        cfg = LoggingConfig(log_dir=str(tmp_path / "logs"), level="INFO")
        setup_logging(cfg)
        setup_logging(cfg)  # second call
        assert len(_mm_handlers(logging.getLogger())) == 2  # exactly 1 file + 1 console

    def test_level_applied_to_root(self, tmp_path: Path):
        cfg = LoggingConfig(log_dir=str(tmp_path / "logs"), level="DEBUG")
        setup_logging(cfg)
        assert logging.getLogger().level == logging.DEBUG

    def test_file_handler_uses_json_formatter(self, tmp_path: Path):
        cfg = LoggingConfig(log_dir=str(tmp_path / "logs"), level="INFO")
        setup_logging(cfg)
        handlers = _mm_handlers(logging.getLogger())
        file_handler = next(
            h for h in handlers
            if isinstance(h, logging.handlers.TimedRotatingFileHandler)
        )
        assert isinstance(file_handler.formatter, JSONFormatter)

    def test_log_record_written_as_json(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        cfg = LoggingConfig(log_dir=str(log_dir), level="INFO")
        setup_logging(cfg)

        logger = get_logger("test.write")
        logger.info("integration check", extra={"tag": "pytest"})

        # Flush and close so the file is flushed to disk.
        for h in _mm_handlers(logging.getLogger()):
            h.flush()

        log_file = log_dir / "mm.log"
        lines = [l for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert lines, "Log file should have at least one line"
        payload = json.loads(lines[-1])
        assert payload["msg"] == "integration check"
        assert payload["tag"] == "pytest"


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------

class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger("app.test")
        assert isinstance(logger, logging.Logger)

    def test_name_preserved(self):
        logger = get_logger("app.collectors.akshare")
        assert logger.name == "app.collectors.akshare"

    def test_same_name_returns_same_instance(self):
        assert get_logger("app.foo") is get_logger("app.foo")


# ---------------------------------------------------------------------------
# Config-level validation of LoggingConfig
# ---------------------------------------------------------------------------

class TestLoggingConfigValidation:
    def _base_cfg(self, **overrides) -> AppConfig:
        lc = LoggingConfig(**overrides)
        cfg = AppConfig(logging=lc)
        return cfg

    def test_valid_levels_accepted(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            cfg = self._base_cfg(level=level)
            cfg.validate()  # must not raise

    def test_invalid_level_raises_config_error(self):
        cfg = self._base_cfg(level="VERBOSE")
        with pytest.raises(ConfigError, match="logging.level"):
            cfg.validate()

    def test_empty_log_dir_raises_config_error(self):
        cfg = self._base_cfg(log_dir="  ")
        with pytest.raises(ConfigError, match="logging.log_dir"):
            cfg.validate()
