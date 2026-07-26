"""Deterministic synthetic series for ML tests."""
import math
import random
from datetime import date, timedelta


def daily_series(n=300, seed=7, base=40.0) -> list[dict]:
    """Seasonal + weekly + trend + noise series as gold_features-style rows."""
    rng = random.Random(seed)
    start = date(2025, 1, 1)
    rows = []
    quantities = []
    for i in range(n):
        d = start + timedelta(days=i)
        seasonal = 1 + 0.3 * math.sin((i / 365) * 2 * math.pi)
        weekly = 1.25 if d.weekday() >= 5 else 1.0
        trend = 1 + i / (n * 3)
        qty = max(0.0, base * seasonal * weekly * trend * (0.85 + rng.random() * 0.3))
        quantities.append(qty)

    for i in range(n):
        d = start + timedelta(days=i)
        rows.append({
            "user_id": "u1", "sku": "S1", "date": d.isoformat(),
            "quantity": quantities[i],
            "dow": d.weekday(), "month": d.month, "is_weekend": d.weekday() >= 5,
            "promo_flag": False, "gap_flag": False,
            "lag_1": quantities[i - 1] if i >= 1 else None,
            "lag_7": quantities[i - 7] if i >= 7 else None,
            "lag_14": quantities[i - 14] if i >= 14 else None,
            "lag_28": quantities[i - 28] if i >= 28 else None,
            "roll_mean_7": (sum(quantities[max(0, i - 7):i]) / len(quantities[max(0, i - 7):i])) if i else None,
            "roll_mean_28": (sum(quantities[max(0, i - 28):i]) / len(quantities[max(0, i - 28):i])) if i else None,
            "is_holiday": False, "days_to_holiday": None, "is_school_break": False,
            "temp_avg": 15 + 10 * math.sin((i / 365) * 2 * math.pi),
            "precip_mm": rng.random() * 3,
            "trends_interest": 50 + int(20 * math.sin((i / 365) * 2 * math.pi)),
            "event_count": 0, "large_event_count": 0,
        })
    return rows
