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

    assert len(create_calls) == 6
    assert len(powershell_calls) == 6
    assert all(
        "StopIfGoingOnBatteries = $false" in call[-1] for call in powershell_calls
    )
    assert all("StartWhenAvailable = $true" in call[-1] for call in powershell_calls)

    news_call = next(call for call in create_calls if "PortfolioWatchdogNewsHourly" in call)
    assert "/ST" in news_call
    assert "00:00" in news_call
    assert "watchdog-task.cmd" in " ".join(news_call)
    assert "&&" not in " ".join(news_call)
    assert (tmp_path / "watchdog-task.cmd").exists()
    assert "portfolio_watchdog" in (tmp_path / "watchdog-task.cmd").read_text(encoding="utf-8")

    news_risk_call = next(call for call in create_calls if "PortfolioWatchdogNewsRiskHourly" in call)
    assert "collect-news-risks" in " ".join(news_risk_call)
    assert "--sync-dashboard" in " ".join(news_risk_call)
    assert "00:10" in news_risk_call

    assert all("PortfolioWatchdogWeeklyReport" not in call for call in create_calls)
    assert all("PortfolioWatchdogReport0800" not in call for call in create_calls)
    assert all("PortfolioWatchdogReport1200" not in call for call in create_calls)
    assert all("PortfolioWatchdogReport1800" not in call for call in create_calls)

    dashboard_calls = [
        call for call in create_calls if "PortfolioWatchdogDashboard" in " ".join(call)
    ]
    assert len(dashboard_calls) == 4
    assert {call[call.index("/ST") + 1] for call in dashboard_calls} == {
        "08:00",
        "12:00",
        "18:00",
        "22:00",
    }
    assert all("refresh-dashboard" in " ".join(call) for call in dashboard_calls)
