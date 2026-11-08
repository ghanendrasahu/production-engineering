---
topic: 32
title: Replication
category: B
skill: production-engineering
status: stable
---

# 032 — Replication

## 1. Topic name and metadata

- **Number:** 32 of 111
- **Title:** Replication
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [database-engineering.md](../references/database-engineering.md)
- **Topic file:** `.agents/skills/production-engineering/topics/032-replication.md`

## 2. What it is

Copying data from a source database to one or more targets continuously, so multiple nodes hold the same data for durability, availability, and read scale.

## 3. Why it exists

A single copy of data is a liability; copies buy durability and reads.

## 4. The engineering problem it solves

A single database is a durability and availability liability (disk failure, accident, corruption); without replication, recovery = restore from backup, meaning minutes-to-hours of data loss and downtime.

## 5. How it works internally

Streaming replication ships WAL records; logical replication decodes logical change sets. Sync vs async: sync (semi-sync `synchronous_commit=remote_apply`) waits for standby ack — durability over latency; async has possible data loss (RPO>0) on failover but better availability. Failover promotion selects a standby; `repmgr`/Patroni/managed services orchestrate leader election and fencing. Replication slots pin WAL if standby is down (disk fill risk).

## 6. Architecture and design principles

Primary ↔ replicas (same AZ + cross-AZ); watchers (Patroni via etcd) elect and fence; apps route via proxy.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Always, for any production DB.

## 8. When NOT to use it

Ephemeral dev data.

**Alternatives:** backups only (insufficient), distributed SQL (CockroachDB/Spanner — built-in replication), cloud multi-AZ.

## 9. Implementation strategies

Postgres: WAL archive + standby; `synchronous_standby_names = 'ANY 1 (s1, s2)'`; Patroni ensures one leader (fencing via etcd/DCS lease). Managed: RDS Multi-AZ + read replicas; monitor `pg_stat_replication.replay_lag`.

## 10. Production-grade implementation

**Scenario:** Orders DB: 1 primary + 1 sync replica same AZ + 2 async cross-region replicas; nightly restore test; RPO = 0 (sync), RTO = 5min via automated failover.

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

Not applicable — this concept is infrastructure/protocol level; there is no FastAPI-specific surface. Apply it underneath FastAPI through configuration, middleware, or dependencies (section 9). Do not force a fake integration.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Replicate the metadata DB+vector store for reads; version both by embedding-model generation — mismatched replicas serve stale vectors.

## 15. Security considerations

WAL streams are network reads of all data — TLS-encrypt replication links.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Async replica without knowing your RPO; manual promotion; replication as backup replacement; no failover testing; ignoring replication slot bloat.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `replication_lag_bytes`, `wal_sender_status`, `slot_retained_bytes`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Failover drill monthly (promote replica, verify app reconnect); restore drill; lag measurement at load; verify no dual-primary after partition (chaos test).

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Patroni/managed failover with fencing
- [ ] Sync for zero-RPO
- [ ] Cross-region for DR
- [ ] Alert on lag
- [ ] Test restores
- [ ] Monitor slots
- [ ] Never rely on one region only.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Async replica promoted → lost committed transactions; replication slot abandoned → WAL disk fill; split-brain after network partition (two primaries) without fencing → corruption; sync replica slow → write latency = replica latency; backup restore untested → backup is useless.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/warm-standby.html
- https://www.postgresql.org/docs/current/streaming-replication.html

**Related topics in this library:** `#29 Read Replicas`, `#85 Failover`, `#33 Leader Election`, `#83 Disaster Recovery`, `#84 Backups`, `#95 Network Partitions`, `#86 Multi-Region Deployment`.
