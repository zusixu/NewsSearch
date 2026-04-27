"""
app/config — configuration loading for the daily AI investment pipeline.

Public API
----------
load_config(*, env_path=None, yaml_path=None) -> AppConfig
    Load and validate configuration from .env + YAML.

load_override(path) -> OverrideConfig
    Load an optional override configuration from a YAML file.

apply_override(config, override) -> AppConfig
    Merge override settings into base config.

AppConfig, SourcesConfig, SchedulerConfig, PromptConfig,
StorageConfig, OutputConfig
    Typed dataclasses representing each configuration section.

OverrideConfig, SourcesOverrideConfig, WebSourceOverride,
TaskPromptOverride, PromptOverrideConfig
    Typed dataclasses for per-run override configuration.

ConfigError
    Raised for structural or value-level configuration problems.
"""

from .loader import load_config
from .override import (
    OverrideConfig,
    PromptOverrideConfig,
    SourcesOverrideConfig,
    TaskPromptOverride,
    WebSourceOverride,
    apply_override,
    load_override,
)
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

__all__ = [
    "load_config",
    "load_override",
    "apply_override",
    "AnalysisConfig",
    "AppConfig",
    "ConfigError",
    "LLMConfig",
    "LoggingConfig",
    "OutputConfig",
    "PromptConfig",
    "SchedulerConfig",
    "SourcesConfig",
    "StorageConfig",
    "OverrideConfig",
    "SourcesOverrideConfig",
    "WebSourceOverride",
    "TaskPromptOverride",
    "PromptOverrideConfig",
]
