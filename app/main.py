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
import datetime
import sys
from pathlib import Path
from typing import Protocol

from app.config import load_config, AppConfig
from app.config.override import OverrideConfig, load_override, apply_override
from app.analysis import AnalysisEngine, AnalysisEngineConfig
from app.analysis.adapters.openai_compatible import OpenAICompatibleAPIError
from app.analysis.prompts import PromptProfileLoader, PromptProfileConfig, MissingPromptProfileError
from app.analysis.prompts.profile import merge_prompt_overrides
from app.storage import (
    ChainScoreStore,
    InfoChainStore,
    PromptProfileStore,
    RunLogStore,
    get_db,
)
from app.reports import (
    DailyReportBuilder,
    ReportArchiveManager,
)
from app.mapping.schema import AStockMapping, AShareMappingScore, AShareMappingWithEvidence
from app.mapping.engine import AShareMappingEngine, MappingScoringEngine, MappingEvidenceCollector
from app.collectors import RunContext, CollectionCache
from app.collectors.akshare_collector import AkShareCollector
from app.collectors.web_collector import WebCollector
from app.collectors.copilot_research_collector import CopilotResearchCollector
from app.collectors.web_access_transport import WebAccessTransport
from app.collectors.raw_document import RawDocument
from app.normalize import (
    deduplicate_by_url,
    deduplicate_by_text,
    normalize_time,
    filter_last_n_days,
    grade_credibility,
)
from app.entity import build_tagged_output
from app.models.news_item import NewsItem
from app.models.event_draft import EventDraft


# ---------------------------------------------------------------------------
# Mode handler protocol — every handler must conform to this signature
# ---------------------------------------------------------------------------

class ModeHandler(Protocol):
    def __call__(self, args: argparse.Namespace, config: AppConfig, profile_config: PromptProfileConfig | None, override: OverrideConfig | None = None) -> int: ...


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------

def _create_collectors(config: AppConfig, override: OverrideConfig | None) -> list:
    """Instantiate enabled collectors based on configuration."""
    cache = CollectionCache(config.storage.raw_dir)
    collectors: list = []

    if config.sources.akshare:
        collectors.append(AkShareCollector(cache=cache))

    if config.sources.web:
        # Default web sources if none configured via override
        web_sources = None
        if override and override.sources.web_sources:
            web_sources = [ws.to_dict() for ws in override.sources.web_sources]
        collectors.append(WebCollector(sources=web_sources, cache=cache))

    if config.sources.copilot_research:
        transport = WebAccessTransport()
        collectors.append(CopilotResearchCollector(transport=transport, cache=cache))

    return collectors


def _run_collection(
    config: AppConfig,
    target_date: datetime.date,
    override: OverrideConfig | None,
    dry_run: bool = False,
) -> list[RawDocument]:
    """Run all enabled collectors and return aggregated RawDocument items."""
    collectors = _create_collectors(config, override)
    if not collectors:
        print("  → collect  : no collectors enabled")
        return []

    ctx = RunContext(
        run_id=f"{target_date.strftime('%Y%m%d')}_manual",
        target_date=target_date,
        is_backfill=False,
        dry_run=dry_run,
        mode="collect_only" if dry_run else "full",
        override=override,
    )

    all_items: list[RawDocument] = []
    total_errors = 0

    for collector in collectors:
        if not collector.is_enabled(config.sources):
            print(f"  → collect  : skipped {collector.source_id} (disabled)")
            continue

        try:
            result = collector.collect(ctx)
            all_items.extend(result.items)
            total_errors += len(result.errors)
            print(f"  → collect  : {collector.source_id} → {len(result.items)} items")
            if result.errors:
                for err in result.errors:
                    print(f"    - error  : {err}")
        except Exception as e:
            print(f"  → collect  : {collector.source_id} failed - {e}", file=sys.stderr)

    print(f"  → collect  : total {len(all_items)} items ({total_errors} errors)")
    return all_items


def _run_normalization(
    raw_items: list[RawDocument],
    date_filter_days: int,
) -> list[NewsItem]:
    """Normalize raw items: convert, dedup, time-normalize, filter, grade."""
    # Convert RawDocument → NewsItem
    news_items = [NewsItem.from_raw(r) for r in raw_items]
    print(f"  → normalize: {len(news_items)} items from raw")

    # URL dedup
    news_items = deduplicate_by_url(news_items)
    print(f"  → normalize: {len(news_items)} items after URL dedup")

    # Text dedup
    news_items = deduplicate_by_text(news_items)
    print(f"  → normalize: {len(news_items)} items after text dedup")

    # Time normalization
    news_items = normalize_time(news_items)
    print(f"  → normalize: time normalized")

    # Date filtering (keep last N days)
    news_items = filter_last_n_days(news_items, n=date_filter_days)
    print(f"  → normalize: {len(news_items)} items after date filter ({date_filter_days} days)")

    # Source credibility grading
    news_items = grade_credibility(news_items)
    print(f"  → normalize: credibility graded")

    return news_items


def _build_tagged_outputs(news_items: list[NewsItem]) -> list:
    """Build TaggedOutput from normalized NewsItem list."""
    from app.entity.evidence import build_evidence_links
    from app.entity.rules import RuleExtractor

    extractor = RuleExtractor()
    tagged_outputs = []

    for item in news_items:
        event = EventDraft.from_news_item(item)
        text = f"{item.title}\n{item.content or ''}"
        hits = extractor.extract(text)
        evidence_links = build_evidence_links(text, hits)
        tagged = build_tagged_output(event=event, text=text, evidence_links=evidence_links)
        tagged_outputs.append(tagged)

    print(f"  → entity   : {len(tagged_outputs)} tagged outputs")
    return tagged_outputs


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------

def _handle_collect_only(args: argparse.Namespace, config: AppConfig, profile_config: PromptProfileConfig | None, override: OverrideConfig | None = None) -> int:
    print("[collect-only] Collection-only run.")
    print(f"  → config   : loaded successfully")
    if override and override != OverrideConfig():
        print(f"  → override : active (search_keywords={len(override.search_keywords)}, "
              f"akshare_providers={override.sources.akshare_providers or 'all'}, "
              f"web_sources={len(override.sources.web_sources)})")

    target_date = datetime.datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.date.today()
    raw_items = _run_collection(config, target_date, override, dry_run=False)
    print(f"[collect-only] Done — {len(raw_items)} items collected.")
    return 0


def _handle_run(args: argparse.Namespace, config: AppConfig, profile_config: PromptProfileConfig | None, override: OverrideConfig | None = None) -> int:
    print("[run] Full pipeline starting.")
    print(f"  → config   : loaded successfully")
    print(f"  → profile  : {profile_config.profile_name if profile_config else 'default'} (version: {profile_config.version if profile_config else 'N/A'})")
    if override and override != OverrideConfig():
        print(f"  → override : active (search_keywords={len(override.search_keywords)}, "
              f"akshare_providers={override.sources.akshare_providers or 'all'}, "
              f"web_sources={len(override.sources.web_sources)})")

    target_date = datetime.datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.date.today()

    # Collection
    raw_items = _run_collection(config, target_date, override, dry_run=False)
    if not raw_items:
        print("[run] No items collected — stopping.")
        return 0

    # Normalization
    news_items = _run_normalization(raw_items, date_filter_days=config.sources.date_filter_days)
    if not news_items:
        print("[run] No items after normalization — stopping.")
        return 0

    # Entity tagging
    tagged_outputs = _build_tagged_outputs(news_items)
    if not tagged_outputs:
        print("[run] No tagged outputs — stopping.")
        return 0

    # Analysis + Report (limit to top 20 tagged outputs to avoid huge LLM requests)
    if profile_config:
        search_keywords = override.search_keywords if override else []
        _run_analysis_portion(
            config,
            profile_config,
            dry_run=False,
            search_keywords=search_keywords,
            report_date=args.date,
            tagged_outputs=tagged_outputs[:20],
            analysis_mode=args.analysis_mode,
        )
    else:
        print("[warn] No prompt profile — analysis skipped.")

    print("[run] Pipeline complete.")
    return 0


def _handle_analyze_only(args: argparse.Namespace, config: AppConfig, profile_config: PromptProfileConfig | None, override: OverrideConfig | None = None) -> int:
    print("[analyze-only] Analysis-only run.")
    print(f"  → config   : loaded successfully")
    print(f"  → profile  : {profile_config.profile_name if profile_config else 'default'} (version: {profile_config.version if profile_config else 'N/A'})")

    if profile_config:
        search_keywords = override.search_keywords if override else []
        _run_analysis_portion(config, profile_config, dry_run=False, search_keywords=search_keywords, report_date=args.date, analysis_mode=args.analysis_mode)
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
        _run_analysis_portion(config, profile_config, dry_run=True, search_keywords=search_keywords, report_date=args.date, analysis_mode=args.analysis_mode)

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
    report_date: str | None = None,
    tagged_outputs: list | None = None,
    analysis_mode: str | None = None,
) -> None:
    """
    Run the analysis portion of the pipeline.

    When ``tagged_outputs`` is provided, uses real data; otherwise falls back
    to a single dummy item for wiring tests.

    ``analysis_mode`` — CLI override for analysis mode ("react" | "legacy").
    When ``None``, uses ``config.analysis.mode`` from config.yaml.
    """
    from app.chains.chain import build_chain
    from app.chains.evidence_retention import ChainEvidenceBundle, collect_all_evidence
    from app.entity.tagged_output import build_tagged_output as _build_tagged_output
    from app.models.event_draft import EventDraft
    from app.models.news_item import NewsItem
    from app.models.raw_document import RawDocument

    if tagged_outputs:
        tagged_inputs = tagged_outputs
    else:
        # Fallback dummy data for dry-run / wiring tests
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
        tagged_inputs = [_build_tagged_output(
            event=dummy_event,
            text="Test Content",
            evidence_links=[],
        )]

    # Determine analysis mode: CLI arg > config.yaml
    resolved_mode = analysis_mode if analysis_mode else config.analysis.mode

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
        llm_response_format=config.llm.response_format,
        llm_timeout=180,
        analysis_mode=resolved_mode,
        react_max_steps_per_group=config.analysis.react_max_steps_per_group,
        react_max_groups=config.analysis.react_max_groups,
        react_enable_web_search=config.analysis.react_enable_web_search,
        react_enable_web_fetch=config.analysis.react_enable_web_fetch,
        react_enable_akshare_query=config.analysis.react_enable_akshare_query,
    )
    engine = AnalysisEngine(engine_config, dry_run=dry_run, search_keywords=search_keywords, profile_config=profile_config)

    print(f"  → engine   : created (dry-run={dry_run}, mode={resolved_mode})")

    # Run analysis
    try:
        chains, response, used_profile = engine.run_full_analysis(
            tagged_inputs,
            profile_name=profile_config.profile_name,
        )
    except TimeoutError as exc:
        print(f"  → analysis : FAILED — LLM API timed out ({exc})", file=sys.stderr)
        print("[run] Analysis timed out — stopping.", file=sys.stderr)
        return
    except (OpenAICompatibleAPIError, Exception) as exc:
        print(f"  → analysis : FAILED — {exc}", file=sys.stderr)
        print("[run] Analysis failed — stopping.", file=sys.stderr)
        return

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

            # Generate report
            report_date = report_date or datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
            report_batch = "pre-market"  # Default batch for manual runs

            # Build A-share mappings using the mapping engine
            mapping_engine = AShareMappingEngine()
            scoring_engine = MappingScoringEngine()
            evidence_collector = MappingEvidenceCollector()

            mappings: dict[str, AStockMapping] = {}
            scores: dict[str, AShareMappingScore] = {}
            with_evidences: dict[str, AShareMappingWithEvidence] = {}

            for chain in chains:
                mapping = mapping_engine.map_information_chain(chain)
                score = scoring_engine.score_mapping(mapping, chain.theme_ids)
                with_evidence = evidence_collector.collect_for_information_chain(chain, mapping)

                mappings[chain.chain_id] = mapping
                scores[chain.chain_id] = score
                with_evidences[chain.chain_id] = with_evidence

            print(f"  → mapping  : generated {len(mappings)} A-share mappings")

            # Collect evidence bundles from chains (needed for react mode source URLs)
            evidence_bundles_list = collect_all_evidence(chains)
            evidence_bundles: dict[str, ChainEvidenceBundle] = {}
            for chain, bundle in zip(chains, evidence_bundles_list):
                evidence_bundles[chain.chain_id] = bundle
            print(f"  → evidence : collected {len(evidence_bundles)} bundles")

            builder = DailyReportBuilder()
            report = builder.build(
                report_date=report_date,
                report_batch=report_batch,
                analysis_response=response,
                mappings=mappings,
                scores=scores,
                with_evidences=with_evidences,
                prompt_profile=used_profile,
                evidence_bundles=evidence_bundles,
            )

            archive = ReportArchiveManager(config.output.reports_dir)
            saved = archive.save_report(
                report,
                save_markdown="markdown" in config.output.formats,
                save_json="json" in config.output.formats,
            )
            for fmt, path in saved.items():
                print(f"  → report   : saved {fmt} → {path}")

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
    parser.add_argument(
        "--analysis-mode",
        choices=["react", "legacy"],
        default=None,
        metavar="MODE",
        help="Analysis mode override (react | legacy); "
             "defaults to config.yaml analysis.mode",
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
