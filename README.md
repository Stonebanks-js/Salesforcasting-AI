# TrendCast AI

**Real-time, multi-product sales forecasting for small sellers — built entirely on free-tier and open-source tools.**

Upload your sales history, and TrendCast forecasts demand for up to 10 SKUs
side-by-side, adjusted for real-world signals: weather, holidays, search
trends, economic indicators, local events, and Amazon marketplace momentum —
with confidence bands, backtest accuracy, and the factors driving each forecast.

## Why

Small sellers forecast with gut feeling; enterprise forecasting platforms need
enterprise budgets and paid data feeds. TrendCast closes the gap with a
free-tier-native pipeline: Kafka → Bronze/Silver/Gold (Spark + Delta Lake) →
LightGBM quantile models → a Next.js dashboard. **Total pilot running cost: $0.**

## Architecture

**Pilot (serverless, $0/month — decision 027):**

```
5 free signal sources ──► GitHub Actions (producers, 4×/day)
                               │ writes signal_events
CSV sales upload ──► FastAPI ──▼──► Supabase Postgres
(Render)                        ▲      │ reads sales + signals
                                │      ▼
                        Next.js dashboard ◄── GitHub Actions (nightly):
                        (Vercel)             transforms → LightGBM train
                                             → infer → upsert forecasts
```

Four services: **Vercel + Render + Supabase + GitHub Actions**. No VM, no
broker, no JVM. The full Kafka + Spark + Delta Lake implementation remains in
the repo (`infra/`, `pipeline/jobs/`) as the v2 scale-up path.

Graceful degradation is a hard requirement: if any signal feed dies, forecasts
fall back to cached values or a baseline model — the dashboard always works.

## Repository Layout

| Dir | What |
|---|---|
| `frontend/` | Next.js 16 + TypeScript + Tailwind dashboard (Vercel) |
| `backend/` | FastAPI REST API (Render) — auth, uploads, forecasts, settings |
| `producers/` | Signal producers + shared quota/backoff/cache lib (GitHub Actions cron) |
| `pipeline/` | `local_nightly.py` serverless pipeline + pure transforms (Spark jobs preserved for v2) |
| `ml/` | LightGBM quantile models, backtest, selection, MLflow tracking |
| `integration/` | Cross-codebase seam tests + tenant isolation + security audit |
| `infra/` | docker-compose (Kafka, producers, pipeline, MLflow) — v2 scale-up path |
| `supabase/` | Postgres migrations (schema + RLS + signal_events bus) |

## Quick Start (local dev)

**Prereqs:** Python 3.11+, Node 24+, Docker (for Kafka), a free Supabase project.

```bash
# 1. Database: run supabase/migrations/0001_init.sql in the Supabase SQL editor

# 2. Backend
cd backend && python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ..\infra\env.example .env   # fill Supabase values
uvicorn app.main:app --reload  # http://localhost:8000/api/v1/health

# 3. Frontend
cd frontend && npm install
cp .env.example .env.local     # fill Supabase values + API URL
npm run dev                    # http://localhost:3000

# 4. Infra (optional for UI dev — uploads work without Kafka)
cd infra && cp env.example .env
docker compose up -d kafka producers
docker compose --profile batch run --rm pipeline   # nightly batch
```

Sign up → onboarding → **Generate demo data** → run the nightly batch →
dashboard shows forecasts. See `deployment.md` for production.

## Testing

130 tests across six suites:

```bash
cd backend     && python -m pytest     # 47
cd producers   && python -m pytest     # 26
cd pipeline    && python -m pytest     # 9
cd ml          && python -m pytest     # 22
cd integration && python -m pytest     # 17 (seams, isolation, failures, security)
cd frontend    && npm test             # 9
```

## Documentation

| Doc | Content |
|---|---|
| `PRD.md` | Requirements, scale targets, success metrics |
| `architecture.md` | System design, topic topology, medallion layout |
| `database_design.md` | Schemas, RLS, sizing vs free tier |
| `api_contracts.md` | All 15 endpoints, degradation contract |
| `data_sources.md` | Free-tier inventory: limits, cadence, fallbacks |
| `ui_plan.md` | Dashboard UX, components, accessibility |
| `testing_strategy.md` | Test pyramid, honest gap register |
| `security.md` | Threat model, controls, incident response |
| `deployment.md` | Free-tier topology + step-by-step |
| `decision_log.md` | 22+ architectural decisions with rationale |
| `implementation_plan.md` | Phase plan & status |
| `master_checklist.md` | Release checklist |

## License

EPL-2.0 — see `LICENSE`.
