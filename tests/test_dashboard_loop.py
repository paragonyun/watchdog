from datetime import datetime

from portfolio_watchdog.dashboard_loop import due_dashboard_loop_jobs, run_dashboard_loop


def test_due_dashboard_loop_jobs_trigger_current_window_once() -> None:
    now = datetime(2026, 6, 18, 18, 10)

    jobs = due_dashboard_loop_jobs(now, ran_keys=set())

    assert [job.name for job in jobs] == [
        "check-news",
        "collect-news-risks",
        "refresh-dashboard",
    ]

    ran_keys = {job.key for job in jobs}

    assert due_dashboard_loop_jobs(now, ran_keys=ran_keys) == []


def test_due_dashboard_loop_jobs_prepare_codex_inputs_at_evening_slot() -> None:
    now = datetime(2026, 6, 18, 22, 5)

    jobs = due_dashboard_loop_jobs(now, ran_keys=set())

    assert [job.name for job in jobs] == [
        "check-news",
        "refresh-dashboard",
        "prepare-codex-inputs",
    ]


def test_due_dashboard_loop_jobs_does_not_backfill_missed_dashboard_windows() -> None:
    now = datetime(2026, 6, 18, 23, 0)

    jobs = due_dashboard_loop_jobs(now, ran_keys=set())

    assert [job.name for job in jobs] == ["check-news"]


def test_run_dashboard_loop_once_executes_due_jobs_without_windows_scheduler() -> None:
    calls = []

    class FakeApp:
        def run_news_check(self):
            calls.append(("run_news_check", None))

        def collect_news_risks(self, sync_dashboard=False):
            calls.append(("collect_news_risks", sync_dashboard))

        def refresh_dashboard(self, sync_codex=True):
            calls.append(("refresh_dashboard", sync_codex))

        def prepare_codex_inputs(self):
            calls.append(("prepare_codex_inputs", None))

    ran_keys = set()

    result = run_dashboard_loop(
        FakeApp(),
        now_func=lambda: datetime(2026, 6, 18, 22, 5),
        sleep_func=lambda seconds: None,
        once=True,
        ran_keys=ran_keys,
    )

    assert calls == [
        ("run_news_check", None),
        ("refresh_dashboard", True),
        ("prepare_codex_inputs", None),
    ]
    assert result["executed"] == [
        "check-news",
        "refresh-dashboard",
        "prepare-codex-inputs",
    ]
    assert len(ran_keys) == 3
