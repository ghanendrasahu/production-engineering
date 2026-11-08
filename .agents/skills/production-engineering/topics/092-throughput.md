---
topic: 92
title: Throughput
category: G
skill: production-engineering
status: stable
---

# 092 — Throughput

## 1. Topic name and metadata

- **Number:** 92 of 111
- **Title:** Throughput
- **Category:** G — Performance Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [performance-engineering.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/092-throughput.md`

## 2. What it is

The rate of completed work per unit time — requests per second, messages per second, rows per second; the system's capacity envelope, bounded by the slowest stage and available resource.

## 3. Why it exists

Capacity must be known, not discovered at peak.

## 4. The engineering problem it solves

Underprovisioned capacity = queue growth and latency collapse at peak; overprovisioned = pure waste; ignorance of the bottleneck stage = scaling the wrong thing (buying app CPU when the DB is the ceiling).

## 5. How it works internally

Little's Law (L = λW) relates in-flight work, arrival rate, latency; saturation at any stage throttles everything (constraint theory). Bottlenecks: CPU (serialization, crypto), DB (connection pool, locks, IO), network (bandwidth, TLS termination), downstream quotas. Capacity planning: measure saturation → add the constrained resource; Amdahl: parallelism ceiling; load testing validates the model; autoscale on saturation metric (queue depth/CPU/connections), not guessed traffic. Throughput vs latency: increasing batch size raises throughput at cost of latency (Little's Law again) — batch only where latency budget allows.

## 6. Architecture and design principles

LB → N app instances → DB/queue; autoscaler keyed to the true constraint; DB as shared capacity ceiling.

**Design principles for this category:** Measure distributions, not averages; optimize the top offender; quantify every trade-off in latency, memory, and cost.

## 7. When to use it

Capacity planning phase for any public service.

## 8. When NOT to use it

Pre-product-market-fit toy (but measure from day one anyway).

**Alternatives:** queue-based load leveling (absorb peaks without sizing for them), backoff/degradation policies.

## 9. Implementation strategies

```bash
k6 run --vus 200 --duration 60s loadtest.js    # measure RPS at acceptable p99
```

```promql
rate(http_requests_total[1m])                       # current throughput
```

Capacity test at 2-3x expected peak; watch queue depth, pool wait, CPU steal.

## 10. Production-grade implementation

**Scenario:** API "slow under load" — throughput plateaued at 900 RPS with CPU 40%; profiled: PgBouncer pool 20 saturated at 900 RPS (lock waits); pool →100, queries optimized → 2,400 RPS at same p99; CPU never was the bottleneck.

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

Tail latency is a distributed phenomenon: one slow shard/hop dominates fanout latency — measure the parent and the children separately.

## 14. AI/ML/LLM application examples where relevant

GPU throughput is tokens/s; batch 8-64 via continuous batching (vLLM) — measure, don't assume.

## 15. Security considerations

Auth-aware quotas stop brute force at scale — per-tenant tokens.

## 16. Performance considerations

The entire point: measure distributions, find the top offender, fix, re-measure — every claim here is a benchmark waiting to happen.

## 17. Common mistakes

"Just add replicas" without finding the bottleneck; ignoring provider quotas (NAT/VPC/Redis connections); one big server when sharding needed; over-provisioning steady state instead of autoscaling bursts; p99 violated while quoting RPS.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `http_requests_total` rate, rows/s, msgs/s per stage

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Staged load ramp to failure; capacity test before launches; regression benchmarks per release; production-like data volumes; quota verification tests (DB max_connections vs N pods × pool).

## 21. Deployment considerations

Performance changes ship behind A/B: measure p50/p95/p99 and cost before/after on real traffic; hedge, don't gamble.

## 22. Production-readiness checklist

- [ ] Profile before scaling
- [ ] Identify the shared constraint
- [ ] Load test at 2x
- [ ] Metrics on queue/pool/lock waits
- [ ] Keepalive
- [ ] Capacity review quarterly
- [ ] Headroom 30-50% on the constraint
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Adding app servers when DB is saturated (more clients → more lock contention → worse); SYN backlog overflow (tune net.core.somaxconn + LB); ephemeral port exhaustion at high RPS (`TIME_WAIT` — keepalive end-to-end); throughput test at warm cache only (production cold day = 2x latency); autoscale on CPU but DB pinned (scale-out hammering a ceiling); hidden synchronous work (logging/audit flush) capping RPS.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://grafana.com/docs/

**Related topics in this library:** `#91 Latency`, `#93 P99 Latency`, `#45 Autoscaling`, `#46 Horizontal Scaling`, `#44 Backpressure`, `#28 Connection Pooling`.
