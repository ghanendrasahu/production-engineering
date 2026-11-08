---
topic: 28
title: Connection Pooling
category: B
skill: production-engineering
status: stable
---

# 028 — Connection Pooling

## 1. Topic name and metadata

- **Number:** 28 of 111
- **Title:** Connection Pooling
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/028-connection-pooling.md`

## 2. What it is

Maintaining a reusable set of database connections so request handlers borrow and return them instead of opening a TCP+TLS+auth handshake per query.

## 3. Why it exists

Opening a connection per query costs more than the query.

## 4. The engineering problem it solves

Postgres forks a backend process per connection (~5-10MB RAM each); without pooling, a 500-thread app tries to open 500 backends, Postgres falls to its knees, and everything queues behind connection setup (10-100ms per query).

## 5. How it works internally

Client pool (SQLAlchemy: `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`; TCP keepalive; pre-ping `pool_pre_ping=True` for stale detection) reuses connections and validates them before checkout. Server side: PgBouncer in transaction pooling mode multiplexes thousands of clients to few server connections (limits supported statements in transaction mode; session-level state breaks). Sizing math: pool_size ≈ (CPU cores × 2) + disk spindles, split per replica; total across replicas must stay under `max_connections` (default 100 — raise carefully).

## 6. Architecture and design principles

App instances (each with pool) → PgBouncer (optional shared pool) → Postgres. K8s: pool per pod, so `replicas × pod_pool` is what you budget.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Always — every production service.

## 8. When NOT to use it

CLI one-shot script.

**Alternatives:** PgBouncer, RDS Proxy, lazy connection per batch job.

## 9. Implementation strategies

```python
engine = create_engine(
    url, pool_size=10, max_overflow=20, pool_timeout=30,
    pool_recycle=1800, pool_pre_ping=True, pool_use_lifo=True,
)
# async:
engine = create_async_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True)
```

PgBouncer: `pool_mode=transaction`, `max_client_conn=1000`, `default_pool_size=25`.

## 10. Production-grade implementation

**Scenario:** 30 pods × pool_size 10 = 300 > max_connections 200 → Postgres refusing connections. Fix: PgBouncer transaction mode, default_pool_size=20; pod pool 5; connection storms eliminated; p95 900ms→120ms.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (inline in section 9)

This concept has no standalone Python surface — its artifacts are configuration,
templates, or pipeline steps. All runnable material for it lives inline in **section 9 (Implementation strategies)** and **section 12 (FastAPI integration)** where applicable. Do not force a toy example here.

## 12. FastAPI integration where relevant

One engine singleton per process; `Depends(get_db)` yields a session; session closed in `finally`; never create engines per request; startup event does a warm `SELECT 1` per worker.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

LLM servers take seconds per request — pool HTTP connections to the inference server; DB pool for the metadata/catalog side.

## 15. Security considerations

Pool exhaustion is a DoS lever — hard limits + auth on the app.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Opening connections in request handlers; pool_size=max_connections per pod; long transactions holding borrowed connections; no monitoring of pool checkout failures; pool with zero pre_ping behind a NAT/LB that drops idle TCP.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `pool_connections_active/idle`, `pool_checkout_wait_seconds`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Load test beyond pool size and assert timeouts not server crashes; kill DB → verify pre_ping reconnect; measure `pool.checkout()` wait with a metric; failover drill to replica.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Pre_ping
- [ ] Pool_recycle < server `tcp_keepalives` and LB idle timeout
- [ ] LIFO reuse (pool_use_lifo) frees idle connections
- [ ] Measure wait time (`pool_wait_seconds`)
- [ ] Keep transactions short (no network calls inside)
- [ ] Budget total connections
- [ ] PgBouncer for many replicas
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Pool exhaustion (leaked sessions not returned → `pool_timeout` errors after 30s); stale connections after DB restart (pre_ping fixes); transaction-mode PgBouncer breaks prepared statements/named portals/`SET` (use session mode or `max_prepared_statements=0`); all pods × overflow = server OOM; pool_size set to 100 per pod ×20 pods.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/runtime-config-connection.html
- https://www.pgbouncer.org/usage.html

**Related topics in this library:** `#25 Database Indexing`, `#40 Deadlocks`, `#32 Replication`, `#28 Connection Pooling` interacts with `#45 Autoscaling` (replica churn), `#40 Deadlocks`.
