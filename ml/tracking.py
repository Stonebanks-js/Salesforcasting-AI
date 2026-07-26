"""MLflow tracking wrapper — optional dependency.

Mirrors the NullProducer pattern: when mlflow is not installed or
MLFLOW_TRACKING_URI is unset, tracking is a no-op so training/inference still
run (useful in tests and minimal environments).
"""
import os
import uuid
from typing import Any


class NullTracker:
    def __init__(self) -> None:
        self.run_id = f"local-{uuid.uuid4().hex[:12]}"

    def __enter__(self) -> "NullTracker":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def log_params(self, params: dict[str, Any]) -> None: ...
    def log_metrics(self, metrics: dict[str, float]) -> None: ...
    def log_artifact(self, path: str) -> None: ...


class MLflowTracker(NullTracker):
    def __init__(self, experiment: str) -> None:
        import mlflow

        mlflow.set_experiment(experiment)
        self._run = mlflow.start_run()
        self.run_id = self._run.info.run_id

    def __enter__(self) -> "MLflowTracker":
        return self

    def __exit__(self, *exc) -> bool:
        import mlflow

        mlflow.end_run()
        return False

    def log_params(self, params: dict[str, Any]) -> None:
        import mlflow

        mlflow.log_params({k: str(v) for k, v in params.items()})

    def log_metrics(self, metrics: dict[str, float]) -> None:
        import mlflow

        mlflow.log_metrics({k: v for k, v in metrics.items() if v is not None})

    def log_artifact(self, path: str) -> None:
        import mlflow

        mlflow.log_artifact(path)


def get_tracker(experiment: str = "trendcast-forecasts") -> NullTracker:
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        return NullTracker()
    try:
        import mlflow  # noqa: F401
    except ImportError:
        return NullTracker()
    try:
        return MLflowTracker(experiment)
    except Exception:  # noqa: BLE001 - tracking must never break training
        return NullTracker()
