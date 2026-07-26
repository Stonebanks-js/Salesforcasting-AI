# TrendCast AI — Deployment

**Version:** 1.0 (Phase 12 output)
**Status:** Awaiting approval

---

## 1. Hosted Kafka Vendor Decision (fact-checked 2026-07-26)

| Candidate | Finding | Verdict |
|---|---|---|
| Upstash Kafka | Docs & pricing pages return **404 — product appears discontinued** | ❌ Rejected |
| Redpanda Serverless | Pay-as-you-go with a **30-day trial only — no permanent free tier** | ❌ As "free"; documented as scale-up path |
| **Oracle Cloud Always Free** | **Confirmed live:** Always Free tier includes Ampere A1 (ARM) + AMD Compute VMs, unlimited time | ✅ **Selected** |

**Decision:** the infra layer (Kafka, producers, pipeline, MLflow) runs on an
**Oracle Always Free VM** using the repo's existing `infra/docker-compose.yml`.
Everything user-facing stays on managed free tiers. Caveat flagged honestly:
Always Free capacity is subject to availability at signup and ARM images must
be multi-arch (`python:3.11-slim`, `apache/kafka`, `mlflow` all publish arm64 —
verified in their manifests; use the AMD Always Free micro instance as fallback).

## 2. Deployment Topology (pilot)

```
Users
  │
  ├─► Vercel (Hobby, free)            → Next.js frontend (static prerender + client data)
  ├─► Render (free web service)       → FastAPI backend (uvicorn)
  └─► Supabase (free tier)            → Postgres + Auth + Storage

Oracle Always Free VM (Docker Compose):
  ├─ Kafka (KRaft, SASL/TLS exposed for the API's sales.raw producer)
  ├─ producers (6 signal producers, 6h cycle)
  ├─ pipeline (nightly batch, cron-triggered on the VM)
  └─ MLflow (internal-only, no public exposure)
```

## 3. Step-by-Step Deployment

### 3.1 Supabase
1. Create a free project at supabase.com.
2. SQL Editor → run `supabase/migrations/0001_init.sql`.
3. Authentication → enable Email provider. (For pilot: disable "Confirm email"
   OR configure SMTP; default is confirm-email.)
4. Storage → create private bucket `sales-uploads`.
5. Record: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   `SUPABASE_JWT_SECRET` (Settings → API).

### 3.2 Backend — Render (free)
1. New → Web Service → connect repo → root dir `backend`.
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Env: all Supabase vars + `KAFKA_BOOTSTRAP_SERVERS=<vm-ip>:9094`
   + `KAFKA_ENABLED=true` + `CORS_ORIGINS=https://<app>.vercel.app`.
5. Free-tier sleep: first request after idle takes ~30s (accepted, NFR note).

### 3.3 Frontend — Vercel (Hobby)
1. Import repo → root dir `frontend`.
2. Env: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
   `NEXT_PUBLIC_API_URL=https://<api>.onrender.com/api/v1`.
3. Deploy. (Framework preset Next.js; no custom config needed.)

### 3.4 Infra VM — Oracle Always Free
1. Create Ampere A1 (or AMD micro) instance, Ubuntu 24.04; open ports
   22 (SSH, your IP only) and 9094 (Kafka SASL/TLS, API egress IP or 0.0.0.0/0
   for pilot with SASL required).
2. Install Docker + compose plugin.
3. `git clone <repo>; cd infra; cp env.example .env` and fill values.
4. `docker compose up -d kafka producers mlflow`
5. Nightly batch: host cron → `0 6 * * * cd infra && docker compose --profile batch run --rm pipeline`
6. Kafka exposure for the API: enable SASL/SSL listener on 9094
   (compose override file `docker-compose.prod.yml` below); the local PLAINTEXT
   listener stays internal.

**`infra/docker-compose.prod.yml` (apply with `-f docker-compose.yml -f docker-compose.prod.yml`):**
```yaml
services:
  kafka:
    environment:
      KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093,SASL_SSL://:9094
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,SASL_SSL://<vm-public-ip>:9094
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,SASL_SSL:SASL_SSL
      KAFKA_SASL_ENABLED_MECHANISMS: SCRAM-SHA-512
    ports:
      - "9094:9094"
```

## 4. Secrets Inventory

| Secret | Where it lives | Never in |
|---|---|---|
| Supabase service-role | Render env, VM .env | frontend, git |
| Supabase JWT secret | Render env | git |
| FRED/Ticketmaster/Keepa keys | VM .env (producers only) | API, frontend, git |
| Kafka SCRAM password | VM .env + Render env | git |

## 5. Rollback & Failure Playbook

- **Bad deploy:** Vercel/Render instant rollback to previous deployment.
- **Nightly batch fails:** idempotent — next run catches up; dashboard keeps
  serving last good forecasts (Supabase retains 7 runs).
- **VM dies:** recreate from compose + git; Delta volume is the only state —
  back up `/delta` daily to Supabase Storage via cron (`rclone`).
- **Free-tier breach:** producers self-throttle; signal badges show degraded.

## 6. Monitoring (free-tier compatible)

- Render/Vercel built-in logs; Supabase dashboard metrics.
- `signal_status` table = quota observability (surfaced in UI).
- Optional: UptimeRobot free tier pinging `/api/v1/health` every 5 min
  (also keeps Render warm).

## 7. Cost Statement

Total monthly cost at pilot scale: **$0** (all services on genuine free tiers).
Named ceilings: Render free instance sleeps; Oracle Always Free capacity
subject to availability; Redpanda Serverless documented as the paid scale-up
path if Kafka outgrows the VM.
