"""Rolling backtest + per-SKU model selection (FR-5.4, decision 006).

Backtest protocol: hold out the last `horizon` days; fit each candidate on
the remainder; compare MAPE on the holdout. LightGBM is evaluated on the
holdout's actual feature rows (one-step-style evaluation — documented
approximation; honest enough for model *selection*).
"""
from dataclasses import dataclass, field
from datetime import date

from ml.baseline import seasonal_naive
from ml.lgbm_model import InsufficientDataError, QuantileLGBM
from ml.metrics import mape

DEFAULT_HORIZON = 60


@dataclass
class BacktestResult:
    sku: str
    mape_baseline: float | None
    mape_lgbm: float | None
    external_null_frac: float
    lgbm_error: str | None = None
    chosen: str = field(init=False)

    def __post_init__(self) -> None:
        self.chosen = choose_model(self.mape_baseline, self.mape_lgbm,
                                   self.external_null_frac)


def external_null_fraction(rows: list[dict]) -> float:
    """Share of nulls across external-signal features — drives degradation."""
    keys = ("temp_avg", "trends_interest", "days_to_holiday", "event_count")
    if not rows:
        return 1.0
    nulls = sum(1 for r in rows for k in keys if r.get(k) is None)
    return nulls / (len(rows) * len(keys))


def choose_model(
    mape_baseline: float | None,
    mape_lgbm: float | None,
    external_null_frac: float,
    degradation_threshold: float = 0.5,
) -> str:
    """Baseline wins ties, missing data, and stale signals — simplest honest
    model wins unless LightGBM is demonstrably better."""
    if external_null_frac > degradation_threshold:
        return "seasonal-naive"
    if mape_lgbm is None:
        return "seasonal-naive"
    if mape_baseline is None:
        return "lightgbm"
    return "lightgbm" if mape_lgbm < mape_baseline else "seasonal-naive"


def run_backtest(
    sku: str,
    rows: list[dict],
    horizon: int = DEFAULT_HORIZON,
) -> BacktestResult:
    rows = sorted(rows, key=lambda r: r["date"])
    train, test = rows[:-horizon], rows[-horizon:]

    actuals = [float(r["quantity"]) for r in test]

    # Baseline.
    history = [float(r["quantity"]) for r in train]
    start = date.fromisoformat(test[0]["date"])
    baseline_preds = [p["yhat"] for p in seasonal_naive(history, start, len(test))]
    mape_base = mape(actuals, baseline_preds)

    # LightGBM.
    mape_lgbm: float | None = None
    lgbm_error: str | None = None
    try:
        model = QuantileLGBM().fit(train)
        lgbm_preds = [p["yhat"] for p in model.predict(test)]
        mape_lgbm = mape(actuals, lgbm_preds)
    except InsufficientDataError as exc:
        lgbm_error = str(exc)

    return BacktestResult(
        sku=sku,
        mape_baseline=mape_base,
        mape_lgbm=mape_lgbm,
        external_null_frac=external_null_fraction(test),
        lgbm_error=lgbm_error,
    )
