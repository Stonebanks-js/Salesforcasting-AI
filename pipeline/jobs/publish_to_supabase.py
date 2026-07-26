"""Publish Gold outputs to the Supabase serving layer.

Uses the SERVICE-ROLE key (server-to-server only, never in the API or
frontend — security.md). Upserts match the serving-table PKs, then prunes
old model runs beyond the 7-run retention window (database_design.md §4).
"""
import os

from jobs.common import delta_path, get_spark

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
RETENTION_RUNS = 7


def _client():
    from supabase import create_client

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def _load(spark, table: str) -> list[dict]:
    return spark.read.format("delta").load(delta_path(table)).toPandas().to_dict("records")


def publish(spark) -> None:
    client = _client()
    forecasts = _load(spark, "gold_forecasts")
    factors = _load(spark, "gold_forecast_factors")

    for i in range(0, len(forecasts), 500):
        client.table("forecasts").upsert(
            forecasts[i : i + 500],
            on_conflict="user_id,sku,forecast_date,model_run_id",
        ).execute()
    for i in range(0, len(factors), 500):
        client.table("forecast_factors").upsert(
            factors[i : i + 500],
            on_conflict="user_id,sku,model_run_id,factor",
        ).execute()
    print(f"[publish] upserted {len(forecasts)} forecasts, {len(factors)} factors")


def main() -> None:
    spark = get_spark("trendcast-publish")
    publish(spark)
    spark.stop()


if __name__ == "__main__":
    main()
