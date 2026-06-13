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

    news_risk_call = next(call for call in create_calls if "PortfolioWatchdogNewsRiskHourly" in call)
    assert "collect-news-risks --sync-dashboard" in " ".join(news_risk_call)
    assert "00:10" in news_risk_call

    assert all("PortfolioWatchdogWeeklyReport" not in call for call in create_calls)
    assert all("PortfolioWatchdogReport0800" not in call for call in create_calls)
    assert all("PortfolioWatchdogReport1200" not in call for call in create_calls)
    assert all("PortfolioWatchdogReport1800" not in call for call in create_calls)

    ledger_calls = [
        call for call in create_calls if "PortfolioWatchdogLedger" in " ".join(call)
    ]
    assert len(ledger_calls) == 4
    assert {call[call.index("/ST") + 1] for call in ledger_calls} == {
        "08:00",
        "12:00",
        "18:00",
        "22:00",
    }
    assert all("sync-ledger" in " ".join(call) for call in ledger_calls)
    assert all("--sync-dashboard" in " ".join(call) for call in ledger_calls)
