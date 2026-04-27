"""Tests for prompt profile loading and management."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.analysis.adapters.contracts import PromptProfile, PromptTaskType
from app.analysis.prompts import (
    FileSystemPromptRenderer,
    MissingPromptProfileError,
    MissingPromptTemplateError,
    PromptProfileConfig,
    PromptProfileError,
    PromptProfileLoader,
    TaskTemplateMapping,
)


# ---------------------------------------------------------------------------
# Test TaskTemplateMapping
# ---------------------------------------------------------------------------


class TestTaskTemplateMapping:
    """Tests for TaskTemplateMapping dataclass."""

    def test_basic_construction(self) -> None:
        """TaskTemplateMapping can be constructed with just a template."""
        mapping = TaskTemplateMapping(template="summary.json")
        assert mapping.template == "summary.json"
        assert mapping.overrides == {}

    def test_with_overrides(self) -> None:
        """TaskTemplateMapping can be constructed with overrides."""
        overrides = {"temperature": 0.7, "max_tokens": 1000}
        mapping = TaskTemplateMapping(template="summary.json", overrides=overrides)
        assert mapping.template == "summary.json"
        assert mapping.overrides == overrides


# ---------------------------------------------------------------------------
# Test PromptProfileConfig
# ---------------------------------------------------------------------------


class TestPromptProfileConfig:
    """Tests for PromptProfileConfig dataclass and loading."""

    def test_from_dict_valid(self) -> None:
        """PromptProfileConfig can be loaded from a valid dictionary."""
        data = {
            "profile_name": "test",
            "version": "1.0.0",
            "description": "Test profile",
            "tasks": {
                "summary": {"template": "summary.json"},
                "chain_completion": {"template": "chain_completion.json"},
                "investment_ranking": {"template": "investment_ranking.json"},
            },
        }
        config = PromptProfileConfig.from_dict(data)
        assert config.profile_name == "test"
        assert config.version == "1.0.0"
        assert config.description == "Test profile"
        assert PromptTaskType.SUMMARY in config.tasks
        assert config.tasks[PromptTaskType.SUMMARY].template == "summary.json"

    def test_from_dict_missing_profile_name(self) -> None:
        """PromptProfileConfig.from_dict raises error if profile_name is missing."""
        data = {
            "version": "1.0.0",
            "description": "Test profile",
            "tasks": {
                "summary": {"template": "summary.json"},
                "chain_completion": {"template": "chain_completion.json"},
                "investment_ranking": {"template": "investment_ranking.json"},
            },
        }
        with pytest.raises(PromptProfileError, match="profile_name must be"):
            PromptProfileConfig.from_dict(data)

    def test_from_dict_empty_profile_name(self) -> None:
        """PromptProfileConfig.from_dict raises error if profile_name is empty."""
        data = {
            "profile_name": "",
            "version": "1.0.0",
            "description": "Test profile",
            "tasks": {
                "summary": {"template": "summary.json"},
                "chain_completion": {"template": "chain_completion.json"},
                "investment_ranking": {"template": "investment_ranking.json"},
            },
        }
        with pytest.raises(PromptProfileError, match="profile_name must be"):
            PromptProfileConfig.from_dict(data)

    def test_from_dict_missing_version(self) -> None:
        """PromptProfileConfig.from_dict raises error if version is missing."""
        data = {
            "profile_name": "test",
            "description": "Test profile",
            "tasks": {
                "summary": {"template": "summary.json"},
                "chain_completion": {"template": "chain_completion.json"},
                "investment_ranking": {"template": "investment_ranking.json"},
            },
        }
        with pytest.raises(PromptProfileError, match="version must be"):
            PromptProfileConfig.from_dict(data)

    def test_from_dict_missing_tasks(self) -> None:
        """PromptProfileConfig.from_dict raises error if tasks is missing."""
        data = {
            "profile_name": "test",
            "version": "1.0.0",
            "description": "Test profile",
        }
        with pytest.raises(PromptProfileError, match="tasks must be"):
            PromptProfileConfig.from_dict(data)

    def test_from_dict_invalid_task_type(self) -> None:
        """PromptProfileConfig.from_dict raises error for unknown task types."""
        data = {
            "profile_name": "test",
            "version": "1.0.0",
            "description": "Test profile",
            "tasks": {
                "invalid_task": {"template": "test.json"},
            },
        }
        with pytest.raises(PromptProfileError, match="Unknown task type"):
            PromptProfileConfig.from_dict(data)

    def test_from_dict_missing_task(self) -> None:
        """PromptProfileConfig.from_dict raises error if a task type is missing."""
        data = {
            "profile_name": "test",
            "version": "1.0.0",
            "description": "Test profile",
            "tasks": {
                "summary": {"template": "summary.json"},
                # Missing chain_completion and investment_ranking
            },
        }
        with pytest.raises(PromptProfileError, match="Missing task configuration"):
            PromptProfileConfig.from_dict(data)

    def test_to_prompt_profile(self) -> None:
        """PromptProfileConfig can create a basic PromptProfile for a task."""
        data = {
            "profile_name": "test",
            "version": "1.0.0",
            "description": "Test profile",
            "tasks": {
                "summary": {"template": "summary.json"},
                "chain_completion": {"template": "chain_completion.json"},
                "investment_ranking": {"template": "investment_ranking.json"},
            },
        }
        config = PromptProfileConfig.from_dict(data)
        profile = config.to_prompt_profile(PromptTaskType.SUMMARY)
        assert isinstance(profile, PromptProfile)
        assert profile.profile_name == "test"
        assert profile.task_type == PromptTaskType.SUMMARY
        assert profile.version == "1.0.0"
        assert profile.description == "Test profile"

    def test_template_for(self) -> None:
        """PromptProfileConfig.template_for returns the correct template filename."""
        data = {
            "profile_name": "test",
            "version": "1.0.0",
            "description": "Test profile",
            "tasks": {
                "summary": {"template": "custom_summary.json"},
                "chain_completion": {"template": "custom_chain.json"},
                "investment_ranking": {"template": "custom_ranking.json"},
            },
        }
        config = PromptProfileConfig.from_dict(data)
        assert config.template_for(PromptTaskType.SUMMARY) == "custom_summary.json"
        assert config.template_for(PromptTaskType.CHAIN_COMPLETION) == "custom_chain.json"
        assert config.template_for(PromptTaskType.INVESTMENT_RANKING) == "custom_ranking.json"


# ---------------------------------------------------------------------------
# Test PromptProfileLoader
# ---------------------------------------------------------------------------


class TestPromptProfileLoader:
    """Tests for PromptProfileLoader class."""

    def test_list_profiles_empty_dir(self) -> None:
        """PromptProfileLoader.list_profiles returns empty list for empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PromptProfileLoader(tmpdir)
            assert loader.list_profiles() == []

    def test_list_profiles(self, tmp_path: Path) -> None:
        """PromptProfileLoader.list_profiles returns sorted list of profile names."""
        # Create some profile files
        (tmp_path / "default.yaml").write_text(
            yaml.dump(
                {
                    "profile_name": "default",
                    "version": "1.0.0",
                    "description": "Default",
                    "tasks": {
                        "summary": {"template": "summary.json"},
                        "chain_completion": {"template": "chain_completion.json"},
                        "investment_ranking": {"template": "investment_ranking.json"},
                    },
                }
            )
        )
        (tmp_path / "aggressive.yaml").write_text(
            yaml.dump(
                {
                    "profile_name": "aggressive",
                    "version": "1.0.0",
                    "description": "Aggressive",
                    "tasks": {
                        "summary": {"template": "summary.json"},
                        "chain_completion": {"template": "chain_completion.json"},
                        "investment_ranking": {"template": "investment_ranking.json"},
                    },
                }
            )
        )
        # Non-YAML file should be ignored
        (tmp_path / "readme.txt").write_text("Readme")

        loader = PromptProfileLoader(tmp_path)
        assert loader.list_profiles() == ["aggressive", "default"]

    def test_load_profile(self, tmp_path: Path) -> None:
        """PromptProfileLoader.load_profile loads and validates a profile."""
        profile_path = tmp_path / "test.yaml"
        profile_path.write_text(
            yaml.dump(
                {
                    "profile_name": "test",
                    "version": "2.1.0",
                    "description": "Test profile",
                    "tasks": {
                        "summary": {"template": "summary.json"},
                        "chain_completion": {"template": "chain.json"},
                        "investment_ranking": {"template": "ranking.json"},
                    },
                }
            )
        )

        loader = PromptProfileLoader(tmp_path)
        config = loader.load_profile("test")
        assert config.profile_name == "test"
        assert config.version == "2.1.0"
        assert config.description == "Test profile"

    def test_load_profile_missing(self, tmp_path: Path) -> None:
        """PromptProfileLoader.load_profile raises error for missing profile."""
        loader = PromptProfileLoader(tmp_path)
        with pytest.raises(MissingPromptProfileError, match="Prompt profile not found"):
            loader.load_profile("nonexistent")

    def test_load_profile_name_mismatch(self, tmp_path: Path) -> None:
        """PromptProfileLoader.load_profile raises error if profile name doesn't match filename."""
        profile_path = tmp_path / "test.yaml"
        profile_path.write_text(
            yaml.dump(
                {
                    "profile_name": "wrong_name",  # Doesn't match filename
                    "version": "1.0.0",
                    "description": "Test",
                    "tasks": {
                        "summary": {"template": "summary.json"},
                        "chain_completion": {"template": "chain_completion.json"},
                        "investment_ranking": {"template": "investment_ranking.json"},
                    },
                }
            )
        )

        loader = PromptProfileLoader(tmp_path)
        with pytest.raises(PromptProfileError, match="Profile name in file"):
            loader.load_profile("test")

    def test_load_profile_inject_name(self, tmp_path: Path) -> None:
        """PromptProfileLoader.load_profile injects filename as profile_name if missing."""
        profile_path = tmp_path / "test.yaml"
        profile_path.write_text(
            yaml.dump(
                {
                    # profile_name missing - should be injected
                    "version": "1.0.0",
                    "description": "Test",
                    "tasks": {
                        "summary": {"template": "summary.json"},
                        "chain_completion": {"template": "chain_completion.json"},
                        "investment_ranking": {"template": "investment_ranking.json"},
                    },
                }
            )
        )

        loader = PromptProfileLoader(tmp_path)
        config = loader.load_profile("test")
        assert config.profile_name == "test"  # Injected from filename

    def test_load_profile_with_fallback(self, tmp_path: Path) -> None:
        """PromptProfileLoader.load_profile_with_fallback falls back to default."""
        # Create default profile
        (tmp_path / "default.yaml").write_text(
            yaml.dump(
                {
                    "profile_name": "default",
                    "version": "1.0.0",
                    "description": "Default",
                    "tasks": {
                        "summary": {"template": "summary.json"},
                        "chain_completion": {"template": "chain_completion.json"},
                        "investment_ranking": {"template": "investment_ranking.json"},
                    },
                }
            )
        )

        loader = PromptProfileLoader(tmp_path)
        config = loader.load_profile_with_fallback("nonexistent", "default")
        assert config.profile_name == "default"

    def test_load_profile_with_fallback_both_missing(self, tmp_path: Path) -> None:
        """PromptProfileLoader.load_profile_with_fallback raises error if both are missing."""
        loader = PromptProfileLoader(tmp_path)
        with pytest.raises(MissingPromptProfileError):
            loader.load_profile_with_fallback("nonexistent", "also_nonexistent")


# ---------------------------------------------------------------------------
# Test integration with FileSystemPromptRenderer
# ---------------------------------------------------------------------------


class TestFileSystemPromptRendererWithProfiles:
    """Tests for FileSystemPromptRenderer with profile configuration."""

    def test_renderer_with_profile_config(self, tmp_path: Path) -> None:
        """FileSystemPromptRenderer uses template from profile config."""
        # Create profile config
        profile_data = {
            "profile_name": "test",
            "version": "1.0.0",
            "description": "Test",
            "tasks": {
                "summary": {"template": "custom_summary.json"},
                "chain_completion": {"template": "chain_completion.json"},
                "investment_ranking": {"template": "investment_ranking.json"},
            },
        }
        profile_config = PromptProfileConfig.from_dict(profile_data)

        # Create templates directory
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        # Create custom template
        custom_template = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Analyze this: {analysis_payload_json}"},
            ]
        }
        (templates_dir / "custom_summary.json").write_text(
            yaml.dump(custom_template, default_flow_style=False)  # Wait, no - our templates are JSON!
            # Actually, let's write JSON directly
        )

        # Let's fix that - write proper JSON
        import json
        (templates_dir / "custom_summary.json").write_text(json.dumps(custom_template))

        # Create renderer with profile config
        renderer = FileSystemPromptRenderer(base_dir=templates_dir, profile_config=profile_config)

        # Check that it uses the custom template path
        template_path = renderer.template_path_for(PromptTaskType.SUMMARY)
        assert template_path.name == "custom_summary.json"

    def test_renderer_without_profile_config_falls_back(self) -> None:
        """FileSystemPromptRenderer falls back to default templates without profile config."""
        renderer = FileSystemPromptRenderer()
        # Uses default template names
        path = renderer.template_path_for(PromptTaskType.SUMMARY)
        assert path.name == "summary.json"
