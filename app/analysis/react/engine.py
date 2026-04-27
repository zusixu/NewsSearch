"""
app/analysis/react/engine.py — ReAct multi-step analysis engine.

Orchestrates the full ReAct pipeline:
  1. Grouper — ask the LLM to cluster tagged outputs / chains into coherent groups.
  2. ReAct loop — for each group, run a multi-step reasoning+acting session
     where the LLM can call tools (web_search, web_fetch, akshare_query).
  3. Finalize — synthesise each session's steps into a ChainAnalysisResult.
  4. Cross-group ranking — order groups into an AnalysisResponse.

The engine reuses the existing ``AnalysisAdapter`` for LLM calls, passing
``AnalysisInput`` with ``extra_context`` populated for the ReAct-specific
prompt placeholders.

Design constraints
------------------
- The adapter's ``analyse()`` returns ``AnalysisResponse``; for ReAct steps
  the engine accesses internal adapter methods (``_render_messages``,
  ``_build_payload``, ``_post``, ``_read_token``) via duck-typing to obtain
  the raw LLM JSON without coercing it into ``AnalysisResponse`` prematurely.
- ``dry_run`` mode short-circuits all LLM calls and returns deterministic
  dummy output.
- Tool execution happens **between** LLM calls: LLM decides → engine executes
  tool → observation fed back to next LLM call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.analysis.adapters.contracts import (
    AnalysisInput,
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    ModelProviderInfo,
    PromptProfile,
    PromptTaskType,
    RankingOutput,
)
from app.analysis.adapters.github_models import PromptRenderer
from app.analysis.react.prompts import (
    GrouperContext,
    ReActContext,
    build_grouper_prompt_context,
    build_react_finalize_prompt_context,
    build_react_step_prompt_context,
)
from app.analysis.react.session import ReActSession, ReActStep
from app.analysis.react.tools import ToolRegistry, tool_registry
from app.chains.chain import InformationChain, build_chain
from app.chains.candidate_generation import generate_candidate_chains
from app.chains.evidence_retention import ChainEvidenceBundle, collect_chain_evidence
from app.entity.tagged_output import TaggedOutput


# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReActEngineConfig:
    """Configuration for :class:`ReActAnalysisEngine`.

    Fields
    ------
    max_steps_per_group
        Maximum ReAct iterations per group (default 5).
    max_groups
        Maximum number of groups to create (default 10).
    enable_web_search
        Register the ``web_search`` tool.
    enable_web_fetch
        Register the ``web_fetch`` tool.
    enable_akshare_query
        Register the ``akshare_query`` tool.
    profile_name
        Prompt profile name to use for template rendering.
    profile_version
        Prompt profile version string.
    """

    max_steps_per_group: int = 5
    max_groups: int = 10
    enable_web_search: bool = True
    enable_web_fetch: bool = True
    enable_akshare_query: bool = True
    profile_name: str = "default"
    profile_version: str = "1.0.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_code_fences(text: str) -> str:
    """Remove Markdown ```json ... ``` wrappers from LLM output."""
    stripped = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
    if m:
        return m.group(1).strip()
    return stripped


def _normalise_chain_results(raw: Any) -> list[dict[str, Any]]:
    """Normalise *raw* into a list of dicts.

    The LLM may return ``chain_results`` as a dict (keyed by index or chain
    id) instead of the expected list, or as a flat JSON array of primitive
    values (e.g. ``[1, 2, 3]``).  This helper coerces all known shapes into
    ``list[dict]``, dropping entries that cannot be converted.
    """
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [
            item
            for item in raw.values()
            if isinstance(item, dict)
        ]
    return []


# ---------------------------------------------------------------------------
# ReActAnalysisEngine
# ---------------------------------------------------------------------------


class ReActAnalysisEngine:
    """Multi-step ReAct analysis engine.

    The engine runs a four-phase pipeline:
    1. **Group** tagged outputs into themed clusters via LLM.
    2. **ReAct** — for each group, run an iterative think→act→observe loop.
    3. **Finalize** — synthesise each session's steps into structured results.
    4. **Rank** — cross-group ranking into an ``AnalysisResponse``.
    """

    def __init__(
        self,
        adapter: Any,
        renderer: PromptRenderer | None,
        engine_config: ReActEngineConfig | None = None,
        *,
        dry_run: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        adapter
            An ``AnalysisAdapter`` implementation (e.g. ``GitHubModelsAdapter``,
            ``OpenAICompatibleAdapter``).
        renderer
            ``FileSystemPromptRenderer`` instance; used directly for prompt
            rendering when the engine needs to bypass the adapter's
            ``analyse()`` pipeline for ReAct-specific raw output.
        engine_config
            ReAct engine configuration; defaults to ``ReActEngineConfig()``.
        dry_run
            If ``True``, skip all LLM calls and return dummy output.
        """
        self._adapter = adapter
        self._renderer = renderer
        self._config = engine_config or ReActEngineConfig()
        self._dry_run = dry_run

        # Build tool registry based on config
        self._tools = ToolRegistry()
        if self._config.enable_web_search:
            from app.analysis.react.tools import web_search_tool

            self._tools.register(web_search_tool)
        if self._config.enable_web_fetch:
            from app.analysis.react.tools import web_fetch_tool

            self._tools.register(web_fetch_tool)
        if self._config.enable_akshare_query:
            from app.analysis.react.tools import akshare_query_tool

            self._tools.register(akshare_query_tool)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        tagged_outputs: Sequence[TaggedOutput],
    ) -> tuple[list[InformationChain], AnalysisResponse]:
        """
        Run the full ReAct analysis pipeline.

        Parameters
        ----------
        tagged_outputs
            Tagged outputs to process.

        Returns
        -------
        tuple[list[InformationChain], AnalysisResponse]
            (chains, analysis_response)
        """
        if not tagged_outputs:
            return ([], _empty_analysis_response(self._config))

        # 1. Build candidate chains (reuse existing deterministic builder)
        chains = generate_candidate_chains(tagged_outputs)
        if not chains:
            return ([], _empty_analysis_response(self._config))

        # 2. Group chains via LLM
        groups = self._group_tagged_outputs(chains, tagged_outputs)

        # 3. Run ReAct sessions per group
        results: list[ChainAnalysisResult] = []
        for group in groups[: self._config.max_groups]:
            session = self._run_react_session(group)
            result = self._finalize_session(session)
            results.append(result)

        # 4. Cross-group ranking
        analysis_response = self._rank_groups(results)

        return (chains, analysis_response)

    # ------------------------------------------------------------------
    # Phase 1: Grouping
    # ------------------------------------------------------------------

    def _group_tagged_outputs(
        self,
        chains: list[InformationChain],
        tagged_outputs: Sequence[TaggedOutput],
    ) -> list[dict[str, Any]]:
        """
        Call the LLM to determine optimal grouping of tagged outputs into
        analysis groups.

        Returns a list of group dicts, each with keys:
        ``group_id``, ``theme``, ``member_chain_ids``, ``rationale``.
        """
        if self._dry_run:
            return self._dry_run_grouper(chains)

        grouper_context = GrouperContext(
            chains=tuple(chains),
            tagged_outputs=tuple(tagged_outputs),
        )
        render_context = build_grouper_prompt_context(
            grouper_context,
            profile_name=self._config.profile_name,
            profile_version=self._config.profile_version,
        )

        prompt_profile = PromptProfile(
            profile_name=self._config.profile_name,
            task_type=PromptTaskType.GROUPER,
            version=self._config.profile_version,
        )
        analysis_input = AnalysisInput(
            chains=tuple(chains[:0]),  # chains are in extra context
            evidence_bundles=tuple(),
            prompt_profile=prompt_profile,
            extra_context=render_context,
        )

        raw = self._call_llm_raw(analysis_input)
        groups: list[dict[str, Any]] = raw.get("groups", [])
        return groups

    @staticmethod
    def _dry_run_grouper(chains: list[InformationChain]) -> list[dict[str, Any]]:
        """Deterministic dummy grouping for dry_run mode."""
        all_ids = [ch.chain_id for ch in chains]
        return [
            {
                "group_id": "g1",
                "theme": "dry-run-theme",
                "member_chain_ids": all_ids,
                "rationale": "Dry-run grouper: all chains in one group.",
            }
        ]

    # ------------------------------------------------------------------
    # Phase 2: ReAct loop per group
    # ------------------------------------------------------------------

    def _run_react_session(self, group: dict[str, Any]) -> ReActSession:
        """
        Run the ReAct iterative loop for a single group.

        The loop: LLM decision → parse → execute tool → observation → repeat,
        until ``is_complete`` or ``max_steps`` is reached.
        """
        group_id = group.get("group_id", "unknown")
        theme = group.get("theme", "unknown")
        member_ids: list[str] = group.get("member_chain_ids", [])

        session = ReActSession(
            group_id=group_id,
            group_context=group,
            max_steps=self._config.max_steps_per_group,
        )

        if self._dry_run:
            return self._dry_run_react_session(session, group)

        # Build ReActContext from group data
        react_context = self._build_react_context(group_id, theme, member_ids)

        available_tools = self._tools.to_schema_dicts()

        while not session.is_finished:
            step_index = session.current_step_count

            # Build prompt context with history
            render_context = build_react_step_prompt_context(
                react_context,
                react_history_json=session.to_history_json(),
                profile_name=self._config.profile_name,
                profile_version=self._config.profile_version,
            )

            prompt_profile = PromptProfile(
                profile_name=self._config.profile_name,
                task_type=PromptTaskType.REACT_STEP,
                version=self._config.profile_version,
            )
            analysis_input = AnalysisInput(
                chains=tuple(),
                evidence_bundles=tuple(),
                prompt_profile=prompt_profile,
                extra_context=render_context,
            )

            # Call LLM
            raw = self._call_llm_raw(analysis_input)
            thought = str(raw.get("thought", ""))
            action: dict[str, Any] | None = raw.get("action")
            is_complete = bool(raw.get("is_complete", False))

            # Execute tool if an action was requested
            observation: str | None = None
            if action and not is_complete:
                tool_name = action.get("tool", "")
                tool_params = action.get("params", {})
                observation = self._execute_tool(tool_name, tool_params)

            step = ReActStep(
                step_index=step_index,
                thought=thought,
                action=action,
                observation=observation,
                is_complete=is_complete,
            )
            session.add_step(step)

        return session

    def _build_react_context(
        self,
        group_id: str,
        theme: str,
        member_chain_ids: list[str],
    ) -> ReActContext:
        """Build a ReActContext from group metadata.

        The member chains are looked up from the chains built during
        ``generate_candidate_chains``.  Since we may not have the full chain
        list at this point, we store the chain IDs and let the prompt context
        builder construct a minimal representation.

        Note: this is a simplified constructor; in a fully integrated pipeline
        the engine would retain the chain map from the grouper step.
        """
        # Chains are captured via the group_context dict; ReActContext stores
        # empty tuple as placeholder — the actual chain data is served from
        # the group_json built in build_react_step_prompt_context.
        return ReActContext(
            group_id=group_id,
            theme=theme,
            member_chains=tuple(),  # chains embedded in group_json
            available_tools=self._tools.to_schema_dicts(),
        )

    @staticmethod
    def _dry_run_react_session(
        session: ReActSession,
        group: dict[str, Any],
    ) -> ReActSession:
        """Deterministic dummy ReAct session for dry_run mode."""
        step = ReActStep(
            step_index=0,
            thought=(
                f"Dry-run ReAct thought for group {session.group_id}: "
                f"theme={group.get('theme', 'unknown')}. "
                "No LLM call was made."
            ),
            action=None,
            observation=None,
            is_complete=True,
        )
        session.add_step(step)
        return session

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def _execute_tool(self, tool_name: str, params: dict[str, Any]) -> str:
        """
        Execute a tool by name and return the observation string.

        Parameters
        ----------
        tool_name
            Name of the tool to execute (e.g. ``"web_search"``).
        params
            Tool parameter dict.

        Returns
        -------
        str
            Observation string from tool execution.
        """
        try:
            return self._tools.execute(tool_name, params)
        except ValueError as exc:
            return f"Tool execution error: {exc}"

    # ------------------------------------------------------------------
    # Phase 3: Finalize
    # ------------------------------------------------------------------

    def _finalize_session(self, session: ReActSession) -> ChainAnalysisResult:
        """
        Synthesise a completed ReAct session into a structured
        ``ChainAnalysisResult``.

        Calls the LLM with the react_finalize template to obtain a proper
        summary and confidence score; falls back to a heuristic synthesis
        when dry_run is active.
        """
        if self._dry_run:
            return self._dry_run_finalize(session)

        render_context = build_react_finalize_prompt_context(
            react_history_json=session.to_history_json(),
            profile_name=self._config.profile_name,
            profile_version=self._config.profile_version,
        )

        prompt_profile = PromptProfile(
            profile_name=self._config.profile_name,
            task_type=PromptTaskType.REACT_FINALIZE,
            version=self._config.profile_version,
        )
        analysis_input = AnalysisInput(
            chains=tuple(),
            evidence_bundles=tuple(),
            prompt_profile=prompt_profile,
            extra_context=render_context,
        )

        try:
            raw = self._call_llm_raw(analysis_input)
            chain_results = _normalise_chain_results(raw.get("chain_results", []))
            if chain_results:
                entry = chain_results[0]
                confidence = float(
                    entry.get("confidence")
                    or entry.get("relevance_score")
                    or entry.get("relevance_to_theme")
                    or entry.get("score", 0.5)
                )
                summary = (
                    entry.get("summary")
                    or entry.get("description")
                    or ""
                )
                completion_notes = (
                    entry.get("completion_notes")
                    or entry.get("evidence")
                    or entry.get("analysis")
                    or ""
                )
                return ChainAnalysisResult(
                    chain_id=session.group_id,
                    summary=summary,
                    completion_notes=completion_notes,
                    key_entities=tuple(entry.get("key_entities", [])),
                    confidence=confidence,
                    prompt_profile=prompt_profile,
                )
        except Exception:
            pass

        # Fallback: synthesize from session steps without LLM
        return _synthesize_result_from_session(session, prompt_profile)

    @staticmethod
    def _dry_run_finalize(session: ReActSession) -> ChainAnalysisResult:
        """Deterministic dummy finalize for dry_run mode."""
        profile = PromptProfile(
            profile_name="default",
            task_type=PromptTaskType.REACT_FINALIZE,
            version="1.0.0",
        )
        return ChainAnalysisResult(
            chain_id=session.group_id,
            summary=f"Dry-run summary for group {session.group_id}: "
            f"{session.current_step_count} step(s).",
            completion_notes="Dry-run completion notes.",
            key_entities=("dry-run-entity-1", "dry-run-entity-2"),
            confidence=0.7,
            prompt_profile=profile,
        )

    # ------------------------------------------------------------------
    # Phase 4: Cross-group ranking
    # ------------------------------------------------------------------

    def _rank_groups(
        self,
        results: list[ChainAnalysisResult],
    ) -> AnalysisResponse:
        """
        Rank analysed groups by investment relevance (confidence descending),
        producing an ``AnalysisResponse``.
        """
        if not results:
            return _empty_analysis_response(self._config)

        sorted_results = sorted(
            results, key=lambda r: r.confidence, reverse=True
        )
        ranking_entries = tuple(
            ChainRankingEntry(
                chain_id=r.chain_id,
                rank=idx + 1,
                score=r.confidence,
                rationale=f"ReAct ranking by confidence: {r.confidence:.2f}",
            )
            for idx, r in enumerate(sorted_results)
        )

        ranking_profile = PromptProfile(
            profile_name=self._config.profile_name,
            task_type=PromptTaskType.INVESTMENT_RANKING,
            version=self._config.profile_version,
        )
        ranking = RankingOutput(
            entries=ranking_entries,
            prompt_profile=ranking_profile,
        )

        provider_info = ModelProviderInfo(
            provider="react-engine",
            model_id="react",
            model_version="1.0",
            endpoint="",
        )

        return AnalysisResponse(
            chain_results=tuple(results),
            ranking=ranking,
            provider_info=provider_info,
        )

    # ------------------------------------------------------------------
    # Raw LLM call (duck-types into adapter internals)
    # ------------------------------------------------------------------

    def _call_llm_raw(self, analysis_input: AnalysisInput) -> dict[str, Any]:
        """
        Call the LLM via the adapter's internal pipeline and return the
        raw JSON content dict.

        Uses duck-typing to access ``_render_messages``, ``_build_payload``,
        ``_post``, and ``_read_token`` (or ``_read_api_key``) on the adapter.
        Raises ``RuntimeError`` when the adapter does not expose the expected
        internal methods.
        """
        if self._dry_run:
            return {}

        # 1. Render messages
        if not hasattr(self._adapter, "_render_messages"):
            raise RuntimeError("Adapter does not expose _render_messages.")
        messages = self._adapter._render_messages(analysis_input)  # type: ignore[reportUnknownMemberType]

        # 2. Build payload
        if not hasattr(self._adapter, "_build_payload"):
            raise RuntimeError("Adapter does not expose _build_payload.")
        payload = self._adapter._build_payload(messages)  # type: ignore[reportUnknownMemberType]

        # 3. Read auth token / api key
        token: str
        if hasattr(self._adapter, "_read_token"):
            token = self._adapter._read_token()  # type: ignore[reportUnknownMemberType]
        elif hasattr(self._adapter, "_read_api_key"):
            token = self._adapter._read_api_key()  # type: ignore[reportUnknownMemberType]
        else:
            raise RuntimeError("Adapter does not expose _read_token or _read_api_key.")

        # 4. POST to API
        if not hasattr(self._adapter, "_post"):
            raise RuntimeError("Adapter does not expose _post.")
        raw: dict = self._adapter._post(payload, token)  # type: ignore[reportUnknownMemberType]

        # 5. Extract content JSON
        choices = raw.get("choices") or []
        if not choices:
            raise RuntimeError("LLM response contained no choices.")
        content_str: str = choices[0]["message"]["content"] or ""
        if not content_str.strip():
            raise RuntimeError(
                f"LLM response content was empty. "
                f"Finish reason: {choices[0].get('finish_reason', 'unknown')}. "
                f"Model: {raw.get('model', 'unknown')}."
            )
        content_str = _strip_code_fences(content_str)
        try:
            return json.loads(content_str)
        except json.JSONDecodeError:
            snippet = content_str[:300].replace("\n", " ")
            raise RuntimeError(
                f"LLM response content is not valid JSON. "
                f"Snippet: {snippet!r}"
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_analysis_response(
    config: ReActEngineConfig,
) -> AnalysisResponse:
    """Return an empty but valid ``AnalysisResponse``."""
    empty_profile = PromptProfile(
        profile_name=config.profile_name,
        task_type=PromptTaskType.SUMMARY,
        version=config.profile_version,
    )
    return AnalysisResponse(
        chain_results=(),
        ranking=RankingOutput(
            entries=(),
            prompt_profile=empty_profile,
        ),
        provider_info=ModelProviderInfo(
            provider="react-engine",
            model_id="react",
            model_version="1.0",
            endpoint="",
        ),
    )


def _synthesize_result_from_session(
    session: ReActSession,
    prompt_profile: PromptProfile,
) -> ChainAnalysisResult:
    """Fallback: build a ``ChainAnalysisResult`` by concatenating step thoughts."""
    thoughts = [step.thought for step in session.steps if step.thought]
    combined = "\n\n".join(thoughts) if thoughts else "No analysis produced."
    # Extract mentioned entities via simple heuristic
    key_entities: tuple[str, ...] = tuple()
    return ChainAnalysisResult(
        chain_id=session.group_id,
        summary=combined[:2000],
        completion_notes=f"Synthesised from {session.current_step_count} ReAct step(s).",
        key_entities=key_entities,
        confidence=0.5,
        prompt_profile=prompt_profile,
    )
