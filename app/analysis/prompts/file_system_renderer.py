"""
Filesystem-backed prompt renderer.

This module keeps prompt text خارج adapter transport code by loading editable
JSON template files from ``app/analysis/prompts/templates`` (or a caller-
supplied directory). JSON was chosen deliberately to avoid introducing a YAML
dependency while still keeping prompts human-editable and versionable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.analysis.adapters.contracts import AnalysisInput, PromptTaskType
from app.analysis.adapters.github_models import ChatMessage
from app.analysis.prompts.profile import PromptProfileConfig


class PromptTemplateError(ValueError):
    """Raised when a prompt template file is malformed or cannot be rendered."""


class MissingPromptTemplateError(FileNotFoundError):
    """Raised when the expected prompt template file does not exist."""


class FileSystemPromptRenderer:
    """Render chat messages from JSON prompt templates on disk."""

    def __init__(
        self,
        base_dir: str | Path | None = None,
        profile_config: PromptProfileConfig | None = None,
        search_keywords: list[str] | None = None,
    ) -> None:
        """
        Initialize the renderer.

        Parameters
        ----------
        base_dir
            Directory containing prompt template JSON files.
        profile_config
            Optional profile configuration to use for template selection.
            If provided, templates will be selected from the profile's task mappings.
        search_keywords
            Optional search keywords to include in the render context.
        """
        self._base_dir = (
            Path(base_dir)
            if base_dir is not None
            else Path(__file__).with_name("templates")
        )
        self._profile_config = profile_config
        self._search_keywords = search_keywords or []

    @property
    def base_dir(self) -> Path:
        """Directory containing prompt template JSON files."""
        return self._base_dir

    @property
    def profile_config(self) -> PromptProfileConfig | None:
        """Profile configuration used for template selection, if any."""
        return self._profile_config

    def render(self, analysis_input: AnalysisInput) -> list[ChatMessage]:
        """Render the template selected by ``analysis_input.prompt_profile.task_type``.

        After template rendering, applies any message overrides from the active
        profile's ``TaskTemplateMapping.overrides`` (e.g. system_message_suffix,
        user_message_prefix, etc.).
        """
        template = self._load_template(
            analysis_input.prompt_profile.task_type,
        )
        render_context = self._build_render_context(analysis_input)

        rendered_messages: list[ChatMessage] = []
        for index, message in enumerate(template["messages"]):
            role = message.get("role")
            content = message.get("content")
            if not isinstance(role, str) or not isinstance(content, str):
                raise PromptTemplateError(
                    f"Template message #{index} must contain string role/content fields."
                )
            try:
                rendered_content = content.format(**render_context)
            except KeyError as exc:
                raise PromptTemplateError(
                    f"Template placeholder {exc!s} is missing from render context."
                ) from exc
            rendered_messages.append(ChatMessage(role=role, content=rendered_content))

        # Apply message overrides from profile config
        rendered_messages = self._apply_overrides(
            rendered_messages,
            analysis_input.prompt_profile.task_type,
        )

        if not rendered_messages:
            raise PromptTemplateError("Template must render at least one message.")
        return rendered_messages

    def template_path_for(self, task_type: PromptTaskType) -> Path:
        """
        Return the on-disk template path for a given task type.

        If a profile config is available, uses the template specified in the profile.
        Otherwise, falls back to the default template mapping.
        """
        if self._profile_config is not None:
            template_filename = self._profile_config.template_for(task_type)
            return self._base_dir / template_filename
        else:
            # Fall back to default template names
            default_filenames: dict[PromptTaskType, str] = {
                PromptTaskType.SUMMARY: "summary.json",
                PromptTaskType.CHAIN_COMPLETION: "chain_completion.json",
                PromptTaskType.INVESTMENT_RANKING: "investment_ranking.json",
            }
            return self._base_dir / default_filenames[task_type]

    def _load_template(self, task_type: PromptTaskType) -> dict[str, Any]:
        path = self.template_path_for(task_type)
        if not path.is_file():
            raise MissingPromptTemplateError(f"Prompt template not found: {path}")

        try:
            template = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PromptTemplateError(f"Prompt template JSON is invalid: {path}") from exc

        messages = template.get("messages")
        if not isinstance(messages, list):
            raise PromptTemplateError(
                f"Prompt template must contain a list field 'messages': {path}"
            )
        return template

    def _build_render_context(self, analysis_input: AnalysisInput) -> dict[str, str]:
        payload = {
            "prompt_profile": {
                "profile_name": analysis_input.prompt_profile.profile_name,
                "task_type": analysis_input.prompt_profile.task_type.value,
                "version": analysis_input.prompt_profile.version,
                "description": analysis_input.prompt_profile.description,
            },
            "chain_count": len(analysis_input.chains),
            "chains": [
                {
                    "chain_id": chain.chain_id,
                    "theme_ids": list(chain.theme_ids),
                    "entity_type_ids": list(chain.entity_type_ids),
                    "nodes": [
                        {
                            "position": node.position,
                            "relation_to_prev": (
                                None
                                if node.relation_to_prev is None
                                else node.relation_to_prev.value
                            ),
                            "title": node.tagged_output.event.title,
                            "occurred_at": node.tagged_output.event.occurred_at,
                            "text": node.tagged_output.text,
                            "theme_ids": list(node.tagged_output.theme_ids),
                            "entity_type_ids": list(node.tagged_output.entity_type_ids),
                            "evidence_count": len(node.tagged_output.evidence_links),
                            "source_item_count": len(node.tagged_output.event.source_items),
                        }
                        for node in chain.nodes
                    ],
                }
                for chain in analysis_input.chains
            ],
            "evidence_bundles": [
                {
                    "chain_id": bundle.chain_id,
                    "source_titles": [item.title for item in bundle.source_items],
                    "evidence_count": len(bundle.evidence_links),
                    "evidence": [
                        {
                            "label_id": link.hit.label_id,
                            "kind": link.hit.kind,
                            "matched_text": link.hit.matched_text,
                            "snippet": link.span.snippet,
                            "start": link.span.start,
                            "end": link.span.end,
                        }
                        for link in bundle.evidence_links
                    ],
                }
                for bundle in analysis_input.evidence_bundles
            ],
        }
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        search_keywords_json = json.dumps(self._search_keywords, ensure_ascii=False)
        return {
            "profile_name": analysis_input.prompt_profile.profile_name,
            "profile_version": analysis_input.prompt_profile.version,
            "profile_description": analysis_input.prompt_profile.description,
            "task_type": analysis_input.prompt_profile.task_type.value,
            "chain_count": str(len(analysis_input.chains)),
            "analysis_payload_json": payload_json,
            "search_keywords_json": search_keywords_json,
        }

    def _apply_overrides(
        self,
        messages: list[ChatMessage],
        task_type: PromptTaskType,
    ) -> list[ChatMessage]:
        """Apply message-level overrides from the active profile config.

        Supported override keys in ``TaskTemplateMapping.overrides``:
          - ``system_message`` — replace the system message content entirely
          - ``system_message_suffix`` — append to the system message content
          - ``user_message_prefix`` — prepend to the user message content
          - ``user_message_suffix`` — append to the user message content
        """
        if self._profile_config is None:
            return messages

        mapping = self._profile_config.tasks.get(task_type)
        if mapping is None or not mapping.overrides:
            return messages

        result: list[ChatMessage] = []
        for msg in messages:
            content = msg.content
            if msg.role == "system":
                if "system_message" in mapping.overrides:
                    content = str(mapping.overrides["system_message"])
                if "system_message_suffix" in mapping.overrides:
                    content = content + str(mapping.overrides["system_message_suffix"])
            elif msg.role == "user":
                if "user_message_prefix" in mapping.overrides:
                    content = str(mapping.overrides["user_message_prefix"]) + content
                if "user_message_suffix" in mapping.overrides:
                    content = content + str(mapping.overrides["user_message_suffix"])
            result.append(ChatMessage(role=msg.role, content=content))
        return result
