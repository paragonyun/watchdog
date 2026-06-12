from datetime import date, datetime

import pytest

from portfolio_watchdog.performance.benchmark import (
    BenchmarkWeight,
    calculate_blended_benchmark,
)


EFFECTIVE_FROM = date(2026, 1, 1)


class CustomDate(date):
    pass


def _weight(**overrides) -> BenchmarkWeight:
    values = {
        "effective_from": EFFECTIVE_FROM,
        "asset_group": "equity",
        "weight": 1.0,
        "benchmark_symbol": "SPY",
    }
    values.update(overrides)
    return BenchmarkWeight(**values)


def test_calculate_blended_benchmark_returns_weighted_decimal_return() -> None:
    weights = [
        _weight(asset_group="equity", weight=0.6, benchmark_symbol="SPY"),
        _weight(asset_group="bond", weight=0.4, benchmark_symbol="AGG"),
    ]

    result = calculate_blended_benchmark(weights, {"SPY": 0.10, "AGG": -0.02})

    assert result == pytest.approx(0.052)


def test_calculate_blended_benchmark_allows_duplicate_benchmark_symbols() -> None:
    weights = [
        _weight(asset_group="equity", weight=0.6),
        _weight(asset_group="isa", weight=0.4),
    ]

    assert calculate_blended_benchmark(weights, {"SPY": 0.05}) == pytest.approx(0.05)


def test_calculate_blended_benchmark_rejects_empty_weights() -> None:
    with pytest.raises(ValueError, match="weights"):
        calculate_blended_benchmark([], {})


@pytest.mark.parametrize("invalid_weight", [-0.1, float("nan"), float("inf")])
def test_calculate_blended_benchmark_rejects_negative_or_nonfinite_weight(
    invalid_weight,
) -> None:
    with pytest.raises(ValueError, match="weight"):
        calculate_blended_benchmark([_weight(weight=invalid_weight)], {"SPY": 0.1})


@pytest.mark.parametrize("total_weight", [0.9998, 1.0002])
def test_calculate_blended_benchmark_rejects_weight_sum_outside_tolerance(
    total_weight,
) -> None:
    with pytest.raises(ValueError, match="sum"):
        calculate_blended_benchmark([_weight(weight=total_weight)], {"SPY": 0.1})


def test_calculate_blended_benchmark_rejects_mixed_effective_dates() -> None:
    weights = [
        _weight(weight=0.5),
        _weight(
            effective_from=date(2026, 2, 1),
            asset_group="bond",
            weight=0.5,
            benchmark_symbol="AGG",
        ),
    ]

    with pytest.raises(ValueError, match="effective_from"):
        calculate_blended_benchmark(weights, {"SPY": 0.1, "AGG": 0.02})


def test_calculate_blended_benchmark_rejects_duplicate_asset_groups() -> None:
    weights = [_weight(weight=0.5), _weight(weight=0.5, benchmark_symbol="QQQ")]

    with pytest.raises(ValueError, match="asset_group"):
        calculate_blended_benchmark(weights, {"SPY": 0.1, "QQQ": 0.2})


@pytest.mark.parametrize(
    "weight",
    [
        _weight(effective_from=datetime(2026, 1, 1)),
        _weight(effective_from=CustomDate(2026, 1, 1)),
        _weight(asset_group=""),
        _weight(asset_group=1),
        _weight(benchmark_symbol=""),
        _weight(benchmark_symbol=1),
    ],
)
def test_calculate_blended_benchmark_rejects_invalid_version_identifiers(
    weight,
) -> None:
    with pytest.raises(ValueError):
        calculate_blended_benchmark([weight], {"SPY": 0.1, 1: 0.1})


def test_calculate_blended_benchmark_rejects_missing_benchmark_return() -> None:
    with pytest.raises(ValueError, match="SPY"):
        calculate_blended_benchmark([_weight()], {})


@pytest.mark.parametrize("invalid_return", [float("nan"), float("inf"), float("-inf")])
def test_calculate_blended_benchmark_rejects_nonfinite_return(invalid_return) -> None:
    with pytest.raises(ValueError, match="return"):
        calculate_blended_benchmark([_weight()], {"SPY": invalid_return})
