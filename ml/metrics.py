"""Forecast quality metrics."""

import math


def mape(actuals: list[float], preds: list[float]) -> float | None:
    """Mean absolute percentage error over non-zero actuals (zero-actual
    points are excluded — MAPE is undefined there; standard practice)."""
    pairs = [(a, p) for a, p in zip(actuals, preds) if a != 0]
    if not pairs:
        return None
    return 100.0 * sum(abs(a - p) / abs(a) for a, p in pairs) / len(pairs)


def rmse(actuals: list[float], preds: list[float]) -> float | None:
    if not actuals:
        return None
    return math.sqrt(
        sum((a - p) ** 2 for a, p in zip(actuals, preds)) / len(actuals)
    )
