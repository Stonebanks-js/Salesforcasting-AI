"""Products & sales history (api_contracts.md §2.4, §2.3)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, get_current_user
from app.db import get_db

router = APIRouter(tags=["products"])


@router.get("/products")
def list_products(
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    query = db.table("products").select("*").eq("user_id", user.user_id)
    if search:
        query = query.ilike("product_name", f"%{search}%")
    resp = query.order("sku").range(offset, offset + limit - 1).execute()
    items = resp.data

    # Flag SKUs that have a forecast in the latest model run (single query).
    skus = [i["sku"] for i in items]
    has_forecast: set[str] = set()
    if skus:
        fc = (
            db.table("forecasts").select("sku").eq("user_id", user.user_id)
            .in_("sku", skus).execute()
        )
        has_forecast = {r["sku"] for r in fc.data}

    for item in items:
        item["has_forecast"] = item["sku"] in has_forecast
    return {"items": items, "total": len(items)}


@router.get("/sales")
def get_sales(
    sku: str,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=1000),
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    query = (
        db.table("sales_daily").select("date,quantity,revenue,promo_flag")
        .eq("user_id", user.user_id).eq("sku", sku)
    )
    if from_date:
        query = query.gte("date", from_date)
    if to_date:
        query = query.lte("date", to_date)
    resp = query.order("date").limit(limit).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="No sales data for sku")
    return {"sku": sku, "items": resp.data}
