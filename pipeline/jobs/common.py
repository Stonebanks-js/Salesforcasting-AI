"""Spark session + Delta path helpers.

All heavy lifting lives in pipeline/transforms (pure functions, unit-tested);
these jobs are thin IO wrappers: Kafka/Delta in -> transforms -> Delta out.
Pilot scale runs Spark in local mode inside a container (architecture.md §2.6).
"""
import os

DELTA_ROOT = os.environ.get("DELTA_ROOT", "/opt/pipeline/delta")
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

TOPICS = {
    "sales": "sales.raw",
    "weather": "signals.weather",
    "holidays": "signals.holidays",
    "trends": "signals.trends",
    "macro": "signals.macro",
    "events": "signals.events",
    "marketplace": "signals.marketplace",
    "health": "signals.health",
}

BRONZE_TABLES = {
    "sales": "bronze_sales_raw",
    "weather": "bronze_weather",
    "holidays": "bronze_holidays",
    "trends": "bronze_trends",
    "macro": "bronze_macro",
    "events": "bronze_events",
    "marketplace": "bronze_marketplace",
}


def delta_path(table: str) -> str:
    return f"{DELTA_ROOT}/{table}"


def get_spark(app_name: str):
    from pyspark.sql import SparkSession

    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .getOrCreate()
    )
