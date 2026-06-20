import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from .runtime_paths import get_executable_root

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]
TaskSpec = Tuple[str, str, str, Optional[str], Optional[str]]


def install_windows_schedule(runner: Runner | None = None) -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Windows 작업 스케줄러 등록은 Windows에서만 지원합니다.")
    run = runner or _default_runner
    workdir = get_executable_root()
    runner_path = _write_task_runner(workdir)
    tasks: List[TaskSpec] = [
        ("PortfolioWatchdogNewsHourly", "check-news", "HOURLY", "00:00", None),
        ("PortfolioWatchdogNewsRiskHourly", "collect-news-risks --sync-dashboard", "HOURLY", "00:10", None),
        ("PortfolioWatchdogDashboard0800", "refresh-dashboard", "DAILY", "08:00", None),
        ("PortfolioWatchdogDashboard1200", "refresh-dashboard", "DAILY", "12:00", None),
        ("PortfolioWatchdogDashboard1800", "refresh-dashboard", "DAILY", "18:00", None),
        ("PortfolioWatchdogDashboard2200", "refresh-dashboard", "DAILY", "22:00", None),
    ]
    for name, command, schedule, start_time, day in tasks:
        args: List[str] = [
            "schtasks",
            "/Create",
            "/TN",
            name,
            "/TR",
            _task_command(runner_path, command),
            "/SC",
            schedule,
            "/F",
        ]
        if schedule == "HOURLY":
            args.extend(["/MO", "1"])
        if day:
            args.extend(["/D", day])
        if start_time:
            args.extend(["/ST", start_time])
        run(args)
        _update_windows_task_settings(name, run)


def _write_task_runner(workdir: Path) -> Path:
    runner = workdir / "watchdog-task.cmd"
    runner.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "set \"SCRIPT_DIR=%~dp0\"\r\n"
        "cd /d \"%SCRIPT_DIR%\" || exit /b 1\r\n"
        "if not exist \"logs\" mkdir \"logs\"\r\n"
        "set \"LOG_FILE=logs\\watchdog-task.log\"\r\n"
        "set \"PYTHON=%SCRIPT_DIR%.venv\\Scripts\\python.exe\"\r\n"
        "echo.>> \"%LOG_FILE%\"\r\n"
        "echo === %DATE% %TIME% watchdog-task %* ===>> \"%LOG_FILE%\"\r\n"
        "if exist \"%PYTHON%\" (\r\n"
        "  \"%PYTHON%\" -m portfolio_watchdog %* >> \"%LOG_FILE%\" 2>&1\r\n"
        ") else (\r\n"
        "  python -m portfolio_watchdog %* >> \"%LOG_FILE%\" 2>&1\r\n"
        ")\r\n"
        "set \"EXIT_CODE=%ERRORLEVEL%\"\r\n"
        "echo exit_code=%EXIT_CODE%>> \"%LOG_FILE%\"\r\n"
        "exit /b %EXIT_CODE%\r\n",
        encoding="utf-8",
    )
    return runner


def _task_command(runner_path: Path, command: str) -> str:
    return subprocess.list2cmdline([str(runner_path), *command.split()])


def _runtime_command(command: str) -> List[str]:
    command_args = command.split()
    return [*_runtime_base_command(), *command_args]


def _runtime_base_command() -> List[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "portfolio_watchdog"]


def _update_windows_task_settings(task_name: str, runner: Runner) -> None:
    quoted_name = _powershell_quote(task_name)
    script = (
        f"$task = Get-ScheduledTask -TaskName {quoted_name}; "
        "$task.Settings.DisallowStartIfOnBatteries = $false; "
        "$task.Settings.StopIfGoingOnBatteries = $false; "
        "$task.Settings.StartWhenAvailable = $true; "
        "Set-ScheduledTask -InputObject $task | Out-Null"
    )
    runner(["powershell", "-NoProfile", "-Command", script])


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _default_runner(args: Sequence[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(list(args), check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"Scheduled task command failed: {detail}") from exc
