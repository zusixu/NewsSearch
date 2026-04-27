<#
.SYNOPSIS
    Run the daily AI investment news pipeline.

.DESCRIPTION
    Runs the pipeline with batch detection (pre-market / midday) and automatic
    retry.  Designed to be called by Windows Task Scheduler or manually.

    The script auto-detects the current batch:
      - Before 12:00 local time  → pre-market (batch_index 0)
      - At or after 12:00        → midday     (batch_index 1)

    A target date can be specified for backfill runs.

.PARAMETER Mode
    Pipeline mode: run | collect-only | analyze-only | dry-run
    Default: run

.PARAMETER Date
    Target date in YYYY-MM-DD format for backfill runs.

.PARAMETER PromptProfile
    Named prompt profile override.

.PARAMETER MaxRetries
    Maximum number of retry attempts on failure. Default: 2

.PARAMETER RetryDelay
    Base delay in seconds between retries. Default: 60

.EXAMPLE
    .\scripts\run_daily.ps1
    .\scripts\run_daily.ps1 -Mode collect-only
    .\scripts\run_daily.ps1 -Date 2025-01-15
    .\scripts\run_daily.ps1 -MaxRetries 3 -RetryDelay 30

.NOTES
    Requires:
      - conda installed and available on PATH (or CONDA_EXE set)
      - A conda environment named 'quant' with all project dependencies
      - Run from the project root directory
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet('run', 'collect-only', 'analyze-only', 'dry-run')]
    [string] $Mode = 'run',

    [Parameter()]
    [string] $Date,

    [Parameter()]
    [string] $PromptProfile,

    [Parameter()]
    [int] $MaxRetries = 2,

    [Parameter()]
    [int] $RetryDelay = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Locate conda
# ---------------------------------------------------------------------------

function Find-Conda {
    if ($env:CONDA_EXE -and (Test-Path $env:CONDA_EXE)) {
        return $env:CONDA_EXE
    }
    $condaOnPath = Get-Command conda -ErrorAction SilentlyContinue
    if ($condaOnPath) {
        return $condaOnPath.Source
    }
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
    Write-Error "[run_daily] ERROR: conda not found."
    exit 1
}

# ---------------------------------------------------------------------------
# Verify 'quant' environment
# ---------------------------------------------------------------------------

$envList = & $condaExe env list 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "[run_daily] ERROR: 'conda env list' failed."
    exit 1
}

$quantExists = $envList | Where-Object { $_ -match '(^|\s)quant(\s|$)' }
if (-not $quantExists) {
    Write-Error "[run_daily] ERROR: conda environment 'quant' not found."
    exit 1
}

# ---------------------------------------------------------------------------
# Determine batch
# ---------------------------------------------------------------------------

$now = Get-Date
$hour = $now.Hour
if ($hour -lt 12) {
    $batchName = "pre-market"
    $batchIndex = 0
} else {
    $batchName = "midday"
    $batchIndex = 1
}

$timestamp = $now.ToString("yyyy-MM-dd HH:mm:ss")
Write-Host "[run_daily] ============================================"
Write-Host "[run_daily] Daily AI Investment Pipeline"
Write-Host "[run_daily] Time       : $timestamp"
Write-Host "[run_daily] Batch      : $batchName (index $batchIndex)"
Write-Host "[run_daily] Mode       : $Mode"
if ($Date)          { Write-Host "[run_daily] Date       : $Date" }
if ($PromptProfile) { Write-Host "[run_daily] Profile    : $PromptProfile" }
Write-Host "[run_daily] MaxRetries : $MaxRetries"
Write-Host "[run_daily] RetryDelay : ${RetryDelay}s"
Write-Host "[run_daily] ============================================"

# ---------------------------------------------------------------------------
# Resolve project root
# ---------------------------------------------------------------------------

$projectRoot = Split-Path -Parent $PSScriptRoot

# ---------------------------------------------------------------------------
# Build argument list
# ---------------------------------------------------------------------------

$appArgs = @($Mode)
if ($Date) {
    $appArgs += '--date', $Date
}
if ($PromptProfile) {
    $appArgs += '--prompt-profile', $PromptProfile
}

# ---------------------------------------------------------------------------
# Run with retry
# ---------------------------------------------------------------------------

$attempt = 0
$exitCode = 1

while ($attempt -le $MaxRetries) {
    if ($attempt -gt 0) {
        $delay = $RetryDelay * [Math]::Pow(2, $attempt - 1)
        Write-Host "[run_daily] Retry $attempt/${MaxRetries} after ${delay}s..."
        Start-Sleep -Seconds $delay
    }

    Write-Host "[run_daily] Running pipeline (attempt $([Math]::Min($attempt + 1, $MaxRetries + 1)))..."

    & $condaExe run `
        --name quant `
        --no-capture-output `
        --live-stream `
        python -m app.main @appArgs

    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        Write-Host "[run_daily] Pipeline completed successfully."
        break
    }

    Write-Warning "[run_daily] Pipeline exited with code $exitCode (attempt $($attempt + 1))."

    $attempt++
}

if ($exitCode -ne 0) {
    Write-Error "[run_daily] All retry attempts exhausted. Last exit code: $exitCode."
}

exit $exitCode
