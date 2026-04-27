"""
Prompt profile loading and management.

This module provides facilities for loading prompt profiles from YAML
configuration files, validating them, and resolving the appropriate
template paths for each task type.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.config.override import PromptOverrideConfig

from app.analysis.adapters.contracts import PromptProfile, PromptTaskType


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PromptProfileError(ValueError):
    """Raised when a prompt profile is invalid or cannot be loaded."""


class MissingPromptProfileError(FileNotFoundError):
    """Raised when a requested prompt profile does not exist."""


# ---------------------------------------------------------------------------
# Task template mapping dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskTemplateMapping:
    """Template configuration for a single task type within a profile."""

    template: str
    """Filename of the JSON template to use for this task."""

    overrides: dict[str, Any] = field(default_factory=dict)
    """Optional overrides to apply to the template (reserved for future use)."""


# ---------------------------------------------------------------------------
# PromptProfileConfig - full profile configuration from YAML
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptProfileConfig:
    """
    Full prompt profile configuration loaded from a YAML file.

    This extends the basic ``PromptProfile`` contract with task-specific
    template mappings and validation logic.
    """

    profile_name: str
    version: str
    description: str
    tasks: dict[PromptTaskType, TaskTemplateMapping]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptProfileConfig:
        """
        Create a ``PromptProfileConfig`` from a parsed YAML dictionary.

        Parameters
        ----------
        data
            Parsed YAML dictionary containing profile configuration.

        Returns
        -------
        PromptProfileConfig
            Validated profile configuration.

        Raises
        ------
        PromptProfileError
            If the configuration is invalid or missing required fields.
        """
        profile_name = data.get("profile_name")
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise PromptProfileError("profile_name must be a non-empty string")

        version = data.get("version")
        if not isinstance(version, str) or not version.strip():
            raise PromptProfileError("version must be a non-empty string")

        description = data.get("description", "")
        if not isinstance(description, str):
            raise PromptProfileError("description must be a string")

        tasks_data = data.get("tasks")
        if not isinstance(tasks_data, dict):
            raise PromptProfileError("tasks must be a dictionary mapping task types to templates")

        tasks: dict[PromptTaskType, TaskTemplateMapping] = {}
        for task_key, task_config in tasks_data.items():
            try:
                task_type = PromptTaskType(task_key)
            except ValueError:
                raise PromptProfileError(f"Unknown task type: {task_key!r}") from None

            if not isinstance(task_config, dict):
                raise PromptProfileError(f"Task configuration for {task_key!r} must be a dictionary")

            template = task_config.get("template")
            if not isinstance(template, str) or not template.strip():
                raise PromptProfileError(f"template for {task_key!r} must be a non-empty string")

            overrides = task_config.get("overrides", {})
            if not isinstance(overrides, dict):
                raise PromptProfileError(f"overrides for {task_key!r} must be a dictionary")

            tasks[task_type] = TaskTemplateMapping(template=template, overrides=overrides)

        # Ensure all task types are covered
        for task_type in PromptTaskType:
            if task_type not in tasks:
                raise PromptProfileError(f"Missing task configuration for {task_type.value!r}")

        return cls(
            profile_name=profile_name,
            version=version,
            description=description,
            tasks=tasks,
        )

    def to_prompt_profile(self, task_type: PromptTaskType) -> PromptProfile:
        """
        Create a basic ``PromptProfile`` for a specific task type from this config.

        Parameters
        ----------
        task_type
            The task type to create a profile for.

        Returns
        -------
        PromptProfile
            Basic profile identifier suitable for use in ``AnalysisInput``.
        """
        return PromptProfile(
            profile_name=self.profile_name,
            task_type=task_type,
            version=self.version,
            description=self.description,
        )

    def template_for(self, task_type: PromptTaskType) -> str:
        """
        Get the template filename for a specific task type.

        Parameters
        ----------
        task_type
            The task type to get the template for.

        Returns
        -------
        str
            Template filename.
        """
        return self.tasks[task_type].template


# ---------------------------------------------------------------------------
# PromptProfileLoader - loads profiles from disk
# ---------------------------------------------------------------------------


class PromptProfileLoader:
    """
    Loads prompt profiles from a directory of YAML files.

    Profiles are stored as ``<profile_name>.yaml`` in the profiles directory.
    """

    def __init__(self, profiles_dir: str | Path) -> None:
        """
        Initialize the loader with a directory path.

        Parameters
        ----------
        profiles_dir
            Path to the directory containing prompt profile YAML files.
        """
        self._profiles_dir = Path(profiles_dir)

    @property
    def profiles_dir(self) -> Path:
        """Directory containing prompt profile YAML files."""
        return self._profiles_dir

    def list_profiles(self) -> list[str]:
        """
        List all available profile names in the profiles directory.

        Returns
        -------
        list[str]
            Sorted list of profile names (without .yaml extension).
        """
        if not self._profiles_dir.is_dir():
            return []

        profiles: list[str] = []
        for path in self._profiles_dir.glob("*.yaml"):
            if path.is_file():
                profiles.append(path.stem)
        return sorted(profiles)

    def load_profile(self, profile_name: str) -> PromptProfileConfig:
        """
        Load a prompt profile by name.

        Parameters
        ----------
        profile_name
            Name of the profile to load (without .yaml extension).

        Returns
        -------
        PromptProfileConfig
            Loaded and validated profile configuration.

        Raises
        ------
        MissingPromptProfileError
            If the profile file does not exist.
        PromptProfileError
            If the profile file is invalid or cannot be parsed.
        """
        path = self._profiles_dir / f"{profile_name}.yaml"
        if not path.is_file():
            raise MissingPromptProfileError(f"Prompt profile not found: {path}")

        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise PromptProfileError(f"Failed to parse YAML profile {path}: {exc}") from exc
        except OSError as exc:
            raise PromptProfileError(f"Failed to read profile file {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise PromptProfileError(f"Profile file {path} must contain a YAML dictionary")

        # Ensure profile_name in the file matches the requested name
        file_profile_name = data.get("profile_name")
        if file_profile_name is not None and file_profile_name != profile_name:
            raise PromptProfileError(
                f"Profile name in file ({file_profile_name!r}) does not match requested name ({profile_name!r})"
            )

        # If profile_name is not in the file, inject it
        if file_profile_name is None:
            data["profile_name"] = profile_name

        return PromptProfileConfig.from_dict(data)

    def load_profile_with_fallback(self, profile_name: str, fallback_name: str = "default") -> PromptProfileConfig:
        """
        Load a prompt profile, falling back to a default profile if it's missing.

        Parameters
        ----------
        profile_name
            Name of the profile to load first.
        fallback_name
            Name of the profile to use as fallback (default: "default").

        Returns
        -------
        PromptProfileConfig
            Loaded profile configuration (either requested or fallback).

        Raises
        ------
        MissingPromptProfileError
            If neither the requested profile nor the fallback exists.
        """
        try:
            return self.load_profile(profile_name)
        except MissingPromptProfileError:
            if profile_name == fallback_name:
                raise
            return self.load_profile(fallback_name)


# ---------------------------------------------------------------------------
# Prompt-override merging
# ---------------------------------------------------------------------------


def merge_prompt_overrides(
    profile_config: PromptProfileConfig,
    prompt_overrides: PromptOverrideConfig,
) -> PromptProfileConfig:
    """Merge :class:`PromptOverrideConfig` into a :class:`PromptProfileConfig`.

    The override's ``system_message_suffix`` and per-task directives are
    written into each task's :attr:`TaskTemplateMapping.overrides` dict so
    that the renderer can apply them after template rendering.

    Returns a **new** ``PromptProfileConfig`` — the original is not mutated.
    """
    if prompt_overrides is None:
        return profile_config

    from dataclasses import replace as _replace

    merged_tasks: dict[PromptTaskType, TaskTemplateMapping] = {}
    for task_type, mapping in profile_config.tasks.items():
        overrides = dict(mapping.overrides)

        # Global system_message_suffix
        if prompt_overrides.system_message_suffix:
            overrides["system_message_suffix"] = prompt_overrides.system_message_suffix

        # Per-task overrides
        task_key = task_type.value
        task_override = prompt_overrides.tasks.get(task_key)
        if task_override is not None:
            if task_override.system_message is not None:
                overrides["system_message"] = task_override.system_message
            if task_override.system_message_suffix is not None:
                overrides["system_message_suffix"] = task_override.system_message_suffix
            if task_override.user_message_prefix is not None:
                overrides["user_message_prefix"] = task_override.user_message_prefix
            if task_override.user_message_suffix is not None:
                overrides["user_message_suffix"] = task_override.user_message_suffix

        merged_tasks[task_type] = _replace(mapping, overrides=overrides)

    return _replace(profile_config, tasks=merged_tasks)
