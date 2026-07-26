"""Keepa-tracked ASINs (api_contracts.md §2.7). Opt-in; hard cap enforced in API
*and* by DB trigger (defense in depth)."""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.schemas import AsinCreate

router = APIRouter(tags=["marketplace"])


@router.get("/marketplace/asins")
def list_asins(user: CurrentUser = Depends(get_current_user), db=Depends(get_db)) -> dict:
    resp = (
        db.table("tracked_asins").select("asin,created_at")
        .eq("user_id", user.user_id).order("created_at").execute()
    )
    return {"items": resp.data}


@router.post("/marketplace/asins", status_code=201)
def add_asin(
    body: AsinCreate,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    existing = (
        db.table("tracked_asins").select("asin").eq("user_id", user.user_id).execute()
    )
    if len(existing.data) >= settings.asin_cap_per_user:
        raise HTTPException(
            status_code=403,
            detail=f"asin_cap_reached: maximum {settings.asin_cap_per_user} tracked ASINs "
                   "per user (free-tier quota)",
        )
    if any(r["asin"] == body.asin for r in existing.data):
        raise HTTPException(status_code=409, detail="ASIN already tracked")
    db.table("tracked_asins").insert({"user_id": user.user_id, "asin": body.asin}).execute()
    return {"asin": body.asin}


@router.delete("/marketplace/asins/{asin}", status_code=204)
def delete_asin(
    asin: str,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> None:
    db.table("tracked_asins").delete().eq("user_id", user.user_id).eq("asin", asin).execute()
