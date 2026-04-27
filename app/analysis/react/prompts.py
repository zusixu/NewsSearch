"""
app/analysis/react/prompts.py — Prompt context builders and constants.

Provides frozen dataclasses for structured prompt context and helper
functions that build the render-context dicts consumed by the prompt
templates (grouper, react_step, react_finalize).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from app.chains.chain import InformationChain
from app.entity.tagged_output import TaggedOutput


# ---------------------------------------------------------------------------
# GrouperContext — context for the grouping prompt
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GrouperContext:
    """
    Structured context passed to the grouper prompt.

    Fields
    ------
    chains
        Information chains to be grouped.
    tagged_outputs
        Tagged outputs referenced by those chains.
    """

    chains: tuple[InformationChain, ...]
    tagged_outputs: tuple[TaggedOutput, ...]


# ---------------------------------------------------------------------------
# ReActContext — context for a single-group ReAct loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReActContext:
    """
    Structured context for a single ReAct session (one group).

    Fields
    ------
    group_id
        Identifier matching the grouper output.
    theme
        Human-readable theme label for this group.
    member_chains
        The information chains assigned to this group.
    available_tools
        List of ``{"name": ..., "description": ..., "parameters": ...}`` dicts
        describing the tools available to the agent.
    """

    group_id: str
    theme: str
    member_chains: tuple[InformationChain, ...]
    available_tools: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Prompt context builders
# ---------------------------------------------------------------------------


def build_grouper_prompt_context(
    grouper_context: GrouperContext,
    profile_name: str = "default",
    profile_version: str = "1.0.0",
) -> dict[str, str]:
    """
    Build the render-context dict for the grouper prompt template.

    Returns a dict with keys expected by ``grouper.json``:
    ``profile_name``, ``profile_version``, ``task_type``,
    ``chain_count``, ``analysis_payload_json``.
    """
    chains_payload = []
    for chain in grouper_context.chains:
        chains_payload.append(
            {
                "chain_id": chain.chain_id,
                "theme_ids": list(chain.theme_ids),
                "entity_type_ids": list(chain.entity_type_ids),
                "node_count": len(chain.nodes),
                "nodes": [
                    {
                        "position": node.position,
                        "title": node.tagged_output.event.title,
                        "occurred_at": node.tagged_output.event.occurred_at,
                        "text": node.tagged_output.text,
                    }
                    for node in chain.nodes
                ],
            }
        )

    payload = {
        "chains": chains_payload,
        "tagged_output_count": len(grouper_context.tagged_outputs),
    }
    analysis_payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)

    return {
        "profile_name": profile_name,
        "profile_version": profile_version,
        "task_type": "grouper",
        "chain_count": str(len(grouper_context.chains)),
        "analysis_payload_json": analysis_payload_json,
    }


def build_react_step_prompt_context(
    react_context: ReActContext,
    react_history_json: str,
    profile_name: str = "default",
    profile_version: str = "1.0.0",
) -> dict[str, str]:
    """
    Build the render-context dict for the react_step prompt template.

    Returns a dict with keys expected by ``react_step.json``:
    ``profile_name``, ``profile_version``, ``task_type``,
    ``react_history_json``, ``group_json``, ``available_tools_json``.
    """
    group_payload = {
        "group_id": react_context.group_id,
        "theme": react_context.theme,
        "member_chains": [
            {
                "chain_id": ch.chain_id,
                "theme_ids": list(ch.theme_ids),
                "entity_type_ids": list(ch.entity_type_ids),
                "nodes": [
                    {
                        "position": n.position,
                        "title": n.tagged_output.event.title,
                        "occurred_at": n.tagged_output.event.occurred_at,
                        "text": n.tagged_output.text,
                    }
                    for n in ch.nodes
                ],
            }
            for ch in react_context.member_chains
        ],
    }
    group_json = json.dumps(group_payload, ensure_ascii=False, sort_keys=True, indent=2)
    available_tools_json = json.dumps(
        react_context.available_tools, ensure_ascii=False, sort_keys=True, indent=2
    )

    return {
        "profile_name": profile_name,
        "profile_version": profile_version,
        "task_type": "react_step",
        "react_history_json": react_history_json,
        "group_json": group_json,
        "available_tools_json": available_tools_json,
    }


def build_react_finalize_prompt_context(
    react_history_json: str,
    profile_name: str = "default",
    profile_version: str = "1.0.0",
) -> dict[str, str]:
    """
    Build the render-context dict for the react_finalize prompt template.

    Returns a dict with keys expected by ``react_finalize.json``:
    ``profile_name``, ``profile_version``, ``task_type``,
    ``react_history_json``.
    """
    return {
        "profile_name": profile_name,
        "profile_version": profile_version,
        "task_type": "react_finalize",
        "react_history_json": react_history_json,
    }
