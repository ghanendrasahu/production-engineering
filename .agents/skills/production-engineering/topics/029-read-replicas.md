---
topic: 29
title: Read Replicas
category: B
skill: production-engineering
status: stable
---

# 029 — Read Replicas

## 1. Topic name and metadata

- **Number:** 29 of 111
- **Title:** Read Replicas
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/029-read-replicas.md`

## 2. What it is

One or more asynchronous (or semi-sync) standby copies of the primary database that serve read-only traffic, offloading the primary.

## 3. Why it exists

Reads outgrow the primary long before writes do.

## 4. The engineering problem it solves

Reads outgrow the primary long before writes do; without replicas, scaling headroom is one machine, and any spike (reports, dashboards) browns out transactional traffic.

## 5. How it works internally

Primary streams WAL (physical replication, LSN positions) to standbys; recovery replays logs continuously. Standbys are hot and read-only (`hot_standby=on`). Replication lag = LSN distance, typically < 1s, grows under write bursts or slow replica I/O. Read-your-writes is not guaranteed — route "read after write" to the primary or use LSN-wait (`pg_current_wal_lsn` vs replay LSN, or `statement_timeout` trick). Managed services (RDS/Cloud SQL) automate provisioning and promotion.

## 6. Architecture and design principles

Writers → primary; readers → replica(s); analytics → separate replica; router (PgBouncer read mode / app routing / RDS reader endpoint) sends SELECTs to replicas, writes to primary.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Read:write ratio > 3:1 and reads dominate; analytics need isolation.

## 8. When NOT to use it

Write-heavy workload (replicas won't help; consider `#30 Sharding`); strong consistency required everywhere; tiny database.

**Alternatives:** caching (`#2 Caching`), materialized views, `#31 Partitioning`, vertical scale-up (`#47 Vertical Scaling`).

## 9. Implementation strategies

```ini
# postgresql.conf on replica
primary_conninfo = 'host=primary port=5432 user=replicator password=...'
hot_standby = on
```

```python
PRIMARY = create_engine(url_primary, ...)
REPLICA = create_engine(url_replica, ...)
def read(...): REPLICA.connect()   # or per-request routing via dependency
```

## 10. Production-grade implementation

**Scenario:** Product catalog read-heavy: 25k read QPS; 2 replicas absorb reads; primary handles writes + session reads; p95 read 90ms→12ms; replica lag alert at >2s; nightly report job pinned to a dedicated replica.

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

Dependency `get_read_db()` vs `get_write_db()`; after any write in this request, set a flag on the request state to force primary reads for consistency.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Feature-flagged model A/B: replicas pinned to model version; shadow traffic comparison before promotion.

## 15. Security considerations

Same data, same authz — replicas must enforce identical access rules.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Reading from replica immediately after write without consistency strategy; replicas sized smaller than primary under read+write-burst load; no lag monitoring; manual promotion; long analytics on the OLTP replica.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `replica_lag_seconds`, `replica_promotions_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Simulate lag (pause replay via `pg_wal_replay_pause()`) and verify app behavior; failover drill; verify write-to-read path after write returns primary result; load test reads on replica.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Route user-facing "read-your-write" reads to primary
- [ ] Alert on lag (`pg_stat_replication`)
- [ ] Promote via managed tooling
- [ ] Size replicas ≤ primary
- [ ] Analytics on separate replica
- [ ] Statement_timeout on replica sessions
- [ ] Test failover quarterly.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Lag spike → stale reads (user sees pre-write data); failover splits brain if old primary doesn't fence (use managed failover + fencing); replica overloaded by batch queries → lag grows unbounded; connection routing sends writes to replica → errors/500s; promotion on unplanned outage without synchronous backup → data loss window (RPO > 0).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/warm-standby.html
- https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/index.html

**Related topics in this library:** `#32 Replication`, `#85 Failover`, `#30 Sharding`, `#34 CAP Theorem`, `#35 Eventual Consistency`, `#45 Autoscaling`.
