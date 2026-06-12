import copy
import json
from datetime import datetime

import pytest

import portfolio_watchdog.performance.service as service_module
from portfolio_watchdog.performance.service import (
    build_performance_summary,
    save_dashboard_payload_v2,
)
from portfolio_watchdog.performance.twr import ValuationPoint


def _point(
    day: int,
    value: float,
    cash_flow: float = 0,
    reconciliation_status: str = "reconciled",
) -> ValuationPoint:
    return ValuationPoint(
        datetime(2026, 6, day),
        value,
        cash_flow,
        reconciliation_status,
    )


def _summary(**overrides) -> dict:
    values = {
        "valuation_points": [_point(1, 100), _point(2, 120), _point(3, 90)],
        "month_points": [_point(1, 100), _point(3, 90)],
        "benchmark_return": 0.05,
        "asset_groups": [{"asset_group": "equity", "value_krw": 90}],
        "assets": [{"symbol": "SPY", "asset_type": "equity", "value_krw": 90}],
        "provider_status": [{"provider": "kis", "status": "ok"}],
        "generated_at": datetime(2026, 6, 3, 8, 0, 0, 123456),
        "portfolio_status": "actual",
        "last_actual_at": datetime(2026, 6, 3, 7, 59, 59, 999999),
        "reconciliation_status": "reconciled",
    }
    values.update(overrides)
    return build_performance_summary(**values)


def test_build_performance_summary_calculates_returns_and_drawdown() -> None:
    summary = _summary()

    assert summary["generated_at"] == "2026-06-03T08:00:00"
    assert summary["total_value_krw"] == 90
    assert summary["data_freshness"] == {
        "portfolio_status": "actual",
        "last_actual_at": "2026-06-03T07:59:59",
        "reconciliation_status": "reconciled",
    }
    assert summary["performance"] == {
        "cumulative_twr_pct": pytest.approx(-10.0),
        "month_twr_pct": pytest.approx(-10.0),
        "benchmark_return_pct": pytest.approx(5.0),
        "excess_return_pct": pytest.approx(-15.0),
        "max_drawdown_pct": pytest.approx(-25.0),
        "status": "confirmed",
    }


def test_build_performance_summary_does_not_mutate_or_alias_input_collections() -> None:
    asset_groups = [{"asset_group": "equity", "details": {"value_krw": 90}}]
    assets = [{"symbol": "SPY", "tags": ["index"]}]
    provider_status = [{"provider": "kis", "status": "ok"}]
    originals = copy.deepcopy((asset_groups, assets, provider_status))

    summary = _summary(
        asset_groups=asset_groups,
        assets=assets,
        provider_status=provider_status,
    )
    summary["asset_groups"][0]["details"]["value_krw"] = 0
    summary["assets"][0]["tags"].append("changed")
    summary["provider_status"][0]["status"] = "failed"

    assert (asset_groups, assets, provider_status) == originals


def test_build_performance_summary_uses_zero_and_none_for_missing_values() -> None:
    summary = _summary(
        valuation_points=[],
        month_points=[],
        benchmark_return=None,
        last_actual_at=None,
    )

    assert summary["total_value_krw"] == 0
    assert summary["data_freshness"]["last_actual_at"] is None
    assert summary["performance"] == {
        "cumulative_twr_pct": None,
        "month_twr_pct": None,
        "benchmark_return_pct": None,
        "excess_return_pct": None,
        "max_drawdown_pct": None,
        "status": "insufficient_data",
    }


@pytest.mark.parametrize(
    ("valuation_points", "month_points", "expected"),
    [
        (
            [_point(1, 100, reconciliation_status="reconciliation_required"), _point(2, 110)],
            [_point(1, 100), _point(2, 110)],
            "provisional",
        ),
        (
            [_point(1, 100), _point(2, 110)],
            [_point(1, 100), _point(2, 110, reconciliation_status="reconciliation_required")],
            "provisional",
        ),
    ],
)
def test_build_performance_summary_is_provisional_for_provisional_returns(
    valuation_points, month_points, expected
) -> None:
    assert _summary(
        valuation_points=valuation_points,
        month_points=month_points,
        benchmark_return=None,
    )["performance"]["status"] == expected


def test_missing_benchmark_does_not_make_performance_provisional() -> None:
    assert _summary(benchmark_return=None)["performance"]["status"] == "confirmed"


def test_top_level_reconciliation_failure_makes_performance_provisional() -> None:
    assert _summary(reconciliation_status="reconciliation_required")["performance"][
        "status"
    ] == "provisional"


def test_reconciliation_failure_takes_priority_over_insufficient_data() -> None:
    assert _summary(
        valuation_points=[],
        month_points=[],
        reconciliation_status="reconciliation_required",
    )["performance"]["status"] == "provisional"


def test_missing_month_data_makes_performance_insufficient() -> None:
    assert _summary(month_points=[])["performance"]["status"] == "insufficient_data"


def test_save_dashboard_payload_v2_writes_utf8_json_atomically(tmp_path, monkeypatch) -> None:
    target = tmp_path / "dashboard_v2_latest.json"
    replacements = []
    real_replace = service_module.os.replace

    def record_replace(source, destination):
        replacements.append((source, destination))
        return real_replace(source, destination)

    monkeypatch.setattr(service_module.os, "replace", record_replace)

    save_dashboard_payload_v2({"schema_version": "dashboard_payload_v2", "name": "ISA"}, target)

    assert json.loads(target.read_text(encoding="utf-8"))["name"] == "ISA"
    assert "\n  \"schema_version\"" in target.read_text(encoding="utf-8")
    assert len(replacements) == 1
    assert replacements[0][0].parent == target.parent
    assert replacements[0][1] == target


def test_save_dashboard_payload_v2_creates_parent_directory(tmp_path) -> None:
    target = tmp_path / "nested" / "dashboard_v2_latest.json"

    save_dashboard_payload_v2({"schema_version": "dashboard_payload_v2"}, target)

    assert target.exists()


def test_save_dashboard_payload_v2_keeps_existing_file_and_cleans_temp_on_replace_failure(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "dashboard_v2_latest.json"
    target.write_text("existing", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(service_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        save_dashboard_payload_v2({"schema_version": "dashboard_payload_v2"}, target)

    assert target.read_text(encoding="utf-8") == "existing"
    assert list(tmp_path.iterdir()) == [target]


def test_save_dashboard_payload_v2_rejects_cloud_unsafe_payload(tmp_path) -> None:
    target = tmp_path / "dashboard_v2_latest.json"

    with pytest.raises(ValueError, match="forbidden cloud field"):
        save_dashboard_payload_v2({"assets": [{"quantity": 1}]}, target)

    assert not target.exists()
