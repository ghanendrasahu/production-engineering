---
topic: 30
title: Sharding
category: B
skill: production-engineering
status: stable
---

# 030 — Sharding

## 1. Topic name and metadata

- **Number:** 30 of 111
- **Title:** Sharding
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/030-sharding.md`

## 2. What it is

Horizontal partitioning of a dataset across multiple independent database instances (shards), each owning a subset by key range or hash.

## 3. Why it exists

One machine eventually cannot hold the data or the write rate.

## 4. The engineering problem it solves

Beyond one machine's write capacity/storage, vertical scaling tops out; sharding is the only way to scale writes and storage indefinitely — at substantial complexity cost.

## 5. How it works internally

Shard key selection dominates outcomes (customer_id, tenant_id). Hash ring or modulo maps key → shard. Cross-shard queries scatter-gather; global unique IDs need snowflakes or UUIDs. Resharding = reshashing with minimal movement (consistent hashing) or online resharding tooling (gh-ost/Vitess). Vitess/Citus automate this; hand-rolled is rarely advisable.

## 6. Architecture and design principles

Router (or Citus coordinator) → shard shards (e.g., shard_0..63 PostgreSQL nodes) → per-shard replicas. App layer pins tenant to shard; caches sharded by same key.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Dataset > 1 machine's write capacity or storage, tenant isolation required, growth projected.

## 8. When NOT to use it

Read-heavy (replicas + cache suffice); < 500GB (single Postgres handles plenty); no ops maturity.

**Alternatives:** read replicas, caching, `#31 Partitioning` (cheaper, same DB), vertical scaling, managed distributed DB (CockroachDB, Spanner).

## 9. Implementation strategies

Citus: `SELECT create_distributed_table('orders', 'user_id');` — query planner scatters. Vitess keyspaces with VReplication for resharding. Application: `shard = hash(user_id) % N` then connect to that shard; keep a directory table for migrations.

## 10. Production-grade implementation

**Scenario:** Tenant-per-shard SaaS, 40 shards × replica pairs, 2TB data, 80k write QPS; per-shard blast radius small; hot tenant identified by shard metrics → moved to dedicated shard.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

Modulo routing helper + connection per shard dict; transactions only within one shard.

## 12. FastAPI integration where relevant

Not applicable — this concept is infrastructure/protocol level; there is no FastAPI-specific surface. Apply it underneath FastAPI through configuration, middleware, or dependencies (section 9). Do not force a fake integration.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Sharded vector search by tenant or namespace; per-shard recall unchanged; scatter-gather latency = slowest shard (tail) — hedge idempotent reads.

## 15. Security considerations

Shard key is an access boundary — enforce per-shard authorization server-side.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Sharding before measuring (cache/replica first); random/auto-increment shard keys (destroys locality); cross-shard transactions; ignoring backup complexity; no hot-key handling.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `shard_key_skew`, per-shard load ratio, scatter latency p99

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Deterministic shard routing tests; hot-shard simulation; failover drill per shard; data-consistency audit across shards; full resharding rehearsal on copies.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Pick the shard key from access patterns
- [ ] Keep all hot-path transactions within one shard
- [ ] Co-locate related tables on same key
- [ ] Plan resharding from day 1
- [ ] Managed (Citus/Vitess/Cloud SQL) strongly preferred over hand-rolled
- [ ] Monitoring per shard
- [ ] Tenant injection testing.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Hot shard (one whale tenant) → uneven load; cross-shard joins become application code; resharding with downtime; scatter-gather latency = slowest shard (tail); backups and migrations ×N complexity; replica lag per shard.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://vitess.io/docs/
- https://www.postgresql.org/docs/current/ddl-partitioning.html

**Related topics in this library:** `#31 Partitioning`, `#32 Replication`, `#29 Read Replicas`, `#28 Connection Pooling`, `#95 Network Partitions`, `#46 Horizontal Scaling`.
