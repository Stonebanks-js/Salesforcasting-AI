import pytest

from ml.lgbm_model import InsufficientDataError, QuantileLGBM
from ml.metrics import mape
from ml.tests.synth import daily_series


def test_fit_requires_minimum_rows():
    rows = daily_series(300)[:50]
    with pytest.raises(InsufficientDataError):
        QuantileLGBM().fit(rows)


def test_quantile_predictions_ordered():
    rows = daily_series(300)
    model = QuantileLGBM(n_estimators=100).fit(rows[:250])
    preds = model.predict(rows[250:])
    assert len(preds) == 50
    for p in preds:
        assert 0 <= p["yhat_lower"] <= p["yhat"] <= p["yhat_upper"]


def test_lgbm_beats_naive_guess_on_structured_series():
    rows = daily_series(400)
    train, test = rows[:340], rows[340:]
    model = QuantileLGBM(n_estimators=150).fit(train)
    preds = [p["yhat"] for p in model.predict(test)]
    actuals = [r["quantity"] for r in test]
    score = mape(actuals, preds)
    assert score is not None and score < 30.0  # structured series should be learnable


def test_feature_importances_cover_all_features():
    rows = daily_series(200)
    model = QuantileLGBM(n_estimators=50).fit(rows)
    imps = model.feature_importances()
    assert set(imps) == set(rows[0].keys()) - {
        "user_id", "sku", "date", "quantity", "gap_flag"
    }
    assert abs(sum(imps.values()) - 1.0) < 1e-6
