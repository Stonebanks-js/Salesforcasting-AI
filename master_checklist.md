# TrendCast AI — Master Checklist

**Version:** 1.0 (Phase 12 output)

---

## Functional Requirements

- [x] FR-1.1 Supabase Auth sign-up/login
- [x] FR-1.2 Onboarding: region, timezone, currency
- [x] FR-1.3 Per-user signal toggles
- [x] FR-2.1 CSV sales upload
- [x] FR-2.2 Per-row validation + error report
- [x] FR-2.3 Synthetic demo-data generator
- [x] FR-2.4 School-vacation calendar upload (ICS/CSV)
- [x] FR-3.1 Independent producers, per-user toggle
- [x] FR-3.2 Weather (Open-Meteo)
- [x] FR-3.3 Holidays (Nager.Date)
- [x] FR-3.4 Search trends (pytrends, backoff)
- [x] FR-3.5 Macro (FRED)
- [x] FR-3.6 Events (Ticketmaster)
- [x] FR-3.7 Marketplace (Keepa, opt-in, 10-ASIN cap)
- [x] FR-3.8 Rate-limit handling + cache + graceful degradation
- [x] FR-4.1–4.4 Bronze/Silver/Gold on Spark + Delta Lake
- [x] FR-5.1 Per-SKU forecast, 30-day default horizon
- [x] FR-5.2 Multi-SKU single request (≤10)
- [x] FR-5.3 Prediction intervals (q10–q90)
- [x] FR-5.4 Baseline + LightGBM, per-SKU MAPE selection
- [x] FR-5.5 MLflow registry (optional/no-op capable)
- [x] FR-5.6 Nightly batch retraining + inference
- [x] FR-5.7 Top-5 factor attribution per forecast
- [x] FR-6.1 Multi-select SKU picker
- [x] FR-6.2 Side-by-side charts with bands
- [x] FR-6.3 External-factor panel
- [x] FR-6.4 Signal health indicators
- [x] FR-6.5 Upload + onboarding UI
- [x] FR-6.6 Responsive, WCAG-AA-targeted
- [x] FR-7.1 Auth-protected API, all endpoints
- [x] FR-7.2 Input validation + RLS least privilege

## Non-Functional Requirements

- [x] NFR-1 Free-tier compliance (automated audit: no paid hosts/keys)
- [x] NFR-2 Security (env-var secrets, RLS, validation — `security.md`)
- [x] NFR-3 Graceful degradation (tested at ingestion, model, and API levels)
- [x] NFR-4 <5s forecast reads (pre-computed serving tables)
- [x] NFR-5 Maintainability (modular, typed, decision-logged)
- [x] NFR-6 Testability (130 tests incl. edge + failure scenarios)

## Quality Gates (§17)

- [x] All deliverables finished (13 phases)
- [x] Reviews pass (per-phase self-review recorded)
- [x] Tests pass (130/130)
- [x] Risks documented (per-phase + `testing_strategy.md` gap register)
- [x] Confidence reported (per-phase)
- [ ] **User approval for release — Phase 13**

## Pre-Deploy Checklist (operator) — serverless topology (Phase 15)

- [ ] Supabase project created, **both migrations applied** (0001, 0002), bucket created
- [ ] Render service deployed, env vars set (`KAFKA_ENABLED=false`), `/api/v1/health` 200
- [ ] Vercel deployed, env vars set, login flow works
- [ ] GitHub Secrets set: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `FRED_API_KEY`, `TICKETMASTER_API_KEY`
- [ ] Producers workflow run manually once → signal badges show live
- [ ] Nightly workflow run manually once → logs show `status: ok`, forecasts > 0
- [ ] Demo data → forecast visible on dashboard
- [ ] UptimeRobot (or equivalent) on `/api/v1/health`
- [ ] ~~Oracle VM~~ — REMOVED (decision 027: serverless pipeline via GitHub Actions)
