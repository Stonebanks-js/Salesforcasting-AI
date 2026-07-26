"""Profile & onboarding (api_contracts.md §2.2)."""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.schemas import SIGNALS, ProfileUpsert

router = APIRouter(tags=["profile"])

# Marketplace is opt-in (Keepa free-tier quota); everything else defaults on.
_DEFAULT_DISABLED = {"marketplace"}


@router.get("/profile")
def get_profile(user: CurrentUser = Depends(get_current_user), db=Depends(get_db)) -> dict:
    resp = db.table("profiles").select("*").eq("id", user.user_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Profile not found; complete onboarding")
    return resp.data[0]


@router.put("/profile")
def put_profile(
    body: ProfileUpsert,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    row = {"id": user.user_id, "onboarding_complete": True, **body.model_dump()}
    resp = db.table("profiles").upsert(row).execute()

    # Seed default signal settings (idempotent: upsert on PK, don't clobber existing).
    existing = db.table("signal_settings").select("signal").eq("user_id", user.user_id).execute()
    existing_signals = {r["signal"] for r in existing.data}
    defaults = [
        {"user_id": user.user_id, "signal": s, "enabled": s not in _DEFAULT_DISABLED}
        for s in SIGNALS
        if s not in existing_signals
    ]
    if defaults:
        db.table("signal_settings").upsert(defaults).execute()

    return resp.data[0] if resp.data else row
