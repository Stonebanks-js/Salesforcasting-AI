"""Silver -> Gold feature engineering (pure functions).

build_feature_rows consumes one SKU's daily sales rows plus per-date signal
lookups and emits the model-ready feature matrix. Spark wrappers feed these
functions; unit tests exercise them directly.
"""
from datetime import date

LAGS = (1, 7, 14, 28)
ROLL_WINDOWS = (7, 28)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_feature_rows(
    sales_rows: list[dict],           # silver_sales_daily for ONE sku, any order
    weather_by_date: dict[str, dict] | None = None,
    calendar_by_date: dict[str, dict] | None = None,
    trends_by_date: dict[str, dict] | None = None,
    events_by_date: dict[str, dict] | None = None,
) -> list[dict]:
    """Emit one feature row per sales date, sorted ascending."""
    weather_by_date = weather_by_date or {}
    calendar_by_date = calendar_by_date or {}
    trends_by_date = trends_by_date or {}
    events_by_date = events_by_date or {}

    rows = sorted(sales_rows, key=lambda r: r["date"])
    quantities = [float(r["quantity"]) for r in rows]

    out: list[dict] = []
    for i, r in enumerate(rows):
        d = date.fromisoformat(r["date"])
        features: dict = {
            "user_id": r["user_id"],
            "sku": r["sku"],
            "date": r["date"],
            "quantity": quantities[i],
            "dow": d.weekday(),
            "month": d.month,
            "is_weekend": d.weekday() >= 5,
            "promo_flag": bool(r.get("promo_flag", False)),
            "gap_flag": bool(r.get("gap_flag", False)),
        }
        for lag in LAGS:
            features[f"lag_{lag}"] = quantities[i - lag] if i >= lag else None
        for window in ROLL_WINDOWS:
            segment = quantities[max(0, i - window):i]
            features[f"roll_mean_{window}"] = _mean(segment)

        cal = calendar_by_date.get(r["date"], {})
        features["is_holiday"] = bool(cal.get("is_holiday", False))
        features["days_to_holiday"] = cal.get("days_to_holiday")
        features["is_school_break"] = bool(cal.get("is_school_break", False))

        wx = weather_by_date.get(r["date"], {})
        features["temp_avg"] = wx.get("temp_avg")
        features["precip_mm"] = wx.get("precip_mm")

        tr = trends_by_date.get(r["date"], {})
        features["trends_interest"] = tr.get("interest")

        ev = events_by_date.get(r["date"], {})
        features["event_count"] = ev.get("event_count", 0)
        features["large_event_count"] = ev.get("large_event_count", 0)

        out.append(features)
    return out
