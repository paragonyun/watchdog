$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "watchdog-task.log"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Set-Location $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
& $Python -m portfolio_watchdog run 2>&1 | Tee-Object -FilePath $LogFile -Append
exit $LASTEXITCODE
