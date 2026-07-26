"""Gold features: Silver -> gold_features via transforms.features.

Per-SKU grouping is done with a driver-side group loop; at pilot scale
(~500 SKUs x ~730 days) this is well within local-mode Spark capacity.
"""
from collections import defaultdict

from jobs.common import delta_path, get_spark
from transforms.features import build_feature_rows


def _index(rows: list[dict], key: str = "date") -> dict[str, dict]:
    return {r[key]: r for r in rows}


def main() -> None:
    spark = get_spark("trendcast-gold-features")

    sales = spark.read.format("delta").load(delta_path("silver_sales_daily")).toPandas().to_dict("records")

    def load(table: str) -> list[dict]:
        try:
            return spark.read.format("delta").load(delta_path(table)).toPandas().to_dict("records")
        except Exception:
            return []  # missing optional signal -> empty lookup (graceful)

    weather = load("silver_weather_daily")
    calendar = load("silver_calendar_daily")
    trends = load("silver_trends_daily")
    events = load("silver_events_daily")

    by_user_sku: dict[tuple, list[dict]] = defaultdict(list)
    for r in sales:
        by_user_sku[(r["user_id"], r["sku"])].append(r)

    def lookup(rows, user_id):
        return _index([r for r in rows if r["user_id"] == user_id])

    feature_rows = []
    for (user_id, sku), sku_sales in by_user_sku.items():
        feature_rows.extend(build_feature_rows(
            sku_sales,
            weather_by_date=lookup(weather, user_id),
            calendar_by_date=lookup(calendar, user_id),
            trends_by_date=lookup(trends, user_id),
            events_by_date=lookup(events, user_id),
        ))

    if feature_rows:
        df = spark.createDataFrame(feature_rows)
        df.write.format("delta").mode("overwrite").save(delta_path("gold_features"))
        print(f"[gold_features] wrote {len(feature_rows)} rows")
    else:
        print("[gold_features] no sales rows; nothing to write")
    spark.stop()


if __name__ == "__main__":
    main()
