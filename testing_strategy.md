# TrendCast AI — Testing Strategy

**Version:** 1.0 (Phase 11 output)
**Status:** Awaiting approval

---

## 1. Test Pyramid & Coverage

| Layer | Location | Count | What it proves |
|---|---|---|---|
| Backend unit/API | `backend/tests` | 47 | Contract behavior of all 15 endpoints, CSV/ICS validation, degradation flags, caps, auth |
| Producer unit | `producers/tests` | 26 | Parse functions, token buckets, backoff, cache TTLs, health state machine, stale fallback |
| Pipeline unit | `pipeline/tests` | 9 | Medallion transform correctness (dedupe, gaps, calendar, ffill, feature joins) |
| ML unit | `ml/tests` | 22 | Baseline, quantile LGBM, backtest, selection rules, recursion, factor attribution |
| Frontend unit | `frontend/src/test` | 9 | Multi-select behavior, degraded badge, a11y table, API client JWT/error handling |
| **Integration** | `integration/` | 17 | Cross-codebase seams (below) |
| **Total** | | **130** | |

## 2. Integration Suite Design

No Docker on the dev machine → an **in-process harness** chains the real production
code across all four codebases, faking only IO boundaries (DB, broker, Spark):

```
CSV ─► csv_sales.load_sales_upload (real) ─► FakeProducer events
    ─► transforms.to_silver (real) ─► build_feature_rows (real)
    ─► ml.train_all (real LightGBM) ─► ml.infer_all (real recursion)
    ─► seed serving tables ─► FastAPI TestClient (real routers)
    ─► response validated against frontend types.ts interfaces (regex-parsed)
```

- **Contract drift guard:** `test_e2e_response_matches_frontend_contract` extracts field
  names from `frontend/src/lib/types.ts` and asserts the API response contains them.
- **Tenant isolation:** 7 tests proving user B cannot read/delete user A's data through
  any endpoint (second line of defense after Postgres RLS).
- **Failure scenarios:** Kafka down mid-upload (still loads), all feeds down (baseline
  forced, forecast still served), Keepa token exhaustion (cycle skipped cleanly).
- **Security audit:** repo scanned for secret patterns, paid-only hosts, committed
  `.env`, template hygiene.

## 3. Container Smoke Tests (for Docker environments)

Run where Docker is available (documents the full-stack path):

```bash
cd infra && cp env.example .env   # fill keys
docker compose up -d kafka producers
docker compose --profile batch run --rm pipeline   # nightly batch once
```

Then: upload demo CSV via the UI → run batch → dashboard shows forecasts.
This is the Phase 12 pre-deployment checklist, not part of CI.

## 4. What Is NOT Tested (honest register)

| Gap | Why | Mitigation |
|---|---|---|
| Spark job wrappers with a real JVM/Kafka | No Docker/JVM locally | Wrappers are thin IO over unit-tested pure cores; smoke-tested in Docker envs |
| Real Supabase RLS enforcement | No Supabase instance locally | Policies reviewed in migration SQL; API-level scoping tested (tenant suite) |
| pytrends/Keepa live throttling | Would burn real quota in CI | Contract-level fakes; backoff logic unit-tested |
| MLflow registry | Optional dep, NullTracker in tests | Smoke-tested with container in Phase 12 |
| E2E browser (Playwright) | Deferred | UI component tests + API contract tests cover seams; Playwright in a later hardening pass |

## 5. CI Plan (GitHub Actions, free)

- `backend.yml`: pytest backend + producers + pipeline + ml + integration
- `frontend.yml`: vitest + `next build`
- Both on push/PR; no secrets required (all external systems faked).

## 6. Quality Gates (per §17)

A phase/release passes only when: all 130 tests green, frontend build green,
security audit green, and the honest-gap register above is current.
