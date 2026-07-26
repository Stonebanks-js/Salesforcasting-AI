from ml.backtest import choose_model, external_null_fraction, run_backtest
from ml.tests.synth import daily_series


def test_choose_model_prefers_lgbm_when_better():
    assert choose_model(20.0, 12.0, 0.1) == "lightgbm"


def test_choose_model_baseline_wins_ties_and_worse():
    assert choose_model(12.0, 12.0, 0.1) == "seasonal-naive"
    assert choose_model(10.0, 15.0, 0.1) == "seasonal-naive"


def test_choose_model_degrades_on_missing_signals():
    # >50% null external features -> baseline regardless of MAPE (NFR-3).
    assert choose_model(25.0, 8.0, 0.7) == "seasonal-naive"


def test_choose_model_handles_none_mape():
    assert choose_model(15.0, None, 0.1) == "seasonal-naive"
    assert choose_model(None, 12.0, 0.1) == "lightgbm"


def test_external_null_fraction():
    rows = [
        {"temp_avg": 20, "trends_interest": None, "days_to_holiday": 3, "event_count": 0},
        {"temp_avg": None, "trends_interest": None, "days_to_holiday": None, "event_count": 1},
    ]
    # 4 nulls of 8 feature slots.
    assert external_null_fraction(rows) == 4 / 8
    assert external_null_fraction([]) == 1.0


def test_run_backtest_produces_both_mapes():
    rows = daily_series(400)
    result = run_backtest("S1", rows, horizon=60)
    assert result.mape_baseline is not None
    assert result.mape_lgbm is not None
    assert result.chosen in ("lightgbm", "seasonal-naive")
    # On this learnable series, LightGBM should be competitive.
    assert result.mape_lgbm < result.mape_baseline + 15


def test_run_backtest_insufficient_data_falls_back():
    rows = daily_series(300)[:80]  # train = 20 rows after 60-day holdout
    result = run_backtest("S1", rows, horizon=60)
    assert result.mape_lgbm is None
    assert result.chosen == "seasonal-naive"
    assert result.mape_baseline is not None
