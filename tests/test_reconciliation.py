from dataclasses import FrozenInstanceError

import pytest

from portfolio_watchdog.ledger.reconciliation import reconcile_asset_quantities
from portfolio_watchdog.models import ReconciliationResult


def test_reconcile_asset_quantities_reports_differences_across_all_symbols() -> None:
    result = reconcile_asset_quantities(
        previous_quantities={"MISSING": 3.0, "SOLD": 2.0},
        transaction_quantity_deltas={"SOLD": -2.0, "NEW": 1.0},
        actual_quantities={"NEW": 1.0, "EXTRA": 4.0},
        tolerance=0.0,
    )

    assert result == ReconciliationResult(
        status="reconciliation_required",
        differences={"EXTRA": 4.0, "MISSING": -3.0},
        tolerance=0.0,
    )


def test_reconcile_asset_quantities_rounds_reported_differences() -> None:
    result = reconcile_asset_quantities(
        previous_quantities={"BTC": 0.0},
        transaction_quantity_deltas={},
        actual_quantities={"BTC": 0.1234567890126},
        tolerance=0.0,
    )

    assert result.differences == {"BTC": 0.123456789013}


def test_reconcile_asset_quantities_allows_difference_exactly_at_tolerance() -> None:
    result = reconcile_asset_quantities(
        previous_quantities={},
        transaction_quantity_deltas={},
        actual_quantities={"BTC": 0.5},
        tolerance=0.5,
    )

    assert result == ReconciliationResult(
        status="reconciled",
        differences={},
        tolerance=0.5,
    )


def test_reconcile_asset_quantities_allows_decimal_difference_at_tolerance() -> None:
    result = reconcile_asset_quantities(
        previous_quantities={"BTC": 0.3},
        transaction_quantity_deltas={},
        actual_quantities={"BTC": 0.4},
        tolerance=0.1,
    )

    assert result.status == "reconciled"
    assert result.differences == {}


def test_reconcile_asset_quantities_reports_decimal_difference_over_tolerance() -> None:
    result = reconcile_asset_quantities(
        previous_quantities={},
        transaction_quantity_deltas={},
        actual_quantities={"BTC": 1.0000000000005},
        tolerance=1.0,
    )

    assert result.status == "reconciliation_required"
    assert "BTC" in result.differences


def test_reconcile_asset_quantities_preserves_small_transaction_delta() -> None:
    result = reconcile_asset_quantities(
        previous_quantities={"BTC": 1.0},
        transaction_quantity_deltas={"BTC": 1e-28},
        actual_quantities={"BTC": 1.0},
        tolerance=0.0,
    )

    assert result.status == "reconciliation_required"
    assert "BTC" in result.differences


@pytest.mark.parametrize("tolerance", [-1.0, float("nan"), float("inf"), float("-inf")])
def test_reconcile_asset_quantities_rejects_invalid_tolerance(tolerance) -> None:
    with pytest.raises(ValueError, match="tolerance"):
        reconcile_asset_quantities({}, {}, {}, tolerance)


@pytest.mark.parametrize(
    ("field", "previous_quantities", "transaction_quantity_deltas", "actual_quantities"),
    [
        ("previous_quantities", {"BTC": float("nan")}, {}, {}),
        ("transaction_quantity_deltas", {}, {"BTC": float("inf")}, {}),
        ("actual_quantities", {}, {}, {"BTC": float("-inf")}),
    ],
)
def test_reconcile_asset_quantities_rejects_non_finite_quantities(
    field, previous_quantities, transaction_quantity_deltas, actual_quantities
) -> None:
    with pytest.raises(ValueError, match=field):
        reconcile_asset_quantities(
            previous_quantities,
            transaction_quantity_deltas,
            actual_quantities,
            tolerance=0.0,
        )


def test_reconciliation_result_is_frozen() -> None:
    result = ReconciliationResult("reconciled", {}, 0.0)

    with pytest.raises(FrozenInstanceError):
        result.status = "reconciliation_required"
