"""Recursive multi-day forecasting.

Lag/rolling features for future dates depend on earlier predictions, so we
forecast one day at a time, feeding each q50 back into history. Exogenous
context comes from the silver layer (calendar deterministic 2y out, weather
forecast 16d, events known-future, trends/macro last-known — per the
graceful-degradation design).
"""
from datetime import date, timedelta
from typing import Protocol

from ml.baseline import seasonal_naive
from ml.featurespec import build_inference_row


class PointForecaster(Protocol):
    def predict(self, rows: list[dict]) -> list[dict]: ...


def recursive_forecast(
    model: PointForecaster,
    history: list[float],
    start: date,
    horizon: int,
    exog_by_date: dict[str, dict] | None = None,
) -> list[dict]:
    """Return [{date, yhat, yhat_lower, yhat_upper}] for `horizon` days."""
    exog_by_date = exog_by_date or {}
    hist = list(history)
    out: list[dict] = []
    for step in range(horizon):
        day = start + timedelta(days=step)
        row = build_inference_row(day, hist, exog_by_date.get(day.isoformat(), {}))
        pred = model.predict([row])[0]
        out.append({
            "date": day.isoformat(),
            "yhat": pred["yhat"],
            "yhat_lower": pred["yhat_lower"],
            "yhat_upper": pred["yhat_upper"],
        })
        hist.append(pred["yhat"])  # recursive feedback
    return out


def forecast_with_model(
    chosen: str,
    model: PointForecaster | None,
    history: list[float],
    start: date,
    horizon: int,
    exog_by_date: dict[str, dict] | None = None,
) -> list[dict]:
    """Dispatch on the per-SKU selection result; baseline needs no artifact."""
    if chosen == "lightgbm" and model is not None:
        return recursive_forecast(model, history, start, horizon, exog_by_date)
    return seasonal_naive(history, start, horizon)
