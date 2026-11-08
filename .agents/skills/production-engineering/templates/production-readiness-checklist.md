---
name: production-readiness-checklist
title: Production Readiness Checklist
---

# Production Readiness Checklist — <service/repo> — <date>

Verdict up top: SHIP / SHIP WITH FIXES (list) / DO NOT SHIP. Reviewer: ___ · Date: ___

## Architecture & Correctness
- [ ] Simplest sufficient design chosen; ADRs written (`architecture-decision-record.md`)
- [ ] Transaction boundaries correct; no network calls inside transactions; consistent lock order
- [ ] Race conditions audited on shared state (atomic ops / version columns / queues)
- [ ] Idempotent mutations (client retries, double-clicks, webhook redelivery are safe)
- [ ] N+1 eliminated — query count per endpoint asserted in tests

## Resilience & Failure Behavior
- [ ] Timeout on every outbound call (connect + read), budgets propagate
- [ ] Retries capped, exponential backoff + jitter, only on transient failures
- [ ] Circuit breakers on flaky deps; degraded mode defined and tested
- [ ] Bounded queues/pools/payloads; backpressure at saturation
- [ ] Rollback rehearsed; canary or flag rollout with auto-rollback on burn-rate

## Data
- [ ] Migrations: expand/contract compatible with previous version; rollback path
- [ ] Indexes verified via `EXPLAIN (ANALYZE, BUFFERS)` at production-like volume
- [ ] Connection pool budget respected (all replicas × pool < max_connections)
- [ ] Backup exists AND restore was tested ≤ 90 days ago; RPO/RTO known

## Security
- [ ] Server-side authn/authz on every route; tenant isolation tested
- [ ] Input validation at boundary; DAST/SAST clean; secrets from manager; CI secrets scan clean
- [ ] TLS/mTLS everywhere incl. internal; `verify=True`; deps scanned (osv-scanner)
- [ ] Logging/trace redaction verified (no PII/tokens/passwords)

## Health & Operations
- [ ] `/healthz` (process) + `/readyz` (dependencies, short deadline) — liveness does NOT check deps
- [ ] Metrics (RED per route), dashboards owned, logs with `trace_id`, P99 tracked vs SLO
- [ ] Alerts actionable with runbooks; MTTA tracked; paging policy agreed
- [ ] Probes: startup/liveness/readiness correct for boot time and dependency behavior

## Sign-off
- [ ] Open risks documented with owner + acceptance by requester
- [ ] Postmortem template pre-filled; on-call owns the service
