import math
from collections.abc import Mapping
from decimal import Decimal, localcontext

from portfolio_watchdog.models import ReconciliationResult


def reconcile_asset_quantities(
    previous_quantities: Mapping[str, float],
    transaction_quantity_deltas: Mapping[str, float],
    actual_quantities: Mapping[str, float],
    tolerance: float,
) -> ReconciliationResult:
    _validate_tolerance(tolerance)
    _validate_quantities(previous_quantities, "previous_quantities")
    _validate_quantities(transaction_quantity_deltas, "transaction_quantity_deltas")
    _validate_quantities(actual_quantities, "actual_quantities")

    symbols = (
        set(previous_quantities)
        | set(transaction_quantity_deltas)
        | set(actual_quantities)
    )
    differences = {}
    with localcontext() as context:
        context.prec = 1000
        decimal_tolerance = Decimal(str(tolerance))
        for symbol in sorted(symbols):
            expected = Decimal(str(previous_quantities.get(symbol, 0.0))) + Decimal(
                str(transaction_quantity_deltas.get(symbol, 0.0))
            )
            difference = Decimal(str(actual_quantities.get(symbol, 0.0))) - expected
            if abs(difference) > decimal_tolerance:
                differences[symbol] = round(float(difference), 12)

    return ReconciliationResult(
        status="reconciliation_required" if differences else "reconciled",
        differences=differences,
        tolerance=tolerance,
    )


def _validate_tolerance(tolerance: float) -> None:
    try:
        valid = math.isfinite(tolerance) and tolerance >= 0
    except TypeError:
        valid = False
    if not valid:
        raise ValueError("tolerance must be a non-negative finite number")


def _validate_quantities(quantities: Mapping[str, float], field: str) -> None:
    for quantity in quantities.values():
        try:
            finite = math.isfinite(quantity)
        except TypeError:
            finite = False
        if not finite:
            raise ValueError(f"{field} values must be finite numbers")
