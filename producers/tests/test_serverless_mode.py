"""Serverless mode (decision 027): SupabasePublisher + CI config assembly."""
from shared.supabase_pub import SupabasePublisher
from runner_ci import build_config_from_supabase


class FakeQuery:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self._cols = None

    def select(self, cols):
        self._cols = cols
        return self

    def upsert(self, rows, on_conflict=None):
        rows = rows if isinstance(rows, list) else [rows]
        key = (on_conflict or "signal").split(",")[0]
        table = self.store.setdefault(self.table, [])
        for row in rows:
            match = next((r for r in table if r.get(key) == row.get(key)), None)
            if match:
                match.update(row)
            else:
                table.append(dict(row))
        return self

    def insert(self, rows):
        rows = rows if isinstance(rows, list) else [rows]
        self.store.setdefault(self.table, []).extend(dict(r) for r in rows)
        return self

    def execute(self):
        data = self.store.get(self.table, [])
        if self._cols and self._cols != "*":
            cols = [c.strip() for c in self._cols.split(",")]
            data = [{c: r.get(c) for c in cols} for r in data]

        class Resp:
            pass
        r = Resp()
        r.data = data
        return r


class FakeClient:
    def __init__(self, seed=None):
        self.store = seed or {}

    def table(self, name):
        return FakeQuery(self.store, name)


def test_publisher_routes_envelopes_to_signal_events():
    client = FakeClient()
    pub = SupabasePublisher(client)
    pub.publish("signals.weather", key="u1", payload={
        "source": "weather", "entity_key": "u1", "observed_at": "2026-07-26",
        "payload": {"user_id": "u1", "temp_avg": 25.0},
    })
    rows = client.store["signal_events"]
    assert len(rows) == 1
    assert rows[0]["source"] == "weather"
    assert rows[0]["observed_at"] == "2026-07-26"
    assert rows[0]["payload"]["temp_avg"] == 25.0


def test_publisher_routes_health_to_signal_status():
    client = FakeClient()
    pub = SupabasePublisher(client)
    pub.publish("signals.health", key="weather", payload={
        "source": "weather", "status": "live", "error": None,
        "last_success_at": "2026-07-26T06:00:00Z",
    })
    rows = client.store["signal_status"]
    assert rows == [{"signal": "weather", "status": "live",
                     "last_success_at": "2026-07-26T06:00:00Z", "last_error": None}]
    # Upsert on conflict key "signal": second report updates, not duplicates.
    pub.publish("signals.health", key="weather", payload={
        "source": "weather", "status": "stale", "error": "http_503",
        "last_success_at": "2026-07-26T06:00:00Z",
    })
    assert len(client.store["signal_status"]) == 1
    assert client.store["signal_status"][0]["status"] == "stale"


def test_build_config_from_supabase():
    client = FakeClient(seed={
        "profiles": [
            {"id": "u1", "country_code": "US", "latitude": 30.3,
             "longitude": -97.7, "timezone": "America/Chicago"},
            {"id": "u2", "country_code": "IN", "latitude": None,
             "longitude": None, "timezone": "UTC"},  # no geo -> no location
        ],
        "signal_settings": [
            {"user_id": "u1", "signal": "weather", "enabled": True},
            {"user_id": "u1", "signal": "trends", "enabled": True},
            {"user_id": "u2", "signal": "marketplace", "enabled": False},
        ],
        "products": [
            {"user_id": "u1", "category": "kitchenware"},
            {"user_id": "u1", "category": "kitchenware"},   # dedupe
            {"user_id": "u1", "category": "apparel"},
            {"user_id": "u1", "category": None},            # skipped
        ],
    })
    config = build_config_from_supabase(client)
    assert config["enabled_signals"] == ["trends", "weather"]
    assert len(config["locations"]) == 1  # u2 lacks geo
    assert config["locations"][0]["user_id"] == "u1"
    assert config["country_codes"] == ["IN", "US"]
    assert config["category_keywords"] == {
        "u1:kitchenware": ["kitchenware"], "u1:apparel": ["apparel"],
    }
    assert config["asins_by_user"] == {}  # marketplace deferred (decision 025)
