"""Single source of truth for model feature columns.

Must stay in sync with pipeline/transforms/features.py (train side) — the
inference builder below produces the same keys from history + exogenous
context for future dates.
"""
from datetime import date

LAG_FEATURES = ("lag_1", "lag_7", "lag_14", "lag_28")
ROLL_FEATURES = ("roll_mean_7", "roll_mean_28")
CALENDAR_FEATURES = ("is_holiday", "days_to_holiday", "is_school_break")
EXOGENOUS_FEATURES = (
    "temp_avg", "precip_mm", "trends_interest", "event_count", "large_event_count",
)

FEATURES: tuple[str, ...] = (
    *LAG_FEATURES,
    *ROLL_FEATURES,
    "dow",
    "month",
    "is_weekend",
    "promo_flag",
    *CALENDAR_FEATURES,
    *EXOGENOUS_FEATURES,
)


def build_inference_row(
    day: date,
    history: list[float],
    exog: dict | None = None,
) -> dict:
    """Feature dict for one future date.

    history: past quantities — actuals first, then prior recursive predictions.
    exog: exogenous context for the date (calendar/weather/trends/events/macro);
    missing keys default safely (graceful degradation, NFR-3).
    """
    exog = exog or {}
    row = {
        "dow": day.weekday(),
        "month": day.month,
        "is_weekend": day.weekday() >= 5,
        "promo_flag": bool(exog.get("promo_flag", False)),
        "is_holiday": bool(exog.get("is_holiday", False)),
        "days_to_holiday": exog.get("days_to_holiday"),
        "is_school_break": bool(exog.get("is_school_break", False)),
        "temp_avg": exog.get("temp_avg"),
        "precip_mm": exog.get("precip_mm"),
        "trends_interest": exog.get("trends_interest"),
        "event_count": exog.get("event_count", 0),
        "large_event_count": exog.get("large_event_count", 0),
    }
    for lag in (1, 7, 14, 28):
        row[f"lag_{lag}"] = history[-lag] if len(history) >= lag else None
    for window in (7, 28):
        segment = history[-window:]
        row[f"roll_mean_{window}"] = (
            sum(segment) / len(segment) if segment else None
        )
    return row
