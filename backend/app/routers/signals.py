"""Signal toggles & global feed health (api_contracts.md §2.6)."""
from fastapi import APIRouter, Depends

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.schemas import SignalSettingsPatch

router = APIRouter(tags=["signals"])


@router.get("/signals/settings")
def get_signal_settings(user: CurrentUser = Depends(get_current_user), db=Depends(get_db)) -> dict:
    resp = db.table("signal_settings").select("*").eq("user_id", user.user_id).execute()
    return {"items": resp.data}


@router.patch("/signals/settings")
def patch_signal_settings(
    body: SignalSettingsPatch,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        rows = [{"user_id": user.user_id, "signal": s, "enabled": e} for s, e in updates.items()]
        db.table("signal_settings").upsert(rows).execute()
    resp = db.table("signal_settings").select("*").eq("user_id", user.user_id).execute()
    return {"items": resp.data}


@router.get("/signals/status")
def get_signal_status(db=Depends(get_db)) -> dict:
    resp = db.table("signal_status").select("*").execute()
    return {"items": resp.data}
