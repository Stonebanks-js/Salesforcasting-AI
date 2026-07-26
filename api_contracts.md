# TrendCast AI — API Contracts

**Version:** 1.0 (Phase 5 output)
**Status:** Awaiting approval
**Base:** `https://<api-host>/api/v1` · Local: `http://localhost:8000/api/v1`

---

## 1. Conventions

- **Auth:** Every endpoint (except `/health`) requires `Authorization: Bearer <supabase_jwt>`.
  FastAPI verifies the JWT against Supabase; `user_id` is derived from the token —
  never accepted as a request parameter.
- **Content type:** `application/json` except file uploads (`multipart/form-data`).
- **Errors:** RFC 7807 problem details:
  ```json
  { "type": "about:blank", "title": "Validation failed", "status": 422,
    "detail": "row 14: quantity must be >= 0", "errors": [ ... ] }
  ```
- **Status codes:** 200 OK · 201 Created · 202 Accepted (async) · 400 Bad Request ·
  401 Unauthenticated · 403 Forbidden (RLS/cap) · 404 Not Found · 409 Conflict ·
  422 Validation · 429 Rate limited · 500 Internal
- **Pagination:** `?limit=` (default 50, max 200) + `?offset=` on list endpoints.
- **Versioning:** path prefix `/api/v1`; breaking changes → `/api/v2`.
- **Idempotency:** CSV re-uploads upsert on `(user_id, sku, date)` — safe to retry.

## 2. Endpoints

### 2.1 Health (public)
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness; returns `{ "status": "ok", "version": "x.y.z" }` |

### 2.2 Profile & Onboarding
| Method | Path | Description |
|---|---|---|
| GET | `/profile` | Current user's profile |
| PUT | `/profile` | Create/update profile (onboarding) |

**PUT /profile — request:**
```json
{
  "business_name": "Acme Crafts",
  "country_code": "US",
  "city": "Austin",
  "latitude": 30.2672,
  "longitude": -97.7431,
  "timezone": "America/Chicago",
  "currency": "USD"
}
```
**Validation:** `country_code` ISO alpha-2; lat ∈ [-90,90]; lon ∈ [-180,180]; `timezone` valid IANA.
**Response 200:** profile object + `"onboarding_complete": true`.
**Side effect:** seeds default `signal_settings` rows (marketplace `enabled=false`, others `true`);
triggers initial history backfill for weather/holidays.

### 2.3 Sales Data
| Method | Path | Description |
|---|---|---|
| POST | `/uploads/sales` | Upload sales CSV (multipart, field `file`) → 202 async validation+load |
| GET | `/uploads` | List uploads with status/error reports |
| GET | `/uploads/{id}` | Single upload incl. `error_report` |
| GET | `/sales?sku=&from=&to=` | Query loaded daily sales (for chart overlays) |

**CSV schema (header required):** `date, sku, product_name, quantity, revenue[, price, promo_flag]`
- `date`: ISO `YYYY-MM-DD` · `quantity` ≥ 0 · `revenue` ≥ 0 · `promo_flag` ∈ {true,false,0,1}
- Limits: 10 MB, ≤ 100k rows, ≤ 500 distinct SKUs per file.
**POST response 202:**
```json
{ "upload_id": "uuid", "status": "pending",
  "status_url": "/api/v1/uploads/uuid" }
```
**Final status (`GET /uploads/{id}`):**
```json
{ "id": "uuid", "status": "loaded", "row_count": 12480,
  "error_report": { "rejected_rows": [
    { "row": 14, "field": "quantity", "message": "must be >= 0" } ] } }
```
Rows with errors are **rejected, valid rows are loaded** (partial success, reported).

### 2.4 Products
| Method | Path | Description |
|---|---|---|
| GET | `/products?search=&limit=&offset=` | List user's SKUs (for multi-select picker) |

**Response 200:**
```json
{ "items": [ { "sku": "MUG-001", "product_name": "Ceramic Mug",
               "category": "kitchenware", "sales_days": 412,
               "last_sale_date": "2026-07-24", "has_forecast": true } ],
  "total": 57 }
```

### 2.5 Forecasts (core)
| Method | Path | Description |
|---|---|---|
| GET | `/forecasts?skus=A,B,C&horizon=30` | Multi-SKU forecasts + intervals + factors |

- `skus`: 1–10 SKUs (comma-separated, URL-encoded) — matches dashboard multi-select
- `horizon`: 7 | 14 | 30 (default 30)

**Response 200:**
```json
{
  "model_run_id": "mlflow-run-abc123",
  "generated_at": "2026-07-25T06:00:00Z",
  "series": [
    { "sku": "MUG-001",
      "model_version": "lightgbm:3",
      "mape_backtest": 14.2,
      "degraded": false,
      "points": [
        { "date": "2026-07-26", "yhat": 42.0, "yhat_lower": 31.0, "yhat_upper": 55.0 }
      ],
      "factors": [
        { "factor": "trends_interest", "importance": 0.31, "direction": "up" },
        { "factor": "days_to_holiday", "importance": 0.22, "direction": "up" }
      ] }
  ],
  "signal_health": [
    { "signal": "trends", "status": "stale", "last_success_at": "2026-07-24T18:00:00Z" }
  ]
}
```
**Degradation contract:** if external signals were stale for a SKU, `degraded: true`
and `model_version` may be `seasonal-naive` (baseline won selection). Forecasts are
**always returned** if sales history exists — never an error due to signal outage (NFR-3).
**Errors:** 404 `sku_not_found` · 409 `insufficient_history` (< 60 sales days) with
`detail` stating minimum.

### 2.6 Signal Settings & Health
| Method | Path | Description |
|---|---|---|
| GET | `/signals/settings` | User's per-signal toggles |
| PATCH | `/signals/settings` | Update toggles `{ "marketplace": false, "trends": true }` |
| GET | `/signals/status` | Global per-feed health (live/stale/degraded/disabled + quota notes) |

### 2.7 Marketplace (Keepa, opt-in)
| Method | Path | Description |
|---|---|---|
| GET | `/marketplace/asins` | List tracked ASINs |
| POST | `/marketplace/asins` | Add `{ "asin": "B08XYZ1234" }` → 201; **403 `asin_cap_reached`** at 10 |
| DELETE | `/marketplace/asins/{asin}` | Untrack |

**Validation:** ASIN regex `^[A-Z0-9]{10}$`. Adding ASIN requires `marketplace` toggle on.

### 2.8 Calendar Upload (school vacations)
| Method | Path | Description |
|---|---|---|
| POST | `/uploads/calendar` | ICS or CSV (`label,start_date,end_date`) upload → 202 |
| GET | `/calendar/events` | List parsed calendar events |
| DELETE | `/calendar/events/{id}` | Remove an event |

## 3. Endpoint ↔ FR Traceability

| Endpoint group | Satisfies |
|---|---|
| `/profile` | FR-1.2, FR-1.3 (region + toggles) |
| `/uploads/sales`, `/sales` | FR-2.1, FR-2.2 |
| `/products` | FR-6.1 (picker data) |
| `/forecasts` | FR-5.1–5.3, FR-5.7, FR-6.2–6.4 |
| `/signals/*` | FR-3.1, FR-6.4 |
| `/marketplace/*` | FR-3.7 (opt-in, cap) |
| `/uploads/calendar`, `/calendar/*` | FR-2.4 |

Auth (FR-1.1) is handled by Supabase Auth directly from the frontend (no proxy endpoints).

## 4. Non-Endpoints (explicit exclusions)

- **No on-demand training/inference endpoint in v1** — forecasts come from the daily
  batch job only (prevents free-tier abuse; NFR-4). A `POST /forecasts/refresh`
  is deferred to v2 with rate limiting.
- **No admin API in v1.**

## 5. Rate Limiting & Security

- API-level limiter (slowapi): 100 req/min/user on reads; 10 uploads/hour/user.
- JWT verification on every request; service-role key used only by pipeline sync job
  (server-to-server, never exposed).
- All inputs Pydantic-validated; CSV content sniffed (reject non-CSV MIME).
- CORS: allow-list frontend origin(s) only.

## 6. Example Error (429)
```json
{ "type": "about:blank", "title": "Rate limit exceeded", "status": 429,
  "detail": "Upload limit: 10/hour. Retry after 14:32:00Z." }
```

## 7. Risks

- **Frontend blocked on async upload UX** — mitigated: `status_url` polling pattern defined here.
- **Multi-SKU response size** at 10 SKUs × 30 days (~300 points + factors) — small (<100KB); fine.
- **horizon restriction (7/14/30)** keeps Gold table bounded; documented for users.

## 8. Open Questions

None.

## 9. Confidence Score

**92%** — Contracts cover all FRs with a clear degradation contract; async upload and
multi-SKU read patterns are conventional and testable.

## 10. Next Steps

- Phase 6: UI Planning (wireframe-level plan for dashboard, onboarding, upload flows)
