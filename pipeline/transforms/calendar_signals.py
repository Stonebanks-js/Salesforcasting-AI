"""Bronze -> Silver calendar signal transforms (holidays + school vacations)."""
from datetime import date, timedelta


def build_calendar_daily(
    user_id: str,
    start: date,
    end: date,
    holiday_dates: set[str],
    school_breaks: list[tuple[str, str]],  # (start_date, end_date) inclusive
) -> list[dict]:
    """One row per day with holiday + school-break features.

    days_to_holiday: days until the next holiday within 30 days (else None).
    """
    holidays = sorted(date.fromisoformat(d) for d in holiday_dates)
    breaks = [(date.fromisoformat(s), date.fromisoformat(e)) for s, e in school_breaks]

    rows = []
    current = start
    while current <= end:
        is_holiday = current in holidays
        days_to = next(
            ((h - current).days for h in holidays if 0 <= (h - current).days <= 30),
            None,
        )
        in_break = any(s <= current <= e for s, e in breaks)
        rows.append({
            "user_id": user_id,
            "date": current.isoformat(),
            "is_holiday": is_holiday,
            "days_to_holiday": days_to,
            "is_school_break": in_break,
        })
        current += timedelta(days=1)
    return rows
