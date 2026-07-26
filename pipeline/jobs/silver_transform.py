"""Silver transform: Bronze -> Silver using the pure transforms core.

Strategy: read bronze payloads, explode JSON, hand rows to the unit-tested
pure functions via pandas maps at modest pilot scale, write silver Delta.
"""
import json

from jobs.common import delta_path, get_spark
from transforms import sales as sales_t
from transforms import signals_daily


def _payloads(spark, bronze_table: str) -> list[dict]:
    df = spark.read.format("delta").load(delta_path(bronze_table))
    rows = []
    for r in df.select("payload", "ingested_at").collect():
        payload = json.loads(r["payload"])
        payload["ingested_at"] = r["ingested_at"]
        rows.append(payload)
    return rows


def _write(spark, table: str, rows: list[dict]) -> None:
    if not rows:
        print(f"[silver] {table}: nothing to write")
        return
    df = spark.createDataFrame(rows)
    df.write.format("delta").mode("overwrite").save(delta_path(table))
    print(f"[silver] {table}: {len(rows)} rows")


def main() -> None:
    spark = get_spark("trendcast-silver")

    # Sales: bronze payloads already carry user_id/sku/date (from the API envelope).
    sales_rows = _payloads(spark, "bronze_sales_raw")
    _write(spark, "silver_sales_daily", sales_t.to_silver(sales_rows))

    # Events: bronze payloads -> daily counts.
    event_rows = _payloads(spark, "bronze_events")
    for r in event_rows:
        r.setdefault("date", r.get("observed_date", ""))
    _write(spark, "silver_events_daily", signals_daily.events_to_daily(event_rows))

    spark.stop()


if __name__ == "__main__":
    main()
