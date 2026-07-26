"""Sales CSV validation and loading.

Contract (api_contracts.md §2.3): rows with errors are rejected, valid rows are
loaded (partial success), and a per-row error report is stored on the upload.
Upsert key (user_id, sku, date) makes re-uploads idempotent.
"""
import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("date", "sku", "product_name", "quantity", "revenue")
OPTIONAL_COLUMNS = ("price", "promo_flag")

_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no", ""}


@dataclass
class SalesParseResult:
    rows: list[dict] = field(default_factory=list)          # valid rows
    products: dict[str, str] = field(default_factory=dict)  # sku -> product_name
    errors: list[dict] = field(default_factory=list)        # {row, field, message}

    @property
    def rejected(self) -> int:
        return len(self.errors)


def _err(row_no: int, field_name: str, message: str) -> dict:
    return {"row": row_no, "field": field_name, "message": message}


def parse_sales_csv(
    content: bytes, *, max_rows: int, max_skus: int
) -> SalesParseResult:
    """Validate raw CSV bytes into normalized sales rows.

    Row numbers in errors are 1-based including the header row
    (first data row = 2), matching spreadsheet expectations.
    """
    result = SalesParseResult()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        result.errors.append(_err(0, "file", "File is not valid UTF-8 text"))
        return result

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        result.errors.append(_err(0, "file", "Empty file"))
        return result

    headers = {h.strip().lower() for h in reader.fieldnames if h}
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        result.errors.append(_err(1, "header", f"Missing required columns: {', '.join(missing)}"))
        return result

    seen_skus: set[str] = set()
    for row_no, raw in enumerate(reader, start=2):
        if row_no - 1 > max_rows:
            result.errors.append(_err(row_no, "file", f"Row limit exceeded ({max_rows})"))
            break

        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        sku = row.get("sku", "")
        if not sku:
            result.errors.append(_err(row_no, "sku", "sku is required"))
            continue
        seen_skus.add(sku)
        if len(seen_skus) > max_skus:
            result.errors.append(_err(row_no, "sku", f"SKU limit exceeded ({max_skus} per file)"))
            continue

        try:
            row_date = date.fromisoformat(row.get("date", ""))
        except ValueError:
            result.errors.append(_err(row_no, "date", "date must be ISO YYYY-MM-DD"))
            continue

        try:
            quantity = float(row.get("quantity", ""))
            if quantity < 0:
                raise ValueError("must be >= 0")
        except ValueError as exc:
            result.errors.append(_err(row_no, "quantity", f"quantity {exc}"))
            continue

        revenue_raw = row.get("revenue", "")
        revenue: float | None = None
        if revenue_raw:
            try:
                revenue = float(revenue_raw)
                if revenue < 0:
                    raise ValueError("must be >= 0")
            except ValueError as exc:
                result.errors.append(_err(row_no, "revenue", f"revenue {exc}"))
                continue

        price: float | None = None
        if row.get("price"):
            try:
                price = float(row["price"])
                if price < 0:
                    raise ValueError("must be >= 0")
            except ValueError as exc:
                result.errors.append(_err(row_no, "price", f"price {exc}"))
                continue

        promo_raw = row.get("promo_flag", "").lower()
        if promo_raw not in _TRUE | _FALSE:
            result.errors.append(_err(row_no, "promo_flag", "must be true/false/0/1"))
            continue

        name = row.get("product_name", "") or sku
        result.products.setdefault(sku, name)
        result.rows.append(
            {
                "sku": sku,
                "date": row_date.isoformat(),
                "quantity": quantity,
                "revenue": revenue,
                "price": price,
                "promo_flag": promo_raw in _TRUE,
            }
        )

    return result


def load_sales_upload(db, producer, *, user_id: str, upload_id: str, content: bytes,
                      max_rows: int, max_skus: int) -> None:
    """Validate + upsert a sales upload; publish Kafka events; update upload status."""
    parsed = parse_sales_csv(content, max_rows=max_rows, max_skus=max_skus)
    report = {"rejected_rows": parsed.errors}

    if parsed.rows:
        # Upsert products first (FK-less but keeps picker fresh), then sales.
        product_rows = [
            {"user_id": user_id, "sku": sku, "product_name": name}
            for sku, name in parsed.products.items()
        ]
        db.table("products").upsert(product_rows, on_conflict="user_id,sku").execute()

        sales_rows = [{"user_id": user_id, "source": "csv", **r} for r in parsed.rows]
        # Batch upserts to stay within PostgREST payload limits.
        for i in range(0, len(sales_rows), 1000):
            db.table("sales_daily").upsert(
                sales_rows[i : i + 1000], on_conflict="user_id,sku,date"
            ).execute()

        _refresh_product_stats(db, user_id=user_id, skus=list(parsed.products))

        from app.kafka import SALES_TOPIC, build_sales_envelope

        for r in parsed.rows:
            try:
                producer.publish(SALES_TOPIC, key=f"{user_id}:{r['sku']}",
                                 payload=build_sales_envelope(user_id, upload_id, r))
            except Exception:  # noqa: BLE001 - stream is best-effort (decision 010)
                logger.warning("Kafka publish failed for %s/%s", user_id, r["sku"],
                               exc_info=True)

    status = "loaded" if parsed.rows else "failed"
    db.table("uploads").update(
        {"status": status, "row_count": len(parsed.rows), "error_report": report}
    ).eq("id", upload_id).execute()


def _refresh_product_stats(db, *, user_id: str, skus: list[str]) -> None:
    """Maintain denormalized sales_days / last_sale_date on products."""
    for sku in skus:
        resp = (
            db.table("sales_daily").select("date")
            .eq("user_id", user_id).eq("sku", sku)
            .execute()
        )
        dates = [r["date"] for r in resp.data]
        if not dates:
            continue
        db.table("products").update(
            {"sales_days": len(dates), "last_sale_date": max(dates)}
        ).eq("user_id", user_id).eq("sku", sku).execute()
