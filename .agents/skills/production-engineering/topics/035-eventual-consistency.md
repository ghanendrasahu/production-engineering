---
topic: 35
title: Eventual Consistency
category: B
skill: production-engineering
status: stable
---

# 035 — Eventual Consistency

## 1. Topic name and metadata

- **Number:** 35 of 111
- **Title:** Eventual Consistency
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [distributed-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/035-eventual-consistency.md`

## 2. What it is

A consistency model in which, absent new updates, all replicas converge to the same value after some (usually sub-second) propagation delay; readers may observe stale data in the interim.

## 3. Why it exists

Synchronous global consistency is too expensive for most read paths.

## 4. The engineering problem it solves

Requiring synchronous global consistency destroys availability and latency at scale; but unmodeled staleness causes user-visible contradictions (cart shows item, checkout says sold out).

## 5. How it works internally

Writes accepted by one replica, propagated asynchronously (WAL streaming, gossip, log shipping). Convergence mechanisms: last-write-wins (needs timestamps — beware `#96 Clock Skew`), CRDTs (counters, sets with mathematical merge — Riak, Redis CRDT Enterprise), version vectors for detecting concurrent writes, read-repair and hinted handoff in Dynamo-style systems. Bounded staleness SLAs (e.g., Cosmos DB's ≤ 5s, or session tokens guaranteeing read-your-writes within a session) make it usable.

## 6. Architecture and design principles

Replicas/caches/read models everywhere; consistency is restored by propagation + occasional reconciliation (anti-entropy, read repair, scheduled audits).

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

High read scale, availability over immediacy, social/feed/cart/profile data.

## 8. When NOT to use it

Balances, inventory enforcement, authz revocation, anything where stale = money or access.

**Alternatives:** strong consistency (primary reads), session consistency, CRDTs for collaborative state.

## 9. Implementation strategies

Read replicas with LSN check for session consistency:

```python
ws = write_engine.connect().scalar(select(func.pg_current_wal_lsn()))   # after write
# route subsequent reads to replica; wait until replay_lsn >= ws (or fallback to primary)
```

Cassandra per-query `CONSISTENCY QUORUM`; cache TTL as bounded staleness (60s); outbox/CDC projection lag metric; client `X-Session-ID` + token for read-your-writes.

## 10. Production-grade implementation

**Scenario:** Product pages served from Redis cache with 60s TTL and invalidation on write via pub/sub — 95% cache hits, max 60s staleness; inventory counts always read from primary (strongly consistent) while descriptions come from cache.

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

Stale indexes are fine for docs; never stale for quota/authz — budget TTLs explicitly.

## 15. Security considerations

Cache authz grants with short TTL only; revoke must beat cache expiry.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

"Eventually consistent" with no bound stated; relying on TTL alone for invalidation; wall-clock ordering; ignoring convergence testing; stale authz caches without TTL discipline.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `convergence_lag_seconds`, `conflicts_resolved_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Convergence test (write once, assert all replicas equal within bound after poll); lag-injection test; conflict-resolution unit tests (concurrent writes); user-facing read-your-writes assertion; chaos test killing a replica and verifying no stale reads beyond bound.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Define per-field staleness budgets
- [ ] Read-your-writes for the writing user
- [ ] Monotonic reads within session
- [ ] Version vectors instead of wall clocks
- [ ] Reconciliation/anti-entropy jobs
- [ ] Lag metrics with alerts
- [ ] Invalidation on write, TTL as backstop
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Unbounded lag without monitoring → day-old data in dashboards; last-write-wins silently overwrites earlier write depending on clock; read-your-writes violation right after write (user sees stale profile); no reconciliation job → permanent divergence in projections; cache invalidation missed → user sees deleted content forever (TTL saves you); using eventual data for authorization decisions (cached role revoked 60s late — acceptable? define it).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://en.wikipedia.org/wiki/Eventual_consistency

**Related topics in this library:** `#34 CAP Theorem`, `#50 Cache Invalidation`, `#29 Read Replicas`, `#14 Idempotency`, `#96 Clock Skew`, `#30 Sharding`.
