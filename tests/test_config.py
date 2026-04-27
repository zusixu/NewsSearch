"""
tests/test_config.py — focused tests for the app.config module.

Covers:
- .env parsing (key/value, quoting, comments, missing file)
- YAML loading (defaults, overrides, partial overrides)
- Validation errors (bad time format, unknown output format, etc.)
- MM_CONFIG_PATH / MM_ENV_PATH env-var overrides
- Token precedence (.env file > os.environ fallback)
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from app.config import AppConfig, ConfigError, load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    """Write dedented *content* to *tmp_path/name* and return the path."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _restore_environ():
    """
    Snapshot os.environ before each test and restore it afterwards.

    load_config() calls _inject_env() which may add keys to os.environ.
    This fixture prevents those side effects from leaking across tests.
    """
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


# ---------------------------------------------------------------------------
# .env parsing
# ---------------------------------------------------------------------------

class TestDotenvParsing:
    def test_plain_key_value(self, tmp_path):
        env_file = _write(tmp_path, ".env", """
            GITHUB_TOKEN=ghp_test123
            AKSHARE_TOKEN=ak_abc
        """)
        cfg = load_config(env_path=env_file, yaml_path=tmp_path / "no.yaml")
        assert cfg.github_token == "ghp_test123"
        assert cfg.akshare_token == "ak_abc"

    def test_double_quoted_value_stripped(self, tmp_path):
        env_file = _write(tmp_path, ".env", 'GITHUB_TOKEN="quoted_token"\n')
        cfg = load_config(env_path=env_file, yaml_path=tmp_path / "no.yaml")
        assert cfg.github_token == "quoted_token"

    def test_single_quoted_value_stripped(self, tmp_path):
        env_file = _write(tmp_path, ".env", "GITHUB_TOKEN='sq_token'\n")
        cfg = load_config(env_path=env_file, yaml_path=tmp_path / "no.yaml")
        assert cfg.github_token == "sq_token"

    def test_comments_and_blank_lines_ignored(self, tmp_path):
        env_file = _write(tmp_path, ".env", """
            # This is a comment
            GITHUB_TOKEN=tok1

            # Another comment
            AKSHARE_TOKEN=tok2
        """)
        cfg = load_config(env_path=env_file, yaml_path=tmp_path / "no.yaml")
        assert cfg.github_token == "tok1"
        assert cfg.akshare_token == "tok2"

    def test_missing_env_file_is_allowed(self, tmp_path):
        """A missing .env file should not raise; tokens default to empty string."""
        cfg = load_config(
            env_path=tmp_path / "does_not_exist.env",
            yaml_path=tmp_path / "no.yaml",
        )
        assert isinstance(cfg, AppConfig)
        assert cfg.github_token == ""

    def test_lines_without_equals_are_skipped(self, tmp_path):
        env_file = _write(tmp_path, ".env", """
            NOT_A_KV_PAIR
            GITHUB_TOKEN=valid
        """)
        cfg = load_config(env_path=env_file, yaml_path=tmp_path / "no.yaml")
        assert cfg.github_token == "valid"

    def test_env_file_token_wins_over_os_environ(self, tmp_path, monkeypatch):
        """Token in .env file takes precedence over a pre-existing os.environ entry."""
        monkeypatch.setenv("GITHUB_TOKEN", "os_env_token")
        env_file = _write(tmp_path, ".env", "GITHUB_TOKEN=file_token\n")
        cfg = load_config(env_path=env_file, yaml_path=tmp_path / "no.yaml")
        assert cfg.github_token == "file_token"

    def test_os_environ_fallback_when_no_env_file(self, tmp_path, monkeypatch):
        """If .env is absent, token is read from os.environ."""
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        cfg = load_config(
            env_path=tmp_path / "no.env",
            yaml_path=tmp_path / "no.yaml",
        )
        assert cfg.github_token == "env_token"


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

class TestYamlLoading:
    def test_defaults_when_yaml_absent(self, tmp_path):
        cfg = load_config(
            env_path=tmp_path / "no.env",
            yaml_path=tmp_path / "no.yaml",
        )
        assert cfg.scheduler.runs == ["08:30", "14:00"]
        assert cfg.sources.akshare is True
        assert cfg.sources.web is True
        assert cfg.sources.copilot_research is True
        assert cfg.output.formats == ["markdown", "json"]
        assert cfg.storage.db_path == "data/db/mm.db"
        assert cfg.prompt.default_profile == "default"

    def test_full_custom_yaml(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", """
            sources:
              akshare: false
              web: true
              copilot_research: true
            scheduler:
              runs:
                - "07:00"
                - "13:30"
            prompt:
              default_profile: aggressive-v1
              profiles_dir: custom/prompts
            storage:
              db_path: custom/db/test.db
              raw_dir: custom/raw
            output:
              reports_dir: custom/reports
              formats:
                - json
        """)
        cfg = load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)
        assert cfg.sources.akshare is False
        assert cfg.scheduler.runs == ["07:00", "13:30"]
        assert cfg.prompt.default_profile == "aggressive-v1"
        assert cfg.storage.db_path == "custom/db/test.db"
        assert cfg.output.reports_dir == "custom/reports"
        assert cfg.output.formats == ["json"]

    def test_partial_yaml_keeps_defaults_for_missing_sections(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", """
            sources:
              akshare: false
        """)
        cfg = load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)
        assert cfg.sources.akshare is False          # overridden
        assert cfg.scheduler.runs == ["08:30", "14:00"]  # default preserved
        assert cfg.output.formats == ["markdown", "json"]  # default preserved

    def test_empty_yaml_file_uses_all_defaults(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", "")
        cfg = load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)
        assert cfg.sources.akshare is True
        assert cfg.scheduler.runs == ["08:30", "14:00"]

    def test_both_output_formats_accepted(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", """
            output:
              formats:
                - markdown
                - json
        """)
        cfg = load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)
        assert set(cfg.output.formats) == {"markdown", "json"}


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestValidationErrors:
    def test_invalid_scheduler_time_raises(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", """
            scheduler:
              runs:
                - "9:30"
        """)
        with pytest.raises(ConfigError, match="HH:MM"):
            load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)

    def test_scheduler_time_missing_leading_zero_raises(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", """
            scheduler:
              runs:
                - "8:30"
        """)
        with pytest.raises(ConfigError, match="HH:MM"):
            load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)

    def test_unknown_output_format_raises(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", """
            output:
              formats:
                - xml
        """)
        with pytest.raises(ConfigError, match="format"):
            load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)

    def test_top_level_list_yaml_raises(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", "- item1\n- item2\n")
        with pytest.raises(ConfigError, match="mapping"):
            load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)

    def test_sources_non_mapping_raises(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", "sources: not_a_dict\n")
        with pytest.raises(ConfigError, match="sources"):
            load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)

    def test_scheduler_non_mapping_raises(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", "scheduler: 42\n")
        with pytest.raises(ConfigError, match="scheduler"):
            load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)

    def test_scheduler_runs_non_list_raises(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", """
            scheduler:
              runs: "08:30"
        """)
        with pytest.raises(ConfigError, match="list"):
            load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)

    def test_empty_prompt_profile_raises(self, tmp_path):
        yaml_file = _write(tmp_path, "config.yaml", """
            prompt:
              default_profile: "   "
        """)
        with pytest.raises(ConfigError, match="default_profile"):
            load_config(env_path=tmp_path / "no.env", yaml_path=yaml_file)


# ---------------------------------------------------------------------------
# Environment-variable path overrides
# ---------------------------------------------------------------------------

class TestEnvVarOverrides:
    def test_mm_config_path_overrides_yaml(self, tmp_path, monkeypatch):
        yaml_file = _write(tmp_path, "my_config.yaml", """
            scheduler:
              runs:
                - "09:00"
                - "15:00"
        """)
        monkeypatch.setenv("MM_CONFIG_PATH", str(yaml_file))
        cfg = load_config(env_path=tmp_path / "no.env")
        assert cfg.scheduler.runs == ["09:00", "15:00"]

    def test_mm_env_path_overrides_env_file(self, tmp_path, monkeypatch):
        env_file = _write(tmp_path, "my.env", "GITHUB_TOKEN=via_mm_env_path\n")
        monkeypatch.setenv("MM_ENV_PATH", str(env_file))
        cfg = load_config(yaml_path=tmp_path / "no.yaml")
        assert cfg.github_token == "via_mm_env_path"

    def test_explicit_arg_overrides_mm_config_path(self, tmp_path, monkeypatch):
        """Explicit yaml_path argument wins over MM_CONFIG_PATH."""
        other_yaml = _write(tmp_path, "other.yaml", """
            scheduler:
              runs:
                - "10:00"
                - "16:00"
        """)
        wrong_yaml = _write(tmp_path, "wrong.yaml", """
            scheduler:
              runs:
                - "99:00"
                - "99:00"
        """)
        monkeypatch.setenv("MM_CONFIG_PATH", str(wrong_yaml))
        cfg = load_config(env_path=tmp_path / "no.env", yaml_path=other_yaml)
        assert cfg.scheduler.runs == ["10:00", "16:00"]


# ---------------------------------------------------------------------------
# AppConfig.validate() unit tests
# ---------------------------------------------------------------------------

class TestAppConfigValidate:
    def _make_cfg(self, **overrides) -> AppConfig:
        return AppConfig(**overrides)

    def test_valid_default_config_passes(self):
        AppConfig().validate()  # must not raise

    def test_multiple_valid_runs(self):
        from app.config.schema import SchedulerConfig
        cfg = AppConfig(scheduler=SchedulerConfig(runs=["00:00", "23:59"]))
        cfg.validate()  # must not raise
