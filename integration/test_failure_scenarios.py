"""Failure-scenario suite (contract §16): free-tier limits hit mid-forecast,
feeds down, Kafka down — the system must degrade, never break.
"""
from datetime import date, timedelta

from app.services.csv_sales import load_sales_upload
from ml.backtest import run_backtest
from ml.forecaster import forecast_with_model
from shared.cache import DiskCache
from shared.http import FetchResult
from tests.fakes import FakeDb
from transforms.features import build_feature_rows
from weather.producer import Location, WeatherProducer

from helpers import synth_csv


class Pub:
    def __init__(self):
        self.events = []

    def publish(self, topic, key, payload):
        self.events.append((topic, key, payload))


class RaisingProducer:
    def publish(self, topic, key, payload):
        raise ConnectionError("broker unreachable")


def fail_fetch(*a, **k):
    return FetchResult(False, 503, None, "http_503")


def test_kafka_down_does_not_break_upload(tmp_path):
    """Decision 010: sales are durable in Postgres; the stream is best-effort."""
    db = FakeDb()
    db.seed("uploads", [{"id": "x", "user_id": "u1", "kind": "sales",
                         "file_path": "u1/f.csv", "status": "pending"}])
    load_sales_upload(db, RaisingProducer(), user_id="u1", upload_id="x",
                      content=synth_csv(days=90), max_rows=100_000, max_skus=500)
    upload = db.tables["uploads"][0]
    assert upload["status"] == "loaded"
    assert len(db.tables["sales_daily"]) == 180


def test_all_feeds_down_producers_degrade(tmp_path):
    """Every producer reports degraded with no cache; none raise."""
    producer = WeatherProducer(Pub(), DiskCache(tmp_path),
                               [Location("u1", 30.27, -97.74)], fetcher=fail_fetch)
    report = producer.run_once()
    assert report.status == "degraded" and report.published == 0
    assert "http_503" in report.error


def test_feeds_down_forecast_still_works_via_baseline(tmp_path):
    """NFR-3 chain: no external features -> selection forces baseline ->
    forecast still produced and marked degraded upstream."""
    import math

    from helpers import trends_lookup

    # Build features with ALL external lookups empty (total feed outage).
    sales = [
        {"user_id": "u1", "sku": "S1",
         "date": (date.today() - timedelta(days=150 - i)).isoformat(),
         "quantity": float(20 + 5 * math.sin(i / 7)), "promo_flag": False,
         "gap_flag": False}
        for i in range(151)
    ]
    features = build_feature_rows(sales)  # no weather/calendar/trends/events
    result = run_backtest("S1", features, horizon=60)
    assert result.external_null_frac > 0.5
    assert result.chosen == "seasonal-naive"  # degradation rule (decision 017)

    history = [r["quantity"] for r in sales]
    preds = forecast_with_model(result.chosen, None, history,
                                date.today() + timedelta(days=1), 7)
    assert len(preds) == 7
    assert all(p["yhat"] >= 0 for p in preds)
    assert trends_lookup(0) is not None  # sanity: helpers unaffected


def test_keepa_token_exhaustion_skips_cycle_not_crashes(tmp_path, monkeypatch):
    """Keepa quota hit mid-night: cycle skipped, other signals unaffected."""
    import marketplace.producer as mp
    from marketplace.producer import MarketplaceProducer

    class EmptyBucket:
        def acquire(self, tokens=1.0, timeout=60.0):
            return False

    monkeypatch.setattr(mp, "BUCKET", EmptyBucket())
    pub = Pub()
    report = MarketplaceProducer(pub, DiskCache(tmp_path),
                                 {"u1": ["B08XYZ1234"]}, api_key="k").run_once()
    assert report.status == "degraded"
    assert "token budget" in report.error
    assert pub.events == []  # nothing partial published
