import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DashboardLoopJob:
    name: str
    key: str


def due_dashboard_loop_jobs(
    now: datetime,
    *,
    ran_keys: set[str],
    refresh_hours: Iterable[int] = (8, 12, 18, 22),
    window_minutes: int = 59,
) -> list[DashboardLoopJob]:
    hour_key = now.strftime("%Y-%m-%dT%H")
    candidates = [
        DashboardLoopJob("check-news", f"check-news:{hour_key}"),
    ]

    if now.minute >= 10:
        candidates.append(
            DashboardLoopJob("collect-news-risks", f"collect-news-risks:{hour_key}")
        )

    if now.hour in set(refresh_hours) and now.minute <= window_minutes:
        candidates.append(
            DashboardLoopJob("refresh-dashboard", f"refresh-dashboard:{hour_key}")
        )

    if now.hour == 22 and 5 <= now.minute <= window_minutes:
        candidates.append(
            DashboardLoopJob("prepare-codex-inputs", f"prepare-codex-inputs:{now:%Y-%m-%d}")
        )

    return [job for job in candidates if job.key not in ran_keys]


def run_dashboard_loop(
    app,
    *,
    interval_seconds: int = 60,
    once: bool = False,
    now_func: Callable[[], datetime] | None = None,
    sleep_func: Callable[[int], None] = time.sleep,
    ran_keys: set[str] | None = None,
) -> dict[str, object]:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    get_now = now_func or (lambda: datetime.now().astimezone())
    completed_keys = ran_keys if ran_keys is not None else set()
    last_result: dict[str, object] = {"executed": []}

    while True:
        now = get_now()
        executed = []
        for job in due_dashboard_loop_jobs(now, ran_keys=completed_keys):
            _run_job(app, job.name)
            completed_keys.add(job.key)
            executed.append(job.name)
        last_result = {"checked_at": now.isoformat(), "executed": executed}
        if executed:
            logger.info("Dashboard loop executed: %s", ", ".join(executed))
        if once:
            return last_result
        sleep_func(interval_seconds)


def _run_job(app, name: str) -> None:
    if name == "check-news":
        app.run_news_check()
        return
    if name == "collect-news-risks":
        app.collect_news_risks(sync_dashboard=True)
        return
    if name == "refresh-dashboard":
        app.refresh_dashboard(sync_codex=True)
        return
    if name == "prepare-codex-inputs":
        app.prepare_codex_inputs()
        return
    raise ValueError(f"unknown dashboard loop job: {name}")
