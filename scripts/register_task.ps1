<#
.SYNOPSIS
    Register Windows Task Scheduler tasks for the daily AI investment pipeline.

.DESCRIPTION
    Creates two scheduled tasks that run the pipeline daily:
      1. "mm-pre-market"  — runs at 08:30 local time (before A-share open at 09:30)
      2. "mm-midday"      — runs at 14:00 local time (mid-afternoon update)

    Both tasks execute scripts\run_daily.ps1 with the appropriate parameters.

.PARAMETER Unregister
    Switch to remove previously registered tasks instead of creating them.

.PARAMETER User
    Windows user account to run the task under. Default: current user.

.EXAMPLE
    .\scripts\register_task.ps1
    .\scripts\register_task.ps1 -Unregister
    .\scripts\register_task.ps1 -User "DOMAIN\UserName"

.NOTES
    Must be run as Administrator.
    Task Scheduler tasks survive reboots and run whether or not the user is logged in.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch] $Unregister,

    [Parameter()]
    [string] $User
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Validate Administrator
# ---------------------------------------------------------------------------

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    Write-Error "[register_task] ERROR: This script must be run as Administrator."
    Write-Host "[register_task] Right-click PowerShell and select 'Run as Administrator', then re-run."
    exit 1
}

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

$projectRoot = Split-Path -Parent $PSScriptRoot
$runDailyScript = Join-Path $projectRoot "scripts\run_daily.ps1"

if (-not (Test-Path $runDailyScript)) {
    Write-Error "[register_task] ERROR: run_daily.ps1 not found at $runDailyScript"
    exit 1
}

# Resolve PowerShell executable
$powershellExe = (Get-Command powershell.exe -ErrorAction SilentlyContinue)
if (-not $powershellExe) {
    $powershellExe = (Get-Command pwsh.exe -ErrorAction SilentlyContinue)
}
if (-not $powershellExe) {
    Write-Error "[register_task] ERROR: PowerShell executable not found on PATH."
    exit 1
}
$powershellPath = $powershellExe.Source

# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------

$tasks = @(
    @{
        Name        = "mm-pre-market"
        Description = "Daily AI investment pipeline — pre-market run (08:30)"
        Time        = "08:30"
        Arguments   = "-NoProfile -ExecutionPolicy Bypass -File `"$runDailyScript`" -Mode run"
    },
    @{
        Name        = "mm-midday"
        Description = "Daily AI investment pipeline — midday run (14:00)"
        Time        = "14:00"
        Arguments   = "-NoProfile -ExecutionPolicy Bypass -File `"$runDailyScript`" -Mode run"
    }
)

# ---------------------------------------------------------------------------
# Unregister mode
# ---------------------------------------------------------------------------

if ($Unregister) {
    foreach ($taskDef in $tasks) {
        $existing = Get-ScheduledTask -TaskName $taskDef.Name -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $taskDef.Name -Confirm:$false
            Write-Host "[register_task] Unregistered task: $($taskDef.Name)"
        } else {
            Write-Host "[register_task] Task not found (skipping): $($taskDef.Name)"
        }
    }
    Write-Host "[register_task] Unregistration complete."
    exit 0
}

# ---------------------------------------------------------------------------
# Register mode
# ---------------------------------------------------------------------------

if (-not $User) {
    $User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
}

foreach ($taskDef in $tasks) {
    # Remove existing task if present
    $existing = Get-ScheduledTask -TaskName $taskDef.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskDef.Name -Confirm:$false
        Write-Host "[register_task] Replaced existing task: $($taskDef.Name)"
    }

    # Parse time
    $timeParts = $taskDef.Time.Split(":")
    $hour = [int]$timeParts[0]
    $minute = [int]$timeParts[1]

    # Create trigger — daily at the specified time
    $trigger = New-ScheduledTaskTrigger -Daily -At "$($hour.ToString('00')):$($minute.ToString('00'))"

    # Create action
    $action = New-ScheduledTaskAction `
        -Execute $powershellPath `
        -Argument $taskDef.Arguments `
        -WorkingDirectory $projectRoot

    # Create settings
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2)

    # Register the task
    Register-ScheduledTask `
        -TaskName $taskDef.Name `
        -Description $taskDef.Description `
        -Trigger $trigger `
        -Action $action `
        -Settings $settings `
        -User $User `
        -RunLevel Highest `
        -Force | Out-Null

    Write-Host "[register_task] Registered task: $($taskDef.Name)"
    Write-Host "                 Time: $($taskDef.Time) daily"
    Write-Host "                 User: $User"
    Write-Host "                 Script: $runDailyScript"
}

Write-Host ""
Write-Host "[register_task] Registration complete."
Write-Host "[register_task] To verify: Get-ScheduledTask -TaskName 'mm-*'"
Write-Host "[register_task] To remove : .\scripts\register_task.ps1 -Unregister"
Write-Host "[register_task] To run now: Start-ScheduledTask -TaskName 'mm-pre-market'"
