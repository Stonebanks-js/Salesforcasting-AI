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
2. SQL Editor → run `supabase/migrations/0001_init.sql`, then
   `supabase/migrations/0002_signal_events.sql`.
3. Authentication → enable Email provider (for pilot: disable "Confirm email"
   or configure SMTP).
4. Storage → create private bucket `sales-uploads`.
5. Record: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   `SUPABASE_JWT_SECRET` (Settings → API).

### 2.2 Backend — Render (free)
1. New → Web Service → connect repo → root dir `backend`.
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Env: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`,
   `KAFKA_ENABLED=false`, `CORS_ORIGINS=https://<app>.vercel.app`.
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
3. Deploy. Preview deployments inherit env vars; keep production values
   identical for pilot (no separate preview config needed).

### 2.4 GitHub Actions (producers + nightly)
1. Repo → Settings → Secrets and variables → Actions → add:
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `FRED_API_KEY`,
   `TICKETMASTER_API_KEY`.
2. Workflows are already in the repo (`.github/workflows/producers.yml`,
   `nightly.yml`) — schedules activate automatically.
3. First run: Actions tab → "Signal Producers (serverless)" → **Run workflow**
   (workflow_dispatch), then "Nightly Forecast Pipeline (serverless)" → Run.
4. Schedules: producers `17 */6 * * *` (4×/day), nightly `42 6 * * *` (06:42 UTC).

### 2.5 Post-deploy verification
1. `curl https://<api>.onrender.com/api/v1/health` → `{"status":"ok"}`.
2. Sign up on the Vercel URL → onboarding → **Generate demo data** → upload
   reaches `loaded` (Data page shows row count).
3. Actions tab → run producers workflow → Settings page signal dots turn green
   (weather/holidays/trends/macro/events `live` in `signal_status`).
4. Actions tab → run nightly workflow → logs show
   `nightly complete: {'status': 'ok', 'forecasts': N}`.
5. Dashboard → select demo SKUs → forecast cards render with bands, MAPE,
   factors, and signal health.
6. **Quota-hit playbook:** a source hitting its free limit flips its badge to
   `stale`/`degraded` automatically — no action needed; forecasts continue on
   cached/baseline paths. Investigate only if a badge stays degraded > 2 days.

## 3. Secrets Inventory

| Secret | Where it lives | Never in |
|---|---|---|
| Supabase service-role | Render env, **GitHub Secrets** | frontend, git |
| Supabase JWT secret | Render env | git |
| FRED/Ticketmaster keys | **GitHub Secrets** (producers workflow) | API, frontend, git |
| ~~Keepa key~~ (deferred, decision 025) | — | — |

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

