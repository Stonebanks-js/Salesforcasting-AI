"""Producer runner: executes all enabled producers on a schedule loop and
reports health to the signals.health topic (consumed by health_sync job).

Config comes from a JSON snapshot file (PRODUCER_CONFIG_JSON) — populated by
the platform from Supabase user settings. Producers never hold Supabase
credentials (security boundary).
"""
import json
import logging
import os
import time
from datetime import datetime, timezone

from shared.cache import DiskCache

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("runner")

CONFIG_PATH = os.environ.get("PRODUCER_CONFIG_JSON", "/config/producers.json")
CACHE_DIR = os.environ.get("CACHE_DIR", "/cache")
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
HEALTH_TOPIC = "signals.health"
CYCLE_SECONDS = int(os.environ.get("PRODUCER_CYCLE_SECONDS", str(6 * 3600)))


class KafkaPublisher:
    def __init__(self) -> None:
        from kafka import KafkaProducer

        self._producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8"),
            retries=3,
        )

    def publish(self, topic: str, key: str, payload: dict) -> None:
        self._producer.send(topic, key=key, value=payload)


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def build_producers(config: dict, publisher, cache: DiskCache) -> list:
    from events.producer import EventsProducer, Location as EvLocation
    from holidays.producer import HolidaysProducer
    from macro.producer import MacroProducer
    from marketplace.producer import MarketplaceProducer
    from trends.producer import TrendsProducer
    from weather.producer import Location, WeatherProducer

    producers = []
    enabled = set(config.get("enabled_signals", []))
    locations = [Location(**loc) for loc in config.get("locations", [])]

    if "weather" in enabled and locations:
        producers.append(WeatherProducer(publisher, cache, locations))
    if "holidays" in enabled and config.get("country_codes"):
        producers.append(HolidaysProducer(publisher, cache, config["country_codes"]))
    if "trends" in enabled and config.get("category_keywords"):
        producers.append(TrendsProducer(
            publisher, cache, config["category_keywords"], config.get("geo_by_user", {})))
    if "macro" in enabled:
        series = tuple(config.get("series") or ("CPIAUCSL", "UMCSENT", "UNRATE", "PCE"))
        producers.append(MacroProducer(publisher, cache, series=series))
    if "events" in enabled and locations:
        producers.append(EventsProducer(publisher, cache,
                                        [EvLocation(**vars(loc)) for loc in locations]))
    if "marketplace" in enabled and config.get("asins_by_user"):
        producers.append(MarketplaceProducer(publisher, cache, config["asins_by_user"]))
    return producers


def run_cycle(publisher, cache: DiskCache, config: dict | None = None) -> None:
    config = config or load_config()
    for producer in build_producers(config, publisher, cache):
        try:
            report = producer.run_once()
        except Exception:  # noqa: BLE001 - one bad producer must not kill the cycle
            logger.exception("producer %s crashed", producer.source)
            continue
        logger.info("%s: status=%s published=%d from_cache=%s",
                    report.source, report.status, report.published, report.from_cache)
        publisher.publish(HEALTH_TOPIC, key=report.source, payload={
            "source": report.source,
            "status": report.status,
            "error": report.error,
            "published": report.published,
            "last_success_at": (
                producer.last_success_at.isoformat()
                if producer.last_success_at else None
            ),
            "reported_at": datetime.now(timezone.utc).isoformat(),
        })


def main() -> None:
    publisher = KafkaPublisher()
    cache = DiskCache(CACHE_DIR)
    logger.info("producer runner starting; cycle=%ds", CYCLE_SECONDS)
    while True:
        run_cycle(publisher, cache)
        time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    main()
