"""
tests/test_override.py — tests for the override configuration system.

Covers:
- Loading override YAML (valid, missing, empty, partial)
- Validation (unknown akshare providers, invalid web source types)
- apply_override() merging logic
- Dataclass construction and defaults
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.config.override import (
    OverrideConfig,
    SourcesOverrideConfig,
    WebSourceOverride,
    TaskPromptOverride,
    PromptOverrideConfig,
    load_override,
    apply_override,
)
from app.config.schema import AppConfig, SourcesConfig, PromptConfig, ConfigError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    """Write dedented *content* to *tmp_path/name* and return the path."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# OverrideConfig defaults
# ---------------------------------------------------------------------------

class TestOverrideConfigDefaults:
    def test_empty_override_has_defaults(self):
        cfg = OverrideConfig()
        assert cfg.search_keywords == []
        assert cfg.sources.akshare_providers == []
        assert cfg.sources.web_sources == []
        assert cfg.sources.copilot_research_enabled is None
        assert cfg.prompt_profile is None
        assert cfg.prompt_overrides.system_message_suffix is None
        assert cfg.prompt_overrides.tasks == {}

    def test_equality(self):
        a = OverrideConfig()
        b = OverrideConfig()
        assert a == b


# ---------------------------------------------------------------------------
# load_override
# ---------------------------------------------------------------------------

class TestLoadOverride:
    def test_none_path_returns_empty(self):
        cfg = load_override(None)
        assert cfg == OverrideConfig()

    def test_missing_file_returns_empty(self, tmp_path: Path):
        cfg = load_override(tmp_path / "nonexistent.yaml")
        assert cfg == OverrideConfig()

    def test_empty_file_returns_empty(self, tmp_path: Path):
        p = _write(tmp_path, "empty.yaml", "")
        cfg = load_override(p)
        assert cfg == OverrideConfig()

    def test_loads_search_keywords(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            search_keywords:
              - "AI芯片"
              - "半导体"
        """)
        cfg = load_override(p)
        assert cfg.search_keywords == ["AI芯片", "半导体"]

    def test_loads_akshare_providers(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            sources:
              akshare_providers:
                - "cctv"
        """)
        cfg = load_override(p)
        assert cfg.sources.akshare_providers == ["cctv"]

    def test_loads_web_sources(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            sources:
              web_sources:
                - url: "https://example.com/feed"
                  type: "rss"
                  provider: "example"
                  timeout: 30
        """)
        cfg = load_override(p)
        assert len(cfg.sources.web_sources) == 1
        ws = cfg.sources.web_sources[0]
        assert ws.url == "https://example.com/feed"
        assert ws.type == "rss"
        assert ws.provider == "example"
        assert ws.timeout == 30

    def test_loads_copilot_research_enabled(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            sources:
              copilot_research_enabled: false
        """)
        cfg = load_override(p)
        assert cfg.sources.copilot_research_enabled is False

    def test_loads_prompt_profile(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            prompt_profile: "aggressive-v1"
        """)
        cfg = load_override(p)
        assert cfg.prompt_profile == "aggressive-v1"

    def test_loads_prompt_overrides(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            prompt_overrides:
              system_message_suffix: "\\nFocus: chips."
              tasks:
                summary:
                  user_message_prefix: "Background: "
                investment_ranking:
                  system_message: "Prioritize semiconductors."
                  user_message_suffix: "\\nWeight x2."
        """)
        cfg = load_override(p)
        assert cfg.prompt_overrides.system_message_suffix == "\nFocus: chips."
        assert "summary" in cfg.prompt_overrides.tasks
        assert cfg.prompt_overrides.tasks["summary"].user_message_prefix == "Background: "
        assert cfg.prompt_overrides.tasks["investment_ranking"].system_message == "Prioritize semiconductors."
        assert cfg.prompt_overrides.tasks["investment_ranking"].user_message_suffix == "\nWeight x2."

    def test_partial_override(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            search_keywords:
              - "test"
        """)
        cfg = load_override(p)
        assert cfg.search_keywords == ["test"]
        assert cfg.sources.akshare_providers == []
        assert cfg.prompt_profile is None

    def test_non_mapping_raises(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            - "not a mapping"
        """)
        with pytest.raises(ConfigError, match="top-level mapping"):
            load_override(p)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestOverrideValidation:
    def test_unknown_akshare_provider_raises(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            sources:
              akshare_providers:
                - "unknown_provider"
        """)
        with pytest.raises(ConfigError, match="unknown provider"):
            load_override(p)

    def test_invalid_web_source_type_raises(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            sources:
              web_sources:
                - url: "https://example.com"
                  type: "xml"
                  provider: "bad"
        """)
        with pytest.raises(ConfigError, match="invalid type"):
            load_override(p)

    def test_empty_web_source_url_raises(self, tmp_path: Path):
        cfg = OverrideConfig(
            sources=SourcesOverrideConfig(
                web_sources=[WebSourceOverride(url="", type="rss", provider="x")],
            ),
        )
        with pytest.raises(ConfigError, match="empty url"):
            cfg.validate()

    def test_empty_web_source_provider_raises(self):
        cfg = OverrideConfig(
            sources=SourcesOverrideConfig(
                web_sources=[WebSourceOverride(url="https://x.com", type="rss", provider="")],
            ),
        )
        with pytest.raises(ConfigError, match="empty provider"):
            cfg.validate()

    def test_valid_akshare_providers_pass(self, tmp_path: Path):
        p = _write(tmp_path, "ov.yaml", """\
            sources:
              akshare_providers:
                - "cctv"
                - "caixin"
        """)
        cfg = load_override(p)
        assert cfg.sources.akshare_providers == ["cctv", "caixin"]


# ---------------------------------------------------------------------------
# WebSourceOverride.to_dict
# ---------------------------------------------------------------------------

class TestWebSourceOverrideToDict:
    def test_with_timeout(self):
        ws = WebSourceOverride(url="https://x.com", type="rss", provider="x", timeout=20)
        d = ws.to_dict()
        assert d == {"url": "https://x.com", "type": "rss", "provider": "x", "timeout": 20}

    def test_without_timeout(self):
        ws = WebSourceOverride(url="https://x.com", type="html", provider="y")
        d = ws.to_dict()
        assert d == {"url": "https://x.com", "type": "html", "provider": "y"}
        assert "timeout" not in d


# ---------------------------------------------------------------------------
# apply_override
# ---------------------------------------------------------------------------

class TestApplyOverride:
    def test_none_override_returns_config_unchanged(self):
        config = AppConfig()
        result = apply_override(config, None)
        assert result is config

    def test_empty_override_returns_config_unchanged(self):
        config = AppConfig()
        result = apply_override(config, OverrideConfig())
        assert result == config

    def test_copilot_research_enabled_override(self):
        config = AppConfig()
        override = OverrideConfig(
            sources=SourcesOverrideConfig(copilot_research_enabled=False),
        )
        result = apply_override(config, override)
        assert result.sources.copilot_research is False
        assert result.sources.akshare is True  # unchanged

    def test_prompt_profile_override(self):
        config = AppConfig()
        override = OverrideConfig(prompt_profile="aggressive-v1")
        result = apply_override(config, override)
        assert result.prompt.default_profile == "aggressive-v1"

    def test_does_not_mutate_original(self):
        config = AppConfig()
        original_profile = config.prompt.default_profile
        override = OverrideConfig(prompt_profile="changed")
        apply_override(config, override)
        assert config.prompt.default_profile == original_profile


# ---------------------------------------------------------------------------
# TaskPromptOverride.from_dict
# ---------------------------------------------------------------------------

class TestTaskPromptOverrideFromDict:
    def test_from_dict_all_fields(self):
        data = {
            "system_message": "New system",
            "system_message_suffix": " suffix",
            "user_message_prefix": "prefix ",
            "user_message_suffix": " suffix",
        }
        tpo = TaskPromptOverride.from_dict(data)
        assert tpo.system_message == "New system"
        assert tpo.system_message_suffix == " suffix"
        assert tpo.user_message_prefix == "prefix "
        assert tpo.user_message_suffix == " suffix"

    def test_from_dict_empty(self):
        tpo = TaskPromptOverride.from_dict({})
        assert tpo.system_message is None
        assert tpo.system_message_suffix is None


# ---------------------------------------------------------------------------
# PromptOverrideConfig.from_dict
# ---------------------------------------------------------------------------

class TestPromptOverrideConfigFromDict:
    def test_from_dict_empty(self):
        poc = PromptOverrideConfig.from_dict({})
        assert poc.system_message_suffix is None
        assert poc.tasks == {}

    def test_from_dict_non_dict(self):
        poc = PromptOverrideConfig.from_dict("not a dict")
        assert poc == PromptOverrideConfig()

    def test_from_dict_with_tasks(self):
        data = {
            "system_message_suffix": " global",
            "tasks": {
                "summary": {
                    "user_message_prefix": "pref",
                },
            },
        }
        poc = PromptOverrideConfig.from_dict(data)
        assert poc.system_message_suffix == " global"
        assert "summary" in poc.tasks
        assert poc.tasks["summary"].user_message_prefix == "pref"
