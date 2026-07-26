"""Silver/Gold transform tests (pure-function core of the medallion pipeline)."""
from datetime import date

from transforms.calendar_signals import build_calendar_daily
from transforms.features import build_feature_rows
from transforms.sales import dedupe_latest, flag_gaps, to_silver
from transforms.signals_daily import events_to_daily, macro_forward_fill


def _sale(day, qty, ingested="2026-07-26T06:00:00Z"):
    return {"user_id": "u1", "sku": "S1", "date": day, "quantity": qty,
            "revenue": qty * 10, "price": 10.0, "promo_flag": False,
            "ingested_at": ingested}


# --- sales -------------------------------------------------------------------
def test_dedupe_keeps_latest_ingested():
    rows = [_sale("2026-07-01", 5, "2026-07-02T00:00:00Z"),
            _sale("2026-07-01", 9, "2026-07-03T00:00:00Z")]
    result = dedupe_latest(rows)
    assert len(result) == 1 and result[0]["quantity"] == 9


def test_gap_flagging():
    rows = to_silver([_sale("2026-07-01", 1), _sale("2026-07-02", 1),
                      _sale("2026-07-05", 1)])  # gap between 07-02 and 07-05
    flags = {r["date"]: r["gap_flag"] for r in rows}
    assert flags == {"2026-07-01": False, "2026-07-02": False, "2026-07-05": True}


def test_negative_quantity_clamped():
    rows = to_silver([_sale("2026-07-01", -3)])
    assert rows[0]["quantity"] == 0.0


# --- calendar ------------------------------------------------------------------
def test_calendar_daily_features():
    rows = build_calendar_daily(
        "u1", date(2026, 12, 23), date(2026, 12, 26),
        holiday_dates={"2026-12-25"},
        school_breaks=[("2026-12-24", "2026-12-31")],
    )
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-12-25"]["is_holiday"] is True
    assert by_date["2026-12-23"]["days_to_holiday"] == 2
    assert by_date["2026-12-26"]["is_school_break"] is True
    assert by_date["2026-12-23"]["is_school_break"] is False


# --- signals -------------------------------------------------------------------
def test_events_daily_counts():
    events = [
        {"user_id": "u1", "date": "2026-08-01", "large_venue": True, "category": "Music"},
        {"user_id": "u1", "date": "2026-08-01", "large_venue": False, "category": "Sports"},
        {"user_id": "u1", "date": "2026-08-02", "large_venue": False, "category": "Music"},
    ]
    rows = events_to_daily(events)
    assert rows[0]["event_count"] == 2 and rows[0]["large_event_count"] == 1
    assert rows[0]["categories"] == ["Music", "Sports"]
    assert rows[1]["event_count"] == 1


def test_macro_forward_fill():
    points = [{"series": "CPIAUCSL", "date": "2026-06-01", "value": 322.5}]
    dates = ["2026-05-30", "2026-06-15", "2026-07-02"]
    rows = macro_forward_fill(points, dates)
    values = {r["date"]: r["value"] for r in rows}
    assert values["2026-05-30"] is None      # before first observation
    assert values["2026-06-15"] == 322.5     # filled
    assert values["2026-07-02"] == 322.5     # carried forward


# --- gold features ---------------------------------------------------------------
def make_sales(n=35, start=date(2026, 6, 1)):
    from datetime import timedelta
    return [
        {"user_id": "u1", "sku": "S1", "date": (start + timedelta(days=i)).isoformat(),
         "quantity": float(i % 7 + 1), "promo_flag": i == 20, "gap_flag": False}
        for i in range(n)
    ]


def test_feature_rows_lags_and_rolling():
    rows = build_feature_rows(make_sales())
    assert len(rows) == 35
    day29 = rows[28]  # 2026-06-29
    assert day29["lag_1"] == rows[27]["quantity"]
    assert day29["lag_7"] == rows[21]["quantity"]
    assert day29["lag_28"] == rows[0]["quantity"]
    assert rows[0]["lag_1"] is None  # no history on day 1
    expected_roll7 = sum(r["quantity"] for r in rows[21:28]) / 7
    assert abs(day29["roll_mean_7"] - expected_roll7) < 1e-9


def test_feature_rows_join_signals():
    sales = make_sales(n=2, start=date(2026, 7, 1))
    rows = build_feature_rows(
        sales,
        weather_by_date={"2026-07-02": {"temp_avg": 25.5, "precip_mm": 1.2}},
        calendar_by_date={"2026-07-02": {"is_holiday": True, "days_to_holiday": 0,
                                          "is_school_break": False}},
        trends_by_date={"2026-07-02": {"interest": 61}},
        events_by_date={"2026-07-02": {"event_count": 3, "large_event_count": 1}},
    )
    day2 = rows[1]
    assert day2["temp_avg"] == 25.5 and day2["precip_mm"] == 1.2
    assert day2["is_holiday"] is True and day2["days_to_holiday"] == 0
    assert day2["trends_interest"] == 61
    assert day2["event_count"] == 3 and day2["large_event_count"] == 1
    # Missing signals default safely (graceful degradation at feature level).
    day1 = rows[0]
    assert day1["temp_avg"] is None and day1["is_holiday"] is False
    assert day1["event_count"] == 0


def test_feature_rows_calendar_fields():
    rows = build_feature_rows(make_sales(n=1, start=date(2026, 7, 4)))  # Saturday
    row = rows[0]
    assert row["dow"] == 5 and row["is_weekend"] is True and row["month"] == 7
