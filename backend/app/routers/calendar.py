"""Calendar events (school vacations etc.) — api_contracts.md §2.8."""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, get_current_user
from app.db import get_db

router = APIRouter(tags=["calendar"])


@router.get("/calendar/events")
def list_events(user: CurrentUser = Depends(get_current_user), db=Depends(get_db)) -> dict:
    resp = (
        db.table("calendar_events").select("*")
        .eq("user_id", user.user_id).order("start_date").execute()
    )
    return {"items": resp.data}


@router.delete("/calendar/events/{event_id}", status_code=204)
def delete_event(
    event_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> None:
    resp = (
        db.table("calendar_events").delete()
        .eq("user_id", user.user_id).eq("id", event_id).execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Event not found")
