"""
app/config/schema.py — typed dataclasses for application configuration.

Secrets (tokens, keys) come from .env.
Business config (sources, schedule, prompts, paths) comes from YAML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HH_MM_RE = re.compile(r"^\d{2}:\d{2}$")
_VALID_OUTPUT_FORMATS = {"markdown", "json"}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class ConfigError(ValueError):
    """Raised when the configuration is structurally invalid or contains bad values."""


# ---------------------------------------------------------------------------
# Section dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SourcesConfig:
    """Controls which data-source adapters are active."""
    akshare: bool = True
    web: bool = True
    # web-access deep-research collector — mandatory participant in every daily run
    copilot_research: bool = True
    # Number of days to retain collected items (items older than this are filtered out).
    # Must be >= 1.  Default: 7 (keep last week only).
    date_filter_days: int = 7


@dataclass
class SchedulerConfig:
    """Daily run schedule expressed as HH:MM strings (24-hour, local time)."""
    # Default: one hour before A-share open (09:30 CST) + mid-afternoon run
    runs: list[str] = field(default_factory=lambda: ["08:30", "14:00"])


@dataclass
class PromptConfig:
    """Prompt-profile selection for the LLM analysis layer."""
    default_profile: str = "default"
    profiles_dir: str = "config/prompt_profiles"
    templates_dir: str = "app/analysis/prompts/templates"


@dataclass
class LLMConfig:
    """LLM adapter configuration — endpoint, model, and credentials.

    When ``endpoint`` is set, the OpenAI-compatible adapter is used.
    Otherwise falls back to the GitHub Models adapter (legacy).
    """
    endpoint: str = ""
    model_id: str = "glm-5.1"
    api_key_env_var: str = "LLM_API_KEY"


@dataclass
class StorageConfig:
    """Paths for the SQLite database and raw data cache."""
    db_path: str = "data/db/mm.db"
    raw_dir: str = "data/raw"


@dataclass
class OutputConfig:
    """Daily report output settings."""
    reports_dir: str = "data/reports"
    formats: list[str] = field(default_factory=lambda: ["markdown", "json"])


@dataclass
class LoggingConfig:
    """Logging sink configuration."""
    log_dir: str = "data/logs"    # directory where mm.log (and rotated copies) are written
    level: str = "INFO"           # one of DEBUG / INFO / WARNING / ERROR / CRITICAL


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    """
    Complete, validated application configuration.

    Instantiate via ``app.config.load_config()``, not directly.
    Secrets are stored on this object but must never be serialised back to disk.
    """
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Loaded from .env — never from YAML
    github_token: str = ""
    akshare_token: str = ""
    llm_api_key: str = ""

    def validate(self) -> None:
        """Raise :class:`ConfigError` for any invalid field value."""
        for entry in self.scheduler.runs:
            if not _HH_MM_RE.match(entry):
                raise ConfigError(
                    f"scheduler.runs entry {entry!r} is not a valid HH:MM time string "
                    f"(expected two-digit hour and minute, e.g. '08:30')"
                )

        unknown = set(self.output.formats) - _VALID_OUTPUT_FORMATS
        if unknown:
            raise ConfigError(
                f"output.formats contains unsupported format(s): {sorted(unknown)}; "
                f"allowed values are {sorted(_VALID_OUTPUT_FORMATS)}"
            )

        if not self.prompt.default_profile.strip():
            raise ConfigError("prompt.default_profile must not be empty")

        if self.logging.level.upper() not in _VALID_LOG_LEVELS:
            raise ConfigError(
                f"logging.level {self.logging.level!r} is not valid; "
                f"allowed values are {sorted(_VALID_LOG_LEVELS)}"
            )

        if not self.logging.log_dir.strip():
            raise ConfigError("logging.log_dir must not be empty")

        if self.sources.date_filter_days < 1:
            raise ConfigError(
                f"sources.date_filter_days must be >= 1; "
                f"got {self.sources.date_filter_days}"
            )
