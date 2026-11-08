---
topic: 85
title: Failover
category: F
skill: production-engineering
status: stable
---

# 085 — Failover

## 1. Topic name and metadata

- **Number:** 85 of 111
- **Title:** Failover
- **Category:** F — Disaster Recovery and Reliability
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [reliability-recovery.md](../references/reliability.md)
- **Topic file:** `.agents/skills/production-engineering/topics/085-failover.md`

## 2. What it is

The automatic or manual reassignment of traffic from a failed component (node, DB, AZ, region) to a healthy standby, minimizing error rate and duration.

## 3. Why it exists

Components fail; traffic must move to healthy ones automatically.

## 4. The engineering problem it solves

Without failover, a single node failure = hard outage; with slow manual failover, a 30-second incident becomes a 30-minute one.

## 5. How it works internally

Detection (heartbeat/probe with ~seconds budget), decision (majority vote/consensus/DCS to avoid split brain), action (promote replica, swap LB targets, update DNS/accelerator), fencing (reject old leader — STONITH), draining (in-flight requests). Active-passive vs active-active. HA solutions: Patroni+etcd (Postgres), K8s leader election for singletons, Route 53 health-checked failover routing, Redis Sentinel. RPO/RTO trade: synchronous replication gives RPO=0; async gives small loss but less latency.

## 6. Architecture and design principles

Health probes → DCS (etcd/Consul) → orchestration → LB/DNS/DB promotion.

**Design principles for this category:** Assume failure; test recovery, not just uptime; the cheapest reliability is the one rehearsed before it is needed.

## 7. When to use it

Any single point of unavailability is unacceptable.

## 8. When NOT to use it

Acceptable RTO of hours (backup/restore suffices — `#84`).

**Alternatives:** n/a — failover is the mechanism; breadth depends on RPO/RTO tier.

## 9. Implementation strategies

```
Patroni: etcd DCS, ttl=30, loop_wait=10, maximum_lag_on_failover=5MB
Route 53: failover routing policy, PRIMARY/SECONDARY + health checks (fast, 10s)
K8s: migrating Deployment to healthy zone = pod reschedule + probes
```

## 10. Production-grade implementation

**Scenario:** Primary DB AZ-1 disk failure at 14:03; Patroni detected in 2s, DCS promoted AZ-2 replica (lag 0.4s); fence issued to old primary's IPMI; app reconnected within 8s; 3 write errors during cutover retried transparently; zero data loss; RTO 8 seconds.

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

Provider failover: automatic fallback chain with breaker — seconds to degrade, zero user-visible 5xx if cache warm.

## 15. Security considerations

Standby must be patched and monitored identically — failover is not an upgrade.

## 16. Performance considerations

Failover/DR add replication RTT (sync) or a lag window (async) — choose per data class, not globally.

## 17. Common mistakes

Manual-only failover; no fencing; auto-promote replicas regardless of lag; identical AZs for "different" datacenters; health checks that pass while degraded; app assumes provider DNS instantly converges.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `failover_duration_seconds`, promotions, replication lag at promotion

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Monthly automated failover drill measuring RTO; fencing verification (old leader write rejected); DNS TTL test; client reconnect storm test; chaos AZ kill.

## 21. Deployment considerations

DR/failover changes must be rehearsed: quarterly game days with measured RTO/RPO; record results; update the runbook after every rehearsal.

## 22. Production-readiness checklist

- [ ] Fence the old primary (never trust "it's probably dead")
- [ ] Lag threshold for promotion
- [ ] Health checks ≠ deep app checks (cheap)
- [ ] Hysteresis against flapping
- [ ] Test failover monthly (gameday)
- [ ] Application reconnect logic with backoff
- [ ] Document manual trigger
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Split brain (both primary and new-primary accept writes — must fence); failover of a lagging replica → seconds of data loss (max_lag threshold); flapping (failure detector too sensitive — hysteresis needed); failover of the control plane (consensus dead in both AZs); clients caching old IP past TTL (use LB/accelerator, short TTL); "automatic" but runbook actually says "wait for human"; failover test that freezes the witness.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.postgresql.org/docs/current/warm-standby.html
- https://aws.amazon.com/rds/features/multi-az/

**Related topics in this library:** `#33 Leader Election`, `#32 Replication`, `#83 Disaster Recovery`, `#86 Multi-Region Deployment`, `#56 Health Checks`, `#95 Network Partitions`.
