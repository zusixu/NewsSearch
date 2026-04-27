# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

**mm** — Daily AI Investment News Pipeline. A Python project that collects, analyzes, and reports on AI/tech investment news with a focus on A-share market mapping.

**Current state**: Core infrastructure complete; source collection, normalization, entity tagging, information-chain, llm-analysis, a-share-mapping, and reporting-output layers all implemented.

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
- **Business config**: `config.yaml` (safe to commit) — sources, schedule, storage paths, logging, etc.
- **Override paths**: `$env:MM_CONFIG_PATH` and `$env:MM_ENV_PATH`.

---

## High-Level Architecture

### Pipeline flow

```
collect → normalize → entity/theme tagging → information chain building → llm analysis → ranking → reporting
```

### Module structure

| Module | Purpose |
|---|---|
| `app/main.py` | CLI entry point with `run`, `collect-only`, `analyze-only`, `dry-run` modes |
| `app/config/` | Configuration loading and typed schema (`.env` + `config.yaml`) |
| `app/logger/` | JSON + console logging setup |
| `app/storage/` | SQLite database schema and connection helpers |
| `app/collectors/` | Source adapters: `akshare`, `web`, `copilot_research` |
| `app/models/` | Shared models: `RawDocument`, `NewsItem`, `EventDraft` |
| `app/normalize/` | Deduplication (URL/text), time normalization, source credibility scoring |
| `app/entity/` | Theme taxonomy, entity types, rule/model extractors, evidence links |
| `app/chains/` | Information chain building — same-topic grouping, temporal ordering, upstream/downstream |
| `app/analysis/` | LLM adapter (GitHub Models), prompt profile rendering, analysis engine |
| `app/mapping/` | A-share mapping engine, industry chain mapping, scoring, evidence links, report generation |
| `app/reports/` | Daily report generation — Markdown + JSON output, archive management |
| `app/scheduler/` | Daily scheduler — batch detection, retry policy, pipeline orchestration |
| `app/qa/` | Quality assurance — error tracking, run log reporting |

### Key data flow contracts

```
RawDocument (collectors)
  → NewsItem (normalized)
    → EventDraft + TaggedOutput (entity/theme)
      → InformationChain (chains)
        → LLM analysis → ChainScores → Top 10 → Report (reports)
          → DailyScheduler (scheduler) + ErrorTracker (qa)
```

---

## Development Workflow

### dev/ task structure

The `dev/` directory contains subdirectories for each major feature, each with:
- `*-plan.md` — Task goals, approach, boundaries
- `*-context.md` — Key files, dependencies, decisions
- `*-task.md` — Checklist for execution status

Always check/update these when working on a feature.

### Current completion status

| Phase | Status |
|---|---|
| project-bootstrap | ✅ Complete |
| source-collection | ✅ Complete |
| normalization-pipeline | ✅ Complete |
| entity-theme-tagging | ✅ Complete |
| information-chain | ✅ Complete |
| llm-analysis | ✅ Complete |
| a-share-mapping | ✅ Complete |
| reporting-output | ✅ Complete |
| scheduler-automation | ✅ Complete |
| qa-observability | ✅ Complete |

---

## Key Conventions

- **Environment**: Use the `quant` conda environment for all runs.
- **Timestamps**: Use ISO-8601 UTC strings for all timestamps in storage.
- **Database**: SQLite at `data/db/mm.db` — foreign keys enabled.
- **Prompt profiles**: Stored in `app/analysis/prompts/` — configurable and swappable.
- **Testing**: pytest is used; write tests for new modules.
- **dev/ docs**: Update task docs immediately as work progresses.

---

## What to Read First

- `README.md` — Getting started and basic commands
- `plan.md` — Overall project plan and roadmap
- `config.yaml` — Business configuration
- `app/storage/schema.sql` — Database schema
