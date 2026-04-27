"""
app/main.py — main CLI entry point.

Usage:
    python -m app.main <mode> [options]

Modes:
    run           Full pipeline: collect -> normalize -> analyze -> report
    collect-only  Collect raw data only; skip analysis and reporting
    analyze-only  Run analysis on already-collected data; skip collection
    dry-run       Validate configuration and pipeline wiring; no I/O side effects

Exit codes:
    0  Success
    1  General runtime error
    2  Invalid CLI arguments
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Protocol

from app.config import load_config, AppConfig
from app.config.override import OverrideConfig, load_override, apply_override
from app.analysis import AnalysisEngine, AnalysisEngineConfig
from app.analysis.prompts import PromptProfileLoader, PromptProfileConfig, MissingPromptProfileError
from app.analysis.prompts.profile import merge_prompt_overrides
from app.storage import (
    ChainScoreStore,
    InfoChainStore,
    PromptProfileStore,
    RunLogStore,
    get_db,
)


# ---------------------------------------------------------------------------
# Mode handler protocol — every handler must conform to this signature
# ---------------------------------------------------------------------------

class ModeHandler(Protocol):
    def __call__(self, args: argparse.Namespace, config: AppConfig, profile_config: PromptProfileConfig | None, override: OverrideConfig | None = None) -> int: ...


# ---------------------------------------------------------------------------
# Stub handlers (collect-only remains stub for now)
# ---------------------------------------------------------------------------

def _handle_collect_only(args: argparse.Namespace, config: AppConfig, profile_config: PromptProfileConfig | None, override: OverrideConfig | None = None) -> int:
    print("[collect-only] Collection-only run (stub).")
    print(f"  → config   : loaded successfully")
    if override and override != OverrideConfig():
        print(f"  → override : active (search_keywords={len(override.search_keywords)}, "
              f"akshare_providers={override.sources.akshare_providers or 'all'}, "
              f"web_sources={len(override.sources.web_sources)})")
    print("  → collect  : not yet implemented")
    return 0


def _handle_run(args: argparse.Namespace, config: AppConfig, profile_config: PromptProfileConfig | None, override: OverrideConfig | None = None) -> int:
    print("[run] Full pipeline starting (stub - only analysis portion implemented).")
    print(f"  → config   : loaded successfully")
    print(f"  → profile  : {profile_config.profile_name if profile_config else 'default'} (version: {profile_config.version if profile_config else 'N/A'})")
    if override and override != OverrideConfig():
        print(f"  → override : active (search_keywords={len(override.search_keywords)}, "
              f"akshare_providers={override.sources.akshare_providers or 'all'}, "
              f"web_sources={len(override.sources.web_sources)})")
    print("  → collect  : not yet implemented")
    print("  → normalize: not yet implemented")
    print("  → analyze  : will run dummy analysis")
    print("  → report   : not yet implemented")

    # Run analysis portion
    if profile_config:
        search_keywords = override.search_keywords if override else []
        _run_analysis_portion(config, profile_config, dry_run=False, search_keywords=search_keywords)
    return 0


def _handle_analyze_only(args: argparse.Namespace, config: AppConfig, profile_config: PromptProfileConfig | None, override: OverrideConfig | None = None) -> int:
    print("[analyze-only] Analysis-only run.")
    print(f"  → config   : loaded successfully")
    print(f"  → profile  : {profile_config.profile_name if profile_config else 'default'} (version: {profile_config.version if profile_config else 'N/A'})")

    if profile_config:
        search_keywords = override.search_keywords if override else []
        _run_analysis_portion(config, profile_config, dry_run=False, search_keywords=search_keywords)
    else:
        print("[error] No prompt profile config available")
        return 1
    return 0


def _handle_dry_run(args: argparse.Namespace, config: AppConfig, profile_config: PromptProfileConfig | None, override: OverrideConfig | None = None) -> int:
    print("[dry-run] Configuration and pipeline wiring check.")
    print("  → config   : loaded successfully")
    print(f"  → prompt   : default_profile={config.prompt.default_profile!r}")
    print(f"  → prompt   : profiles_dir={config.prompt.profiles_dir!r}")
    print(f"  → prompt   : templates_dir={config.prompt.templates_dir!r}")
    adapter_type = "openai_compatible" if config.llm.endpoint else "github_models"
    print(f"  → llm      : adapter={adapter_type}")
    print(f"  → llm      : model_id={config.llm.model_id!r}")
    if config.llm.endpoint:
        print(f"  → llm      : endpoint={config.llm.endpoint!r}")
    has_key = bool(config.llm_api_key)
    print(f"  → llm      : api_key={'set' if has_key else 'MISSING'}")
    print(f"  → sources  : date_filter_days={config.sources.date_filter_days}")

    # Show override info
    if override and override != OverrideConfig():
        print(f"  → override : active")
        if override.search_keywords:
            print(f"  → override : search_keywords={override.search_keywords}")
        if override.sources.akshare_providers:
            print(f"  → override : akshare_providers={override.sources.akshare_providers}")
        if override.sources.web_sources:
            print(f"  → override : web_sources={len(override.sources.web_sources)} source(s)")
            for ws in override.sources.web_sources:
                print(f"    - {ws.provider}: {ws.url} ({ws.type})")
        if override.prompt_profile:
            print(f"  → override : prompt_profile={override.prompt_profile!r}")
        if override.prompt_overrides.system_message_suffix:
            print(f"  → override : global system_message_suffix set")
        if override.prompt_overrides.tasks:
            print(f"  → override : per-task prompt overrides: {list(override.prompt_overrides.tasks.keys())}")
    else:
        print(f"  → override : none")

    if profile_config:
        print(f"  → profile  : {profile_config.profile_name!r} (version: {profile_config.version!r})")
        print(f"  → profile  : description={profile_config.description!r}")
        for task_type, mapping in profile_config.tasks.items():
            print(f"  → profile  : {task_type.value} → template={mapping.template!r}")

    # List available profiles
    try:
        profiles_dir = Path(config.prompt.profiles_dir)
        loader = PromptProfileLoader(profiles_dir)
        available = loader.list_profiles()
        if available:
            print(f"  → profiles : available={available!r}")
        else:
            print(f"  → profiles : no profiles found in {profiles_dir}")
    except Exception as e:
        print(f"  → profiles : failed to list profiles: {e}")

    # Run a dummy analysis to verify the engine works
    if profile_config:
        print("\n[dry-run] Testing analysis engine...")
        search_keywords = override.search_keywords if override else []
        _run_analysis_portion(config, profile_config, dry_run=True, search_keywords=search_keywords)

    print("\n[dry-run] Complete - no data written to persistent storage.")
    return 0


# ---------------------------------------------------------------------------
# Analysis runner — shared between modes
# ---------------------------------------------------------------------------

def _run_analysis_portion(
    config: AppConfig,
    profile_config: PromptProfileConfig,
    dry_run: bool = True,
    search_keywords: list[str] | None = None,
) -> None:
    """
    Run the analysis portion of the pipeline.

    This function uses dummy/test data for now, but demonstrates the full flow.
    """
    from app.chains.chain import build_chain
    from app.entity.tagged_output import build_tagged_output
    from app.models.event_draft import EventDraft
    from app.models.news_item import NewsItem
    from app.models.raw_document import RawDocument

    # Build some dummy tagged outputs for testing
    dummy_raw = RawDocument(
        source="test",
        provider="test",
        title="Test News",
        content="Test Content",
        url=None,
        date="2025-01-01",
    )
    dummy_news = NewsItem.from_raw(dummy_raw)
    dummy_event = EventDraft.from_news_item(dummy_news)
    dummy_tagged = build_tagged_output(
        event=dummy_event,
        text="Test Content",
        evidence_links=[],
    )

    # Create analysis engine
    engine_config = AnalysisEngineConfig(
        github_token=config.github_token,
        model_id=config.llm.model_id,
        templates_dir=config.prompt.templates_dir,
        profiles_dir=config.prompt.profiles_dir,
        default_profile_name=config.prompt.default_profile,
        llm_endpoint=config.llm.endpoint,
        llm_api_key=config.llm_api_key,
        llm_api_key_env_var=config.llm.api_key_env_var,
    )
    engine = AnalysisEngine(engine_config, dry_run=dry_run, search_keywords=search_keywords, profile_config=profile_config)

    print(f"  → engine   : created (dry-run={dry_run})")

    # Run analysis
    chains, response, used_profile = engine.run_full_analysis(
        [dummy_tagged],
        profile_name=profile_config.profile_name,
    )

    print(f"  → chains   : built {len(chains)} chains")
    print(f"  → analysis : complete, got {len(response.chain_results)} chain results")

    # Print summary of results
    if response.chain_results:
        print(f"  → results  :")
        for result in response.chain_results[:3]:  # Show first 3
            print(f"    chain {result.chain_id[:8]}...: confidence={result.confidence:.2f}")

    if response.ranking.entries:
        print(f"  → top 3    :")
        for entry in response.ranking.entries[:3]:
            print(f"    rank {entry.rank}: chain {entry.chain_id[:8]}... (score={entry.score:.2f})")

    # Persist to database if not dry-run
    if not dry_run:
        try:
            conn = get_db(config.storage.db_path)

            # Archive prompt profile
            profile_store = PromptProfileStore(conn, templates_dir=config.prompt.templates_dir)
            profile_id = profile_store.archive_profile(profile_config, config.prompt.templates_dir)
            print(f"  → profile  : archived (id={profile_id})")

            # Start a run log
            run_store = RunLogStore(conn)
            run_id = run_store.start_run(
                prompt_profile_name=profile_config.profile_name,
                prompt_profile_version=profile_config.version,
                prompt_profile_desc=profile_config.description,
            )
            print(f"  → run      : started (id={run_id})")

            # Store chains and scores (dummy mapping for now)
            chain_store = InfoChainStore(conn)
            score_store = ChainScoreStore(conn)
            chain_db_ids = {}
            for chain in chains:
                db_id = chain_store.insert_chain(
                    run_id=run_id,
                    title=f"Chain {chain.chain_id[:8]}",
                    summary=f"Summary for {chain.chain_id}",
                    chain_type="unknown",
                )
                chain_db_ids[chain.chain_id] = db_id

            score_ids = score_store.insert_from_analysis_response(
                response,
                chain_db_ids,
                run_id=run_id,
            )
            print(f"  → scores   : stored {len(score_ids)} scores")

            # Finish run log
            run_store.finish_run(run_id, success=True)
            print(f"  → run      : finished successfully")

        except Exception as e:
            print(f"  → storage  : failed to persist - {e}", file=sys.stderr)
    else:
        print(f"  → storage  : skipped (dry-run)")


# ---------------------------------------------------------------------------
# Mode dispatch table
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, ModeHandler] = {
    "run": _handle_run,
    "collect-only": _handle_collect_only,
    "analyze-only": _handle_analyze_only,
    "dry-run": _handle_dry_run,
}


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.main",
        description="Daily AI investment news pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "modes:",
            "  run            Full pipeline (collect -> analyze -> report)",
            "  collect-only   Collect raw data only",
            "  analyze-only   Analyze previously collected data",
            "  dry-run        Validate config/wiring, no side effects",
        ]),
    )
    parser.add_argument(
        "mode",
        choices=list(_HANDLERS),
        metavar="mode",
        help="Pipeline mode to execute (run | collect-only | analyze-only | dry-run)",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Target date for backfill runs (default: today)",
    )
    parser.add_argument(
        "--prompt-profile",
        metavar="PROFILE",
        default=None,
        help="Named prompt profile to use for analysis (overrides YAML default)",
    )
    parser.add_argument(
        "--override",
        metavar="PATH",
        default=None,
        help="Path to a YAML override file for customising search keywords, "
             "data sources, and prompts for this run",
    )
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    # argparse exits with code 2 on bad arguments — that matches our contract
    args = parser.parse_args(argv)

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        print(f"[error] Failed to load configuration: {e}", file=sys.stderr)
        return 1

    # Load override configuration (if provided)
    try:
        override = load_override(args.override)
    except Exception as e:
        print(f"[error] Failed to load override configuration: {e}", file=sys.stderr)
        return 1

    # Merge override into base config
    if override is not None and override != OverrideConfig():
        config = apply_override(config, override)

    # Load prompt profile if needed for this mode
    profile_config: PromptProfileConfig | None = None
    if args.mode in ("run", "analyze-only", "dry-run"):
        # Priority: override YAML > --prompt-profile CLI > config.yaml default
        profile_name = (
            override.prompt_profile
            if override and override.prompt_profile
            else args.prompt_profile or config.prompt.default_profile
        )
        try:
            profiles_dir = Path(config.prompt.profiles_dir)
            loader = PromptProfileLoader(profiles_dir)
            profile_config = loader.load_profile_with_fallback(profile_name, config.prompt.default_profile)
        except MissingPromptProfileError as e:
            print(f"[error] Prompt profile not found: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[error] Failed to load prompt profile: {e}", file=sys.stderr)
            return 1

        # Merge prompt overrides from override file into profile config
        if override and override.prompt_overrides:
            try:
                profile_config = merge_prompt_overrides(profile_config, override.prompt_overrides)
            except Exception as e:
                print(f"[error] Failed to merge prompt overrides: {e}", file=sys.stderr)
                return 1

    handler = _HANDLERS[args.mode]
    return handler(args, config, profile_config, override)


if __name__ == "__main__":
    sys.exit(main())
