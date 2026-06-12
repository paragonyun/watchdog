from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from portfolio_watchdog.cloud_contract import assert_cloud_safe
from portfolio_watchdog.performance.risk import calculate_drawdowns
from portfolio_watchdog.performance.twr import (
    ValuationPoint,
    calculate_monthly_return,
    calculate_twr,
)


def build_performance_summary(
    valuation_points: list[ValuationPoint],
    month_points: list[ValuationPoint],
    benchmark_return: float | None,
    asset_groups: list[dict[str, Any]] | dict[str, Any],
    assets: list[dict[str, Any]],
    provider_status: list[dict[str, Any]],
    generated_at: datetime | str,
    portfolio_status: str,
    last_actual_at: datetime | str | None,
    reconciliation_status: str,
) -> dict[str, Any]:
    cumulative = calculate_twr(valuation_points)
    monthly = calculate_monthly_return(month_points)
    benchmark_return_pct = (
        None if benchmark_return is None else benchmark_return * 100
    )
    excess_return_pct = (
        None
        if cumulative.cumulative_return_pct is None or benchmark_return_pct is None
        else cumulative.cumulative_return_pct - benchmark_return_pct
    )
    drawdowns = calculate_drawdowns(
        [point.total_value_krw for point in valuation_points]
    )

    return {
        "generated_at": _iso_seconds(generated_at),
        "total_value_krw": (
            valuation_points[-1].total_value_krw if valuation_points else 0
        ),
        "data_freshness": {
            "portfolio_status": portfolio_status,
            "last_actual_at": _iso_seconds(last_actual_at),
            "reconciliation_status": reconciliation_status,
        },
        "performance": {
            "cumulative_twr_pct": cumulative.cumulative_return_pct,
            "month_twr_pct": monthly.cumulative_return_pct,
            "benchmark_return_pct": benchmark_return_pct,
            "excess_return_pct": excess_return_pct,
            "max_drawdown_pct": min(drawdowns) if drawdowns else None,
            "status": _performance_status(
                cumulative.status, monthly.status, reconciliation_status
            ),
        },
        "asset_groups": deepcopy(asset_groups),
        "assets": deepcopy(assets),
        "provider_status": deepcopy(provider_status),
    }


def save_dashboard_payload_v2(payload: dict[str, Any], path: Path | str) -> None:
    assert_cloud_safe(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(payload, temp_file, ensure_ascii=False, indent=2)
        os.replace(temp_path, target)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _performance_status(
    cumulative_status: str, monthly_status: str, reconciliation_status: str
) -> str:
    if (
        "provisional" in (cumulative_status, monthly_status)
        or reconciliation_status != "reconciled"
    ):
        return "provisional"
    if "insufficient_data" in (cumulative_status, monthly_status):
        return "insufficient_data"
    return "confirmed"


def _iso_seconds(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return parsed.isoformat(timespec="seconds")
