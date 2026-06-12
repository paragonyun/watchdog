import math


def calculate_drawdowns(values: list[float]) -> list[float]:
    for value in values:
        try:
            valid = math.isfinite(value) and value >= 0
        except TypeError:
            valid = False
        if not valid:
            raise ValueError("values must contain non-negative finite numbers")

    drawdowns = []
    peak = 0.0
    for value in values:
        peak = max(peak, value)
        drawdowns.append((value - peak) / peak * 100 if peak > 0 else 0)
    return drawdowns
