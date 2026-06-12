import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ValuationPoint:
    captured_at: datetime
    total_value_krw: float
    external_cash_flow_krw: float
    reconciliation_status: str


@dataclass(frozen=True)
class TwrResult:
    cumulative_return_pct: float | None
    period_returns_pct: list[float]
    status: str


def calculate_twr(points: list[ValuationPoint]) -> TwrResult:
    _validate_points(points)

    if len(points) < 2 or points[0].total_value_krw == 0:
        return TwrResult(None, [], "insufficient_data")

    linked_return = 1.0
    period_returns_pct = []
    for previous, current in zip(points, points[1:]):
        if previous.total_value_krw == 0:
            return TwrResult(None, [], "insufficient_data")
        period_return = (
            current.total_value_krw - current.external_cash_flow_krw
        ) / previous.total_value_krw - 1
        linked_return *= 1 + period_return
        period_returns_pct.append(period_return * 100)

    status = (
        "confirmed"
        if all(point.reconciliation_status == "reconciled" for point in points)
        else "provisional"
    )
    return TwrResult(
        round((linked_return - 1) * 100, 6),
        period_returns_pct,
        status,
    )


def calculate_monthly_return(points: list[ValuationPoint]) -> TwrResult:
    _validate_points(points)
    months = {
        (captured_at.year, captured_at.month)
        for captured_at in (_utc_datetime(point.captured_at) for point in points)
    }
    if len(months) > 1:
        raise ValueError("points must belong to a single month")
    return calculate_twr(points)


def _validate_points(points: list[ValuationPoint]) -> None:
    previous_captured_at = None
    for point in points:
        if not isinstance(point.captured_at, datetime):
            raise ValueError("captured_at must be a datetime")
        captured_at = _utc_datetime(point.captured_at)
        if previous_captured_at is not None and captured_at <= previous_captured_at:
            raise ValueError("captured_at must be strictly increasing")
        previous_captured_at = captured_at

        _validate_finite(point.total_value_krw, "total_value_krw")
        if point.total_value_krw < 0:
            raise ValueError("total_value_krw must be non-negative")
        _validate_finite(point.external_cash_flow_krw, "external_cash_flow_krw")


def _validate_finite(value: float, field: str) -> None:
    try:
        finite = math.isfinite(value)
    except TypeError:
        finite = False
    if not finite:
        raise ValueError(f"{field} must be finite")


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
