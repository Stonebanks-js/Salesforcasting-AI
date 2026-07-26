# TrendCast AI — Implementation Plan

**Version:** 1.0 (Phase 12 output)
**Status:** Living document

---

## Phase Status

| # | Phase | Status | Key artifacts |
|---|---|---|---|
| 1 | Repository Audit | ✅ Complete | Greenfield confirmed |
| 2 | Requirements | ✅ Complete | `PRD.md` |
| 3 | Architecture | ✅ Complete | `architecture.md`, `data_sources.md` |
| 4 | Database Design | ✅ Complete | `database_design.md` (+2 amendments) |
| 5 | API Design | ✅ Complete | `api_contracts.md` |
| 6 | UI Planning | ✅ Complete | `ui_plan.md` |
| 7 | Backend Development | ✅ Complete | `backend/` — 47 tests green |
| 8 | Frontend Development | ✅ Complete | `frontend/` — 9 tests + build green |
| 9 | Data Pipeline | ✅ Complete | `producers/`, `pipeline/`, `infra/` — 35 tests green |
| 10 | Forecasting Model | ✅ Complete | `ml/` — 22 tests green |
| 11 | Integration Testing | ✅ Complete | `integration/` — 17 tests green, 2 real bugs fixed |
| 12 | Deployment | ✅ Complete | `deployment.md`, CI, `render.yaml`, README |
| 13 | Release Approval | ⏳ Pending | `master_checklist.md` sign-off |

## Execution Notes

**Order rationale:** contracts before code (DB + API + UI plans locked before
implementation), code before integration, integration before deployment.
Amendments during implementation were logged as decisions (020–022) rather
than silently absorbed.

**Test counts by phase:** Phase 7: 47 · Phase 8: 9 · Phase 9: +35 ·
Phase 10: +22 · Phase 11: +17 → **130 total**.

## Deferred Work (explicit, with owners)

| Item | Deferred to | Reason |
|---|---|---|
| Playwright E2E browser tests | Hardening pass | Component + contract tests cover seams |
| ES256/JWKS JWT support | Hardening pass | HS256 covers current Supabase projects |
| Docker smoke test of full stack | First deploy | No Docker on dev machine; scripted in testing_strategy.md §3 |
| Shopify/WooCommerce connectors | v2 | Stretch in PRD |
| `POST /forecasts/refresh` on-demand | v2 | Batch-only protects free tiers |
| Real-time sales streaming (POS) | v2 | CSV batch is v1 scope |
| Multi-tenant billing | v2+ | Explicit non-goal |

## Milestones to Pilot

1. ✅ Code-complete v1 (this phase)
2. ⬜ Deploy per `deployment.md` §3 (Supabase → Render → Vercel → Oracle VM)
3. ⬜ Docker smoke test on the VM (testing_strategy.md §3)
4. ⬜ Pilot with 1–2 real users + synthetic data
5. ⬜ First weekly forecast-quality review (MAPE by SKU vs 25% target)
