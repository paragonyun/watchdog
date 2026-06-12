import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence


@dataclass(frozen=True)
class BenchmarkWeight:
    effective_from: date
    asset_group: str
    weight: float
    benchmark_symbol: str


def calculate_blended_benchmark(
    weights: Sequence[BenchmarkWeight], returns: Mapping[str, float]
) -> float:
    validated_weights = _validate_weights(weights)
    for symbol, value in returns.items():
        if not _is_finite(value):
            raise ValueError(f"benchmark return for {symbol} must be finite")
    for weight in validated_weights:
        if weight.benchmark_symbol not in returns:
            raise ValueError(f"missing benchmark return for {weight.benchmark_symbol}")
    return math.fsum(
        weight.weight * returns[weight.benchmark_symbol]
        for weight in validated_weights
    )


def _validate_weights(weights: Sequence[BenchmarkWeight]) -> list[BenchmarkWeight]:
    validated = list(weights)
    if not validated:
        raise ValueError("weights must not be empty")

    effective_from = validated[0].effective_from
    asset_groups = set()
    for weight in validated:
        if type(weight.effective_from) is not date:
            raise ValueError("effective_from must be a date")
        if not isinstance(weight.asset_group, str) or not weight.asset_group:
            raise ValueError("asset_group must be a non-empty string")
        if not isinstance(weight.benchmark_symbol, str) or not weight.benchmark_symbol:
            raise ValueError("benchmark_symbol must be a non-empty string")
        if not _is_finite(weight.weight) or weight.weight < 0:
            raise ValueError("weight must be finite and nonnegative")
        if weight.effective_from != effective_from:
            raise ValueError("weights must have the same effective_from")
        if weight.asset_group in asset_groups:
            raise ValueError(f"duplicate asset_group: {weight.asset_group}")
        asset_groups.add(weight.asset_group)

    if abs(math.fsum(weight.weight for weight in validated) - 1.0) > 0.0001:
        raise ValueError("weight sum must be within 0.0001 of 1.0")
    return validated


def _is_finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except TypeError:
        return False
