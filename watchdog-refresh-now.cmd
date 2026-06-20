@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%scripts\refresh_dashboard_now.ps1"

if not exist "%PS1%" (
  echo PowerShell refresh script not found:
  echo %PS1%
  pause
  exit /b 1
)

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Dashboard refresh finished successfully.
) else (
  echo Dashboard refresh failed with exit code %EXIT_CODE%.
  echo Check the latest logs\dashboard-refresh-now-*.log file for details.
)
echo.
pause
exit /b %EXIT_CODE%
