import subprocess
import portfolio_watchdog.scheduler as scheduler


def test_install_windows_schedule_updates_power_settings(monkeypatch, tmp_path) -> None:
    calls = []

    def runner(args):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(scheduler.platform, "system", lambda: "Windows")
    monkeypatch.setattr(scheduler, "get_executable_root", lambda: tmp_path)

    scheduler.install_windows_schedule(runner=runner)

    create_calls = [call for call in calls if call[0] == "schtasks"]
    powershell_calls = [call for call in calls if call[0] == "powershell"]

    assert len(create_calls) == 1
    assert len(powershell_calls) == 1
    assert "StopIfGoingOnBatteries = $false" in powershell_calls[0][-1]
    assert "StartWhenAvailable = $true" in powershell_calls[0][-1]

    news_call = next(call for call in create_calls if "PortfolioWatchdogNewsHourly" in call)
    assert "/ST" in news_call
    assert "00:00" in news_call

    assert all("PortfolioWatchdogWeeklyReport" not in call for call in create_calls)
    assert all("PortfolioWatchdogReport0800" not in call for call in create_calls)
    assert all("PortfolioWatchdogReport1200" not in call for call in create_calls)
    assert all("PortfolioWatchdogReport1800" not in call for call in create_calls)
