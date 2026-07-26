"""Parse-function tests with representative API payloads per source."""
from weather.producer import Location, WeatherProducer, parse_daily
from holidays.producer import HolidaysProducer, parse_holidays
from trends.producer import TrendsProducer, parse_trends
from macro.producer import MacroProducer, parse_observations
from events.producer import EventsProducer, parse_events
from marketplace.producer import MarketplaceProducer, parse_products
from shared.cache import DiskCache
from shared.http import FetchResult


class Pub:
    def __init__(self):
        self.events = []

    def publish(self, topic, key, payload):
        self.events.append((topic, key, payload))


# --- weather -----------------------------------------------------------------
OPEN_METEO = {
    "daily": {
        "time": ["2026-07-26", "2026-07-27"],
        "temperature_2m_max": [31.5, 32.1],
        "temperature_2m_min": [20.2, 21.0],
        "temperature_2m_mean": [25.8, 26.4],
        "precipitation_sum": [0.0, 4.2],
        "snowfall_sum": [0.0, 0.0],
        "weather_code": [1, 61],
    }
}


def test_weather_parse():
    records = parse_daily("u1", OPEN_METEO)
    assert len(records) == 2
    key, day, payload = records[1]
    assert key == "u1" and day == "2026-07-27"
    assert payload["temp_max"] == 32.1 and payload["precip_mm"] == 4.2


def test_weather_producer_end_to_end(tmp_path):
    loc = Location(user_id="u1", latitude=30.27, longitude=-97.74)
    producer = WeatherProducer(Pub(), DiskCache(tmp_path), [loc],
                               fetcher=lambda *a, **k: FetchResult(True, 200, OPEN_METEO))
    report = producer.run_once()
    assert report.status == "live" and report.published == 2


def test_weather_producer_failure_falls_back(tmp_path):
    pub = Pub()
    cache = DiskCache(tmp_path)
    loc = Location(user_id="u1", latitude=30.27, longitude=-97.74)
    ok = WeatherProducer(pub, cache, [loc],
                         fetcher=lambda *a, **k: FetchResult(True, 200, OPEN_METEO))
    ok.run_once()
    pub.events.clear()
    failing = WeatherProducer(pub, cache, [loc],
                              fetcher=lambda *a, **k: FetchResult(False, 500, None, "http_500"))
    report = failing.run_once()
    assert report.from_cache and report.published == 2


# --- holidays ----------------------------------------------------------------
NAGER = [
    {"date": "2026-12-25", "localName": "Christmas Day", "name": "Christmas Day",
     "global": True, "counties": None},
    {"date": "2026-11-26", "localName": "Thanksgiving", "name": "Thanksgiving Day",
     "global": False, "counties": ["US-TX"]},
]


def test_holidays_parse():
    records = parse_holidays("US", NAGER)
    assert len(records) == 2
    assert records[0][0] == "US:2026-12-25"
    assert records[1][2]["counties"] == ["US-TX"]


def test_holidays_fetch_both_years(tmp_path):
    producer = HolidaysProducer(Pub(), DiskCache(tmp_path), ["US"],
                                fetcher=lambda *a, **k: FetchResult(True, 200, NAGER))
    report = producer.run_once()
    assert report.published == 4  # 2 holidays x 2 years


# --- trends ------------------------------------------------------------------
def test_trends_parse():
    data = {"coffee maker": [("2026-07-20", 45), ("2026-07-21", 52)]}
    records = parse_trends("u1", "kitchenware", data)
    assert len(records) == 2
    assert records[0][0] == "u1:kitchenware:coffee maker"
    assert records[1][2]["interest"] == 52


def test_trends_producer_batches_keywords(tmp_path):
    calls = []

    def fake_fetch(keywords, geo):
        calls.append((keywords, geo))
        return {k: [("2026-07-21", 10)] for k in keywords}

    producer = TrendsProducer(
        Pub(), DiskCache(tmp_path),
        {"u1:kitchenware": ["a", "b", "c", "d"]},  # 4 keywords -> capped to 3
        {"u1": "US"},
        fetcher=fake_fetch,
    )
    report = producer.run_once()
    assert report.published == 3
    assert calls[0][0] == ["a", "b", "c"] and calls[0][1] == "US"


# --- macro -------------------------------------------------------------------
FRED = {
    "observations": [
        {"date": "2026-06-01", "value": "322.561"},
        {"date": "2026-05-01", "value": "."},      # FRED missing marker -> skipped
        {"date": "2026-04-01", "value": "321.050"},
    ]
}


def test_macro_parse_skips_missing():
    records = parse_observations("CPIAUCSL", FRED)
    assert len(records) == 2
    assert records[0][2] == {"series": "CPIAUCSL", "value": 322.561}


def test_macro_requires_api_key(tmp_path):
    producer = MacroProducer(Pub(), DiskCache(tmp_path), api_key="")
    report = producer.run_once()
    assert report.status == "degraded"
    assert "FRED_API_KEY" in report.error


# --- events ------------------------------------------------------------------
TICKETMASTER = {
    "_embedded": {
        "events": [
            {"id": "E1", "name": "Stadium Concert",
             "dates": {"start": {"localDate": "2026-08-01"}},
             "classifications": [{"segment": {"name": "Music"}}],
             "_embedded": {"venues": [{"name": "City Stadium"}]}},
            {"id": "E2", "name": "No Date Event", "dates": {"start": {}}},
        ]
    }
}


def test_events_parse():
    records = parse_events("u1", TICKETMASTER)
    assert len(records) == 1  # event without a date is skipped
    key, day, payload = records[0]
    assert key == "u1:E1" and day == "2026-08-01"
    assert payload["category"] == "Music" and payload["large_venue"] is True


def test_events_404_is_empty_not_failure(tmp_path):
    loc = Location(user_id="u1", latitude=30.27, longitude=-97.74)
    producer = EventsProducer(
        Pub(), DiskCache(tmp_path), [loc], api_key="k",
        fetcher=lambda *a, **k: FetchResult(False, 404, None, "http_404"),
    )
    report = producer.run_once()
    assert report.status == "live" and report.published == 0


# --- marketplace ---------------------------------------------------------------
KEEPA = {
    "products": [
        {"asin": "B08XYZ1234", "title": "Widget",
         "csv": [[5300000, 1299, 5300001, 1199],  # price history (cents)
                 [], [], [5300000, 4500, 5300001, 3200]]},  # csv[3] = BSR
    ]
}


def test_marketplace_parse():
    records = parse_products("u1", KEEPA)
    assert len(records) == 1
    key, day, payload = records[0]
    assert key == "u1:B08XYZ1234"
    assert payload["price"] == 11.99   # last price, cents -> dollars
    assert payload["bsr"] == 3200      # last BSR


def test_marketplace_respects_token_bucket(tmp_path, monkeypatch):
    import marketplace.producer as mp

    class EmptyBucket:
        def acquire(self, tokens=1.0, timeout=60.0):
            return False

    monkeypatch.setattr(mp, "BUCKET", EmptyBucket())
    producer = MarketplaceProducer(Pub(), DiskCache(tmp_path),
                                   {"u1": ["B08XYZ1234"]}, api_key="k")
    report = producer.run_once()
    assert report.status == "degraded"
    assert "token budget" in report.error
