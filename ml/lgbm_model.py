"""LightGBM quantile regression (decision 006).

Three boosters (q10/q50/q90) give native prediction intervals; NaN handling is
built into LightGBM, so missing external features degrade gracefully.
"""
import numpy as np

from ml.featurespec import FEATURES

MIN_TRAIN_ROWS = 60


class InsufficientDataError(ValueError):
    pass


class QuantileLGBM:
    version = "lightgbm"

    def __init__(self, quantiles=(0.1, 0.5, 0.9), **lgb_params) -> None:
        self.quantiles = quantiles
        self._params = {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 10,
            "verbose": -1,
            **lgb_params,
        }
        self._models: dict[float, object] = {}
        self.n_features_: int = 0

    @staticmethod
    def _matrix(rows: list[dict]) -> np.ndarray:
        return np.array(
            [[np.nan if r.get(f) is None else float(r[f]) for f in FEATURES] for r in rows],
            dtype=float,
        )

    def fit(self, rows: list[dict]) -> "QuantileLGBM":
        import lightgbm as lgb

        trainable = [r for r in rows if r.get("quantity") is not None]
        if len(trainable) < MIN_TRAIN_ROWS:
            raise InsufficientDataError(
                f"need >= {MIN_TRAIN_ROWS} rows, got {len(trainable)}"
            )
        X = self._matrix(trainable)
        y = np.array([float(r["quantity"]) for r in trainable])
        dataset = lgb.Dataset(X, label=y, feature_name=list(FEATURES))
        for q in self.quantiles:
            params = {
                "objective": "quantile",
                "alpha": q,
                "learning_rate": self._params["learning_rate"],
                "num_leaves": self._params["num_leaves"],
                "min_data_in_leaf": self._params["min_child_samples"],
                "verbose": -1,
                "seed": 42,
            }
            self._models[q] = lgb.train(
                params, dataset, num_boost_round=self._params["n_estimators"]
            )
        self.n_features_ = X.shape[1]
        return self

    def predict(self, rows: list[dict]) -> list[dict]:
        """Return [{yhat, yhat_lower, yhat_upper}] aligned with input rows."""
        if not self._models:
            raise RuntimeError("model is not fitted")
        X = self._matrix(rows)
        preds = {q: m.predict(X) for q, m in self._models.items()}
        qs = sorted(preds)
        out = []
        for i in range(len(rows)):
            lo, mid, hi = (max(preds[q][i], 0.0) for q in (qs[0], qs[1], qs[2]))
            # Quantile crossing guard (rare but possible with small data).
            lo, mid, hi = min(lo, mid, hi), sorted((lo, mid, hi))[1], max(lo, mid, hi)
            out.append({"yhat": mid, "yhat_lower": lo, "yhat_upper": hi})
        return out

    def feature_importances(self) -> dict[str, float]:
        """Normalized gain importances from the median model (0..1)."""
        median = self._models.get(0.5)
        if median is None:
            return {}
        gains = np.asarray(median.feature_importance(importance_type="gain"), dtype=float)
        total = gains.sum()
        weights = gains / total if total > 0 else np.zeros_like(gains)
        names = median.feature_name()
        return {f: float(w) for f, w in zip(names, weights)}
