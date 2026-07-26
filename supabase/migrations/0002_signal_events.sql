-- TrendCast AI — Serverless signal bus (Phase 15, decision 027)
-- Replaces Kafka topics for the pilot: producers insert envelopes here via the
-- service role (GitHub Actions); the nightly pipeline reads them the same way.
-- RLS enabled with NO user policies = accessible only via service role.

create table public.signal_events (
  id          bigint generated always as identity,
  source      text not null,             -- weather | holidays | trends | macro | events | marketplace
  entity_key  text not null,
  observed_at text not null,             -- ISO date of the observation
  ingested_at timestamptz not null default now(),
  payload     jsonb not null
);

create index signal_events_source_date_idx
  on public.signal_events(source, observed_at);

alter table public.signal_events enable row level security;
-- No user policies: reads/writes happen exclusively via the service role
-- (CI producers + nightly pipeline). Users never touch this table.

-- Retention helper: prune raw events older than 400 days (called by nightly job)
create or replace function public.prune_signal_events() returns void
language sql as $$
  delete from public.signal_events
  where ingested_at < now() - interval '400 days';
$$;
