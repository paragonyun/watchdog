param(
    [switch]$SkipCodex,
    [switch]$PrepareCodexInputs,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"
$RunStamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$RunId = "$RunStamp-$PID"
$LogFile = Join-Path $LogDir "dashboard-refresh-now-$RunId.log"

function Write-RefreshLog {
    param([string]$Message)
    $Message | Tee-Object -FilePath $LogFile -Append | ForEach-Object { Write-Host $_ }
}

function Invoke-LoggedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$StepName
    )

    $stdoutFile = Join-Path $LogDir "dashboard-refresh-now-$RunId-$StepName.stdout.tmp"
    $stderrFile = Join-Path $LogDir "dashboard-refresh-now-$RunId-$StepName.stderr.tmp"
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $ProjectRoot `
        -NoNewWindow `
        -Wait `
        -PassThru `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile

    foreach ($outputFile in @($stdoutFile, $stderrFile)) {
        if (Test-Path $outputFile) {
            foreach ($line in Get-Content -Path $outputFile) {
                Write-RefreshLog $line
            }
            Remove-Item -Path $outputFile -Force -ErrorAction SilentlyContinue
        }
    }

    return $process.ExitCode
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Set-Location $ProjectRoot

if (-not (Test-Path $Python)) {
    throw "Python virtual environment not found: $Python"
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"

$refreshArgs = @("-m", "portfolio_watchdog", "refresh-dashboard")
if ($SkipCodex) {
    $refreshArgs += "--skip-codex"
}

$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
Write-RefreshLog ""
Write-RefreshLog "=== Portfolio Watchdog manual refresh: $startedAt ==="
Write-RefreshLog "Project: $ProjectRoot"
Write-RefreshLog "Log: $LogFile"
Write-RefreshLog "Command: $Python $($refreshArgs -join ' ')"

if ($DryRun) {
    Write-RefreshLog "Dry run only. No API call or dashboard upload was executed."
    exit 0
}

$refreshExitCode = Invoke-LoggedProcess -FilePath $Python -Arguments $refreshArgs -StepName "refresh"
if ($refreshExitCode -ne 0) {
    Write-RefreshLog "Manual refresh failed with exit code $refreshExitCode."
    exit $refreshExitCode
}

if ($PrepareCodexInputs) {
    $codexArgs = @("-m", "portfolio_watchdog", "prepare-codex-inputs")
    Write-RefreshLog "Command: $Python $($codexArgs -join ' ')"
    $codexExitCode = Invoke-LoggedProcess -FilePath $Python -Arguments $codexArgs -StepName "codex-inputs"
    if ($codexExitCode -ne 0) {
        Write-RefreshLog "Codex input preparation failed with exit code $codexExitCode."
        exit $codexExitCode
    }
}

$finishedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
Write-RefreshLog "Manual refresh completed: $finishedAt"
exit 0
