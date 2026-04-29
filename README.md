# mm — Daily AI Investment News Pipeline

> **Bootstrap state** — core infrastructure is in place (config, logging, SQLite, CLI entry point).
> Source collection, scheduling, and reporting pipelines are not yet implemented.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Windows 10/11 | PowerShell 5.1+ included |
| [Miniconda or Anaconda](https://docs.conda.io/en/latest/miniconda.html) | `conda` must be on `PATH`, or `CONDA_EXE` set |
| `quant` conda environment | Python 3.11, see below |

### Create the `quant` environment

```powershell
conda create -n quant python=3.11
conda activate quant
pip install pyyaml pytest
```

---

## Configuration

### 1. Copy `.env.example` → `.env`

```powershell
Copy-Item .env.example .env
```

Edit `.env` and fill in your API tokens (never commit `.env`):

```
GITHUB_TOKEN=ghp_...
# AKSHARE_TOKEN=...   # uncomment if required
```

### 2. Review `config.yaml`

`config.yaml` (project root) holds all non-secret settings.  
Key sections:

| Section | Key defaults |
|---|---|
| `sources` | akshare, web, copilot_research all enabled |
| `scheduler` | 08:30 and 14:00 daily runs |
| `storage` | `data/db/mm.db` (SQLite) |
| `logging` | `data/logs/`, level `INFO` |

Override config or env paths via environment variables:

```powershell
$env:MM_CONFIG_PATH = "D:\project\mm\config.yaml"
$env:MM_ENV_PATH    = "D:\project\mm\.env"
```

---

## Running the project

All commands must be run from the **project root** (`D:\project\mm`).

### Option A — PowerShell bootstrap script (recommended)

`scripts\bootstrap.ps1` automatically uses the `quant` conda environment; no manual activation needed.

```powershell
# Validate config and pipeline wiring (no side effects)
.\scripts\bootstrap.ps1 dry-run

# Full pipeline (stub — outputs not yet implemented)
.\scripts\bootstrap.ps1 run

# Collect only
.\scripts\bootstrap.ps1 collect-only

# Analyze only
.\scripts\bootstrap.ps1 analyze-only

# Backfill a specific date
.\scripts\bootstrap.ps1 run --Date 2025-01-15

# Use a named prompt profile
.\scripts\bootstrap.ps1 run --PromptProfile aggressive-v1
```

### Option B — Direct Python (inside `quant` environment)

```powershell
conda activate quant
python -m app.main dry-run
python -m app.main run --date 2025-01-15
```

---

## Running tests

```powershell
conda activate quant
cd D:\project\mm

# All bootstrap tests
pytest tests\ -v

# Config module only
pytest tests\test_config.py -v

# Logger module only
pytest tests\test_logger.py -v

# Storage / SQLite module only
pytest tests\test_storage.py -v
```

Expected: **71 tests, all passing**.

---

## Key files

```
D:\project\mm\
├── .env.example          # Copy to .env, fill in tokens
├── config.yaml           # Business config (safe to commit)
├── app\
│   ├── main.py           # CLI entry point  (python -m app.main)
│   ├── config\           # Config loader + schema
│   ├── logger\           # JSON + console logging
│   └── storage\          # SQLite init (schema.sql, database.py)
├── scripts\
│   └── bootstrap.ps1     # PowerShell launcher (quant env auto-selected)
├── tests\
│   ├── test_config.py
│   ├── test_logger.py
│   └── test_storage.py
└── data\                 # Runtime data (gitignored content)
    ├── db\               # mm.db written here at runtime
    ├── logs\             # Rotating JSON log files
    ├── raw\              # Raw collector output (future)
    └── reports\          # Generated reports (future)
```

---

## What is NOT yet implemented


- LLM analysis prompt


These are tracked in `plan.md` and will be implemented in subsequent subtasks.
