"""Bronze -> Silver daily alignment for weather, trends, events, marketplace.

Common rule: keep the latest-ingested record per entity per day; stale flags
from producers are carried through so Gold can weight or exclude features.
"""


def latest_per_day(records: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    best: dict[tuple, dict] = {}
    for r in records:
        key = tuple(r[f] for f in key_fields) + (r["date"],)
        if key not in best or str(r.get("ingested_at", "")) >= str(best[key].get("ingested_at", "")):
            best[key] = r
    return sorted(best.values(), key=lambda r: key_fields and tuple(str(r[f]) for f in key_fields) + (r["date"],))


def events_to_daily(records: list[dict]) -> list[dict]:
    """Event records -> per-user per-day counts."""
    counts: dict[tuple[str, str], dict] = {}
    for r in records:
        key = (r["user_id"], r["date"])
        bucket = counts.setdefault(key, {
            "user_id": r["user_id"], "date": r["date"],
            "event_count": 0, "large_event_count": 0, "categories": set(),
        })
        bucket["event_count"] += 1
        if r.get("large_venue"):
            bucket["large_event_count"] += 1
        if r.get("category"):
            bucket["categories"].add(r["category"])
    return [
        {**b, "categories": sorted(b["categories"])}
        for b in sorted(counts.values(), key=lambda b: (b["user_id"], b["date"]))
    ]


def macro_forward_fill(series_points: list[dict], dates: list[str]) -> list[dict]:
    """Monthly macro observations -> daily rows via forward-fill.

    series_points: [{series, date, value}] (any series). Output covers every
    input date; values before the first observation are None.
    """
    by_series: dict[str, dict[str, float]] = {}
    for p in series_points:
        by_series.setdefault(p["series"], {})[p["date"]] = p["value"]

    out: list[dict] = []
    for series, points in by_series.items():
        known = sorted(points.items())
        last: float | None = None
        idx = 0
        for d in sorted(dates):
            while idx < len(known) and known[idx][0] <= d:
                last = known[idx][1]
                idx += 1
            out.append({"series": series, "date": d, "value": last})
    return out
