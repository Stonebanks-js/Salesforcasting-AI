"""Seasonal-naive baseline (weekly seasonality) — always computed.

Purpose (decision 006): honest comparison point for model selection AND the
automatic fallback when external features are missing/stale. Intervals widen
with horizon via residual variance of weekly differences.
"""
from datetime import date, timedelta

Z_80 = 1.2816  # two-sided 80% interval


def seasonal_naive(
    history: list[float],
    start: date,
    horizon: int,
) -> list[dict]:
    """Forecast `horizon` days after the last history point.

    yhat[d] = value from the same weekday last week; falls back to the
    trailing 28-day mean when fewer than 7 history points exist.
    """
    tail_mean = sum(history[-28:]) / len(history[-28:]) if history else 0.0

    # Residual scale from weekly differences (robust enough for a baseline).
    diffs = [history[i] - history[i - 7] for i in range(7, len(history))]
    if diffs:
        sigma = (sum(d * d for d in diffs) / len(diffs)) ** 0.5
    else:
        sigma = max(tail_mean * 0.2, 1.0)

    out = []
    for step in range(1, horizon + 1):
        idx = len(history) + step - 1
        if idx - 7 >= 0:
            yhat = (history + [p["yhat"] for p in out])[idx - 7]
        else:
            yhat = tail_mean
        spread = Z_80 * sigma * (step ** 0.5)
        out.append({
            "date": (start + timedelta(days=step - 1)).isoformat(),
            "yhat": max(yhat, 0.0),
            "yhat_lower": max(yhat - spread, 0.0),
            "yhat_upper": yhat + spread,
        })
    return out
