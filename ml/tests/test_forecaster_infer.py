from datetime import date, timedelta

from ml.factors import direction_sign, top_factors
from ml.forecaster import forecast_with_model, recursive_forecast
from ml.infer import build_future_context, infer_all


class LagSevenEcho:
    """Fake model: predicts the value from 7 days ago — verifies recursion."""

    def __init__(self):
        self.seen_histories = []

    def predict(self, rows):
        out = []
        for r in rows:
            v = r.get("lag_7") or r.get("roll_mean_7") or 0.0
            out.append({"yhat": v, "yhat_lower": v - 1, "yhat_upper": v + 1})
        return out


def test_recursive_forecast_feeds_predictions_back():
    history = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    model = LagSevenEcho()
    start = date(2026, 7, 27)
    preds = recursive_forecast(model, history, start, horizon=14)
    assert len(preds) == 14
    # First week echoes history; second week must echo *predictions* (recursion).
    assert [p["yhat"] for p in preds[:7]] == history
    assert [p["yhat"] for p in preds[7:]] == history


def test_forecast_with_model_falls_back_to_baseline():
    history = [10.0] * 14
    start = date(2026, 7, 27)
    # chosen=lightgbm but artifact missing -> baseline (NFR-3 at serving).
    preds = forecast_with_model("lightgbm", None, history, start, 7)
    assert all(p["yhat"] == 10.0 for p in preds)


def test_build_future_context_ranges_and_trends_carryover():
    start = date(2026, 7, 27)
    ctx = build_future_context(
        calendar_rows=[
            {"user_id": "u1", "date": "2026-07-27", "is_holiday": True,
             "days_to_holiday": 0, "is_school_break": False},
            {"user_id": "u1", "date": "2026-06-01", "is_holiday": True,
             "days_to_holiday": 0, "is_school_break": False},  # out of range
        ],
        weather_rows=[{"user_id": "u1", "date": "2026-07-28",
                       "temp_avg": 30.0, "precip_mm": 2.0}],
        events_rows=[],
        trends_rows=[{"user_id": "u1", "date": "2026-07-20", "interest": 66}],
        start=start, horizon=7,
    )
    assert ctx[("u1", "2026-07-27")]["is_holiday"] is True
    assert ("u1", "2026-06-01") not in ctx
    assert ctx[("u1", "2026-07-28")]["temp_avg"] == 30.0
    assert ctx[("u1", "2026-07-27")]["trends_interest"] == 66  # last-known fill


def test_infer_all_emits_gold_rows():
    today = date.today()
    start = today + timedelta(days=1)
    models = {
        ("u1", "S1"): {
            "chosen": "seasonal-naive", "model": None,
            "model_run_id": "run-1", "model_version": "seasonal-naive",
            "mape_backtest": 18.5,
            "factors": [{"factor": "days_to_holiday", "importance": 0.6,
                         "direction": "up"}],
        }
    }
    history = {("u1", "S1"): [float(i % 7 + 5) for i in range(60)]}
    forecasts, factors = infer_all(models, history, {}, start, horizon=7,
                                   batch_run_id="nightly-20260727")

    assert len(forecasts) == 7
    row = forecasts[0]
    assert row["forecast_date"] == start.isoformat()
    # Served run id is the nightly BATCH id, not the per-SKU MLflow run id.
    assert row["model_run_id"] == "nightly-20260727"
    assert all(f["model_run_id"] == "nightly-20260727" for f in forecasts)
    assert row["yhat_lower"] <= row["yhat"] <= row["yhat_upper"]
    assert len(factors) == 1 and factors[0]["factor"] == "days_to_holiday"


def test_factors_excludes_lags_and_limits_to_five():
    importances = {
        "lag_1": 0.4, "temp_avg": 0.3, "trends_interest": 0.2,
        "days_to_holiday": 0.1, "event_count": 0.05, "is_holiday": 0.02,
        "precip_mm": 0.01, "roll_mean_7": 0.5,
    }
    rows = [
        {"temp_avg": float(i), "trends_interest": float(100 - i),
         "days_to_holiday": float(i % 5), "event_count": i % 2,
         "is_holiday": i % 3 == 0, "precip_mm": float(i % 4),
         "quantity": float(i * 2)}
        for i in range(30)
    ]
    factors = top_factors(importances, rows, k=5)
    names = [f["factor"] for f in factors]
    assert "lag_1" not in names and "roll_mean_7" not in names
    assert len(factors) <= 5
    assert factors[0]["factor"] == "temp_avg"  # highest non-lag importance
    assert abs(sum(f["importance"] for f in factors) - 1.0) < 1e-2  # 4-dp rounding


def test_direction_sign():
    up_rows = [{"f": float(i), "quantity": float(i)} for i in range(20)]
    down_rows = [{"f": float(i), "quantity": float(100 - i)} for i in range(20)]
    flat_rows = [{"f": 1.0, "quantity": float(i)} for i in range(20)]
    assert direction_sign(up_rows, "f") == "up"
    assert direction_sign(down_rows, "f") == "down"
    assert direction_sign(flat_rows, "f") == "neutral"
    assert direction_sign([], "f") == "neutral"
