"""Multi-SKU forecast serving (api_contracts.md §2.5).

Forecasts are read-only from the latest published model run (batch-only, NFR-4).
Signal outages never cause errors here — series are flagged ``degraded`` instead
(degradation contract, NFR-3).
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, get_current_user
from app.db import get_db

router = APIRouter(tags=["forecasts"])

MIN_HISTORY_DAYS = 60  # below this a SKU cannot be forecast (contract §2.5)
_BASELINE_PREFIX = "seasonal-naive"


def _latest_run_id(db, user_id: str) -> tuple[str, str] | None:
    resp = (
        db.table("forecasts").select("model_run_id,generated_at")
        .eq("user_id", user_id).order("generated_at", desc=True).limit(1).execute()
    )
    if not resp.data:
        return None
    return resp.data[0]["model_run_id"], resp.data[0]["generated_at"]


@router.get("/forecasts")
def get_forecasts(
    skus: str = Query(..., description="Comma-separated SKUs, 1-10"),
    horizon: int = Query(default=30),
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    sku_list = [s.strip() for s in skus.split(",") if s.strip()]
    if not 1 <= len(sku_list) <= 10:
        raise HTTPException(status_code=400, detail="Provide between 1 and 10 SKUs")
    if horizon not in (7, 14, 30):
        raise HTTPException(status_code=400, detail="horizon must be 7, 14, or 30")

    # Verify ownership/existence and history depth.
    products = (
        db.table("products").select("sku,sales_days")
        .eq("user_id", user.user_id).in_("sku", sku_list).execute()
    )
    found = {p["sku"]: p for p in products.data}
    missing = [s for s in sku_list if s not in found]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"sku_not_found: {', '.join(missing)}",
        )
    insufficient = [s for s in sku_list if (found[s].get("sales_days") or 0) < MIN_HISTORY_DAYS]
    if insufficient:
        raise HTTPException(
            status_code=409,
            detail=(
                f"insufficient_history: {', '.join(insufficient)} — "
                f"minimum {MIN_HISTORY_DAYS} sales days required"
            ),
        )

    latest = _latest_run_id(db, user.user_id)
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail="No forecasts yet — the nightly batch has not run for this account",
        )
    run_id, generated_at = latest

    end_date = date.today() + timedelta(days=horizon)
    rows = (
        db.table("forecasts").select("*")
        .eq("user_id", user.user_id).eq("model_run_id", run_id)
        .in_("sku", sku_list).lte("forecast_date", end_date.isoformat())
        .order("forecast_date").execute()
    )

    factors = (
        db.table("forecast_factors").select("*")
        .eq("user_id", user.user_id).eq("model_run_id", run_id)
        .in_("sku", sku_list).execute()
    )
    factors_by_sku: dict[str, list[dict]] = {}
    for f in factors.data:
        factors_by_sku.setdefault(f["sku"], []).append(
            {"factor": f["factor"], "importance": float(f["importance"]),
             "direction": f.get("direction")}
        )
    for fl in factors_by_sku.values():
        fl.sort(key=lambda x: x["importance"], reverse=True)
        del fl[5:]  # top-5 per SKU (contract §2.5)

    points_by_sku: dict[str, list[dict]] = {}
    meta_by_sku: dict[str, dict] = {}
    for r in rows.data:
        points_by_sku.setdefault(r["sku"], []).append(
            {"date": r["forecast_date"], "yhat": float(r["yhat"]),
             "yhat_lower": float(r["yhat_lower"]), "yhat_upper": float(r["yhat_upper"])}
        )
        meta_by_sku[r["sku"]] = {
            "model_version": r["model_version"],
            "mape_backtest": float(r["mape_backtest"]) if r["mape_backtest"] is not None else None,
        }

    health = db.table("signal_status").select("*").execute()
    degraded_signals = {
        h["signal"] for h in health.data if h["status"] in ("stale", "degraded")
    }

    series = []
    for sku in sku_list:
        meta = meta_by_sku.get(sku, {})
        model_version = meta.get("model_version", _BASELINE_PREFIX)
        degraded = bool(degraded_signals) or model_version.startswith(_BASELINE_PREFIX)
        series.append(
            {
                "sku": sku,
                "model_version": model_version,
                "mape_backtest": meta.get("mape_backtest"),
                "degraded": degraded,
                "points": points_by_sku.get(sku, []),
                "factors": factors_by_sku.get(sku, []),
            }
        )

    return {
        "model_run_id": run_id,
        "generated_at": generated_at,
        "series": series,
        "signal_health": [
            {"signal": h["signal"], "status": h["status"],
             "last_success_at": h.get("last_success_at"), "quota_note": h.get("quota_note")}
            for h in health.data
        ],
    }
