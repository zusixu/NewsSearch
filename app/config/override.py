"""
app/config/override.py — override configuration for per-run customisation.

All fields are optional.  When absent, base ``config.yaml`` / CLI defaults
are used unchanged.  Load via :func:`load_override` and merge into
:class:`~app.config.schema.AppConfig` via :func:`apply_override`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .schema import AppConfig, ConfigError

_KNOWN_AKSHARE_PROVIDERS = frozenset({"cctv", "caixin"})
_VALID_WEB_SOURCE_TYPES = frozenset({"rss", "html"})


# ---------------------------------------------------------------------------
# Section dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WebSourceOverride:
    """A single web source entry in the override file."""

    url: str
    type: str  # "rss" or "html"
    provider: str
    timeout: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to the dict format consumed by :class:`WebCollector`."""
        d: dict[str, Any] = {
            "url": self.url,
            "type": self.type,
            "provider": self.provider,
        }
        if self.timeout is not None:
            d["timeout"] = self.timeout
        return d


@dataclass(frozen=True)
class SourcesOverrideConfig:
    """Override which data-source providers are active."""

    akshare_providers: list[str] = field(default_factory=list)
    web_sources: list[WebSourceOverride] = field(default_factory=list)
    copilot_research_enabled: bool | None = None
    date_filter_days: int | None = None


@dataclass(frozen=True)
class TaskPromptOverride:
    """Per-task prompt message overrides."""

    system_message: str | None = None
    system_message_suffix: str | None = None
    user_message_prefix: str | None = None
    user_message_suffix: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskPromptOverride:
        return cls(
            system_message=data.get("system_message"),
            system_message_suffix=data.get("system_message_suffix"),
            user_message_prefix=data.get("user_message_prefix"),
            user_message_suffix=data.get("user_message_suffix"),
        )


@dataclass(frozen=True)
class PromptOverrideConfig:
    """Prompt customisation that is applied after template rendering."""

    system_message_suffix: str | None = None
    tasks: dict[str, TaskPromptOverride] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptOverrideConfig:
        if not isinstance(data, dict):
            return cls()
        suffix = data.get("system_message_suffix")
        tasks_raw = data.get("tasks", {})
        tasks: dict[str, TaskPromptOverride] = {}
        if isinstance(tasks_raw, dict):
            for key, val in tasks_raw.items():
                if isinstance(val, dict):
                    tasks[key] = TaskPromptOverride.from_dict(val)
        return cls(system_message_suffix=suffix, tasks=tasks)


@dataclass(frozen=True)
class OverrideConfig:
    """Top-level override configuration loaded from a YAML file."""

    search_keywords: list[str] = field(default_factory=list)
    sources: SourcesOverrideConfig = field(default_factory=SourcesOverrideConfig)
    prompt_profile: str | None = None
    prompt_overrides: PromptOverrideConfig = field(default_factory=PromptOverrideConfig)

    def validate(self) -> None:
        """Raise :class:`ConfigError` for invalid field values."""
        unknown = set(self.sources.akshare_providers) - _KNOWN_AKSHARE_PROVIDERS
        if unknown:
            raise ConfigError(
                f"sources.akshare_providers contains unknown provider(s): "
                f"{sorted(unknown)}; allowed values are {sorted(_KNOWN_AKSHARE_PROVIDERS)}"
            )

        for ws in self.sources.web_sources:
            if ws.type not in _VALID_WEB_SOURCE_TYPES:
                raise ConfigError(
                    f"sources.web_sources entry with provider {ws.provider!r} "
                    f"has invalid type {ws.type!r}; "
                    f"allowed values are {sorted(_VALID_WEB_SOURCE_TYPES)}"
                )
            if not ws.url.strip():
                raise ConfigError(
                    f"sources.web_sources entry with provider {ws.provider!r} "
                    f"has an empty url"
                )
            if not ws.provider.strip():
                raise ConfigError(
                    f"sources.web_sources entry with url {ws.url!r} "
                    f"has an empty provider"
                )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_web_sources(raw: list[Any]) -> list[WebSourceOverride]:
    """Parse a list of web source dicts from YAML."""
    result: list[WebSourceOverride] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ConfigError(
                f"sources.web_sources entry must be a mapping, got {type(entry).__name__}"
            )
        url = str(entry.get("url", "")).strip()
        src_type = str(entry.get("type", "rss")).strip().lower()
        provider = str(entry.get("provider", "")).strip()
        timeout = entry.get("timeout")
        if timeout is not None:
            timeout = int(timeout)
        result.append(WebSourceOverride(
            url=url, type=src_type, provider=provider, timeout=timeout,
        ))
    return result


def _parse_sources(raw: dict[str, Any]) -> SourcesOverrideConfig:
    """Parse the ``sources`` section of the override YAML."""
    if not isinstance(raw, dict):
        return SourcesOverrideConfig()

    ak_providers_raw = raw.get("akshare_providers", [])
    ak_providers = [str(p) for p in ak_providers_raw] if isinstance(ak_providers_raw, list) else []

    web_raw = raw.get("web_sources", [])
    web_sources = _parse_web_sources(web_raw) if isinstance(web_raw, list) else []

    cre = raw.get("copilot_research_enabled")
    copilot_enabled = bool(cre) if cre is not None else None

    dfd = raw.get("date_filter_days")
    date_filter_days = int(dfd) if dfd is not None else None

    return SourcesOverrideConfig(
        akshare_providers=ak_providers,
        web_sources=web_sources,
        copilot_research_enabled=copilot_enabled,
        date_filter_days=date_filter_days,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_override(path: str | Path | None = None) -> OverrideConfig:
    """Load an override configuration from a YAML file.

    Parameters
    ----------
    path:
        Path to the override YAML file.  If ``None`` or the file does not
        exist, returns an empty :class:`OverrideConfig` (all defaults).

    Returns
    -------
    OverrideConfig
        Validated override configuration.

    Raises
    ------
    ConfigError
        On structural problems or invalid field values.
    """
    if path is None:
        return OverrideConfig()

    p = Path(path)
    if not p.exists():
        return OverrideConfig()

    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if data is None:
        return OverrideConfig()
    if not isinstance(data, dict):
        raise ConfigError(
            f"Override file at '{p}' must be a top-level mapping, "
            f"got {type(data).__name__}"
        )

    # search_keywords
    kw_raw = data.get("search_keywords", [])
    keywords = [str(k) for k in kw_raw] if isinstance(kw_raw, list) else []

    # sources
    sources = _parse_sources(data.get("sources", {}))

    # prompt_profile
    pp = data.get("prompt_profile")
    prompt_profile = str(pp) if pp is not None else None

    # prompt_overrides
    po_raw = data.get("prompt_overrides", {})
    prompt_overrides = PromptOverrideConfig.from_dict(po_raw) if isinstance(po_raw, dict) else PromptOverrideConfig()

    cfg = OverrideConfig(
        search_keywords=keywords,
        sources=sources,
        prompt_profile=prompt_profile,
        prompt_overrides=prompt_overrides,
    )
    cfg.validate()
    return cfg


def apply_override(config: AppConfig, override: OverrideConfig) -> AppConfig:
    """Merge override settings into base config and return a new AppConfig.

    Only overrides fields that have explicit values in the override file.
    Does not mutate the original ``config``.
    """
    if override is None:
        return config

    from dataclasses import replace as _replace

    new_sources = config.sources
    if override.sources.copilot_research_enabled is not None:
        new_sources = _replace(
            config.sources,
            copilot_research=override.sources.copilot_research_enabled,
        )
    if override.sources.date_filter_days is not None:
        new_sources = _replace(
            new_sources,
            date_filter_days=override.sources.date_filter_days,
        )

    new_prompt = config.prompt
    if override.prompt_profile is not None:
        new_prompt = _replace(
            config.prompt,
            default_profile=override.prompt_profile,
        )

    from dataclasses import replace as _r
    return _r(
        config,
        sources=new_sources,
        prompt=new_prompt,
    )
