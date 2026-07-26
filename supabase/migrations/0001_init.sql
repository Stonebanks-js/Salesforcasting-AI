-- TrendCast AI — Initial schema (implements database_design.md v1.0)
-- Amendment 1: products gains denormalized sales_days / last_sale_date,
-- maintained by the CSV loader, so GET /products needs no aggregation queries.

create table public.profiles (
  id                  uuid primary key references auth.users(id) on delete cascade,
  business_name       text,
  country_code        char(2) not null,
  city                text,
  latitude            double precision check (latitude between -90 and 90),
  longitude           double precision check (longitude between -180 and 180),
  timezone            text not null default 'UTC',
  currency            char(3) not null default 'USD',
  onboarding_complete boolean not null default false,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create table public.products (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.profiles(id) on delete cascade,
  sku            text not null,
  product_name   text not null,
  category       text,
  sales_days     integer not null default 0,       -- Amendment 1 (denormalized)
  last_sale_date date,                             -- Amendment 1 (denormalized)
  created_at     timestamptz not null default now(),
  unique (user_id, sku)
);
create index products_user_idx on public.products(user_id);

create table public.sales_daily (
  user_id    uuid not null references public.profiles(id) on delete cascade,
  sku        text not null,
  date       date not null,
  quantity   numeric(12,2) not null check (quantity >= 0),
  revenue    numeric(14,2) check (revenue >= 0),
  price      numeric(12,2),
  promo_flag boolean not null default false,
  source     text not null default 'csv' check (source in ('csv','synthetic','manual')),
  created_at timestamptz not null default now(),
  primary key (user_id, sku, date)
);
create index sales_daily_user_date_idx on public.sales_daily(user_id, date desc);

create table public.uploads (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.profiles(id) on delete cascade,
  kind         text not null check (kind in ('sales','calendar')),
  file_path    text not null,
  status       text not null default 'pending'
               check (status in ('pending','validated','loaded','failed')),
  row_count    integer,
  error_report jsonb,
  created_at   timestamptz not null default now()
);

create table public.calendar_events (
  id         bigint generated always as identity unique,  -- Amendment 2: API deletes by id
  user_id    uuid not null references public.profiles(id) on delete cascade,
  label      text not null,
  start_date date not null,
  end_date   date not null check (end_date >= start_date),
  created_at timestamptz not null default now(),
  primary key (user_id, label, start_date)
);

create table public.signal_settings (
  user_id uuid not null references public.profiles(id) on delete cascade,
  signal  text not null check (signal in
          ('weather','holidays','trends','macro','events','marketplace')),
  enabled boolean not null default true,
  primary key (user_id, signal)
);

create table public.tracked_asins (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.profiles(id) on delete cascade,
  asin       text not null check (asin ~ '^[A-Z0-9]{10}$'),
  created_at timestamptz not null default now(),
  unique (user_id, asin)
);

create or replace function public.enforce_asin_cap() returns trigger
language plpgsql as $$
begin
  if (select count(*) from public.tracked_asins where user_id = new.user_id) >= 10 then
    raise exception 'ASIN cap reached: maximum 10 tracked ASINs per user (free-tier quota)';
  end if;
  return new;
end $$;

create trigger tracked_asins_cap before insert on public.tracked_asins
  for each row execute function public.enforce_asin_cap();

create table public.forecasts (
  user_id       uuid not null references public.profiles(id) on delete cascade,
  sku           text not null,
  forecast_date date not null,
  model_run_id  text not null,
  model_version text not null,
  yhat          numeric(14,2) not null,
  yhat_lower    numeric(14,2) not null,
  yhat_upper    numeric(14,2) not null,
  mape_backtest numeric(6,2),
  generated_at  timestamptz not null default now(),
  primary key (user_id, sku, forecast_date, model_run_id)
);
create index forecasts_serving_idx on public.forecasts(user_id, sku, forecast_date);

create table public.forecast_factors (
  user_id      uuid not null references public.profiles(id) on delete cascade,
  sku          text not null,
  model_run_id text not null,
  factor       text not null,
  importance   numeric(6,4) not null,
  direction    text check (direction in ('up','down','neutral')),
  primary key (user_id, sku, model_run_id, factor)
);

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

-- ---------------------------------------------------------------------------
-- Row-Level Security
-- ---------------------------------------------------------------------------
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
create policy signal_settings_owner on public.signal_settings
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy asins_owner on public.tracked_asins
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy forecasts_read on public.forecasts
  for select using (auth.uid() = user_id);
create policy factors_read on public.forecast_factors
  for select using (auth.uid() = user_id);
create policy signal_status_read on public.signal_status
  for select to authenticated using (true);
