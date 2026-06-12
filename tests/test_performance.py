from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from portfolio_watchdog.performance.risk import calculate_drawdowns
from portfolio_watchdog.performance.twr import (
    TwrResult,
    ValuationPoint,
    calculate_monthly_return,
    calculate_twr,
)


def point(
    day: int,
    total_value_krw: float,
    external_cash_flow_krw: float = 0,
    reconciliation_status: str = "reconciled",
    *,
    month: int = 6,
) -> ValuationPoint:
    return ValuationPoint(
        datetime(2026, month, day),
        total_value_krw,
        external_cash_flow_krw,
        reconciliation_status,
    )


def test_performance_models_are_frozen() -> None:
    valuation = point(1, 1_000_000)
    result = TwrResult(10.0, [10.0], "confirmed")

    with pytest.raises(FrozenInstanceError):
        valuation.total_value_krw = 2_000_000
    with pytest.raises(FrozenInstanceError):
        result.status = "provisional"


def test_twr_excludes_external_cash_flow_before_current_valuation() -> None:
    result = calculate_twr(
        [
            point(1, 1_000_000),
            point(2, 1_200_000, 100_000),
        ]
    )

    assert result == TwrResult(10.0, [pytest.approx(10.0)], "confirmed")


def test_twr_links_period_returns() -> None:
    result = calculate_twr(
        [
            point(1, 100),
            point(2, 110),
            point(3, 99),
        ]
    )

    assert result.cumulative_return_pct == -1.0
    assert result.period_returns_pct == [pytest.approx(10.0), pytest.approx(-10.0)]


def test_twr_rounds_cumulative_return_to_six_decimal_places() -> None:
    result = calculate_twr([point(1, 100), point(2, 100.123456789)])

    assert result.cumulative_return_pct == 0.123457


@pytest.mark.parametrize(
    "points",
    [
        [],
        [point(1, 100)],
        [point(1, 0), point(2, 100)],
        [point(1, 100), point(2, 0), point(3, 100)],
    ],
)
def test_twr_returns_insufficient_data_when_a_return_cannot_be_calculated(
    points,
) -> None:
    assert calculate_twr(points) == TwrResult(None, [], "insufficient_data")


@pytest.mark.parametrize(
    "points",
    [
        [point(1, 100, reconciliation_status="reconciliation_required"), point(2, 110)],
        [point(1, 100), point(2, 110, reconciliation_status="reconciliation_required")],
    ],
)
def test_twr_is_provisional_when_any_point_is_not_reconciled(points) -> None:
    assert calculate_twr(points).status == "provisional"


def test_twr_is_confirmed_when_all_points_are_reconciled() -> None:
    assert calculate_twr([point(1, 100), point(2, 110)]).status == "confirmed"


@pytest.mark.parametrize(
    "points",
    [
        [point(2, 100), point(1, 110)],
        [point(1, 100), point(1, 110)],
    ],
)
def test_twr_rejects_non_increasing_capture_times(points) -> None:
    with pytest.raises(ValueError, match="captured_at.*strictly increasing"):
        calculate_twr(points)


def test_twr_rejects_non_datetime_capture_time() -> None:
    points = [
        point(1, 100),
        ValuationPoint("2026-06-02", 110, 0, "reconciled"),
    ]

    with pytest.raises(ValueError, match="captured_at.*datetime"):
        calculate_twr(points)


def test_twr_orders_naive_and_aware_capture_times_as_utc() -> None:
    points = [
        point(1, 100),
        ValuationPoint(
            datetime(2026, 6, 2, 9, tzinfo=timezone(timedelta(hours=9))),
            110,
            0,
            "reconciled",
        ),
    ]

    assert calculate_twr(points).cumulative_return_pct == 10.0


def test_twr_rejects_same_instant_with_different_offsets() -> None:
    points = [
        point(1, 100),
        ValuationPoint(
            datetime(2026, 6, 1, 9, tzinfo=timezone(timedelta(hours=9))),
            110,
            0,
            "reconciled",
        ),
    ]

    with pytest.raises(ValueError, match="captured_at.*strictly increasing"):
        calculate_twr(points)


@pytest.mark.parametrize(
    ("field", "points"),
    [
        ("total_value_krw", [point(1, float("nan")), point(2, 100)]),
        ("total_value_krw", [point(1, 100), point(2, float("inf"))]),
        ("external_cash_flow_krw", [point(1, 100), point(2, 110, float("-inf"))]),
    ],
)
def test_twr_rejects_non_finite_values(field, points) -> None:
    with pytest.raises(ValueError, match=field):
        calculate_twr(points)


def test_twr_rejects_negative_total_value() -> None:
    with pytest.raises(ValueError, match="total_value_krw"):
        calculate_twr([point(1, 100), point(2, -1)])


def test_monthly_return_uses_twr_for_the_month() -> None:
    points = [
        point(1, 1_000),
        point(15, 1_200, 100),
        point(30, 1_210),
    ]

    assert calculate_monthly_return(points) == calculate_twr(points)


def test_monthly_return_rejects_points_from_different_months() -> None:
    with pytest.raises(ValueError, match="single month"):
        calculate_monthly_return([point(30, 100, month=6), point(1, 110, month=7)])


def test_drawdown_uses_running_peak() -> None:
    assert calculate_drawdowns([100, 120, 90, 108]) == [0, 0, -25, -10]


def test_drawdown_is_zero_until_a_positive_peak_exists() -> None:
    assert calculate_drawdowns([0, 0, 10, 5]) == [0, 0, 0, -50]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -1])
def test_drawdown_rejects_invalid_values(value) -> None:
    with pytest.raises(ValueError, match="values"):
        calculate_drawdowns([100, value])
