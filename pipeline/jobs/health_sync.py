"""Health sync: consume signals.health -> upsert Supabase signal_status.

Producers never hold Supabase credentials (security boundary); they report
health to Kafka and this job owns the serving-table writes.
"""
import json
import os

from jobs.common import KAFKA_BOOTSTRAP, TOPICS, get_spark

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def main() -> None:
    from supabase import create_client

    spark = get_spark("trendcast-health-sync")
    raw = (
        spark.read.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", TOPICS["health"])
        .option("startingOffsets", "earliest")
        .load()
    )
    values = [r[0] for r in raw.select(raw["value"].cast("string")).collect()]
    if not values:
        print("[health_sync] no health messages")
        return

    # Keep only the latest report per signal.
    latest: dict[str, dict] = {}
    for v in values:
        msg = json.loads(v)
        payload = msg.get("payload", msg)
        signal = payload.get("source") or payload.get("signal")
        if signal:
            latest[signal] = payload

    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    for signal, payload in latest.items():
        client.table("signal_status").upsert({
            "signal": signal,
            "status": payload.get("status", "degraded"),
            "last_success_at": payload.get("last_success_at"),
            "last_error": payload.get("error"),
        }).execute()
    print(f"[health_sync] upserted status for {len(latest)} signals")
    spark.stop()


if __name__ == "__main__":
    main()
