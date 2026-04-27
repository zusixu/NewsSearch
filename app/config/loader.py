"""
app/config/loader.py — load .env + YAML into a typed AppConfig.

Resolution order for each config file:
  1. Explicit argument to load_config()
  2. MM_ENV_PATH / MM_CONFIG_PATH environment variable
  3. .env / config.yaml in the current working directory
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .schema import (
    AnalysisConfig,
    AppConfig,
    ConfigError,
    LLMConfig,
    LoggingConfig,
    OutputConfig,
    PromptConfig,
    SchedulerConfig,
    SourcesConfig,
    StorageConfig,
)

_DEFAULT_ENV_FILE = ".env"
_DEFAULT_YAML_FILE = "config.yaml"


# ---------------------------------------------------------------------------
# .env parser
# ---------------------------------------------------------------------------

def _parse_dotenv(path: Path) -> dict[str, str]:
    """
    Parse a .env file and return key/value pairs.

    Rules:
    - Lines starting with ``#`` and blank lines are ignored.
    - Values may be optionally wrapped in single or double quotes (stripped).
    - Does NOT modify ``os.environ``; caller decides what to do with the result.
    """
    result: dict[str, str] = {}
    if not path.exists():
        return result
    with path.open(encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in ('"', "'")
            ):
                value = value[1:-1]
            result[key] = value
    return result


def _inject_env(env_vars: dict[str, str]) -> None:
    """
    Set env_vars into os.environ only for keys not already present.

    Existing environment variables (e.g. from the shell or CI) take precedence
    over the .env file — consistent with standard dotenv convention.
    """
    for key, value in env_vars.items():
        if key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def _load_yaml_file(path: Path) -> dict[str, Any]:
    """
    Load a YAML config file.  Returns ``{}`` if the file does not exist.
    Raises :class:`ConfigError` if the file exists but is not a YAML mapping.
    """
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(
            f"YAML config at '{path}' must be a top-level mapping, "
            f"got {type(data).__name__}"
        )
    return data


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_sources(raw: dict[str, Any]) -> SourcesConfig:
    section = raw.get("sources", {})
    if not isinstance(section, dict):
        raise ConfigError(
            f"'sources' must be a mapping, got {type(section).__name__}"
        )
    return SourcesConfig(
        akshare=bool(section.get("akshare", True)),
        web=bool(section.get("web", True)),
        copilot_research=bool(section.get("copilot_research", True)),
        date_filter_days=int(section.get("date_filter_days", 7)),
    )


def _build_scheduler(raw: dict[str, Any]) -> SchedulerConfig:
    section = raw.get("scheduler", {})
    if not isinstance(section, dict):
        raise ConfigError(
            f"'scheduler' must be a mapping, got {type(section).__name__}"
        )
    runs = section.get("runs", ["08:30", "14:00"])
    if not isinstance(runs, list):
        raise ConfigError(
            f"'scheduler.runs' must be a list, got {type(runs).__name__}"
        )
    return SchedulerConfig(runs=[str(r) for r in runs])


def _build_prompt(raw: dict[str, Any]) -> PromptConfig:
    section = raw.get("prompt", {})
    if not isinstance(section, dict):
        raise ConfigError(
            f"'prompt' must be a mapping, got {type(section).__name__}"
        )
    return PromptConfig(
        default_profile=str(section.get("default_profile", "default")),
        profiles_dir=str(section.get("profiles_dir", "config/prompt_profiles")),
        templates_dir=str(section.get("templates_dir", "app/analysis/prompts/templates")),
    )


def _build_storage(raw: dict[str, Any]) -> StorageConfig:
    section = raw.get("storage", {})
    if not isinstance(section, dict):
        raise ConfigError(
            f"'storage' must be a mapping, got {type(section).__name__}"
        )
    return StorageConfig(
        db_path=str(section.get("db_path", "data/db/mm.db")),
        raw_dir=str(section.get("raw_dir", "data/raw")),
    )


def _build_output(raw: dict[str, Any]) -> OutputConfig:
    section = raw.get("output", {})
    if not isinstance(section, dict):
        raise ConfigError(
            f"'output' must be a mapping, got {type(section).__name__}"
        )
    fmts = section.get("formats", ["markdown", "json"])
    if not isinstance(fmts, list):
        raise ConfigError(
            f"'output.formats' must be a list, got {type(fmts).__name__}"
        )
    return OutputConfig(
        reports_dir=str(section.get("reports_dir", "data/reports")),
        formats=[str(f) for f in fmts],
    )


def _build_logging(raw: dict[str, Any]) -> LoggingConfig:
    section = raw.get("logging", {})
    if not isinstance(section, dict):
        raise ConfigError(
            f"'logging' must be a mapping, got {type(section).__name__}"
        )
    return LoggingConfig(
        log_dir=str(section.get("log_dir", "data/logs")),
        level=str(section.get("level", "INFO")),
    )


def _build_analysis(raw: dict[str, Any]) -> AnalysisConfig:
    section = raw.get("analysis", {})
    if not isinstance(section, dict):
        raise ConfigError(
            f"'analysis' must be a mapping, got {type(section).__name__}"
        )
    react = section.get("react", {})
    if not isinstance(react, dict):
        react = {}
    return AnalysisConfig(
        mode=str(section.get("mode", "legacy")),
        react_max_steps_per_group=int(react.get("max_steps_per_group", 5)),
        react_max_groups=int(react.get("max_groups", 10)),
        react_enable_web_search=bool(react.get("enable_web_search", True)),
        react_enable_web_fetch=bool(react.get("enable_web_fetch", True)),
        react_enable_akshare_query=bool(react.get("enable_akshare_query", True)),
    )


def _build_llm(raw: dict[str, Any]) -> LLMConfig:
    section = raw.get("llm", {})
    if not isinstance(section, dict):
        raise ConfigError(
            f"'llm' must be a mapping, got {type(section).__name__}"
        )
    return LLMConfig(
        endpoint=str(section.get("endpoint", "")),
        model_id=str(section.get("model_id", "deepseek-v4-flash")),
        api_key_env_var=str(section.get("api_key_env_var", "LLM_API_KEY")),
        response_format=section.get("response_format", "json_object"),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(
    *,
    env_path: Path | str | None = None,
    yaml_path: Path | str | None = None,
) -> AppConfig:
    """
    Load and validate application configuration.

    Parameters
    ----------
    env_path:
        Path to the ``.env`` file.  Falls back to ``MM_ENV_PATH`` env var,
        then ``<cwd>/.env``.
    yaml_path:
        Path to the YAML config file.  Falls back to ``MM_CONFIG_PATH`` env var,
        then ``<cwd>/config.yaml``.

    Returns
    -------
    AppConfig
        Fully validated configuration object.

    Raises
    ------
    ConfigError
        On structural problems (wrong YAML types) or invalid field values.
    """
    # --- resolve paths -------------------------------------------------------
    resolved_env = Path(
        env_path
        if env_path is not None
        else os.environ.get("MM_ENV_PATH", _DEFAULT_ENV_FILE)
    )
    resolved_yaml = Path(
        yaml_path
        if yaml_path is not None
        else os.environ.get("MM_CONFIG_PATH", _DEFAULT_YAML_FILE)
    )

    # --- load .env -----------------------------------------------------------
    env_vars = _parse_dotenv(resolved_env)
    _inject_env(env_vars)

    # --- load YAML -----------------------------------------------------------
    raw = _load_yaml_file(resolved_yaml)

    # --- build typed config --------------------------------------------------
    # For token fields: .env file takes explicit precedence over any pre-existing
    # os.environ value so that project-level secrets are predictable.
    cfg = AppConfig(
        sources=_build_sources(raw),
        scheduler=_build_scheduler(raw),
        prompt=_build_prompt(raw),
        llm=_build_llm(raw),
        storage=_build_storage(raw),
        output=_build_output(raw),
        logging=_build_logging(raw),
        analysis=_build_analysis(raw),
        github_token=(
            env_vars.get("GITHUB_TOKEN")
            if "GITHUB_TOKEN" in env_vars
            else os.environ.get("GITHUB_TOKEN", "")
        ),
        akshare_token=(
            env_vars.get("AKSHARE_TOKEN")
            if "AKSHARE_TOKEN" in env_vars
            else os.environ.get("AKSHARE_TOKEN", "")
        ),
        llm_api_key=(
            env_vars.get("LLM_API_KEY")
            if "LLM_API_KEY" in env_vars
            else os.environ.get("LLM_API_KEY", "")
        ),
    )

    cfg.validate()
    return cfg
