# Engineering Checklists

Copy-paste gates for the moments that decide whether production goes well. Pull the checklist matching the task; do not read all of them.

## Production Readiness

Run before any production deploy. Pair with `templates/production-audit.md` for full audits.

## Architecture & Code
- [ ] Requirements and failure scenarios documented; simplest architecture chosen (see SKILL.md decision framework)
- [ ] Modular boundaries; no duplicated logic; DI used where it aids tests
- [ ] Input validation at every boundary (Pydantic/schema); consistent exception types; no bare `except:`
- [ ] No hardcoded secrets; config from env; startup fails fast on missing config
- [ ] Timeouts on every outbound call and DB statement; retries exponential + jitter; only where idempotent
- [ ] Bounded queues and bounded concurrency everywhere; no unbounded in-memory growth
- [ ] Transactions short; lock ordering consistent; `statement_timeout` set

## Data
- [ ] Migrations applied via pipeline; backward-compatible (expand → backfill → contract)
- [ ] Indexes for hot queries; `EXPLAIN` verified; `N+1` eliminated (query count asserted in tests)
- [ ] Backups exist AND restore was tested in the last 90 days; RPO/RTO documented
- [ ] Rollback for this release rehearsed against current schema

## API & Web
- [ ] AuthN/Z on every route; scopes verified; rate limits set; input size caps
- [ ] Error responses never leak internals; consistent error shape
- [ ] CORS explicit allowlist (if browser clients); security headers (HSTS/CSP/X-Content-Type-Options)
- [ ] Health (`/healthz`) and readiness (`/readyz`) endpoints; readiness checks real dependencies with deadline

## Operations
- [ ] Structured JSON logs with trace_id; PII redaction filter verified
- [ ] RED metrics per route + exemplars; dashboards exist for new paths
- [ ] Alerts for new failure modes (actionable only, with runbook)
- [ ] Canary or staged rollout plan; auto-rollback criteria (error budget burn) defined
- [ ] On-call owns this service; escalation path documented
- [ ] Rollback command tested and < 5 minutes; image/artifact retained (digest-pinned)

## Verification
- [ ] Tests pass incl. failure-path tests; load test at 2x expected peak passed
- [ ] Chaos/failure injection performed for new dependency (kill it; observe behavior)
- [ ] Security review passed (see `checklists/security-review.md`); secrets scan clean
- [ ] Outstanding risks documented and signed off by the requester

## Security Review

Before exposing an endpoint, handling user data, or granting new access. Severity: CRITICAL = fix before ship; HIGH = fix before production; MEDIUM = ticket with owner.

## Authentication & Authorization
- [ ] CRITICAL: Every mutating/sensitive route requires auth; no endpoint forgets it (grep for unauthenticated routes)
- [ ] CRITICAL: Tokens verified — signature, expiry, issuer, audience, algorithm allowlist (no `alg: none`)
- [ ] HIGH: Least-privilege scopes/roles; tenant isolation enforced server-side on every query/cache/tool call
- [ ] HIGH: Refresh tokens rotate; reuse invalidates family; access tokens ≤ 15 min
- [ ] MEDIUM: Step-up (re-auth) for payments/deletions/admin

## Input & Output
- [ ] CRITICAL: No SQL/command/template injection — parameters/allowlists everywhere; no f-string SQL
- [ ] CRITICAL: Output encoding per context (HTML/attr/JS/URL); autoescaping enabled; every raw-HTML sink audited
- [ ] HIGH: File upload — type/size/AV scanned; stored outside web root with random names
- [ ] HIGH: SSRF — URLs validated (scheme allowlist + resolved IP not private/loopback/metadata), redirects revalidated
- [ ] MEDIUM: Error pages reveal nothing (stack traces, versions, SQL)

## Secrets & Crypto
- [ ] CRITICAL: No secrets in repo/image/CI logs; `detect-secrets`/gitleaks clean; scan runs in CI
- [ ] CRITICAL: TLS ≥1.2 everywhere incl. internal (mTLS for east-west); `verify=True`; no `verify=False`
- [ ] HIGH: Encryption at rest for storage/backups; keys in KMS; rotation plan + tested
- [ ] HIGH: Secrets rotation with overlap; apps fail-fast if missing

## Web/App Hygiene
- [ ] HIGH: CSRF defenses on cookie-auth mutations (SameSite=Lax + token/custom header)
- [ ] HIGH: CORS explicit allowlist; no `*` with credentials; `Vary: Origin`
- [ ] HIGH: Security headers: HSTS, CSP (no unsafe-inline), X-Content-Type-Options, frame-ancestors
- [ ] MEDIUM: Dependency scan clean (osv-scanner); base image patched; non-root container
- [ ] MEDIUM: Rate limiting + request size caps on all routes; expensive endpoints stricter
- [ ] MEDIUM: Auth/session audit log events (login, reset, privilege change) shipped and retained

## Data & Privacy
- [ ] HIGH: PII inventory; minimize; redact in logs/spans; encrypt field-level where required
- [ ] MEDIUM: Deletion/export (GDPR) paths verified incl. backups retention policy
- [ ] MEDIUM: Least-privilege DB role (app role: no DDL/superuser); separate migration role

## AI-Specific (if applicable)
- [ ] HIGH: Prompt injection defenses (instruction/data separation, tool least privilege, no secrets in context)
- [ ] HIGH: Per-tenant retrieval/cache/tool isolation; output PII filter; model output never eval'd
- [ ] MEDIUM: Cost/spend budget with alert + kill switch; token quota per tenant

**Sign-off:** reviewer + date. ZERO critical findings open at deploy.

## Performance Review

Use before load testing, release, or when latency/throughput regresses. Numbers claimed, not vibes.

## Measurement First
- [ ] Baseline captured: p50/p95/p99 per route at production-like data size and concurrency
- [ ] Load test at 2x expected peak executed (k6/Locust); results stored with build SHA
- [ ] p99 (not average) is the headline metric; fanout P999 checked for parallel architectures
- [ ] Profiler run attached (py-spy / pyinstrument / EXPLAIN (ANALYZE, BUFFERS))

## Data & Queries
- [ ] No seq scans on hot tables (EXPLAIN checked); indexes match predicates; stats fresh (pg_stat_statements)
- [ ] Query count per endpoint asserted in tests (no N+1); pagination by keyset not deep OFFSET
- [ ] Transaction duration < 100ms; lock waits monitored; connection pool wait ~0 under peak
- [ ] Connection pooling sized for all replicas (replicas × pod_pool < server budget; PgBouncer if needed)

## Caching & Compute
- [ ] Hot reads cached (cache-aside, TTL + jitter, single-flight on miss); hit ratio measured
- [ ] Cache invalidation path defined and tested; stampede protection present
- [ ] Responses gzip/br compressed; static served via CDN; payload minimized (field selection, protobuf/orjson)
- [ ] Obvious CPU hotspots eliminated (per-request allocations, sync I/O in hot path)

## Tail Latency (P99)
- [ ] GC/runtime pauses measured (or ruled out); lock/queue waits measured
- [ ] Fanout children bounded by remaining deadline; hedged requests only for idempotent reads with headroom
- [ ] Slow tenant/route isolated; dashboards split by route and tenant
- [ ] Cache misses don't fall off a cliff at 10x (cold-start path tested)

## Capacity & Limits
- [ ] Saturation point identified (the real constraint: DB? GPU? gateway?); headroom ≥ 30-50% on it
- [ ] Autoscaling on saturation metric (queue depth/CPU/conns), with scale-down stabilization
- [ ] Provider quotas checked (DB max_connections, NAT, API RPM); LLM TPM tracked
- [ ] Retry amplification bounded; breakers in place; shedding policy (429/503 + Retry-After) at saturation

## Budgets
- [ ] Latency budget decomposed per hop with owners; SLO thresholds set; alert on burn rate
- [ ] Cost per request computed (LLM tokens, DB, egress) — no silent 3x regressions
**Sign-off:** p99 before → p99 after, load conditions, reviewer.

## Deployment Review

Use when changing CI/CD, rollout strategy, or before a risky release.

## Artifact & Pipeline
- [ ] Build once; promote same digest everywhere (staging == prod); image tagged by SHA/digest, no `:latest`
- [ ] CI < 10 min target; lint+typecheck+tests+security scan gates; no `continue-on-error`
- [ ] OIDC/short-lived credentials for cloud auth; no static keys in pipeline YAML
- [ ] Lockfiles committed; hermetic builds (uv sync --frozen / npm ci); base image by digest

## Rollout Strategy (choose consciously)
- [ ] Rolling: `maxUnavailable: 0`, `maxSurge: 1`; preStop drain; terminationGrace ≥ longest request
- [ ] Or Canary: automated analysis on SLIs + auto-rollback; sticky cohorts; bake ≥ 10 min/step
- [ ] Or Blue-green: double capacity; smoke gate before flip; DB expand/contract compatible with BOTH versions
- [ ] Feature flags for risky behavior: kill switch tested; flag owners + removal date assigned
- [ ] Rollback rehearsed THIS release: command known, time measured (< 5 min), previous artifact retained

## Data & Migrations
- [ ] Expand/contract respected; old code runs on new schema for the full rollout window
- [ ] Indexes `CONCURRENTLY`; backfills batched + throttled; migration tested on prod-like copy
- [ ] Backup taken pre-DDL; downgrade path or explicit irreversible note

## Platform Readiness
- [ ] Probes: startup (slow boots), liveness (cheap, no dependencies), readiness (real deps, short deadline)
- [ ] Resource requests+limits set; PDBs; HPA with stabilization; namespace quotas fine
- [ ] Secrets/config via platform (external-secrets/CSI), not baked; env vars audited
- [ ] Health endpoint shape verified from outside (LB/CDN path); TLS cert valid > 30 days

## Post-Deploy Verification
- [ ] Smoke suite green; synthetic probe from ≥2 regions; dashboards show deploy SHA marked
- [ ] 5xx rate + p99 checked at 5/15/30/60 min; error budget unaffected
- [ ] Rollback triggers pre-agreed (burn rate > X for 5 min ⇒ auto-rollback)
- [ ] Stakeholders notified; change window respected for freezes
**Sign-off:** deployer + reviewer + timestamp.

## Database Review

Before schema changes, new queries, or performance claims. Pair with `references/database-engineering.md`.

## Schema Changes
- [ ] Migration in same PR as code; revision chain valid; `downgrade` tested or marked irreversible
- [ ] Backward compatible with previous app version (expand → backfill → contract, days apart)
- [ ] `ALTER` on big tables batched/`CONCURRENTLY`; no long AccessExclusiveLock windows
- [ ] Backup/snapshot before DDL; restore tested if change is risky
- [ ] `alembic check` / schema-drift detection clean in CI

## Query Review (per PR touching data access)
- [ ] Query count per request asserted (no N+1; eager loading explicit — selectin/joined)
- [ ] `WHERE`/`JOIN`/`ORDER BY` columns indexed; composite index order justified (selectivity)
- [ ] `EXPLAIN (ANALYZE, BUFFERS)` pasted for new/changed queries; no full seq scans on large tables
- [ ] Keyset pagination for deep lists; no unbounded `SELECT *`; LIMIT always present in list paths
- [ ] Short transactions; no external calls inside; explicit lock ordering if multiple rows locked
- [ ] `statement_timeout` set appropriately; pool budget: replicas × pool_size < max_connections

## Locking & Concurrency
- [ ] Expected interleavings analyzed: read-modify-write via atomic SQL / `FOR UPDATE` / version column (optimistic)
- [ ] Hot-row contention identified; strategy documented (pessimistic vs optimistic vs queue)
- [ ] Deadlock potential reviewed; deadlock victim retry present; `log_lock_waits=on`
- [ ] Idempotency for client-retried mutations; unique constraints as final arbiter

## Data Lifecycle
- [ ] Retention policy defined for new tables (partition drop / TTL / archival); GDPR erasure path OK
- [ ] Backups include new data; restore tested if table is critical; replication slots unblocked
- [ ] Read-replica lag acceptable for new read paths; consistency expectations documented

## Verification
- [ ] Tests against prod-like volume (≥1M rows seed) — plans flip at scale
- [ ] pg_stat_statements baseline captured; post-change comparison planned
- [ ] Rollback plan for data (not just schema) written down
**Sign-off:** reviewer + date. Zero CRITICAL findings before merge to main.

## Incident Response

During and immediately after a production incident. Print it; keep it in the repo.

**Principle: mitigate first, understand later. Roll back, flag off, or failover — then diagnose.**

## First 5 Minutes
- [ ] Acknowledge the page (MTTA < 5 min target)
- [ ] Open incident channel/bridge; assign roles: **Incident Commander**, **Comms**, **Scribe**
- [ ] State severity (P1 full outage/data risk · P2 major degradation · P3 minor · P4 backlog)
- [ ] Scribe starts timeline NOW: every action + timestamp, in-channel
- [ ] Current impact quantified: users, error rate, % revenue path affected

## Mitigation
- [ ] Immediate reversible action identified: deploy rollback / kill flag / failover / scale up / shed load
- [ ] Rollback/flag commands prepared BEFORE executing; execute and watch metrics (5xx, p99) for 2 min
- [ ] If rollback unsafe → isolate: drain traffic, route around, flip dependent off
- [ ] Communicate to stakeholders + status page **every 30 minutes** even if "no change"
- [ ] Escalate: need more hands? Provider support? Management? Decision to declare disaster?

## Containment & Recovery
- [ ] Root cause narrowed but NOT required to restore service; stop the bleeding, not the investigation
- [ ] Data integrity checked (no partial writes committed? idempotency charges? duplicates sent?)
- [ ] Recovery confirmed on metrics, not vibes: error rate back to baseline for ≥10 min, p99 normal
- [ ] Monitor for recurrence window (e.g., caches refilling, cron overlap) — stay on watch 1h after all-clear
- [ ] Status page updated to RESOLVED; affected users notified if data impact

## Immediately After
- [ ] All-clear declared explicitly in channel; temporary credentials/silences removed
- [ ] Logs/metrics/trace snapshots preserved (retention extended for this window)
- [ ] Postmortem scheduled within 48h (mandatory for P1/P2); owner assigned
- [ ] Follow-up: error-budget charged; deployment frozen until review (if burn policy says so)

## What NOT to Do
- Do not debug before mitigating. Do not deploy unreviewed fixes during P1.
- Do not keep silence; do not skip postmortem because "it was obvious".
- Do not blame; the system let the failure happen — find systemic fixes.

**Blameless always. Curiosity over certainty. Facts over memory.**
