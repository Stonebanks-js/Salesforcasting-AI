# TrendCast AI — Security

**Version:** 1.0 (Phase 11 output)
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
- API uses the **anon key + caller JWT**; the service-role key exists only in the
  offline pipeline sync job (server-to-server, never in API or frontend).

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

### 2.3 Input Validation & Uploads
- Pydantic schemas on every request body; `extra="forbid"` on PATCH payloads.
- CSV/ICS uploads: extension + content-type check, 10MB cap, 100k row / 500 SKU
  caps, per-row validation, UTF-8 enforcement; rejected rows reported, never
  partially-parsed into invalid states.
- ICS parser is a strict line scanner (no eval, no XML entity expansion surface).
- ASIN format enforced by regex at API and by CHECK constraint in DB.

### 2.4 Rate Limiting & Quota Protection
- API: 100 req/min default (slowapi middleware); uploads 10/hour.
- External free-tier quotas protected by per-source token buckets + backoff;
  Keepa additionally hard-capped at 10 ASINs/user in BOTH API and a DB trigger.

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
| API keys (FRED/TM/Keepa) | Secret | Env vars; producers-only; never logged |
| Signal health | Internal | Read by any authenticated user (non-sensitive) |
| User profile/geo | PII-adjacent | City-level only; no precise address stored |

## 4. Known Limitations (documented, accepted for pilot)

1. JWT verification is HS256-only (fine for current Supabase projects; ES256/JWKS
   needed if the project migrates — tracked as hardening).
2. Rate limiting is per-instance in-memory (free-tier hosts are single-instance;
   move to Redis if scaled).
3. Uploaded CSVs are validated but not virus-scanned (acceptable for text-only
   CSV at pilot; ClamAV sidecar if requirements change).
4. Supabase Storage files are kept 90 days then pruned (retention policy).

## 5. Incident Response (pilot)

- Secret leak → rotate key at provider, update env, redeploy (no code change).
- Cross-tenant bug → disable API (Render), patch, add regression test, redeploy.
- Free-tier quota breach → producer self-throttles (token buckets); health badge
  shows degraded; no user-facing failure.
