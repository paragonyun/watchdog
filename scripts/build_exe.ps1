$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

& $Python -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name PortfolioWatchdog `
  --paths src `
  --add-data "config\config.example.yaml;config" `
  --add-data ".env.example;." `
  scripts\portfolio_watchdog_entry.py

Write-Host "Build complete: dist\PortfolioWatchdog\PortfolioWatchdog.exe"
