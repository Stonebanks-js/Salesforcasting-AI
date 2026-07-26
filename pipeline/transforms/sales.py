"""Bronze -> Silver sales transforms (pure functions — Spark-free core).

Input records: bronze_sales_raw payload dicts with at least
{user_id, sku, date, quantity, revenue, price, promo_flag, ingested_at}.
"""
from datetime import date, timedelta


def dedupe_latest(records: list[dict]) -> list[dict]:
    """Keep the latest-ingested record per (user_id, sku, date)."""
    best: dict[tuple, dict] = {}
    for r in records:
        key = (r["user_id"], r["sku"], r["date"])
        if key not in best or str(r.get("ingested_at", "")) >= str(best[key].get("ingested_at", "")):
            best[key] = r
    return sorted(best.values(), key=lambda r: (r["user_id"], r["sku"], r["date"]))


def flag_gaps(records: list[dict]) -> list[dict]:
    """Add gap_flag: True where a SKU has a hole > 1 day in its history."""
    by_sku: dict[tuple, list[dict]] = {}
    for r in records:
        by_sku.setdefault((r["user_id"], r["sku"]), []).append(r)

    out: list[dict] = []
    for (_, _), rows in by_sku.items():
        rows.sort(key=lambda r: r["date"])
        prev: date | None = None
        for r in rows:
            current = date.fromisoformat(r["date"])
            gap = prev is not None and (current - prev) > timedelta(days=1)
            out.append({**r, "gap_flag": gap})
            prev = current
    return out


def to_silver(records: list[dict]) -> list[dict]:
    """Full bronze->silver for sales: dedupe + type enforce + gap flags."""
    silver = []
    for r in flag_gaps(dedupe_latest(records)):
        qty = float(r["quantity"])
        silver.append({
            "user_id": r["user_id"],
            "sku": r["sku"],
            "date": r["date"],
            "quantity": max(qty, 0.0),
            "revenue": float(r["revenue"]) if r.get("revenue") is not None else None,
            "price": float(r["price"]) if r.get("price") is not None else None,
            "promo_flag": bool(r.get("promo_flag", False)),
            "gap_flag": r["gap_flag"],
        })
    return silver
