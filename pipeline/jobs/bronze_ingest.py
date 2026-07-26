"""Bronze ingest: Kafka topics -> append-only Bronze Delta tables.

Batch (triggered by scheduler) rather than Structured Streaming at pilot
scale — daily micro-batches are sufficient and far simpler to operate.
"""
import sys

from jobs.common import BRONZE_TABLES, KAFKA_BOOTSTRAP, TOPICS, delta_path, get_spark


def ingest_topic(spark, topic_key: str) -> int:
    topic = TOPICS[topic_key]
    raw = (
        spark.read.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .load()
    )
    if raw.rdd.isEmpty():
        return 0

    from pyspark.sql import functions as F

    envelope = raw.select(
        F.col("key").cast("string").alias("entity_key_raw"),
        F.col("value").cast("string").alias("raw_json"),
        F.col("timestamp").alias("kafka_ts"),
    )
    parsed = envelope.select(
        F.get_json_object("raw_json", "$.source").alias("source"),
        F.get_json_object("raw_json", "$.entity_key").alias("entity_key"),
        F.get_json_object("raw_json", "$.observed_at").alias("observed_at"),
        F.get_json_object("raw_json", "$.ingested_at").alias("ingested_at"),
        F.get_json_object("raw_json", "$.schema_version").alias("schema_version"),
        F.get_json_object("raw_json", "$.payload").alias("payload"),
    )
    parsed.write.format("delta").mode("append").save(delta_path(BRONZE_TABLES[topic_key]))
    return parsed.count()


def main() -> None:
    spark = get_spark("trendcast-bronze-ingest")
    topics = sys.argv[1:] or list(BRONZE_TABLES)
    for topic_key in topics:
        count = ingest_topic(spark, topic_key)
        print(f"[bronze_ingest] {topic_key}: {count} records appended")
    spark.stop()


if __name__ == "__main__":
    main()
