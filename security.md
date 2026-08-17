# TrendCast AI — Security

**Version:** 1.1 (Phase 15 — serverless credential placement)
**Status:** Awaiting approval

---

## 1. Threat Model (pilot scope)

A multi-tenant SaaS handling sales data (commercially sensitive per user) and
free-tier API keys. Primary threats: cross-tenant data access, credential
leakage, malicious file uploads, and quota abuse.

## 2. Controls

### 2.1 Authentication & Tenant Isolation
- Supabase Auth (email/password); JWT verified by the API on every request
  (HS256 with project JWT secret; ES256/JWKS support is a documented hardening item).
- `user_id` is ALWAYS derived from the token — never accepted as a parameter.
- **Two-layer isolation:** Postgres RLS policies per table (migration 0001) +
  API queries scoped by token user_id. Integration suite proves layer 2.
- API uses the **anon key + caller JWT**, so PostgREST enforces RLS *as the calling
  user*. The service-role key never reaches the API or the frontend — it lives
  only in GitHub Actions (decision 028). This is enforced structurally, not by
  convention: `backend/app/config.py` declares no `supabase_service_role_key`
  field, so the API cannot read one even if it were present in the environment.

### 2.2 Secrets Management
- Secrets only via environment variables; `.env` gitignored; templates
  (`env.example`, `.env.example`) carry placeholders only — enforced by
  `test_security_audit.py` in CI.
- Repo is scanned for secret patterns (AWS keys, private key blocks, live JWTs,
  generic secret assignments) on every test run.
- **Serverless mode (Phase 15, decision 028):** producers and the nightly pipeline
  hold the Supabase **service-role key** in GitHub Secrets (encrypted, masked in
  logs, never printed). This supersedes the Kafka-mediated boundary (decision 015)
  for the pilot — CI runners are ephemeral server-side compute with the same trust
  level as the retired VM path. `signal_events` has RLS with no user policies:
  service-role only, invisible to all authenticated users.

#### Credential placement (serverless pilot)

Three trust zones. A credential appearing outside its zone is a security defect,
not a configuration preference. **Values are never recorded in this repository.**

| Credential | Zone / store | Why it must not move |
|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | **GitHub Secrets only** | Bypasses RLS on every table for every tenant. In the API it would void layer 1 of tenant isolation; in the browser it would expose all tenants' data. |
| `SUPABASE_JWT_SECRET` | **Render only** | Signs and verifies auth tokens. Anyone holding it can mint a valid token for an arbitrary `user_id` and impersonate any tenant. |
| `SUPABASE_ANON_KEY` | Render + Vercel | Publishable by design; safe in the browser *because* RLS constrains it. Not a secret, but still env-supplied. |
| `FRED_API_KEY`, `TICKETMASTER_API_KEY` | **GitHub Secrets only** | Free-tier quota keys. Only the producers call these APIs; the API and frontend never do. |
| `NEXT_PUBLIC_*` | Vercel (build-time) | Inlined into the client bundle at build time. Anything placed here is public — permanently, including in already-served bundles. |

Rotation: rotating `SUPABASE_JWT_SECRET` invalidates every live session and
regenerates the anon and service-role keys with it, so all three zones must be
updated together and both services redeployed.

### 2.3 Input Validation & Uploads
- Pydantic schemas on every request body; `extra="forbid"` on PATCH payloads.
- CSV/ICS uploads: extension + content-type check, 10MB cap, 100k row / 500 SKU
  caps, per-row validation, UTF-8 enforcement; rejected rows reported, never
  partially-parsed into invalid states.
- ICS parser is a strict line scanner (no eval, no XML entity expansion surface).
- ASIN format enforced by regex at API and by CHECK constraint in DB.

### 2.4 Rate Limiting & Quota Protection
- API: 100 req/min default (slowapi middleware); uploads 10/hour.
- External free-tier quotas protected by per-source token buckets + backoff.
- The 10-ASIN/user cap remains enforced in BOTH the API and the
  `tracked_asins_cap` DB trigger, though the marketplace signal itself is
  dormant for the pilot (decision 025 — Keepa confirmed paid). The schema and
  cap are retained for the v2 SP-API path.

### 2.5 Dependency & Supply Chain
- All dependencies are open-source; version-bounded in requirements files.
- No paid SDKs anywhere in the stack (audited by test: paid host scan).

### 2.6 Transport & CORS
- HTTPS in production (Vercel/Render terminate TLS); CORS allow-lists the
  frontend origin only.

## 3. Data Classification

| Data | Class | Handling |
|---|---|---|
| Sales history | Confidential (per tenant) | RLS-scoped; retained per user; deleted with account |
| Forecasts | Confidential (derived) | Same RLS scope |
| API keys (FRED / Ticketmaster) | Secret | GitHub Secrets only; producers-only; masked in CI logs, never printed |
| Signal health | Internal | Read by any authenticated user (non-sensitive) |
| User profile/geo | PII-adjacent | City-level only; no precise address stored |

## 4. Known Limitations (documented, accepted for pilot)

1. JWT verification is HS256-only (fine for current Supabase projects; ES256/JWKS
   needed if the project migrates — tracked as hardening).
2. Rate limiting is per-instance in-memory (free-tier hosts are single-instance;
   move to Redis if scaled).
3. Uploaded CSVs are validated but not virus-scanned (acceptable for text-only
   CSV at pilot; ClamAV sidecar if requirements change).
4. The private `sales-uploads` Storage bucket exists but is **not currently
   written to**: uploads are parsed in memory and rows land directly in
   `sales_daily`, while `uploads.file_path` records a path that is never
   created. No raw-file retention policy is therefore in force. Either wire the
   bucket up or drop it — the current state is a documentation/implementation
   mismatch, not a leak.
5. Working notes and AI session transcripts are a live leak vector: they tend to
   accumulate pasted credentials in plaintext. `Notes-*.txt` is gitignored at the
   repo root, but the repository is **public** — treat any credential that has
   ever appeared in such a file, or in a chat window, as disclosed and rotate it.

## 5. Incident Response (pilot)

- Secret leak → rotate key at provider, update env, redeploy (no code change).
- Cross-tenant bug → disable API (Render), patch, add regression test, redeploy.
- Free-tier quota breach → producer self-throttles (token buckets); health badge
  shows degraded; no user-facing failure.
