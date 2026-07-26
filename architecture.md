# TrendCast AI — Architecture

**Version:** 1.1 (Phase 15 amendment)
**Status:** Live
**Constraint:** 100% free-tier / open-source stack at pilot scale (~10 users, ~500 SKUs)

> ## ⚠️ Phase 15 Amendment — Serverless Pilot Topology (decision 027)
>
> The Oracle VM hosting path proved unworkable; free VM alternatives are inadequate.
> **The pilot runs WITHOUT Kafka, Spark, Delta, or a VM:**
>
> - **Producers** run as a GitHub Actions scheduled workflow (every 6h, unlimited free
>   minutes on public repos), writing signal envelopes directly to a Supabase
>   **`signal_events`** table via a `SupabasePublisher` (same `Publisher` protocol as
>   the Kafka producer — producers' core logic is unchanged).
> - **The nightly pipeline** runs as a second GitHub Actions workflow
>   (`pipeline/local_nightly.py`): reads `sales_daily` + `signal_events` from Supabase,
>   executes the **same unit-tested pure transforms and ML code**, and upserts
>   `forecasts`/`forecast_factors` back into Supabase. No JVM, no broker, no VM.
> - **Backend** runs with `KAFKA_ENABLED=false`; sales are read by the pipeline
>   directly from `sales_daily` (they were always durable there first — decision 010).
> - **Final pilot stack: Vercel + Render + Supabase + GitHub Actions** — $0/month.
>
> The Kafka/Spark/Delta implementation below remains in the repo, fully tested, as the
> **v2 scale-up path** when volume justifies a broker and a lakehouse. Sections 1–9
> describe that target architecture; the pilot is its serverless projection.

---

## 1. System Overview

```
                        ┌─────────────────────────────────────────────────┐
                        │              EXTERNAL DATA SOURCES               │
                        │  Open-Meteo │ Nager.Date │ pytrends │ FRED │    │
                        │  Ticketmaster │ Keepa (opt-in, 10 ASIN cap)      │
                        └───────┬─────────────────────────────────────────┘
                                │ (6 independent producers, per-user toggle)
                                ▼
┌──────────┐   HTTPS   ┌─────────────────┐         ┌──────────────────────┐
│  Next.js │ ◄────────► │  FastAPI Backend │ ──────► │  Supabase (free tier) │
│ Dashboard│   JWT     │  (REST + auth)   │  SQL    │  Postgres + Auth +    │
│ (Vercel) │           │  (Render/Railway)│         │  Storage (CSV uploads)│
└──────────┘           └───────┬─────────┘         └──────────────────────┘
                               │ produces                ▲ reads Gold forecasts
                               ▼                         │ via sync job
                    ┌─────────────────────┐              │
                    │   Apache Kafka       │              │
                    │ (Docker local /      │              │
                    │  Upstash/Redpanda    │              │
                    │  serverless free)    │              │
                    └───────┬─────────────┘              │
                            │ consume                    │
                            ▼                            │
        ┌───────────────────────────────────────┐       │
        │   Apache Spark + Delta Lake (self-host)│       │
        │  BRONZE ──► SILVER ──► GOLD            │       │
        │  raw      clean/agg   feature tables   │       │
        │                       + forecasts      │───────┘
        └───────────────┬───────────────────────┘
                        │ fit / register / log
                        ▼
              ┌───────────────────┐
              │  MLflow (open-src) │
              │  Tracking + Model  │
              │  Registry          │
              └───────────────────┘
```

**Core data flow:**
1. Producers stream external signals into Kafka topics (one topic per signal type).
2. Sales data enters via CSV upload (FastAPI → Supabase Storage → batch loader job → Kafka `sales.raw` topic).
3. Spark Structured Streaming/batch jobs land Kafka topics into Bronze Delta tables.
4. Silver jobs clean, deduplicate, and aggregate to daily-per-SKU grain; signals aligned by date/region.
5. Gold jobs build model-ready feature tables.
6. Training job (scheduled daily) fits per-SKU models, backtests, logs to MLflow, registers best model.
7. Batch inference writes forecasts + intervals + factor attributions to a Gold `forecasts` table.
8. A sync job publishes Gold forecasts into Supabase Postgres (serving tables).
9. FastAPI serves forecasts to the Next.js dashboard from Supabase (fast, cheap, cached).

**Why forecasts are served from Postgres, not Spark:** the dashboard needs <5s reads;
Spark is not an online serving layer. Pre-computed daily inference (NFR-4) keeps reads cheap.

## 2. Component Breakdown

### 2.1 Frontend — Next.js + TypeScript + Tailwind (Vercel free tier)
- App Router, server components where useful; client components for charts.
- Charting: **Recharts** (open-source, MIT) — forecast lines + confidence band areas.
- Auth via `@supabase/supabase-js` with Supabase Auth; JWT passed to FastAPI.
- Pages: `/login`, `/onboarding` (region, signal toggles), `/upload`, `/dashboard` (multi-SKU forecast), `/settings`.
- Multi-select SKU picker with search; side-by-side forecast panels; signal-health badges.

### 2.2 Backend — FastAPI + Python (Render/Railway free tier)
- REST API, JWT verification against Supabase Auth JWKS.
- Endpoints (detailed in Phase 5 / `api_contracts.md`):
  - `POST /uploads/sales` — CSV ingest + validation
  - `GET /products` — user's SKUs
  - `GET /forecasts?skus=...&horizon=...` — pre-computed forecasts + intervals + factors
  - `GET /signals/status` — per-feed health (live/stale/degraded/disabled)
  - `GET|PATCH /settings` — region, signal toggles, tracked ASINs (≤10)
- Writes/reads serving tables in Supabase Postgres with RLS.
- Publishes `sales.raw` events to Kafka after CSV validation.
- Forecast requests are **read-only from serving tables** — no on-demand model calls in v1
  (on-demand inference is fallback-only, guarded by a timeout).

### 2.3 Database — Supabase free tier (Postgres + Auth + Storage)
- **Auth:** Supabase Auth (email/password). RLS on all user tables.
- **Storage:** private bucket `sales-uploads` for raw CSVs.
- **Serving tables** (schema detailed in Phase 4): `profiles`, `products`,
  `sales_daily`, `forecasts`, `forecast_factors`, `signal_status`, `tracked_asins`,
  `calendar_uploads`.
- 500MB free-tier budget is ample at pilot scale (~500 SKUs × ~2yr daily rows ≈ 365k rows).

### 2.4 Streaming — Apache Kafka
- **Local dev:** Kafka (KRaft, single broker) via Docker Compose.
- **Deployed pilot:** Upstash Kafka *or* Redpanda Serverless free tier — final vendor
  decision deferred to Phase 12 with a quota check; the producer/consumer code is
  vendor-neutral (`kafka-python`), only bootstrap config changes.
- **Topic topology:**

| Topic | Producer | Content | Retention |
|---|---|---|---|
| `sales.raw` | FastAPI | Validated sales rows from CSV | 30d |
| `signals.weather` | weather-producer | Daily/hourly wx per user-location | 90d |
| `signals.holidays` | holiday-producer | Holidays per country code | 365d |
| `signals.trends` | trends-producer | Keyword interest per category/region | 90d |
| `signals.macro` | macro-producer | FRED series observations | 365d |
| `signals.events` | events-producer | Local events per geo | 90d |
| `signals.marketplace` | marketplace-producer | Keepa price/BSR per tracked ASIN | 90d |
| `signals.health` | all producers | Heartbeat + quota status messages | 30d |

- All messages are JSON with a common envelope: `{source, entity_key, observed_at, ingested_at, payload, schema_version}`.
- Single partition per topic is sufficient at pilot scale; partition keys reserved for growth.

### 2.5 Producers — Python (containerized, Docker Compose locally; Render/Railway cron/worker when deployed)
- One producer service per signal (independently deployable/toggleable).
- Shared library: rate limiter, exponential backoff with jitter, last-known-value cache
  (Redis-free: local disk cache + Supabase `signal_status` table), dead-letter logging.
- Refresh cadences in `data_sources.md`.

### 2.6 Analytics — Apache Spark + Delta Lake (self-hosted, Docker Compose)
- **Rejected:** Databricks Community Edition (single tiny cluster, no production SLAs/Jobs/Serving).
- Spark runs in **local mode inside a container** at pilot scale — no cluster needed for
  ~365k rows/year. Architecture is cluster-ready if volume grows.
- Delta Lake tables stored on a mounted volume (MinIO/S3-compatible optional; local volume in v1).

**Medallion layout:**

| Layer | Tables | Transformations |
|---|---|---|
| Bronze | `bronze_sales_raw`, `bronze_weather`, `bronze_holidays`, `bronze_trends`, `bronze_macro`, `bronze_events`, `bronze_marketplace` | Raw landing, schema-on-read enforced on write, append-only, ingestion metadata |
| Silver | `silver_sales_daily` (SKU×date), `silver_signals_daily` (signal×date×region) | Deduplication, type enforcement, timezone normalization to user tz, gap-flagging, unit normalization |
| Gold | `gold_features` (SKU×date feature matrix), `gold_forecasts` (SKU×date×horizon predictions + intervals), `gold_forecast_factors` (feature attributions) | Lag/rolling features, calendar features (holiday proximity, school-vacation flags from uploads), signal joins, train/inference split |

- **Jobs:** `bronze_ingest`, `silver_transform`, `gold_features`, `train_models`,
  `batch_inference`, `publish_to_supabase` — orchestrated by a simple scheduler
  (cron in container; document upgrade path to Airflow/Dagster if needed — rejected for v1 as overkill).

### 2.7 ML — Forecasting Models + MLflow
- **Baseline:** seasonal-naive (weekly seasonality) — always computed as fallback.
- **Primary:** per-SKU gradient-boosted model (LightGBM, open-source) on Gold features
  (lags, rolling stats, calendar, external signals). Quantile regression (α=0.1/0.5/0.9)
  gives prediction intervals natively.
- **Rejected for v1:** deep learning (overkill at 500 SKUs, high ops cost), Prophet
  (fine but weaker with many external regressors; kept as alternative if LightGBM underperforms).
- **Model selection:** backtest on last 60 days; pick per-SKU winner by MAPE between
  baseline and LightGBM. Baseline wins automatically when external features are missing/stale
  → graceful degradation at the model level.
- **MLflow** (open-source, self-hosted in Docker): experiment tracking + model registry.
  Serving is batch inference in Spark, so no ML serving infra needed.
- **Explainability:** LightGBM feature importances per forecast stored in
  `gold_forecast_factors` (top-5 external factors per SKU), surfaced in the dashboard.

### 2.8 Sync to Serving Layer
- `publish_to_supabase` job upserts `gold_forecasts`/`gold_forecast_factors` into
  Supabase `forecasts`/`forecast_factors` tables daily.
- Supabase is the single read source for the API → dashboard reads stay on the free tier
  and never touch Spark.

## 3. Repository Structure (monorepo)

```
Salesforcasting-AI/
├── docs/                     # PRD, architecture, api_contracts, etc. (root-level per plan)
├── frontend/                 # Next.js + TS + Tailwind
├── backend/                  # FastAPI app
│   ├── app/ (routers, services, db, kafka producer, auth)
│   └── tests/
├── producers/                # 6 signal producers + shared lib
│   ├── shared/ (ratelimit, backoff, cache, envelope, health)
│   ├── weather/ holidays/ trends/ macro/ events/ marketplace/
│   └── tests/
├── pipeline/                 # Spark jobs (bronze/silver/gold/train/inference/publish)
│   ├── jobs/
│   ├── delta/  (mounted volume)
│   └── tests/
├── ml/                       # model training code, feature definitions, evaluation
├── data_gen/                 # synthetic sales data generator
├── infra/
│   ├── docker-compose.yml    # kafka, spark, mlflow, minio(optional)
│   └── env.example
└── .github/workflows/        # CI (tests, lint) — free GitHub Actions
```

## 4. Security Architecture

- Secrets only in env vars (`.env` gitignored; `env.example` committed).
- Supabase RLS: users read/write only their own rows; service-role key used only by
  backend/sync jobs, never in frontend.
- FastAPI validates JWT (Supabase) on every request; Pydantic validation on all inputs.
- CSV uploads: size cap (10MB), type sniffing, row-level validation errors.
- Producers never receive user credentials; region/ASIN config read from serving DB by
  a config-snapshot topic/table.
- Details in `security.md` (Phase 7 companion).

## 5. Deployment Topology (pilot)

| Component | Host (free tier) | Notes |
|---|---|---|
| Next.js | Vercel Hobby | HTTPS, CDN |
| FastAPI | Render/Railway free | Possible cold starts — acceptable |
| Supabase | Supabase cloud free | Postgres + Auth + Storage |
| Kafka | Upstash/Redpanda serverless free | Vendor picked in Phase 12 |
| Producers | Render/Railway cron jobs | Or a single free worker running all 6 on schedules |
| Spark + Delta + MLflow | Docker Compose (local or free VPS) | Batch jobs on schedule; not public-facing |

Trade-off note: Spark/MLflow have no credible always-on free host; pilot runs them on a
dev machine/free VPS as scheduled batch. This is the honest ceiling of "free" for the
analytics layer — flagged per project principles. Forecast *serving* remains fully hosted
and free.

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| pytrends throttled by Google | Trends signal stale | Backoff + cache last-known; degrade to baseline model; health badge in UI |
| Keepa token exhaustion | Marketplace signal stale | 10-ASIN cap, token bucket, daily batch only |
| Free Kafka vendor limits (partitions/throughput) | Producer lag | Low volume at pilot; vendor quota check in Phase 12 |
| Render/Railway sleep | API cold start (~30s) | Acceptable for pilot; health endpoint + retry in frontend |
| Spark on free VPS reliability | Missed daily job | Idempotent jobs; catch-up on next run; Supabase keeps last good forecasts |
| Supabase 500MB | Storage growth | Retention policies; CSVs in Storage bucket, not DB |

## 7. Open Questions

None blocking. Vendor pick for hosted Kafka (Upstash vs Redpanda) is deferred to
Phase 12 by design.

## 8. Confidence Score

**90%** — Architecture is conventional, modular, and free-tier-honest. Main uncertainty
is operational: behavior of unofficial/rate-limited sources (pytrends, Keepa) under
real conditions, to be validated in Phase 9 integration testing.

## 9. Next Steps

- Phase 4: Database Design (Supabase schema + RLS + Delta table schemas)
- Phase 5: API Design (`api_contracts.md`)
