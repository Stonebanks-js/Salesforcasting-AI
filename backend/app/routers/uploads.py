"""Sales & calendar uploads (api_contracts.md §2.3, §2.8).

Async pattern: 202 + status_url; processing runs as a background task and the
client polls GET /uploads/{id} until a terminal status.
"""
import uuid

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Request,
                     UploadFile, status)

from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.kafka import EventProducer, get_producer
from app.limiter import limiter
from app.schemas import UploadAccepted
from app.services import calendar_parser, csv_sales

router = APIRouter(tags=["uploads"])

_CSV_TYPES = {"text/csv", "application/vnd.ms-excel", "text/plain", "application/octet-stream"}


async def _read_and_check(file: UploadFile, settings: Settings) -> bytes:
    if file.content_type and file.content_type not in _CSV_TYPES and not (
        file.filename or ""
    ).lower().endswith((".csv", ".ics")):
        raise HTTPException(status_code=400, detail="Only CSV/ICS files are accepted")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > settings.upload_max_mb * 1024 * 1024:
        raise HTTPException(
            status_code=400, detail=f"File exceeds {settings.upload_max_mb}MB limit"
        )
    return content


def _create_upload(db, user_id: str, kind: str, file_path: str) -> str:
    upload_id = str(uuid.uuid4())
    db.table("uploads").insert(
        {"id": upload_id, "user_id": user_id, "kind": kind,
         "file_path": file_path, "status": "pending"}
    ).execute()
    return upload_id


@router.post("/uploads/sales", status_code=status.HTTP_202_ACCEPTED,
             response_model=UploadAccepted)
@limiter.limit("10/hour")
async def upload_sales(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
    producer: EventProducer = Depends(get_producer),
    settings: Settings = Depends(get_settings),
) -> UploadAccepted:
    content = await _read_and_check(file, settings)
    upload_id = _create_upload(db, user.user_id, "sales",
                               f"{user.user_id}/{uuid.uuid4()}.csv")
    background.add_task(
        csv_sales.load_sales_upload, db, producer,
        user_id=user.user_id, upload_id=upload_id, content=content,
        max_rows=settings.upload_max_rows, max_skus=settings.upload_max_skus,
    )
    return UploadAccepted(upload_id=upload_id, status_url=f"/api/v1/uploads/{upload_id}")


@router.post("/uploads/calendar", status_code=status.HTTP_202_ACCEPTED,
             response_model=UploadAccepted)
@limiter.limit("10/hour")
async def upload_calendar(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UploadAccepted:
    content = await _read_and_check(file, settings)
    upload_id = _create_upload(db, user.user_id, "calendar",
                               f"{user.user_id}/{uuid.uuid4()}.ics")
    background.add_task(
        _load_calendar, db, user_id=user.user_id, upload_id=upload_id,
        content=content, filename=file.filename or "calendar.csv",
    )
    return UploadAccepted(upload_id=upload_id, status_url=f"/api/v1/uploads/{upload_id}")


def _load_calendar(db, *, user_id: str, upload_id: str, content: bytes, filename: str) -> None:
    parsed = calendar_parser.parse_calendar(content, filename)
    if parsed.events:
        rows = [{"user_id": user_id, **e} for e in parsed.events]
        db.table("calendar_events").upsert(
            rows, on_conflict="user_id,label,start_date"
        ).execute()
    status_value = "loaded" if parsed.events else "failed"
    db.table("uploads").update(
        {"status": status_value, "row_count": len(parsed.events),
         "error_report": {"rejected_rows": parsed.errors}}
    ).eq("id", upload_id).execute()


@router.get("/uploads")
def list_uploads(
    limit: int = 50, offset: int = 0,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    resp = (
        db.table("uploads").select("*").eq("user_id", user.user_id)
        .order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    )
    return {"items": resp.data, "total": len(resp.data)}


@router.get("/uploads/{upload_id}")
def get_upload(
    upload_id: str,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    resp = (
        db.table("uploads").select("*").eq("id", upload_id)
        .eq("user_id", user.user_id).execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Upload not found")
    return resp.data[0]
