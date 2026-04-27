# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

**mm** — Daily AI Investment News Pipeline. A Python project that collects, analyzes, and reports on AI/tech investment news with a focus on A-share market mapping.

**Current state**: All core modules complete. Source collection, normalization, entity tagging, information-chain, LLM analysis (legacy + ReAct), A-share mapping, reporting, scheduling, and QA layers all implemented and tested.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Windows 10/11 | PowerShell 5.1+ |
| Miniconda/Anaconda | `conda` on `PATH` or `CONDA_EXE` set |
| `quant` conda environment | Python 3.11 |

---

## Common Commands

### Running the pipeline

```powershell
# PowerShell bootstrap (recommended — auto-selects quant environment)
.\scripts\bootstrap.ps1 dry-run
.\scripts\bootstrap.ps1 run
.\scripts\bootstrap.ps1 collect-only
.\scripts\bootstrap.ps1 analyze-only
.\scripts\bootstrap.ps1 run --Date 2025-01-15
.\scripts\bootstrap.ps1 run --PromptProfile aggressive-v1
```

```powershell
# Direct Python (inside activated quant environment)
conda activate quant
python -m app.main dry-run
python -m app.main run --date 2025-01-15
python -m app.main run --analysis-mode react
```

### Running tests

```powershell
# All tests
pytest tests\ -v

# Specific modules
pytest tests\test_config.py -v
pytest tests\test_logger.py -v
pytest tests\test_storage.py -v

# Collector tests
pytest tests\test_collector_interface.py -v
pytest tests\test_akshare_collector.py -v
pytest tests\test_web_collector.py -v
pytest tests\test_copilot_research_collector.py -v

# Normalization tests
pytest tests\test_raw_document.py -v
pytest tests\test_news_item.py -v
pytest tests\test_url_dedup.py -v
pytest tests\test_text_dedup.py -v
pytest tests\test_time_norm.py -v
pytest tests\test_source_credibility.py -v

# Entity/theme tagging tests
pytest tests\test_theme_taxonomy.py -v
pytest tests\test_entity_types.py -v
pytest tests\test_rule_extractor.py -v
pytest tests\test_model_extractor.py -v
pytest tests\test_evidence.py -v
pytest tests\test_tagged_output.py -v

# Information-chain tests
pytest tests\test_chain.py -v
pytest tests\test_relation_type.py -v
pytest tests\test_same_topic_grouping.py -v
pytest tests\test_temporal_connection.py -v
pytest tests\test_upstream_downstream.py -v
pytest tests\test_candidate_generation.py -v
pytest tests\test_evidence_retention.py -v

# LLM analysis tests
pytest tests\test_analysis_adapter_contracts.py -v
pytest tests\test_github_models_adapter.py -v
pytest tests\test_filesystem_prompt_renderer.py -v
pytest tests\test_prompt_profile.py -v
pytest tests\test_prompt_version_tracking.py -v
pytest tests\test_analysis_engine.py -v
pytest tests\test_react_tools.py -v
pytest tests\test_react_session.py -v
pytest tests\test_react_engine.py -v

# A-share mapping tests
pytest tests\test_a_share_mapping_schema.py -v
pytest tests\test_industry_chain.py -v
pytest tests\test_mapping_engine.py -v
pytest tests\test_mapping_score.py -v
pytest tests\test_mapping_evidence.py -v
pytest tests\test_mapping_report.py -v

# Reporting tests
pytest tests\test_reports.py -v

# Scheduler & QA tests
pytest tests\test_scheduler.py -v
pytest tests\test_error_tracker.py -v
pytest tests\test_pipeline_integration.py -v
```

---

## Configuration

- **Secrets**: Copy `.env.example` → `.env` and fill in tokens (never commit `.env`).
- **Business config**: `config.yaml` (safe to commit) — sources, schedule, storage paths, logging, analysis mode, etc.
- **Override paths**: `$env:MM_CONFIG_PATH` and `$env:MM_ENV_PATH`.
- **Prompt profiles**: `config/prompt_profiles/default.yaml` — default prompt template mapping.

---

## High-Level Architecture

### Pipeline flow

```
collect → normalize → entity/theme tagging → information chain → llm analysis → a-share mapping → ranking → reporting
```

### LLM analysis dual mode

- **legacy** (default): Single LLM call for analysis + ranking
- **react**: Multi-step ReAct agent — Grouper → per-group ReAct iterations → Finalize → cross-group ranking

Switch via `config.yaml` `analysis.mode` or CLI `--analysis-mode {react,legacy}`

### Module structure

| Module | Purpose | Key Files |
|---|---|---|
| `app/main.py` | CLI entry point (run, collect-only, analyze-only, dry-run) | `main.py` |
| `app/config/` | Configuration loading and typed schema | `loader.py`, `schema.py`, `override.py` |
| `app/logger/` | JSON NDJSON + console logging | `setup.py`, `formatter.py` |
| `app/storage/` | SQLite schema and CRUD stores | `database.py`, `schema.sql` |
| `app/collectors/` | Source adapters (akshare, web, copilot_research) | `base.py`, `akshare_collector.py`, `web_collector.py`, `copilot_research_collector.py`, `web_access_transport.py` |
| `app/models/` | Shared data models | `raw_document.py`, `news_item.py`, `event_draft.py` |
| `app/normalize/` | Dedup, time normalization, source credibility, date filter | `url_dedup.py`, `text_dedup.py`, `time_norm.py`, `source_credibility.py`, `date_filter.py` |
| `app/entity/` | Theme taxonomy, entity types, rule/model extractors | `themes.py`, `entity_types.py`, `rules/extractor.py`, `model_extractor.py` |
| `app/chains/` | Information chain building | `chain.py`, `candidate_generation.py`, `evidence_retention.py` |
| `app/analysis/` | LLM adapters, prompt rendering, analysis engine | `adapters/contracts.py`, `adapters/github_models.py`, `adapters/openai_compatible.py`, `engine.py` |
| `app/analysis/react/` | ReAct multi-step analysis engine | `engine.py`, `tools.py`, `session.py`, `prompts.py` |
| `app/mapping/` | A-share mapping, industry chain, scoring, evidence | `schema.py`, `industry_chain.py`, `engine.py`, `report.py` |
| `app/reports/` | Daily report generation and archive | `core.py` |
| `app/scheduler/` | Daily scheduler with batch detection and retry | `scheduler.py` |
| `app/qa/` | Error tracking and run log reporting | `error_tracker.py` |
| `app/ranking/` | Placeholder (ranking is inlined in analysis engine) | `__init__.py` (empty) |

### Key data flow contracts

```
RawDocument (collectors)
  → NewsItem (normalized)
    → EventDraft + TaggedOutput (entity/theme)
      → InformationChain + ChainEvidenceBundle (chains)
        → LLM analysis → AnalysisResponse + ChainScores
          → AShareMapping + MappingScore (mapping)
            → DailyReport (reports)
              → DailyScheduler (scheduler) + ErrorTracker (qa)
```

---

## Key Conventions

- **Environment**: Use the `quant` conda environment for all runs.
- **Timestamps**: Use ISO-8601 UTC strings for all timestamps in storage.
- **Database**: SQLite at `data/db/mm.db` — foreign keys enabled, all DDL uses `IF NOT EXISTS`.
- **Dataclasses**: All data models use `frozen=True` (immutable) by default; mutable dataclasses are exceptions and must be justified.
- **Prompt profiles**: Stored in `app/analysis/prompts/` — configurable and swappable.
- **Testing**: pytest is used; write tests for new modules. All 53 test files should pass.
- **Logging**: JSON NDJSON + console via `app/logger/`. New modules doing I/O must log key operations.
- **Third-party deps**: Lazy-import at function level for optional packages (akshare, requests, bs4).

---

## Known Issues & Technical Debt

See `rule.md` for development standards. Key items:

1. **`app/mapping/report.py` duplicates `app/reports/core.py`** — mapping version is older and lacks risk_warnings/rationale/source_urls; still re-exported from `mapping/__init__.py`
2. **`app/ranking/` is empty** — ranking logic is inlined in `app/analysis/engine.py`
3. **Relation-type overwrite cascade** in chains pipeline — `generate_candidate_chains` overwrites `SAME_TOPIC`→`TEMPORAL`→`UPSTREAM_DOWNSTREAM`; only the last survives on `ChainNode.relation_to_prev`
4. **ReAct engine duck-typing** — `_call_llm_raw` accesses private adapter methods (`_render_messages`, `_build_payload`, `_post`); fragile across adapter changes
5. **`web_access_transport.py` has no logging** — entire 805-line file doing network I/O with zero log output
6. **Timeliness score hardcoded to 80** in `mapping/engine.py` `ScoreEngine`
7. **`use_profile` dead code** in `analysis/engine.py` — calls nonexistent method on `FileSystemPromptRenderer`
8. **Two ReAct tools are stubs** — `web_search` and `akshare_query` return placeholder data
9. **Storage layering violation** — `app/storage/database.py` imports from `app/analysis/`
10. **`apply_override` incomplete** — parses `search_keywords`, `web_sources`, `prompt_overrides` but does not wire them into `AppConfig`

---

## What to Read First

- `PROJECT_INDEX.md` — Code-level structure index, data flow contracts, module quick-reference
- `rule.md` — Development standards and conventions for contributors
- `config.yaml` — Business configuration
- `app/storage/schema.sql` — Database schema (9 tables)
