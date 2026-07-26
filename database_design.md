# TrendCast AI — Database Design

**Version:** 1.0 (Phase 4 output)
**Status:** Awaiting approval
**Stores:** (A) Supabase Postgres — serving/OLTP layer · (B) Delta Lake — analytics/medallion layer

---

## Design Principles

1. **Supabase is the only store the API and dashboard touch.** Delta/Spark is offline analytics.
2. **Row-Level Security everywhere** — tenant isolation enforced by Postgres, not app code.
3. **Idempotent writes** — unique constraints match job upsert keys so batch re-runs are safe.
4. **500MB free-tier budget** — sizing validated in §4; retention policies defined up front.

---

## A. Supabase Postgres Schema

### A.1 `profiles` — user business context (1:1 with auth.users)
```sql
create table public.profiles (
  id                 uuid primary key references auth.users(id) on delete cascade,
  business_name      text,
  country_code       char(2) not null,               -- ISO 3166-1 alpha-2, drives Nager.Date/pytrends region
  city               text,
  latitude           double precision,               -- drives Open-Meteo + Ticketmaster geo
  longitude          double precision,
  timezone           text not null default 'UTC',    -- IANA tz; Silver layer normalizes to this
  currency           char(3) not null default 'USD',
  onboarding_complete boolean not null default false,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
```

### A.2 `products` — user's SKUs
```sql
create table public.products (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.profiles(id) on delete cascade,
  sku          text not null,
  product_name text not null,
  category     text,                                 -- drives pytrends keyword mapping
  sales_days   integer not null default 0,           -- Amendment 1 (denormalized)
  last_sale_date date,                               -- Amendment 1 (denormalized)
  created_at   timestamptz not null default now(),
  unique (user_id, sku)
);
create index products_user_idx on public.products(user_id);
```
> **Amendment 1 (Phase 7):** `sales_days` / `last_sale_date` denormalized onto the table
> (maintained by the CSV loader) so `GET /products` needs no aggregation queries and the
> forecasts endpoint can check the 60-day minimum history cheaply.

### A.3 `sales_daily` — cleaned daily sales (grain: user × sku × date)
```sql
create table public.sales_daily (
  id         bigint generated always as identity,
  user_id    uuid not null references public.profiles(id) on delete cascade,
  sku        text not null,
  date       date not null,
  quantity   numeric(12,2) not null check (quantity >= 0),
  revenue    numeric(14,2) check (revenue >= 0),
  price      numeric(12,2),
  promo_flag boolean not null default false,
  source     text not null default 'csv' check (source in ('csv','synthetic','manual')),
  created_at timestamptz not null default now(),
  primary key (user_id, sku, date)                   -- upsert key = idempotent CSV re-uploads
);
create index sales_daily_user_date_idx on public.sales_daily(user_id, date desc);
```

### A.4 `uploads` — CSV upload audit trail
```sql
create table public.uploads (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.profiles(id) on delete cascade,
  kind         text not null check (kind in ('sales','calendar')),
  file_path    text not null,                        -- Supabase Storage object path
  status       text not null default 'pending'
               check (status in ('pending','validated','loaded','failed')),
  row_count    integer,
  error_report jsonb,                                -- per-row validation errors [{row, field, message}]
  created_at   timestamptz not null default now()
);
```

### A.5 `calendar_events` — school-vacation / custom calendar (from ICS/CSV upload)
```sql
create table public.calendar_events (
  id         bigint generated always as identity unique,  -- Amendment 2: API deletes by id
  user_id    uuid not null references public.profiles(id) on delete cascade,
  label      text not null,                          -- e.g. 'Summer break'
  start_date date not null,
  end_date   date not null check (end_date >= start_date),
  created_at timestamptz not null default now(),
  primary key (user_id, label, start_date)
);
```
> **Amendment 2 (Phase 7):** added identity `id` — `api_contracts.md` deletes events by
> `{id}`; composite PK retained for upsert idempotency.

### A.6 `signal_settings` — per-user signal toggles
```sql
create table public.signal_settings (
  user_id  uuid not null references public.profiles(id) on delete cascade,
  signal   text not null check (signal in
           ('weather','holidays','trends','macro','events','marketplace')),
  enabled  boolean not null default true,            -- marketplace defaults false (opt-in)
  primary key (user_id, signal)
);
```

### A.7 `tracked_asins` — Keepa marketplace tracking (hard cap 10/user)
```sql
create table public.tracked_asins (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.profiles(id) on delete cascade,
  asin       text not null check (asin ~ '^[A-Z0-9]{10}$'),
  created_at timestamptz not null default now(),
  unique (user_id, asin)
);
-- Cap enforced in DB, not just app code:
create function public.enforce_asin_cap() returns trigger language plpgsql as $$
begin
  if (select count(*) from public.tracked_asins where user_id = new.user_id) >= 10 then
    raise exception 'ASIN cap reached: maximum 10 tracked ASINs per user (free-tier quota)';
  end if;
  return new;
end $$;
create trigger tracked_asins_cap before insert on public.tracked_asins
  for each row execute function public.enforce_asin_cap();
```

### A.8 `forecasts` — published model output (grain: user × sku × forecast_date × model_run)
```sql
create table public.forecasts (
  user_id       uuid not null references public.profiles(id) on delete cascade,
  sku           text not null,
  forecast_date date not null,
  model_run_id  text not null,                       -- MLflow run id; only latest run is served
  model_version text not null,                       -- e.g. 'lightgbm:3' or 'seasonal-naive'
  yhat          numeric(14,2) not null,
  yhat_lower    numeric(14,2) not null,              -- 80% interval (q10)
  yhat_upper    numeric(14,2) not null,              -- 80% interval (q90)
  mape_backtest numeric(6,2),                        -- per-SKU backtest quality, surfaced in UI
  generated_at  timestamptz not null default now(),
  primary key (user_id, sku, forecast_date, model_run_id)
);
create index forecasts_serving_idx
  on public.forecasts(user_id, sku, forecast_date) where generated_at > now() - interval '7 days';
```

### A.9 `forecast_factors` — per-forecast explainability (top-5 factors per SKU)
```sql
create table public.forecast_factors (
  user_id     uuid not null references public.profiles(id) on delete cascade,
  sku         text not null,
  model_run_id text not null,
  factor      text not null,                         -- e.g. 'weather.temperature', 'holiday.proximity'
  importance  numeric(6,4) not null,                 -- normalized 0..1
  direction   text check (direction in ('up','down','neutral')),
  primary key (user_id, sku, model_run_id, factor)
);
```

### A.10 `signal_status` — global feed health (written by producers, read by all)
```sql
create table public.signal_status (
  signal          text primary key check (signal in
                  ('weather','holidays','trends','macro','events','marketplace')),
  status          text not null check (status in ('live','stale','degraded','disabled')),
  last_success_at timestamptz,
  last_error      text,
  calls_today     integer not null default 0,
  quota_note      text,
  updated_at      timestamptz not null default now()
);
```

### A.11 Row-Level Security Policies
```sql
-- Enable RLS on all tenant tables
alter table public.profiles         enable row level security;
alter table public.products         enable row level security;
alter table public.sales_daily      enable row level security;
alter table public.uploads          enable row level security;
alter table public.calendar_events  enable row level security;
alter table public.signal_settings  enable row level security;
alter table public.tracked_asins    enable row level security;
alter table public.forecasts        enable row level security;
alter table public.forecast_factors enable row level security;
alter table public.signal_status    enable row level security;

-- Tenant isolation: owner-only access (pattern repeated per table)
create policy profiles_owner on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);
create policy products_owner on public.products
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy sales_owner on public.sales_daily
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy uploads_owner on public.uploads
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy calendar_owner on public.calendar_events
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy signals_owner on public.signal_settings
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy asins_owner on public.tracked_asins
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy forecasts_read on public.forecasts
  for select using (auth.uid() = user_id);
create policy factors_read on public.forecast_factors
  for select using (auth.uid() = user_id);
-- Forecasts/factors are INSERT/UPDATE-only via service role (sync job); users read-only.
create policy signal_status_read on public.signal_status
  for select to authenticated using (true);          -- global health is non-sensitive
```

### A.12 Storage Buckets
| Bucket | Access | Content |
|---|---|---|
| `sales-uploads` | Private; owner-scoped path `{user_id}/{upload_id}.csv` | Raw sales + calendar files |
- Policy: users can `insert/select` only objects under their own `user_id` prefix.

---

## B. Delta Lake Schemas (Analytics Layer)

Common envelope on all Bronze tables:
`source STRING, entity_key STRING, observed_at TIMESTAMP, ingested_at TIMESTAMP,
schema_version INT, payload STRING(JSON)`

### B.1 Bronze (raw, append-only)
| Table | Grain | Key payload fields |
|---|---|---|
| `bronze_sales_raw` | row per CSV record | date, sku, product_name, quantity, revenue, price, promo_flag |
| `bronze_weather` | location × hour | temp, precip, snowfall, wind, weather_code |
| `bronze_holidays` | country × holiday | date, local_name, counties[] |
| `bronze_trends` | keyword × geo × week | interest (0–100) |
| `bronze_macro` | series × date | value |
| `bronze_events` | event | start_date, category, venue_size, geo |
| `bronze_marketplace` | asin × day | price, bsr, category |

Partitioning: `date(observed_at)` for high-volume tables (sales, weather); unpartitioned
for small ones (holidays, macro).

### B.2 Silver (cleaned, daily grain, user-timezone normalized)
| Table | Schema (key columns) |
|---|---|
| `silver_sales_daily` | `user_id, sku, date, quantity, revenue, price, promo_flag, gap_flag BOOL` |
| `silver_weather_daily` | `user_id, date, temp_avg, temp_max, temp_min, precip_mm, snowfall_mm, weather_code` |
| `silver_calendar_daily` | `user_id, date, is_holiday, holiday_name, days_to_holiday INT, is_school_break` |
| `silver_trends_daily` | `user_id, category, date, interest, stale_flag BOOL` |
| `silver_macro_daily` | `series, date, value` (forward-filled monthly → daily) |
| `silver_events_daily` | `user_id, date, event_count, large_event_count, categories[]` |
| `silver_marketplace_daily` | `user_id, asin, date, price, bsr, stale_flag BOOL` |

### B.3 Gold (model-ready + outputs)
| Table | Schema (key columns) |
|---|---|
| `gold_features` | `user_id, sku, date` + feature cols: `lag_1/7/14/28, roll_mean_7/28, dow, month, is_holiday, days_to_holiday, is_school_break, temp_avg, precip_mm, trends_interest, macro_* (ffill), event_count, mkt_price, mkt_bsr` + `signal_quality MAP<STRING,STRING>` |
| `gold_forecasts` | `user_id, sku, forecast_date, model_run_id, model_version, yhat, yhat_p10, yhat_p90, mape_backtest, generated_at` |
| `gold_forecast_factors` | `user_id, sku, model_run_id, factor, importance, direction` |
| `gold_model_metrics` | `model_run_id, user_id, sku, model_version, mape, rmse, trained_at` (audit/backtest history) |

`gold_*` outputs map 1:1 to Supabase `forecasts`/`forecast_factors` via the
`publish_to_supabase` upsert job (upsert keys match the PKs above).

---

## 4. Sizing vs. 500MB Free Tier (pilot)

| Table | Rows (est.) | Size (est.) |
|---|---|---|
| `sales_daily` | 500 SKUs × 730 days ≈ 365k | ~40 MB |
| `forecasts` | 500 SKUs × 30 days × 7-day retention of runs ≈ 105k live | ~15 MB |
| `forecast_factors` | 500 × 5 × 7 runs ≈ 17k | ~2 MB |
| `sales-uploads` bucket | 10 users × 10 MB cap | ~100 MB (Storage, separate from DB) |
| Everything else | small | <5 MB |

**Total DB: ~65 MB ≈ 13% of free quota. ✅ Comfortable.**

**Retention policies:** `forecasts`/`forecast_factors` keep latest 7 model runs
(daily job prunes older); Bronze Delta tables per §2.4 retention; uploads pruned after 90 days.

## 5. Risks

- **RLS misconfiguration** → cross-tenant leak. Mitigation: integration tests asserting
  tenant isolation (Phase 11); policies are uniform and reviewed.
- **Forecast table growth** if runs accumulate → pruning job is part of `publish_to_supabase`.
- **ASIN cap bypass** → enforced by DB trigger, not app code.

## 6. Open Questions

None.

## 7. Confidence Score

**93%** — Schema covers all FRs; grain choices match pipeline upsert keys; sizing verified.

## 8. Next Steps

- Phase 5: API Design → `api_contracts.md`
