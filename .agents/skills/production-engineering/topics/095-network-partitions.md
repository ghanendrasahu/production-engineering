---
topic: 95
title: Network Partitions
category: H
skill: production-engineering
status: stable
---

# 095 — Network Partitions

## 1. Topic name and metadata

- **Number:** 95 of 111
- **Title:** Network Partitions
- **Category:** H — Networking and Communication
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [distributed-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/095-network-partitions.md`

## 2. What it is

A failure mode in which nodes in a distributed system are alive but cannot communicate with each other (dropped packets, saturated links, routing failure, AZ isolation) — the defining failure of distributed systems.

## 3. Why it exists

Networks split; systems must choose what halts and what serves.

## 4. The engineering problem it solves

Treating the network as reliable produces split-brain, lost quorum, and half-written systems; partitions are guaranteed to happen eventually — your only choice is behavior during them.

## 5. How it works internally

Detection: heartbeats, TCP keepalive timeouts, Phi accrual failure detector (Cassandra) vs fixed thresholds (false positives), gossip. Behavior: CP systems halt (no quorum); AP systems serve and reconcile; leases must outlive the partition duration with fencing; majority quorum requires ⌊N/2⌋+1 votes; even-sized clusters split evenly (never use 2 nodes); multi-AZ latency ~1-2ms is the usual partition trigger; MTU/MTU mismatch, security groups, DNS TTL — many "partitions" are misconfig, not physics.

## 6. Architecture and design principles

Placement of voters, witnesses, quorum configs, FD detectors, control-plane vs data-plane separation (data plane keeps serving stale reads; control plane halts).

**Design principles for this category:** Choose transport by semantics (ordering, latency, loss tolerance); name everything through discovery, never literals.

## 7. When to use it

Architecting any system >1 node with shared state — always.

## 8. When NOT to use it

Single point by definition (laptop).

**Alternatives:** n/a — partitions are inevitable; only the response design is optional.

## 9. Implementation strategies

etcd cluster of 3 or 5 voters across AZs; `raft-heartbeat = 100ms`, election timeout 1s; Patroni: `ttl=30 loops_wait=5`; chaos mesh/toxiproxy to inject partition in test; monitor `node_network_*` and inter-node RTT.

## 10. Production-grade implementation

**Scenario:** 3-AZ Kubernetes control plane + etcd; an AZ network incident isolated one zone; etcd lost no quorum (2/3 alive), all services kept serving; failover plan executed — control plane reads/writes continued; the isolated AZ re-joined and caught up via log replication; zero data loss.

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

The network is the shared resource: ordering, loss, partitions, and clock skew are not pathologies — they are the medium. Design with them.

## 14. AI/ML/LLM application examples where relevant

Region split: EU tenants must not fail over to US for data-residency AI workloads — legal requirement, not availability preference.

## 15. Security considerations

Session continuity across partitions — tokens must not validate on both sides of split brain.

## 16. Performance considerations

Protocol choice is throughput choice: HTTP/2 multiplexing, gRPC streaming, QUIC vs TCP trade loss sensitivity against HOL blocking.

## 17. Common mistakes

2-node "HA" clusters; same-zone replicas; no fencing; fixed heartbeat failure detectors with tight thresholds (false positives cause flapping); assuming partitions are mythical; client retries hammering partitioned backends (make them fail fast).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `partition_events_total`, quorum status, unreachable peers

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Quarterly chaos drill: sever one AZ/DC; assert (a) CP halts writes but control plane stays consistent, or (b) AP keeps serving; fencing verified by rejecting stale tokens; quorum-loss test (kill 2 of 3) → system correctly refuses; MTU blackhole test on staging.

## 21. Deployment considerations

Protocol/version changes are deploys too: enable H2/H3 at the edge first, verify clients, then simplify origins; DNS/cert changes rehearsed with low TTL.

## 22. Production-readiness checklist

- [ ] Odd voters (3/5) across AZs
- [ ] Fencing tokens everywhere mutable state is protected
- [ ] Majority quorum for anything strong
- [ ] Timeouts tuned above RTT, below detection SLO
- [ ] Runbook for partition response
- [ ] Chaos-test partitions quarterly
- [ ] Design for partition: what keeps working, what halts — and document it.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Split-brain dual-write after failed fencing (worst case — silent corruption); 2-node cluster partitions 50/50 → no writes anywhere; asymmetric partition (A→B works, B→A dropped) fooling heartbeats; flaky MTU blackholing large packets — consensus traffic stalls but pings pass; DNS pointing to dead AZ after partition; client-side caches masking the partition until TTL expiry.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://raft.github.io/
- https://jepsen.io/

**Related topics in this library:** `#33 Leader Election`, `#34 CAP Theorem`, `#32 Replication`, `#38 Distributed Locks`, `#96 Clock Skew`, `#85 Failover`, `#86 Multi-Region Deployment`.
