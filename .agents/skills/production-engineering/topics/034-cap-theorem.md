---
topic: 34
title: CAP Theorem
category: B
skill: production-engineering
status: stable
---

# 034 — CAP Theorem

## 1. Topic name and metadata

- **Number:** 34 of 111
- **Title:** CAP Theorem
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [distributed-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/034-cap-theorem.md`

## 2. What it is

In the presence of a network partition (P), a distributed system must choose between consistency (C — all nodes see the same data) and availability (A — every request gets a non-error response). When the network is healthy you get both; the theorem only constrains partition behavior.

## 3. Why it exists

During a partition, safety and reachability cannot both be guaranteed.

## 4. The engineering problem it solves

Teams discover too late that their "highly available" system returned divergent data during a partition — or that their "consistent" system returned 100% errors instead of reads.

## 5. How it works internally

Partition tolerance is not optional for anything crossing a network (the network *will* partition). During a partition, a node that cannot see its peers must either serve potentially stale data (favor A — Dynamo/Cassandra, AP) or refuse to serve (favor C — Spanner/etcd via consensus, CP). Genuine CA exists only within one machine. Important refinements: PACELC extends the trade-off to normal operation (latency vs consistency); many systems mix modes (MongoDB per-node read concern, etcd linearizable reads). CAP is about *availability of the whole system during partitions*, not about consistency quality otherwise.

## 6. Architecture and design principles

DB selection + replication mode + client routing decisions; all derived from which side of CAP you pick for each operation.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Choosing storage/replication semantics — it is a decision lens, not a feature.

## 8. When NOT to use it

Single-node deployment (CAP is meaningless there).

**Alternatives:** per-operation consistency levels, CP consensus for control plane, AP for data plane.

## 9. Implementation strategies

CP: etcd/Consul/ZooKeeper, Postgres synchronous replication, Spanner. AP: Cassandra (tunable consistency per query: QUORUM, ONE), DynamoDB (eventually + conditional writes for critical keys), Redis (AP-ish with async replication). Mixed: read replicas with consistency routing.

## 10. Production-grade implementation

**Scenario:** Cart service on Cassandra with `LOCAL_QUORUM` writes/reads; during an AZ partition the store keeps serving (AP) — carts may briefly diverge; checkout reconciles via conflict resolution (last-write-wins with timestamp + business rule for money-ish fields). Analytics reads never block writes.

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

During partitions: CP for quota/billing (reject), AP for retrieval cache — document which side each AI path chose.

## 15. Security considerations

Never authorize off eventual data — stale grants are takeover windows.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

"We're CA"; claiming MongoDB is CP/AP without understanding read/write concern; strong consistency required but AP DB chosen for scale; AP for financial balance without reconciliation; ignoring quorum sizing (even counts split).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `quorum_health`, `minority_side_unavailable` (per CP side)

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Chaos partition test (drop traffic between DCs); assert documented behavior: CP rejects, AP serves; verify conflict-resolution rules at scale; quorum-loss drill; verify alerting on quorum degradation.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Choose per data class: money → CP
- [ ] Cart/session → AP with reconciliation
- [ ] Presence → AP
- [ ] Accept stale reads only with explicit contract
- [ ] Document the chosen behavior during partitions
- [ ] Test partitions (chaos), not just theory
- [ ] Monitor quorum health.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** AP system shows stale/price-drift data during partition → customer anger, support tickets; CP system hard-fails everything → 100% error rate during partition; quorum loss (2 of 3 down) → no majority, no writes; "CA" assumptions invalidated by a single cross-AZ link; misreading CAP as "pick 2 of 3" and ignoring partition as inevitability.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://en.wikipedia.org/wiki/CAP_theorem

**Related topics in this library:** `#35 Eventual Consistency`, `#32 Replication`, `#33 Leader Election`, `#95 Network Partitions`, `#96 Clock Skew`, `#86 Multi-Region Deployment`.
