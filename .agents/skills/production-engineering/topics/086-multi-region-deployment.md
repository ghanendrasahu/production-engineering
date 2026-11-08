---
topic: 86
title: Multi-Region Deployment
category: F
skill: production-engineering
status: stable
---

# 086 — Multi-Region Deployment

## 1. Topic name and metadata

- **Number:** 86 of 111
- **Title:** Multi-Region Deployment
- **Category:** F — Disaster Recovery and Reliability
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [reliability-recovery.md](../references/reliability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/086-multi-region-deployment.md`

## 2. What it is

Running the system in two or more geographic regions concurrently — active-active (both serve) or active-passive (standby serves failover) — for survive-region loss, latency, or data residency.

## 3. Why it exists

One region is one blast radius.

## 4. The engineering problem it solves

A single region is a single blast radius: region-wide cloud outages (they happen regularly) can take your service, and only multi-region survives them.

## 5. How it works internally

Data replication across regions: sync (only same-metro, e.g., us-east-1a→1b) or async (us-east-1→eu-west-1, RPO seconds-minutes). Global ingress: anycast/global accelerator/Route 53 latency routing steers users to nearest healthy region. Active-active data needs conflict handling (CRDTs, LWW, or shard-write-own-region with follow-the-sun) or accept divergent reads briefly. Stateless app layer replicates trivially; the database is the hard part (DynamoDB global tables, Spanner multi-region, CockroachDB, Aurora Global, logical replication).

## 6. Architecture and design principles

Two regions; each with LB+app+DB; replication link(s); global DNS/accelerator health-based routing; IaC for both; replication lag alerting; conflict-resolution policy documented.

**Design principles for this category:** Assume failure; test recovery, not just uptime; the cheapest reliability is the one rehearsed before it is needed.

## 7. When to use it

Regulatory data residency, SLO unattainable in one region, active legal/executive commitment to region-loss survival.

## 8. When NOT to use it

Single-region RPO/RTO acceptable (most products — cost not justified).

**Alternatives:** warm standby (pilot light), cross-AZ HA (covers 90% of failures), managed global services (DynamoDB Global Tables/Aurora Global).

## 9. Implementation strategies

```
Route 53 latency routing + health checks → region endpoints
DynamoDB global tables (multi-active, last-writer-wins) or
Aurora Global Database (async <1s lag, region promotion ~1min)
S3 CRR replication; SQS per region + cross-region fanout
```

## 10. Production-grade implementation

**Scenario:** Chat/SaaS: active-active us-east-1 + eu-west-1 (users pinned by latency to nearest; writes to primary-of-user region; reads local; PII residency for EU pinned to eu); eu region loss → accelerator routes all traffic to us, 40s degraded reads, zero data loss; us-east outage in 2026 handled transparently for 63% of traffic.

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

DR is inherently distributed: replication links, region failover, and cross-region consistency decide whether your 'HA' survives the disaster or just survives the drill.

## 14. AI/ML/LLM application examples where relevant

Region-pinned inference for data residency (EU tenants → EU region) — route by tenant, verify isolation.

## 15. Security considerations

Identical IAM/secrets/policies in both regions — divergence is a bypass.

## 16. Performance considerations

Failover/DR add replication RTT (sync) or a lag window (async) — choose per data class, not globally.

## 17. Common mistakes

"Multi-region" DNS-only without data replication (advertised DR, actual total loss); two writers on strongly-consistent data without conflict resolution; same cloud region pair behind one control plane domain; replication without monitoring; 100% active-active when active-passive would do (2x cost for 1% gain); forgetting artifacts (image registry, helm charts) replication.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `cross_region_replication_lag`, conflict count, region error budget

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Kill-region game day; replication-lag alarm test; conflict injection test (same key written both regions → resolution correct); RTO/RPO measurement; cross-region restore verification; residency compliance audit.

## 21. Deployment considerations

DR/failover changes must be rehearsed: quarterly game days with measured RTO/RPO; record results; update the runbook after every rehearsal.

## 22. Production-readiness checklist

- [ ] Pin data residency where legal
- [ ] Global accelerator not DNS TTL for cutover
- [ ] One designated writer per entity (or CRDT)
- [ ] Lag SLOs with alerts
- [ ] IaC ×2
- [ ] Identical observability stack per region with a unified dashboard
- [ ] Quarterly failover drill cross-region
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Async replication lag spike → users switching regions see older data; dual-active write conflict (same cart in both regions) → corrupt cart unless LWW/CRDT; failover during partition: both regions think the other is dead → divergent writes (must define one writer or use conflict-free types); inter-region latency (~35-120ms) eating p99; costs double+; config drift between "identical" regions (they never are — inventory both with tooling); observability split per region; replication of secrets/certs/images forgotten.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-workloads-on-aws.pdf

**Related topics in this library:** `#83 Disaster Recovery`, `#85 Failover`, `#34 CAP Theorem`, `#32 Replication`, `#48 CDN`, `#33 Leader Election`.
