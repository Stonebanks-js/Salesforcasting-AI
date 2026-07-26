# TrendCast AI — Data Sources Inventory (Free-Tier Register)

**Version:** 1.0 (Phase 3 output)
**Status:** Awaiting approval
**Rule:** Every source must be free or have a genuinely usable free tier at pilot scale.
If a free tier is projected to be exceeded, it must be flagged here — never silently assumed.

---

## Source Register

### 1. Open-Meteo — Weather
- **URL:** https://open-meteo.com
- **Cost:** Free for non-commercial use; **no API key required**
- **Rate limits:** ~10k calls/day, ~5k/hour, ~600/min (non-commercial fair use)
- **Auth:** None
- **Data used:** Daily forecast + historical (archive API): temperature, precipitation,
  snowfall, wind, weather-code — at user-configured coordinates
- **Refresh cadence:** Forecast daily; history backfill once on onboarding
- **Pilot-scale projection:** 10 users × ~2 calls/day ≈ 20 calls/day — **well within limits ✅**
- **Fallback on exhaustion/outage:** Cache last-known forecast (24h TTL); exclude weather
  features beyond that; model degrades to baseline-eligible; health status → `stale`/`degraded`

### 2. Nager.Date — Public Holidays
- **URL:** https://date.nager.at
- **Cost:** Free; **no API key required**
- **Rate limits:** No published hard limit; polite-use expected
- **Auth:** None
- **Data used:** Public holidays per ISO country code (100+ countries), incl. regional subdivisions
- **Refresh cadence:** Once per year per configured country (fully cacheable); on region change
- **Pilot-scale projection:** ~10–20 calls/year — **negligible ✅**
- **Fallback:** Holidays are deterministic and cacheable for a full year; outage has
  effectively zero impact (serve from cache/Delta)

### 3. pytrends — Search Trends (UNOFFICIAL)
- **URL:** https://github.com/GeneralMills/pytrends (wraps Google Trends)
- **Cost:** Free; **no API key** — but **unofficial and unsupported**
- **Rate limits:** Undocumented; Google returns HTTP 429 under moderate load;
  practical safe budget ≈ a few calls/hour with backoff
- **Auth:** None
- **Data used:** Weekly/daily interest-over-time for 1–3 keywords per product category, per region
- **Refresh cadence:** Every 6 hours per keyword set (batched), randomized jitter
- **Pilot-scale projection:** ~500 SKUs → ~25 categories × 4 calls/day ≈ 100 calls/day —
  **feasible only with aggressive caching and per-keyword batching ⚠️**
- **Fallback on throttle:** Exponential backoff (max 24h); serve last-known values up to 7 days;
  then exclude trends features and mark `degraded`. **This source may break at any time;
  it is a supplementary signal, never a core dependency.**

### 4. FRED — Macroeconomic Indicators
- **URL:** https://fred.stlouisfed.org/docs/api
- **Cost:** Free; **free API key required**
- **Rate limits:** No published hard cap; throttling under abuse; polite batching expected
- **Auth:** API key (env var `FRED_API_KEY`)
- **Data used:** Configurable series (defaults: CPIAUCSL, UMCSENT, UNRATE, PCE) —
  monthly observations
- **Refresh cadence:** Daily check; series update monthly → effectively ~1 call/series/month
- **Pilot-scale projection:** <150 calls/month — **well within limits ✅**
- **Fallback:** Monthly macro data forward-fills cleanly; serve last-known up to 90 days

### 5. Ticketmaster Discovery — Local Events
- **URL:** https://developer.ticketmaster.com
- **Cost:** Free tier; **free API key required**
- **Rate limits:** ~5,000 calls/day, ~5 calls/second (free tier)
- **Auth:** API key (env var `TICKETMASTER_API_KEY`)
- **Data used:** Events by geo-radius around user coordinates: date, category, venue size
- **Refresh cadence:** Daily per user-region (1 call/user/day, batched by proximity)
- **Pilot-scale projection:** ~10 calls/day — **well within limits ✅**
- **Fallback:** Events beyond 7 days stale are dropped (they decay in relevance anyway);
  mark `stale`; model proceeds without event features
- **Coverage note:** Weak outside major markets — treated as supplementary signal

### 6. Keepa — Amazon Marketplace (OPT-IN, capped)
- **URL:** https://keepa.com/#!api
- **Cost:** Free tier; **free API key required**
- **Rate limits:** Token-based; free tier grants a small token allotment refilling
  ≈ 1 token/minute; each product query costs ≥1 token
- **Auth:** API key (env var `KEEPA_API_KEY`)
- **Data used:** Price history + Best-Sellers-Rank history per tracked ASIN
- **Refresh cadence:** Once daily per ASIN (strict token bucket)
- **Pilot-scale projection:** **Hard cap: 10 ASINs per user** → 10 users × 10 ASINs ×
  1 token/day = 100 tokens/day — **feasible only with the cap and daily batching ⚠️**
- **Fallback on token exhaustion:** Skip cycle, serve last-known (7-day TTL), mark
  `degraded`, surface quota message in UI. Opt-in toggle; off by default

### 7. User Sales Data (CORE — always required)
- **Source:** CSV upload via dashboard (schema: `date, sku, product_name, quantity,
  revenue[, price, promo_flag]`), stored in Supabase Storage, validated by FastAPI
- **Refresh cadence:** User-initiated; synthetic generator available for demo
- **Fallback:** None — forecasting requires sales history; this is the one hard dependency

### 8. School-Vacation Calendar Upload (USER-PROVIDED, optional)
- **Source:** Manual ICS/CSV upload (no reliable global free API exists — confirmed decision)
- **Processing:** Parsed to date-range flags per region; joined as calendar features in Silver/Gold
- **Fallback:** Absent → feature is simply all-zero; no degradation state needed

---

## Quota Monitoring

- Every producer reports `{source, calls_made, quota_known, status}` to the
  `signals.health` Kafka topic each run; persisted to Supabase `signal_status`.
- Dashboard shows per-feed badge: **live** (fresh), **stale** (cache in use),
  **degraded** (feature excluded), **disabled** (user toggle off).
- QA gate (Phase 11): audit confirms no paid keys and no projected free-tier breach.

## Deferred / Rejected Sources

| Source | Reason |
|---|---|
| OpenWeatherMap | Open-Meteo preferred (keyless, no signup); OWM kept as documented fallback (60 calls/min free) |
| PredictHQ | Free tier too limited for production reliance; Ticketmaster chosen |
| Amazon SP-API | Requires seller approval; not "free to call" — Keepa used instead |
| Alpha Vantage | FRED preferred for macro reliability; AV documented as fallback (500 calls/day free) |
| School-vacation APIs | No reliable global free option — manual upload instead |
