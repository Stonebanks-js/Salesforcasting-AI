# TrendCast AI — UI Plan

**Version:** 1.0 (Phase 6 output)
**Status:** Awaiting approval
**Stack:** Next.js (App Router) · TypeScript · Tailwind CSS · Recharts · Supabase JS

---

## 1. Design Goals

1. **Multi-product comparison is the hero** — selecting several SKUs and seeing
   side-by-side forecasts must be the fastest path in the app (≤ 2 clicks from login).
2. **Trust through transparency** — every forecast shows its confidence band, backtest
   accuracy (MAPE), top driving factors, and live signal health.
3. **Degradation is visible, not scary** — stale/disabled signals shown as calm badges,
   never blocking the user.
4. **Accessible & responsive** — WCAG AA; usable on a 13" laptop and a phone.

## 2. Sitemap & Flows

```
/login ──► /onboarding (first login only) ──► /dashboard (default landing)
                                              ├── /upload
                                              └── /settings
```

**Core flow:** Login → Dashboard → click SKU multi-select → pick 2–10 SKUs →
forecasts render side-by-side with bands, factors, and signal health.

**First-run flow:** Sign up → Onboarding (business info + region + signal toggles) →
prompted to upload CSV **or** generate synthetic demo data → land on Dashboard with
"forecasts ready tomorrow after first nightly run" state (batch-only architecture —
empty-state honesty, with demo data shortcut).

## 3. Page Plans

### 3.1 `/login`
- Supabase Auth email/password; sign-up + sign-in tabs; password reset link.
- Server-side redirect to `/dashboard` if session exists.

### 3.2 `/onboarding` (wizard, 2 steps)
- **Step 1 — Business:** name, country (dropdown → ISO code), city (text, geocoded to
  lat/lon via Open-Meteo geocoding API — free/keyless), timezone (auto from geo, editable),
  currency.
- **Step 2 — Signals:** 6 toggle cards with plain-language descriptions and free-tier
  notes (e.g., marketplace card says "optional, up to 10 Amazon products").
- Submit → `PUT /profile` → redirect `/upload` with "Add your data" prompt.

### 3.3 `/upload`
- Dropzone (CSV) with schema hint + downloadable template + per-row error report
  after processing (polls `GET /uploads/{id}` every 2s until terminal state).
- **"Generate demo data instead"** button → synthetic dataset (500 SKUs optional; default 20).
- Second dropzone for school-vacation calendar (ICS/CSV) — collapsible "Advanced".

### 3.4 `/dashboard` — the core screen

```
┌──────────────────────────────────────────────────────────────────────┐
│ TrendCast AI                              🟢 signals 5/6 live   ⚙ 👤 │
├──────────────────────────────────────────────────────────────────────┤
│ [ SKU multi-select ▾  3 selected: MUG-001, TSH-022, CAB-104    ] [▶] │
│ Horizon: ( 7 | 14 | ●30 ) days            Last run: today 06:00 UTC  │
├──────────────────────────────┬───────────────────────────────────────┤
│ MUG-001 · Ceramic Mug        │ TSH-022 · Logo Tee                    │
│ MAPE 14.2% · lightgbm        │ MAPE 21.7% · seasonal-naive ⚠degraded │
│ ╭──────╮  ╭──────╮           │ ╭──────╮  ╭──────╮                     │
│ │      ╲╱│      │  chart w/  │ │      ╲╱│      │                     │
│ │ shaded │band  │           │ │      │      │                        │
│ ╰──────╯  ╰──────╯           │ ╰──────╯  ╰──────╯                     │
│ ▲ trends interest (31%)      │ ▲ days_to_holiday (24%)              │
│ ▲ days_to_holiday (22%)      │ ▼ temperature (12%)                  │
├──────────────────────────────┴───────────────────────────────────────┤
│ CAB-104 · USB-C Cable 2m — MAPE 11.8% · lightgbm  …                  │
└──────────────────────────────────────────────────────────────────────┘
```

- **SKU multi-select:** searchable combobox (cmdk-style), 1–10 selections, chips for
  selected SKUs; selections persisted in URL (`?skus=`) for shareability.
- **Forecast cards:** one per SKU, responsive grid (1 col mobile → 2–3 col desktop).
  Each: Recharts `AreaChart` — shaded P10–P90 band + median line + optional historical
  overlay (toggle); MAPE badge; model version; top-5 factor list with ▲▼ direction.
- **Degraded state:** amber badge + tooltip ("Forecast uses baseline model — search
  trends feed is stale"). Never an error page.
- **Signal health strip (top-right):** 6 dots with tooltip per feed; click → `/settings#signals`.
- **Insufficient history:** card shows "Need N more days of sales data" state.
- **Empty state (no forecasts yet):** explains nightly batch + CTA to upload/generate data.

### 3.5 `/settings`
- Profile/region editing; signal toggles; tracked ASIN manager (add/remove, "4 of 10
  used" quota meter); calendar event list; data management (re-upload, delete).

## 4. Component Tree (dashboard)

```
<AppShell>                      # nav, auth guard, signal health strip
├── <SignalHealthStrip>         # GET /signals/status, 60s SWR refresh
├── <SkuMultiSelect>            # cmdk combobox; GET /products?search=
├── <HorizonToggle>             # 7/14/30
└── <ForecastGrid>
    └── <ForecastCard> ×N       # keyed by sku
        ├── <ForecastChart>     # Recharts Area + Line + optional history overlay
        ├── <MapeBadge>
        ├── <ModelBadge>        # lightgbm | seasonal-naive (+ degraded icon)
        └── <FactorList>        # top-5 ▲▼ with importance bars
```

## 5. State & Data Fetching

- **Server state:** SWR (lightweight, free) — `useSWR` hooks per endpoint; forecast
  fetch keyed on `[skus, horizon]`; revalidate on focus off (data is daily-batch).
- **URL state:** selected SKUs + horizon in query params (`nuqs` or native
  `useSearchParams`) — shareable links.
- **Client state:** minimal (upload progress, wizard step) — React `useState`; no Redux.
- **Auth:** Supabase JS session; middleware guard for protected routes; JWT attached
  to API calls via a fetch wrapper.

## 6. Styling & Accessibility

- Tailwind; dark-mode-ready tokens (class strategy); charts themed via CSS variables.
- Recharts colors: categorical palette (colorblind-safe, Okabe-Ito); confidence band =
  same hue at 20% opacity — never color-only meaning (badges have icons + text).
- Keyboard: full combobox navigation, focus-visible rings, skip-to-content.
- ARIA: charts get `role="img"` + text summary table (`<details>` "View data as table" —
  doubles as no-JS/screen-reader path).
- `prefers-reduced-motion`: disable chart animations.

## 7. Performance Budget

- Dashboard first load < 200KB JS (route-level code splitting; Recharts lazy-loaded).
- Forecast fetch: single `/forecasts` call for all selected SKUs (< 100KB).
- Lighthouse targets: Performance ≥ 90, Accessibility ≥ 95.

## 8. Frontend Testing Plan (feeds Phase 11)

- Component tests (Vitest + Testing Library): multi-select behavior, degraded badge
  rendering, error/empty states.
- API mock: MSW with fixtures matching `api_contracts.md` exactly (contract-first UI).
- E2E (Playwright, free): login → generate demo data → dashboard renders ≥ 1 forecast card.

## 9. Risks

- **Recharts bundle size** — mitigated by lazy import; fallback to lighter lib only if budget breaks.
- **Empty-state confusion** (batch-only forecasts) — mitigated with explicit onboarding copy + demo-data CTA.
- **Multi-select on mobile** — chips collapse into a count + bottom-sheet picker.

## 10. Open Questions

None.

## 11. Confidence Score

**90%** — Conventional patterns throughout; contract-first with MSW means frontend can
be built in parallel with backend.

## 12. Next Steps

- Phase 7: Backend Development (FastAPI app + Supabase schema + RLS + tests)
