---
topic: 33
title: Leader Election
category: B
skill: production-engineering
status: stable
---

# 033 — Leader Election

## 1. Topic name and metadata

- **Number:** 33 of 111
- **Title:** Leader Election
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [distributed-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/033-leader-election.md`

## 2. What it is

The process by which a group of nodes agrees on one leader to coordinate writes or critical sections, with the others standing by to take over on failure.

## 3. Why it exists

Exactly one node must act as the writer — split brain corrupts everything.

## 4. The engineering problem it solves

Without a single leader, two nodes both accept writes and diverge (split-brain), corrupting data or double-charging — or duplicate batch jobs run concurrently.

## 5. How it works internally

Consensus-based election (Raft/Paxos) or lease-based election with a shared store (etcd/ZooKeeper with TTL + fencing tokens; Consul sessions). Raft: candidate requests votes from majority; majority wins; leader replicates log entries; follower election timer (~150-300ms) triggers new election on silence. Fencing: the leader must attach a monotonically increasing **fencing token** to protected writes; the storage system rejects tokens lower than the last seen — this is what actually stops a deposed leader (e.g., GC pause then write) from corrupting data. Leases need renewal < TTL; holder must prove leadership on every critical write, not just at acquisition.

## 6. Architecture and design principles

Leader + followers behind a virtual IP or through a consensus-backed registry; clients route to leader or through a load balancer that understands leadership.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

One writer must exist — schedulers, primary DB, partition assignment.

## 8. When NOT to use it

Stateless handlers (LB handles this), reads-only.

**Alternatives:** K8s leader election (Lease object), single replica + Patroni, consensus DB (etcd/ZooKeeper) as source of truth.

## 9. Implementation strategies

Patroni (Postgres HA) uses etcd as the DCS with fencing; Kafka uses controller election via KRaft/ZooKeeper; Redis Sentinel for cache failover; app-level: `SET lease NX PX 10000` with a uniqueness token (uuid) + compare-and-delete renewal via Lua.

```python
import uuid
FENCE = uuid.uuid4().hex
r.set("leader:scheduler", FENCE, nx=True, px=15000)   # acquire
# renew halfway through the lease with Lua: only delete/re-set if we still hold it
```

## 10. Production-grade implementation

**Scenario:** Nightly billing scheduler on 3 pods; etcd-backed lease; fencing token passed to the DB so a partitioned leader's stale UPDATE is rejected after a new leader emerges; zero double invoices during a network partition.

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

One scheduler must coordinate distributed embedding runs — lease + fence; duplicate indexing doubles cost silently.

## 15. Security considerations

Lease tokens leak authority — fence them; never log; rotate on suspicion.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Election without fencing (the classic "zombie leader" bug); lease longer than your outage tolerance; heartbeat from the same event loop as the work; leader performing writes without checking the token; "leader" by config flag in a deploy (two leaders after config drift).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `leader_changes_total`, `lease_renewal_failures_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Network-partition chaos test (block leader); GC-pause injection; verify stale-token write rejected; failover drill measuring time-to-new-leader; election-storm test under flaky links.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Always fencing tokens
- [ ] TTL ~ 3-10× RTT, renew at 1/3
- [ ] Election timeouts randomized
- [ ] Monitor leadership changes and lease expirations
- [ ] Never assume "I acquired it, I keep it"
- [ ] Test failover
- [ ] Treat DCS as a critical dependency with alerting.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Leader GC-pauses 30s, lease expires, new leader elected, old leader wakes and writes — without fencing tokens → corruption; split brain with two primaries on both sides of partition; flapping (election every 200ms) due to short timeouts or slow acks; DCS (etcd) unavailable → no new leader can be elected (failover stalls); lease renewal blocked by a full event loop (no election but also no renewal) → leadership lost predictably at ~TTL.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://raft.github.io/
- https://etcd.io/docs/

**Related topics in this library:** `#32 Replication`, `#95 Network Partitions`, `#38 Distributed Locks`, `#85 Failover`, `#96 Clock Skew` (lease timing), `#8 Kubernetes`.
