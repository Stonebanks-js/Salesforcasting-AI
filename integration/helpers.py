"""Shared helpers for integration tests."""
from datetime import date, datetime, timedelta, timezone
import math
import random

import jwt

USER = "u1-integration"


def mint_token(user_id: str = USER, secret: str = "integration-secret") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "aud": "authenticated",
         "iat": now, "exp": now + timedelta(hours=1)},
        secret, algorithm="HS256",
    )


def synth_csv(days: int = 200, seed: int = 11) -> bytes:
    """Deterministic 2-SKU CSV matching the upload contract schema."""
    rng = random.Random(seed)
    products = [("MUG-001", "Ceramic Mug", 30.0), ("TSH-022", "Logo Tee", 18.0)]
    lines = ["date,sku,product_name,quantity,revenue,price,promo_flag"]
    today = date.today()
    for sku, name, base in products:
        price = 12.0 + rng.random() * 10
        for d in range(days, 0, -1):
            day = today - timedelta(days=d)
            doy = day.timetuple().tm_yday
            seasonal = 1 + 0.3 * math.sin((doy / 365) * 2 * math.pi)
            weekly = 1.25 if day.weekday() >= 5 else 1.0
            qty = max(0, round(base * seasonal * weekly * (0.8 + rng.random() * 0.4)))
            lines.append(
                f"{day.isoformat()},{sku},{name},{qty},{qty * price:.2f},{price:.2f},false"
            )
    return "\n".join(lines).encode()


def weather_lookup(days: int = 60) -> dict[str, dict]:
    """Synthetic weather for the most recent `days` (joins against sales)."""
    out = {}
    today = date.today()
    for d in range(days, -30, -1):  # includes 30 future days (forecast window)
        day = today - timedelta(days=d)
        out[day.isoformat()] = {
            "temp_avg": 18 + 8 * math.sin((day.timetuple().tm_yday / 365) * 2 * math.pi),
            "precip_mm": 1.0,
        }
    return out


def trends_lookup(days: int = 60, value: int = 55) -> dict[str, dict]:
    today = date.today()
    return {
        (today - timedelta(days=d)).isoformat(): {"interest": value}
        for d in range(days, -30, -1)
    }
