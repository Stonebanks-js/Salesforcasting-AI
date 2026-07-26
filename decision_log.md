# TrendCast AI — Decision Log

| # | Date | Phase | Decision | Rationale / Trade-offs |
|---|---|---|---|---|
| 001 | 2026-07-26 | 2 | Self-hosted Spark + Delta Lake over Databricks Community Edition | CE has a single tiny cluster, no production SLAs/Jobs/Serving — not viable beyond demos. Self-hosted Spark (local mode in Docker) is cluster-ready if volume grows. |
| 002 | 2026-07-26 | 2 | Free hosted Kafka (Upstash/Redpanda serverless) for pilot deploy; Docker locally | Vendor-neutral client (`kafka-python`); final vendor pick deferred to Phase 12 with quota check. |
| 003 | 2026-07-26 | 2 | Keepa opt-in, hard cap 10 ASINs/user | Free token allotment (~1 token/min refill) cannot scale beyond this; cap enforced in DB trigger + API (defense in depth). |
| 004 | 2026-07-26 | 2 | School vacations via manual ICS/CSV upload | No reliable global free API exists. |
| 005 | 2026-07-26 | 3 | Forecasts served from Supabase Postgres, not Spark | Spark is offline analytics; <5s dashboard reads (NFR-4) require a serving store. Batch inference publishes Gold → Postgres daily. |
| 006 | 2026-07-26 | 3 | LightGBM quantile regression as primary model; seasonal-naive baseline always computed | Native prediction intervals (q10/q50/q90) + feature importances for explainability; baseline enables graceful degradation and honest model selection by backtest MAPE. Deep learning rejected (ops cost at 500 SKUs). |
| 007 | 2026-07-26 | 7 | **DB Amendment 1:** denormalize `sales_days`/`last_sale_date` onto `products` | Avoids N+1/aggregation queries on `GET /products` and cheap 60-day-minimum check in `/forecasts`. Maintained by CSV loader. |
| 008 | 2026-07-26 | 7 | **DB Amendment 2:** add identity `id` to `calendar_events` | `api_contracts.md` deletes by `{id}`; composite PK kept for upsert idempotency. |
| 009 | 2026-07-26 | 7 | API accesses PostgREST with anon key + caller JWT (no service-role in API) | RLS enforced by Postgres as the calling user = least privilege; service-role reserved for offline pipeline sync job only. |
| 010 | 2026-07-26 | 7 | Kafka failure must not fail uploads (`NullProducer` fallback) | Sales rows are durable in Supabase first; the stream is for analytics convenience (NFR-3). |
| 011 | 2026-07-26 | 8 | Client-side auth guard (AppShell) instead of Next.js middleware | Avoids `@supabase/ssr` cookie plumbing at pilot scale; guard is equivalent for a fully client-rendered dashboard. Revisit if SSR is introduced. |
| 012 | 2026-07-26 | 8 | Demo data generated in-browser (`demoData.ts`), uploaded via the real CSV path | Demo users exercise the identical ingest/validation pipeline as real users; no separate seed path to maintain. |
| 013 | 2026-07-26 | 9 | Batch micro-batch (daily) Bronze ingest instead of Structured Streaming | Daily cadence satisfies FR-5.6; far simpler to operate at pilot scale; Kafka retention (30–365d) makes catch-up safe. |
| 014 | 2026-07-26 | 9 | Medallion logic in pure functions (`transforms/`) with thin Spark IO wrappers | Spark jobs become untestable black boxes otherwise; 100% of transform logic is unit-tested without a JVM. |
| 015 | 2026-07-26 | 9 | Producers never hold Supabase credentials; health flows via `signals.health` topic → `health_sync` job | Preserves the service-role boundary (security.md); health status reaches the dashboard without widening producer privileges. |
| 016 | 2026-07-26 | 10 | LightGBM native `lgb.train` API instead of sklearn wrapper | Avoids a scikit-learn dependency in the pipeline image; same model with fewer moving parts. |
| 017 | 2026-07-26 | 10 | Baseline wins ties AND is forced when external-feature null fraction > 50% | Graceful degradation encoded in model selection (NFR-3), not just ingestion — stale signals can never silently degrade forecast quality. |
| 018 | 2026-07-26 | 10 | Factor direction via Pearson sign on training data; lags excluded from displayed factors | Cheap, honest 'what drove this forecast' without SHAP's compute cost; lags describe momentum, not external drivers (UX semantics). |
| 019 | 2026-07-26 | 10 | MLflow optional via NullTracker (same pattern as NullProducer) | Training/inference must run in minimal environments (tests, local dev without MLflow container); registry is observability, not a runtime dependency. |
| 020 | 2026-07-26 | 11 | `model_run_id` on served forecasts = nightly BATCH id, not per-SKU MLflow run id | Serving exposes "the latest run" as one coherent batch; per-SKU runs stay in `gold_model_metrics`. Found by e2e test (two SKUs → two run ids → API would filter one out). |
| 021 | 2026-07-26 | 11 | Kafka publish failures inside upload loop are caught per-row | Decision 010 applied at row level too — a broker outage mid-upload must not fail the load. Found while writing failure-scenario tests. |
| 022 | 2026-07-26 | 11 | Contract drift guarded by parsing `types.ts` interfaces in integration tests | Frontend/backend contract can never silently diverge; CI fails on mismatch. |
| 023 | 2026-07-26 | 12 | Infra layer on Oracle Cloud Always Free VM; **no hosted Kafka vendor** | Fact-checked: Upstash Kafka pages 404 (product appears discontinued); Redpanda Serverless is trial-then-paid, not free. Oracle Always Free (Ampere A1/AMD compute) confirmed live and genuinely free. Existing compose file deploys unchanged. Redpanda documented as paid scale-up path. Supersedes decision 002's vendor TBD. |
| 024 | 2026-07-26 | 12 | Kafka exposed to API via SASL/SSL listener on 9094 (compose prod override) | Public PLAINTEXT Kafka would be unacceptable; SCRAM-SHA-512 + TLS with PLAINTEXT kept internal-only. |
