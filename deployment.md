# TrendCast AI — Deployment

**Version:** 2.0 (Phase 15 — serverless pilot topology, decision 027)
**Status:** Live

---

## 1. Pilot Topology (serverless, $0/month)

```
Users
  │
  ├─► Vercel (Hobby, free)       → Next.js frontend
  ├─► Render (free web service)  → FastAPI backend
  └─► Supabase (free tier)       → Postgres + Auth + Storage
                                     (+ signal_events bus)

GitHub Actions (unlimited free minutes — public repo):
  ├─ producers.yml (cron 4×/day) → signal fetching → Supabase signal_events
  └─ nightly.yml (cron daily)    → transforms + LightGBM train/infer → forecasts
```

**No VM, no Kafka, no Spark, no Docker required anywhere.** The Kafka/Spark/Delta
stack remains in `infra/` + `pipeline/jobs/` as the v2 scale-up path (see §6).

## 2. Step-by-Step Deployment

### 2.1 Supabase
1. Create a free project at supabase.com.
2. SQL Editor → run the migrations **in order**:
   `0001_init.sql`, `0002_signal_events.sql`, `0003_harden_function_search_path.sql`.
3. Authentication → enable Email provider (for pilot: disable "Confirm email"
   or configure SMTP).
4. Storage → create private bucket `sales-uploads`. *(Reserved: no code writes to
   it today — uploads are parsed in memory straight into `sales_daily`. Create it
   so the name is claimed, but nothing depends on it yet.)*
5. Record: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   `SUPABASE_JWT_SECRET` (Settings → API).

### 2.2 Backend — Render (free)
1. New → Web Service → connect repo → root dir `backend`.
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Env: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`,
   `KAFKA_ENABLED=false`, `CORS_ORIGINS=https://<app>.vercel.app`.
   - `CORS_ORIGINS` must be the **exact** deployed origin — scheme + host, no
     trailing slash, no path. It is matched literally, not by pattern. Leaving
     the `<app>` placeholder in place makes every browser request fail preflight
     with `400 Disallowed CORS origin`, which surfaces in the UI as an opaque
     "failed to fetch" rather than an auth or server error.
   - Comma-separate to allow local development too:
     `https://<app>.vercel.app,http://localhost:3000`.
   - `SUPABASE_URL` is the bare project URL (`https://<ref>.supabase.co`) with
     **no** `/rest/v1` suffix — the client appends its own paths.
5. Health check path: `/api/v1/health`.
6. Free-tier sleep: first request after idle takes ~30s (accepted).

### 2.3 Frontend — Vercel (Hobby)
1. Import repo → root dir `frontend` (framework preset Next.js auto-detected).
2. Env (all public/client-side by design):
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_API_URL=https://<api>.onrender.com/api/v1`
     — set this AFTER the first Render deploy (URL only known then), then
     redeploy; or set a predictable Render service name first.
     **Include `/api/v1`; omit any trailing slash.** The client builds requests as
     `${NEXT_PUBLIC_API_URL}${path}`, so dropping the suffix yields `/products`
     at the domain root (404) and a trailing slash yields `//products` (also 404).
     `NEXT_PUBLIC_*` values are inlined at **build** time, so editing this in the
     Vercel dashboard does nothing until you redeploy. Verify the built value with
     `curl -s https://<app>.vercel.app/dashboard | grep -o 'onrender[^"]*'`.
3. Deploy. Preview deployments inherit env vars; keep production values
   identical for pilot (no separate preview config needed).

### 2.4 GitHub Actions (producers + nightly)
1. Repo → Settings → Secrets and variables → Actions → add:
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `FRED_API_KEY`,
   `TICKETMASTER_API_KEY`.
2. Workflows are already in the repo (`.github/workflows/producers.yml`,
   `nightly.yml`) — schedules activate automatically.
3. Do **not** run the workflows yet — see §2.5. Both are no-ops until at least one
   user has completed onboarding, and a green run at this stage proves nothing.
4. Schedules: producers `17 */6 * * *` (4×/day), nightly `42 6 * * *` (06:42 UTC).

### 2.5 First-user validation (run in this order)

> **Order is not optional.** The pipeline is data-driven end to end:
> `runner_ci.py` derives its enabled-signal set from the `signal_settings` table,
> and its weather/events locations from `profiles.latitude/longitude`. With no
> rows in those tables, `enabled_signals` is empty and the producer cycle fetches
> **nothing** — not even FRED macro, which needs no user location. The nightly
> job likewise returns `{"status": "empty", "forecasts": 0}` and exits 0.
>
> Both workflows therefore report **success while doing nothing**. A green tick
> is not evidence the pipeline works; run duration is the honest tell — a real
> nightly trains LightGBM per SKU and takes minutes, not the ~30s a no-op takes.
>
> The single unlock is one user completing onboarding, which writes one
> `profiles` row and six `signal_settings` rows. Nothing upstream of that matters.

1. **API reachable:** `curl https://<api>.onrender.com/api/v1/health` → `{"status":"ok"}`.
2. **CORS correct:** preflight must return `204` with an `access-control-allow-origin`
   header — a `400` here blocks every browser call:
   ```bash
   curl -i -X OPTIONS https://<api>.onrender.com/api/v1/products \
     -H "Origin: https://<app>.vercel.app" \
     -H "Access-Control-Request-Method: GET"
   ```
3. **Frontend points at the API:** confirm the built bundle contains the
   `/api/v1` suffix (see §2.3). Wrong value ⇒ redeploy, not just an env edit.
4. **Sign up** on the Vercel URL. Verify in Supabase: `auth.users` has 1 row.
5. **Complete onboarding** (business name, country, city). This is the step that
   creates the `profiles` row — no database trigger does it, so if the
   `PUT /api/v1/profile` call fails, signup still "succeeds" and the account is
   left in a half-created state that looks fine in the UI. Verify:
   ```sql
   select count(*) from profiles;                                  -- expect 1
   select count(*) from profiles
     where latitude is not null and longitude is not null;          -- expect 1
   select count(*) from signal_settings;                            -- expect 6
   ```
   A `profiles` row with **null lat/long** means the Open-Meteo city geocode
   failed. Onboarding still completes, but weather and events will silently never
   produce data. Re-run onboarding with a larger nearby city.
6. **Generate demo data** → upload reaches `loaded` (Data page shows row count).
   Verify `sales_daily` is non-empty.
7. **Producers:** Actions tab → "Signal Producers (serverless)" → Run workflow.
   Expect the log line `config: signals=[...] locations=1 ...` with a non-empty
   signal list. Then `select count(*) from signal_events;` → non-zero, and the
   Settings page dots turn green (`signal_status` populated).
8. **Nightly:** Actions tab → "Nightly Forecast Pipeline (serverless)" → Run.
   Expect `nightly complete: {'status': 'ok', 'forecasts': N}` with `N > 0`.
   A `'status': 'empty'` result means step 5 or 6 did not actually land.
9. **Dashboard** → select demo SKUs → forecast cards render with bands, MAPE,
   factors, and signal health.
10. **Quota-hit playbook:** a source hitting its free limit flips its badge to
    `stale`/`degraded` automatically — no action needed; forecasts continue on
    cached/baseline paths. Investigate only if a badge stays degraded > 2 days.

## 3. Secrets Inventory

| Secret | Where it lives | Never in |
|---|---|---|
| Supabase service-role | **GitHub Secrets only** | **Render**, frontend, git |
| Supabase JWT secret | Render env only | GitHub, frontend, git |
| Supabase anon key | Render env + Vercel env | git |
| FRED/Ticketmaster keys | **GitHub Secrets** (producers workflow) | Render, frontend, git |
| ~~Keepa key~~ (deferred, decision 025) | — | — |

> **The service-role key must never be set on Render.** It bypasses RLS on every
> table for every tenant, which would defeat layer 1 of tenant isolation. The API
> is built to run without it: `backend/app/config.py` declares no field for it,
> so setting it on Render has no effect except to widen the blast radius of a
> host compromise. See security.md §2.2 for the full three-zone model.

**Rotation:** replace the value at the provider, update Render env (auto-redeploy)
and/or GitHub Secrets (next workflow run picks it up). No code changes.

## 4. Rollback & Failure Playbook

- **Bad deploy:** Vercel/Render instant rollback to previous deployment.
- **Nightly workflow fails:** idempotent — re-run via workflow_dispatch; the
  dashboard keeps serving last good forecasts (7-run retention).
- **Workflow disabled after 60 days of repo inactivity:** GitHub auto-pauses
  schedules on idle repos — any commit re-activates; note in ops runbook.
- **Free-tier breach:** producers self-throttle; signal badges show degraded.

## 5. Monitoring (free-tier compatible)

- Render/Vercel built-in logs; Supabase dashboard metrics.
- GitHub Actions run history = pipeline observability (failed runs email you).
- `signal_status` table = quota observability (surfaced in the UI).
- Optional: UptimeRobot free tier on `/api/v1/health` (also keeps Render warm).

## 6. V2 Scale-Up Path (preserved)

When volume outgrows the serverless projection (many users, high-frequency
signals), provision any Docker host and use the preserved stack:
`infra/docker-compose.yml` (Kafka + producers + pipeline + MLflow) with the
Spark jobs in `pipeline/jobs/`. Migration = point producers at the broker and
run the Spark nightly instead of `local_nightly.py` — transform/ML code is shared.

## 7. Cost Statement

Total monthly cost at pilot scale: **$0** — Vercel Hobby, Render free web
service, Supabase free tier, GitHub Actions (public repo, unlimited minutes).
Named ceilings: Render sleeps when idle; GitHub pauses schedules on 60-day-idle
repos; Supabase 500MB (13% used at pilot sizing).

