---
topic: 31
title: Partitioning
category: B
skill: production-engineering
status: stable
---

# 031 — Partitioning

## 1. Topic name and metadata

- **Number:** 31 of 111
- **Title:** Partitioning
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/031-partitioning.md`

## 2. What it is

Splitting one large table into physical partitions (by range, list, or hash of a key) inside a single database for faster scans, cheaper purges, and better maintenance.

## 3. Why it exists

Big tables must be prunable for scans, purges, and maintenance.

## 4. The engineering problem it solves

A 300M-row `events` table makes every vacuum, index build, and backup brutal; dropping 30 days of data with `DELETE` creates bloat and locks.

## 5. How it works internally

PostgreSQL declarative partitioning: parent table + per-partition child tables; planner prunes partitions by constraint (`WHERE created_at >= now() - interval '7 days'` touches only recent partitions); partition pruning at plan time (static) or runtime (dynamic, for prepared statements/`EXECUTE`). Partition-wise joins and aggregates parallelize. `DETACH PARTITION` is instant vs DELETE + VACUUM.

## 6. Architecture and design principles

Inside the same Postgres; partitions stored as separate relations; global (cross-partition) unique constraints impossible — uniqueness must include partition key.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Very large tables with time-range filters or retention drop requirements.

## 8. When NOT to use it

Table < 10M rows; dominant access pattern is by non-key (global scan unavoidable); cross-partition uniqueness required.

**Alternatives:** `#30 Sharding`, archival to object storage + external tables, materialized rollups.

## 9. Implementation strategies

```sql
CREATE TABLE events (id bigint, created_at timestamptz NOT NULL, user_id bigint, payload jsonb)
PARTITION BY RANGE (created_at);
CREATE TABLE events_2026_11 PARTITION OF events
  FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
-- monthly pg_partman or manual:
ALTER TABLE events DETACH PARTITION events_2026_08 CONCURRENTLY;  -- instant drop
```

## 10. Production-grade implementation

**Scenario:** 400M-row `audit_log` partitioned monthly; delete of > 180 days = instant DETACH; quarterly partition creation automated (pg_partman); backups of hot partitions separate; p95 queries only recent partitions stay < 20ms.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

SQLAlchemy model with `postgresql_partition_by="RANGE (created_at)"`; create partition tables via scheduled migration/pg_partman.

## 12. FastAPI integration where relevant

Not applicable — this concept is infrastructure/protocol level; there is no FastAPI-specific surface. Apply it underneath FastAPI through configuration, middleware, or dependencies (section 9). Do not force a fake integration.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Partition event/audit tables by day; detach old partitions instantly — ML pipelines scan huge ranges cheaply.

## 15. Security considerations

Partition DDL needs a migration role separate from the app role.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Partitioning small tables; hash partition across one DB for "sharding feel"; range by a non-filtered column; default partition catching everything (hides bugs); forgetting index per partition (each child needs its own).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `partition_pruning_hits`, `bloat_ratio`, next-partition-exists gauge

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

EXPLAIN verifying pruning; detach/attach test; next-partition-missing drill; query timing at full scale; vacuum/bloat check monthly.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Partition by the dominant filter (time)
- [ ] Monthly range + retention by detach
- [ ] Pg_partman to automate create/drop
- [ ] Keep partition count < 100
- [ ] Include partition key in unique indexes
- [ ] Test pruning with EXPLAIN (look for "Partitions chosen").
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Queries without partition-key predicate scan ALL partitions (slower than before); unique constraint missing partition key → rejected; forgetting to create next month's partition → INSERT into parent fails ("no partition found"); partition count explosion (>1000 children degrades planner); wrong granularity (too small → partition overhead).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/ddl-partitioning.html

**Related topics in this library:** `#25 Database Indexing`, `#26 Query Optimization`, `#29 Read Replicas` (partition + replica combo), `#81 Database Migrations`.
