"""Training job: gold_features -> per-SKU backtest -> model selection ->
fit final model -> persist artifact + metrics (MLflow when available).

Artifacts live under MODEL_DIR (mounted volume); MLflow (when configured)
mirrors params/metrics/artifacts for the registry view (decision 006).
"""
import json
import os
import pickle
from collections import defaultdict
from datetime import datetime, timezone

from ml.backtest import run_backtest
from ml.factors import top_factors
from ml.lgbm_model import InsufficientDataError, QuantileLGBM
from ml.tracking import get_tracker

MODEL_DIR = os.environ.get("MODEL_DIR", "/opt/models")


def train_all(feature_rows: list[dict], model_dir: str = MODEL_DIR) -> list[dict]:
    """Train/select per (user_id, sku). Returns gold_model_metrics rows."""
    by_sku: dict[tuple, list[dict]] = defaultdict(list)
    for r in feature_rows:
        by_sku[(r["user_id"], r["sku"])].append(r)

    metrics_rows: list[dict] = []
    for (user_id, sku), rows in sorted(by_sku.items()):
        rows = sorted(rows, key=lambda r: r["date"])
        result = run_backtest(sku, rows)

        with get_tracker() as tracker:
            run_id = tracker.run_id
            tracker.log_params({"user_id": user_id, "sku": sku,
                                "chosen": result.chosen})
            tracker.log_metrics({
                "mape_baseline": result.mape_baseline,
                "mape_lgbm": result.mape_lgbm,
            })

            artifact_path = None
            model_version = "seasonal-naive"
            if result.chosen == "lightgbm":
                try:
                    model = QuantileLGBM().fit(rows)
                    artifact_dir = os.path.join(model_dir, user_id, sku)
                    os.makedirs(artifact_dir, exist_ok=True)
                    artifact_path = os.path.join(artifact_dir, "model.pkl")
                    with open(artifact_path, "wb") as fh:
                        pickle.dump(model, fh)
                    model_version = f"lightgbm:{run_id[:8]}"
                    meta = {
                        "user_id": user_id, "sku": sku,
                        "model_run_id": run_id,
                        "model_version": model_version,
                        "mape_backtest": result.mape_lgbm,
                        "factors": top_factors(model.feature_importances(), rows),
                        "trained_at": datetime.now(timezone.utc).isoformat(),
                    }
                    with open(os.path.join(artifact_dir, "meta.json"), "w") as fh:
                        json.dump(meta, fh)
                    tracker.log_artifact(artifact_path)
                except InsufficientDataError:
                    result.chosen = "seasonal-naive"
                    model_version = "seasonal-naive"

            metrics_rows.append({
                "model_run_id": run_id,
                "user_id": user_id,
                "sku": sku,
                "model_version": model_version,
                "mape": result.mape_lgbm if result.chosen == "lightgbm" else result.mape_baseline,
                "mape_baseline": result.mape_baseline,
                "chosen": result.chosen,
                "external_null_frac": round(result.external_null_frac, 4),
                "artifact_path": artifact_path,
                "trained_at": datetime.now(timezone.utc).isoformat(),
            })
    return metrics_rows


def main() -> None:
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from jobs.common import delta_path, get_spark

    spark = get_spark("trendcast-train")
    try:
        rows = (
            spark.read.format("delta").load(delta_path("gold_features"))
            .toPandas().to_dict("records")
        )
    except Exception:
        print("[train] gold_features not found; run gold_features first")
        return

    metrics = train_all(rows)
    if metrics:
        df = spark.createDataFrame(metrics)
        df.write.format("delta").mode("overwrite").save(delta_path("gold_model_metrics"))
        print(f"[train] trained {len(metrics)} SKU models")
    spark.stop()


if __name__ == "__main__":
    main()
