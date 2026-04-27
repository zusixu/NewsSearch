<#
.SYNOPSIS
    Bootstrap wrapper — run the mm pipeline inside the 'quant' conda environment.

.DESCRIPTION
    Activates the local conda 'quant' environment and executes `python -m app.main`
    with any arguments forwarded verbatim.  Must be run from the project root
    (D:\project\mm) or any directory where the project root is on PYTHONPATH.

    This script is bootstrap-level only: it does NOT register scheduled tasks,
    implement retries, or perform daily orchestration.  See scripts/register_task.ps1
    (future) for scheduler integration.

.PARAMETER Mode
    Pipeline mode: run | collect-only | analyze-only | dry-run
    Required positional argument forwarded to app.main.

.PARAMETER Date
    Target date for backfill runs in YYYY-MM-DD format.
    Forwarded as --date to app.main.

.PARAMETER PromptProfile
    Named prompt profile override.
    Forwarded as --prompt-profile to app.main.

.EXAMPLE
    .\scripts\bootstrap.ps1 run
    .\scripts\bootstrap.ps1 collect-only --Date 2025-01-15
    .\scripts\bootstrap.ps1 dry-run
    .\scripts\bootstrap.ps1 analyze-only --PromptProfile aggressive-v1

.NOTES
    Requires:
      - conda installed and available on PATH (or CONDA_EXE set)
      - A conda environment named 'quant' with all project dependencies
      - Run from the project root directory (D:\project\mm)
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('run', 'collect-only', 'analyze-only', 'dry-run')]
    [string] $Mode,

    [Parameter()]
    [string] $Date,

    [Parameter()]
    [string] $PromptProfile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Locate conda
# ---------------------------------------------------------------------------

function Find-Conda {
    # 1. Honour explicit CONDA_EXE if set
    if ($env:CONDA_EXE -and (Test-Path $env:CONDA_EXE)) {
        return $env:CONDA_EXE
    }
    # 2. Try conda on PATH
    $condaOnPath = Get-Command conda -ErrorAction SilentlyContinue
    if ($condaOnPath) {
        return $condaOnPath.Source
    }
    # 3. Common Windows install locations
    $candidates = @(
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "C:\miniconda3\Scripts\conda.exe",
        "C:\anaconda3\Scripts\conda.exe",
        "C:\ProgramData\miniconda3\Scripts\conda.exe",
        "C:\ProgramData\anaconda3\Scripts\conda.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

$condaExe = Find-Conda
if (-not $condaExe) {
    Write-Error @"
[bootstrap] ERROR: conda not found.
  Checked: CONDA_EXE env var, PATH, and common install locations.
  Please install Miniconda/Anaconda or set the CONDA_EXE environment variable.
"@
    exit 1
}

Write-Verbose "[bootstrap] Using conda: $condaExe"

# ---------------------------------------------------------------------------
# Verify the 'quant' environment exists
# ---------------------------------------------------------------------------

$envList = & $condaExe env list 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "[bootstrap] ERROR: 'conda env list' failed (exit $LASTEXITCODE). Is conda functional?"
    exit 1
}

$quantExists = $envList | Where-Object { $_ -match '(^|\s)quant(\s|$)' }
if (-not $quantExists) {
    Write-Error @"
[bootstrap] ERROR: conda environment 'quant' not found.
  Run: conda create -n quant python=3.11
  then install project dependencies before using this script.
"@
    exit 1
}

# ---------------------------------------------------------------------------
# Resolve project root (script lives in <root>\scripts\)
# ---------------------------------------------------------------------------

$projectRoot = Split-Path -Parent $PSScriptRoot
Write-Verbose "[bootstrap] Project root: $projectRoot"

# ---------------------------------------------------------------------------
# Build argument list for app.main
# ---------------------------------------------------------------------------

$appArgs = @($Mode)
if ($Date) {
    $appArgs += '--date', $Date
}
if ($PromptProfile) {
    $appArgs += '--prompt-profile', $PromptProfile
}

Write-Host "[bootstrap] Mode       : $Mode"
if ($Date)          { Write-Host "[bootstrap] Date       : $Date" }
if ($PromptProfile) { Write-Host "[bootstrap] Profile    : $PromptProfile" }
Write-Host "[bootstrap] Env        : quant"
Write-Host "[bootstrap] Root       : $projectRoot"
Write-Host ""

# ---------------------------------------------------------------------------
# Run via 'conda run' — no shell activation required, works in non-interactive
# contexts (Task Scheduler, CI, etc.)
# ---------------------------------------------------------------------------

& $condaExe run `
    --name quant `
    --no-capture-output `
    --live-stream `
    python -m app.main @appArgs

$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Error "[bootstrap] Pipeline exited with code $exitCode."
}

exit $exitCode
