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
    tasks: List[TaskSpec] = [
        ("PortfolioWatchdogNewsHourly", "check-news", "HOURLY", "00:00", None),
        ("PortfolioWatchdogNewsRiskHourly", "collect-news-risks --sync-dashboard", "HOURLY", "00:10", None),
        ("PortfolioWatchdogLedger0800", "sync-ledger --sync-dashboard", "DAILY", "08:00", None),
        ("PortfolioWatchdogLedger1200", "sync-ledger --sync-dashboard", "DAILY", "12:00", None),
        ("PortfolioWatchdogLedger1800", "sync-ledger --sync-dashboard", "DAILY", "18:00", None),
        ("PortfolioWatchdogLedger2200", "sync-ledger --sync-dashboard", "DAILY", "22:00", None),
    ]
    for name, command, schedule, start_time, day in tasks:
        args: List[str] = [
            "schtasks",
            "/Create",
            "/TN",
            name,
            "/TR",
            _task_command(workdir, command),
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


def _task_command(workdir: Path, command: str) -> str:
    return f'cmd /c cd /d "{workdir}" && {subprocess.list2cmdline(_runtime_command(command))}'


def _runtime_command(command: str) -> List[str]:
    command_args = command.split()
    if getattr(sys, "frozen", False):
        return [sys.executable, *command_args]
    return [sys.executable, "-m", "portfolio_watchdog", *command_args]


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
    return subprocess.run(list(args), check=True, capture_output=True, text=True)
