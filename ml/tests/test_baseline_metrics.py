from datetime import date

from ml.baseline import seasonal_naive
from ml.metrics import mape, rmse


def test_seasonal_naive_repeats_last_week():
    history = [10, 20, 30, 40, 50, 60, 70] * 4
    preds = seasonal_naive(history, date(2026, 7, 27), horizon=7)
    assert [p["yhat"] for p in preds] == [10, 20, 30, 40, 50, 60, 70]


def test_baseline_intervals_ordered_and_widening():
    # Slightly noisy history so the residual scale is non-zero.
    history = [float(i % 7 + 1) + (i % 3) * 0.5 for i in range(56)]
    preds = seasonal_naive(history, date(2026, 7, 27), horizon=14)
    for p in preds:
        assert p["yhat_lower"] <= p["yhat"] <= p["yhat_upper"]
    spreads = [p["yhat_upper"] - p["yhat"] for p in preds]
    assert spreads[-1] > spreads[0]  # uncertainty grows with horizon


def test_baseline_with_short_history_uses_mean():
    preds = seasonal_naive([5.0, 7.0], date(2026, 7, 27), horizon=3)
    assert all(p["yhat"] == 6.0 for p in preds)


def test_mape_skips_zero_actuals():
    assert mape([10, 0, 20], [11, 5, 18]) == (10.0 + 10.0) / 2
    assert mape([0, 0], [1, 2]) is None


def test_rmse():
    assert rmse([1, 2, 3], [1, 2, 3]) == 0.0
    assert rmse([], []) is None
