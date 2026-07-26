# TrendCast AI — Product Requirements Document (PRD)

**Version:** 1.0 (Phase 2 output)
**Status:** Awaiting approval
**License:** EPL-2.0

---

## 1. Product Summary

TrendCast AI is a real-time, multi-product sales-forecasting SaaS for small-to-mid-size
sellers (retail, e-commerce, D2C, marketplace sellers). Users upload their sales history,
and the platform produces demand forecasts for one or more SKUs at once, adjusted for
external real-world signals — weather, holidays, search trends, macroeconomic indicators,
local events, and marketplace momentum — using **only free-tier or open-source services**.

## 2. Problem Statement

Small sellers forecast with gut feeling or moving averages. Commercial forecasting
platforms are priced for enterprises and rely on paid data feeds. TrendCast AI closes
this gap with a free-tier-native pipeline (Kafka → Bronze/Silver/Gold → ML models)
and a dashboard that shows side-by-side multi-SKU forecasts with confidence bands and
explainable external drivers.

## 3. Target Users

- Independent sellers and small e-commerce brands
- Small retail chains / small warehouses
- Marketplace sellers (Amazon/Shopify/WooCommerce)

## 4. Confirmed Decisions (from stakeholder intake)

| Decision | Answer |
|---|---|
| Target region | **Multi-region / configurable** — user sets region at onboarding (drives holiday country codes, weather geocoding, event coverage) |
| Scale target | **Small business pilot** — ~10 users, ~500 SKUs, daily forecasts; free-tier sizing must be verified against this |
| Analytics stack | **Open-source Apache Spark + Delta Lake (self-hosted)** — Databricks Community Edition rejected for production viability; MLflow (open-source) for model registry |
| Default external signals | **All six enabled:** Open-Meteo (weather), Nager.Date (holidays), pytrends (search trends), FRED (macro), Ticketmaster (events), Keepa (marketplace) |
| Deployment | **Vercel free tier (Next.js frontend) + Render/Railway free tier (FastAPI backend)**; Kafka/Spark containerized; Supabase cloud free tier |
| Sample data | **Synthetic data generator** — realistic multi-SKU daily sales with seasonality, promotions, and weather/holiday effects |

## 5. Functional Requirements

### FR-1 Authentication & Onboarding
- FR-1.1 Email/password sign-up and login via Supabase Auth (free tier).
- FR-1.2 Onboarding: user sets business region (country, and optionally city/coordinates
  for weather), timezone, and default currency.
- FR-1.3 Per-user toggle for each of the six external signal feeds.

### FR-2 Sales Data Ingestion
- FR-2.1 CSV upload of historical sales (schema: `date, sku, product_name, quantity, revenue, optional: price, promo_flag`).
- FR-2.2 CSV validation with clear per-row error reporting.
- FR-2.3 Synthetic dataset generator for demo/evaluation (built-in, since no real data provided).
- FR-2.4 School-vacation calendar upload (ICS/CSV) as an optional user-provided signal.
- FR-2.5 (Stretch) Shopify/WooCommerce connector — deferred unless pilot scope allows.

### FR-3 External Signal Ingestion
- FR-3.1 Each signal is an independent Kafka producer, toggleable per user.
- FR-3.2 Weather: Open-Meteo (keyless, free) — forecast + historical weather at user coordinates.
- FR-3.3 Holidays: Nager.Date (keyless, free) — public holidays per configured country.
- FR-3.4 Search trends: pytrends — keyword interest per product category, with backoff/retry.
- FR-3.5 Macro: FRED — configurable macro series (e.g., CPI, consumer sentiment).
- FR-3.6 Events: Ticketmaster Discovery free tier — local events near user coordinates.
- FR-3.7 Marketplace: ~~Keepa free tier~~ **DEFERRED TO V2 (Phase 14, decision 025)** —
  Keepa confirmed paid during credential collection; no viable free alternative.
  Producer code retained, disabled by default; SP-API is the documented free path
  for users holding a Professional Seller account.
- FR-3.8 Every producer implements: rate-limit handling, caching of last-known values,
  and graceful degradation (forecast proceeds with stale/missing signal + user notification).

### FR-4 Data Pipeline (Medallion)
- FR-4.1 Bronze: raw Kafka streams landed to Delta tables (immutable, append-only).
- FR-4.2 Silver: cleaned, deduplicated, schema-enforced daily aggregates per SKU + aligned external signals.
- FR-4.3 Gold: model-ready feature tables (lags, rolling stats, calendar features, external signal features).
- FR-4.4 Pipeline runs on self-hosted Apache Spark + Delta Lake.

### FR-5 Forecasting
- FR-5.1 Per-SKU demand forecast with configurable horizon (default: 30 days daily).
- FR-5.2 Multi-SKU forecasting in a single request (side-by-side comparison).
- FR-5.3 Prediction intervals (confidence bands).
- FR-5.4 Baseline model (seasonal naive / Prophet-class) + ML model with external regressors;
  simple model selection by backtest MAPE.
- FR-5.5 Model versioning via MLflow Model Registry (open-source).
- FR-5.6 Scheduled daily retraining/inference job.
- FR-5.7 Explainability: per-forecast list of top contributing external factors.

### FR-6 Dashboard (Frontend)
- FR-6.1 Multi-select product/SKU picker with search.
- FR-6.2 Side-by-side forecast charts with confidence bands.
- FR-6.3 External-factor panel showing which signals influenced each forecast.
- FR-6.4 Signal health indicators (per-feed status: live / stale / degraded / disabled).
- FR-6.5 Data upload UI (CSV) and onboarding flow (region, signal toggles).
- FR-6.6 Responsive and accessible (WCAG AA target).

### FR-7 API
- FR-7.1 FastAPI backend: auth-protected endpoints for upload, products, forecasts,
  signal status, and user settings.
- FR-7.2 Input validation on all endpoints; least-privilege DB access (Supabase RLS).

## 6. Non-Functional Requirements

- **NFR-1 Free-tier compliance:** every third-party service must be free or have a
  genuinely usable free tier at pilot scale; quotas tracked and documented in
  `data_sources.md`; any projected breach must be flagged, not silently assumed.
- **NFR-2 Security:** no secrets in repo; env-var configuration; validated inputs;
  Supabase RLS for row-level tenant isolation.
- **NFR-3 Graceful degradation:** loss of any single external feed must not break
  forecasting — degrade to last-known value or exclude the feature, and surface it in the UI.
- **NFR-4 Performance:** forecast request for 10 SKUs returns in < 5s (served from
  pre-computed Gold-layer predictions; on-demand only as fallback).
- **NFR-5 Maintainability:** modular producers, typed Python (mypy-friendly), typed
  TypeScript, documented API contracts.
- **NFR-6 Testability:** unit, integration, API, edge-case (rate-limit hit mid-forecast),
  and failure-scenario (feed down) tests.

## 7. Non-Goals (v1)

- Paid/enterprise data feeds (paid SP-API tiers, Bloomberg, etc.)
- Billing/subscription infrastructure
- Non-retail forecasting (services, etc.)
- Real POS/streaming sales ingestion (CSV batch is v1; Kafka carries external signals)
- Shopify/WooCommerce live connectors (stretch only)

## 8. Free-Tier Constraint Summary (to be detailed in data_sources.md)

| Service | Free ceiling | Pilot-scale risk |
|---|---|---|
| Supabase | 500MB DB, 50k MAU auth | Low at 10 users / 500 SKUs |
| Open-Meteo | Keyless, generous non-commercial limits | Low |
| Nager.Date | Keyless, free | Very low (annual fetch, cacheable) |
| pytrends | Unofficial, Google rate-limits | Medium — aggressive caching + backoff required |
| FRED | Free with API key | Low (daily series, cacheable) |
| Ticketmaster | 5k calls/day free tier | Medium — must cache + batch by geography |
| Keepa | Token-limited free tier | **High** — tokens replenish ~1/min; must strictly budget tracked SKUs |
| Vercel | Hobby tier | Low (dashboard is light) |
| Render/Railway | Free tier (sleep/limited hours possible) | Medium — cold starts acceptable for pilot |

## 9. Success Metrics (pilot)

- Forecast MAPE ≤ 25% on synthetic validation set for baseline+external model,
  and measurably better than seasonal-naive baseline.
- All six producers degrade gracefully when their feed is disabled/killed in tests.
- Zero paid keys in the stack (QA security gate).

## 10. Open Questions — RESOLVED

1. **Keepa free tier viability:** ✅ RESOLVED — Marketplace signal is per-user **opt-in**,
   capped at **10 tracked ASINs per user**, with aggressive caching. Documented as a
   hard quota in `data_sources.md`.
2. **School vacations:** ✅ RESOLVED — **Manual calendar upload** (ICS/CSV). Users may
   upload their region's school-vacation calendar as a custom signal; treated as an
   optional seventh input to the holiday/calendar feature set.
3. **Kafka hosting:** ✅ RESOLVED — **Free hosted Kafka (Upstash or Redpanda serverless
   free tier)** for the deployed pilot; local dev uses Dockerized Kafka. Final vendor
   pick documented in `deployment.md` after a quota check at the Deployment phase.
4. **Repo naming:** ✅ RESOLVED — Repository name stays `Salesforcasting-AI`; README
   and all docs brand the product as **TrendCast AI**.

## 11. Next Steps

- Phase 3: Architecture (system design, component diagram, Kafka topics, Spark/Delta
  layout, MLflow, deployment topology) → documented in `architecture.md`.
- Produce `data_sources.md` with per-source rate limits, auth, cadence, and fallback plans.
