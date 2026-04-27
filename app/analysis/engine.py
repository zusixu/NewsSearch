"""
app/analysis/engine.py — analysis orchestration engine.

This module ties together:
  - TaggedOutput -> InformationChain (via existing chain builders)
  - InformationChain -> AnalysisInput
  - AnalysisInput -> AnalysisResponse (via adapter)
  - Persistence of results (via storage layer)
  - Prompt profile management
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.analysis.adapters.contracts import (
    AnalysisAdapter,
    AnalysisInput,
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    PromptProfile,
    PromptTaskType,
)
from app.analysis.adapters.github_models import (
    GitHubModelsAdapter,
    GitHubModelsConfig,
    PromptRenderer,
)
from app.analysis.adapters.openai_compatible import (
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
)
from app.analysis.prompts import FileSystemPromptRenderer, PromptProfileConfig, PromptProfileLoader
from app.chains.chain import InformationChain, build_chain
from app.chains.candidate_generation import generate_candidate_chains
from app.chains.evidence_retention import ChainEvidenceBundle, collect_all_evidence
from app.entity.tagged_output import TaggedOutput


# ---------------------------------------------------------------------------
# DryRunAnalysisAdapter — no LLM calls, deterministic output for dry-run
# ---------------------------------------------------------------------------


class DryRunAnalysisAdapter:
    """
    AnalysisAdapter implementation that doesn't call any LLM.
    Returns deterministic dummy output for dry-run mode.
    """

    def analyse(self, analysis_input: AnalysisInput) -> AnalysisResponse:
        """
        Return a deterministic dummy AnalysisResponse without any LLM calls.
        """
        chain_results = []
        for idx, chain in enumerate(analysis_input.chains):
            chain_results.append(
                ChainAnalysisResult(
                    chain_id=chain.chain_id,
                    summary=f"Dry-run summary for chain {idx}",
                    completion_notes=f"Dry-run completion notes for chain {idx}",
                    key_entities=(f"entity-{idx}-1", f"entity-{idx}-2"),
                    confidence=0.5 + (0.1 * idx) if idx < 5 else 0.9,
                    prompt_profile=analysis_input.prompt_profile,
                )
            )

        # Create ranking entries sorted by confidence descending
        sorted_results = sorted(
            [(idx, r) for idx, r in enumerate(chain_results)],
            key=lambda x: x[1].confidence,
            reverse=True,
        )
        ranking_entries = [
            ChainRankingEntry(
                chain_id=r.chain_id,
                rank=rank,
                score=r.confidence,
                rationale=f"Dry-run rationale for rank {rank}: confidence {r.confidence:.2f}",
            )
            for rank, (_, r) in enumerate(sorted_results, 1)
        ]

        # Reconstruct the prompt profile for ranking
        ranking_prompt_profile = PromptProfile(
            profile_name=analysis_input.prompt_profile.profile_name,
            task_type=PromptTaskType.INVESTMENT_RANKING,
            version=analysis_input.prompt_profile.version,
            description=analysis_input.prompt_profile.description,
        )

        from app.analysis.adapters.contracts import RankingOutput, ModelProviderInfo

        ranking = RankingOutput(
            entries=tuple(ranking_entries),
            prompt_profile=ranking_prompt_profile,
        )

        provider_info = ModelProviderInfo(
            provider="dry-run",
            model_id="dry-run-model",
            model_version="1.0",
            endpoint="",
        )

        return AnalysisResponse(
            chain_results=tuple(chain_results),
            ranking=ranking,
            provider_info=provider_info,
        )


# ---------------------------------------------------------------------------
# AnalysisEngine — orchestrates the full analysis pipeline
# ---------------------------------------------------------------------------


@dataclass
class AnalysisEngineConfig:
    """Configuration for the AnalysisEngine."""

    github_token: str = ""
    model_id: str = "gpt-4o-mini"  # Default to cost-effective model
    templates_dir: str = "app/analysis/prompts/templates"
    profiles_dir: str = "config/prompt_profiles"
    default_profile_name: str = "default"
    # OpenAI-compatible adapter settings
    llm_endpoint: str = ""
    llm_api_key: str = ""
    llm_api_key_env_var: str = "LLM_API_KEY"


class AnalysisEngine:
    """
    Orchestrates the full analysis pipeline from tagged outputs to structured results.

    Responsibilities:
      - Load prompt profiles
      - Build information chains from tagged outputs
      - Prepare analysis input
      - Call the analysis adapter (LLM)
      - Coordinate persistence (delegated to storage layer)
    """

    def __init__(
        self,
        config: AnalysisEngineConfig,
        *,
        dry_run: bool = False,
        search_keywords: list[str] | None = None,
        profile_config: PromptProfileConfig | None = None,
    ) -> None:
        """
        Initialize the analysis engine.

        Parameters
        ----------
        config
            Engine configuration including GitHub token and model settings.
        dry_run
            If True, use DryRunAnalysisAdapter instead of GitHub Models.
        search_keywords
            Optional search keywords to include in prompt render context.
        profile_config
            Optional prompt profile config for the renderer (enables override support).
        """
        self._config = config
        self._dry_run = dry_run

        # Load prompt profile loader
        self._profile_loader = PromptProfileLoader(Path(config.profiles_dir))

        # Create renderer with profile config for override support
        self._renderer = FileSystemPromptRenderer(
            Path(config.templates_dir),
            profile_config=profile_config,
            search_keywords=search_keywords,
        )

        # Create adapter — prefer OpenAI-compatible when endpoint is configured
        if dry_run:
            self._adapter: AnalysisAdapter = DryRunAnalysisAdapter()
        elif config.llm_endpoint:
            oai_config = OpenAICompatibleConfig(
                model_id=config.model_id,
                endpoint=config.llm_endpoint,
                api_key=config.llm_api_key,
                api_key_env_var=config.llm_api_key_env_var,
            )
            self._adapter = OpenAICompatibleAdapter(oai_config, self._renderer)
        else:
            gh_config = GitHubModelsConfig(
                model_id=config.model_id,
                token_env_var="GITHUB_TOKEN",
            )
            # Inject token into env for the adapter
            import os
            env = dict(os.environ)
            env["GITHUB_TOKEN"] = config.github_token
            self._adapter = GitHubModelsAdapter(gh_config, self._renderer, env=env)

    def load_profile(self, profile_name: str | None = None) -> PromptProfileConfig:
        """
        Load a prompt profile by name (or default).

        Parameters
        ----------
        profile_name
            Name of the profile to load; uses default_profile_name if None.

        Returns
        -------
        PromptProfileConfig
            The loaded profile configuration.
        """
        name = profile_name or self._config.default_profile_name
        return self._profile_loader.load_profile_with_fallback(
            name, self._config.default_profile_name
        )

    def build_chains(
        self,
        tagged_outputs: Sequence[TaggedOutput],
    ) -> list[InformationChain]:
        """
        Build information chains from tagged outputs.

        Parameters
        ----------
        tagged_outputs
            Sequence of TaggedOutput objects to group into chains.

        Returns
        -------
        list[InformationChain]
            List of built information chains.
        """
        return generate_candidate_chains(tagged_outputs)

    def analyse_chains(
        self,
        chains: Sequence[InformationChain],
        profile_config: PromptProfileConfig,
    ) -> AnalysisResponse:
        """
        Analyse a list of information chains and return structured results.

        Parameters
        ----------
        chains
            Information chains to analyse.
        profile_config
            Prompt profile configuration to use.

        Returns
        -------
        AnalysisResponse
            Structured analysis results.
        """
        if not chains:
            # Empty input: return empty valid response
            empty_profile = PromptProfile(
                profile_name=profile_config.profile_name,
                task_type=PromptTaskType.SUMMARY,
                version=profile_config.version,
                description=profile_config.description,
            )
            from app.analysis.adapters.contracts import RankingOutput, ModelProviderInfo

            return AnalysisResponse(
                chain_results=(),
                ranking=RankingOutput(
                    entries=(),
                    prompt_profile=empty_profile,
                ),
                provider_info=ModelProviderInfo(
                    provider="dry-run" if self._dry_run else "github_models",
                    model_id=self._config.model_id,
                    model_version="1.0",
                    endpoint="",
                ),
            )

        # Collect evidence bundles for each chain
        evidence_bundles = collect_all_evidence(chains)

        # Build the prompt profile for analysis (using SUMMARY task type as main)
        prompt_profile = PromptProfile(
            profile_name=profile_config.profile_name,
            task_type=PromptTaskType.SUMMARY,
            version=profile_config.version,
            description=profile_config.description,
        )

        # Build analysis input
        analysis_input = AnalysisInput(
            chains=tuple(chains),
            evidence_bundles=tuple(evidence_bundles),
            prompt_profile=prompt_profile,
        )

        # Update renderer with profile if needed
        if hasattr(self._renderer, "use_profile"):
            self._renderer.use_profile(profile_config)

        # Run analysis
        return self._adapter.analyse(analysis_input)

    def run_full_analysis(
        self,
        tagged_outputs: Sequence[TaggedOutput],
        profile_name: str | None = None,
    ) -> tuple[list[InformationChain], AnalysisResponse, PromptProfileConfig]:
        """
        Run the full analysis pipeline: build chains, analyse, return everything.

        Parameters
        ----------
        tagged_outputs
            Tagged outputs to process.
        profile_name
            Optional prompt profile name to use (overrides default).

        Returns
        -------
        tuple[list[InformationChain], AnalysisResponse, PromptProfileConfig]
            (chains, analysis_response, profile_config)
        """
        profile_config = self.load_profile(profile_name)
        chains = self.build_chains(tagged_outputs)
        response = self.analyse_chains(chains, profile_config)
        return (chains, response, profile_config)
