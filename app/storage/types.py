"""
app/storage/types.py — shared type definitions for the storage layer.

These types were extracted from the analysis layer to resolve a layering
violation (rule.md §3.1: storage must not import from analysis).

Types defined here:
  - PromptTaskType (str, Enum)
  - PromptProfileError (Exception)
  - TaskTemplateMapping (frozen dataclass)
  - PromptProfileConfig (frozen dataclass)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# PromptTaskType — enumeration of supported analysis tasks
# ---------------------------------------------------------------------------


class PromptTaskType(str, Enum):
    """The analysis tasks supported by the adapter layer."""

    SUMMARY = "summary"
    """摘要归纳 — narrative summary of chain events."""

    CHAIN_COMPLETION = "chain_completion"
    """链路补全 — infer or complete missing causal links in a chain."""

    INVESTMENT_RANKING = "investment_ranking"
    """投资排序 — rank chains by investment relevance."""

    GROUPER = "grouper"
    """分组策略 — determine optimal grouping of tagged outputs."""

    REACT_STEP = "react_step"
    """ReAct 单步迭代 — single reasoning+acting iteration."""

    REACT_FINALIZE = "react_finalize"
    """ReAct 最终输出 — synthesise steps into final analysis."""


# ---------------------------------------------------------------------------
# PromptProfileError
# ---------------------------------------------------------------------------


class PromptProfileError(ValueError):
    """Raised when a prompt profile is invalid or cannot be loaded."""


# ---------------------------------------------------------------------------
# TaskTemplateMapping
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

        # Auto-add ReAct-internal task types (not user-configurable)
        _REACT_DEFAULT_TEMPLATES: dict[PromptTaskType, str] = {
            PromptTaskType.GROUPER: "grouper.json",
            PromptTaskType.REACT_STEP: "react_step.json",
            PromptTaskType.REACT_FINALIZE: "react_finalize.json",
        }
        for react_task_type, react_template in _REACT_DEFAULT_TEMPLATES.items():
            if react_task_type not in tasks:
                tasks[react_task_type] = TaskTemplateMapping(template=react_template)

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

    def to_prompt_profile(self, task_type: PromptTaskType) -> "PromptProfile":
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
        # Lazy import to avoid circular imports with contracts.py
        from app.analysis.adapters.contracts import PromptProfile

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
