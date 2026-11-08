---
topic: 93
title: P99 Latency
category: G
skill: production-engineering
status: stable
---

# 093 — P99 Latency

## 1. Topic name and metadata

- **Number:** 93 of 111
- **Title:** P99 Latency
- **Category:** G — Performance Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [performance-engineering.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/093-p99-latency.md`

## 2. What it is

The 99th-percentile response time — 1 in 100 requests is slower than this; the SLO-relevant figure for tail experience.

## 3. Why it exists

The slowest 1% defines the experience at scale.

## 4. The engineering problem it solves

Averages and even P95s hide the requests that get your service called "slow" — at scale, 1% of 10M requests = 100k bad experiences daily.

## 5. How it works internally

Percentiles need full distribution info — histograms in metrics (Prom histogram_quantile), HDR histograms (succinct data structure storing percentiles exactly at low cost), or reservoir sampling. Causes of tail: GC pauses, lock/queue waits, cold cache, slow queries (plan flips), noisy neighbors (shared VMs), network retransmits, retry amplification, stragglers in scatter-gather (fanout to 100 shards → P99 determined by slowest shard). Fixes: hedging/cancellation, backup requests, cache warming, pool headroom, isolation of slow tenants, removal of lock convoys.

## 6. Architecture and design principles

Measured at every tier of the call graph; SLOs defined on it; dashboards split by route/tenant; exemplars link slow traces directly.

**Design principles for this category:** Measure distributions, not averages; optimize the top offender; quantify every trade-off in latency, memory, and cost.

## 7. When to use it

Any user-facing production service with SLOs — always.

## 8. When NOT to use it

N/a.

**Alternatives:** HDR histogram-based percentiles for exactness; tail-sampling traces keyed on the slow ones.

## 9. Implementation strategies

```promql
histogram_quantile(0.99, sum by (le, route) (rate(http_request_seconds_bucket[5m])))
histogram_quantile(0.99, sum by (le, route) (rate(http_engine_request_seconds_bucket{engine="llm"}[5m])))
```

Histogram buckets set deliberately around the SLO (e.g., include 0.3s, 0.5s, 1s boundaries).

## 10. Production-grade implementation

**Scenario:** Search API p95 120ms but p99 4s; traces showed 2% of queries hit a stale plan → seq scan on 40M rows; planner hints + index fixed; p99 150ms; ALSO found GC pause tail in the worker — moved to ZGC; variance gone.

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

TTFT p99 across tenants — long contexts (32k+) dominate tail; cap context or queue separately.

## 15. Security considerations

Attacker-forced slow auth leaks into P99 — watch auth p99 specifically.

## 16. Performance considerations

The entire point: measure distributions, find the top offender, fix, re-measure — every claim here is a benchmark waiting to happen.

## 17. Common mistakes

Average-as-SLO; tail ignored because "it only affects 1%"; retries increasing tail; no bucket near SLO boundary; global p99 across heterogeneous routes.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `histogram_quantile(0.99, latency_bucket)`, SLO-boundary bucket counts

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Load test reporting p95/p99/p999 per route; hedged-request integration test (cancel losing request); chaos: GC injection, dependency latency +50% → assert p99 still under SLO; per-tenant hot-key test.

## 21. Deployment considerations

Performance changes ship behind A/B: measure p50/p95/p99 and cost before/after on real traffic; hedge, don't gamble.

## 22. Production-readiness checklist

- [ ] SLOs on p99 (and p999 for fanout-heavy)
- [ ] Custom histogram buckets incl. SLO boundary
- [ ] Per-route + per-tenant split
- [ ] Trace exemplars on the p99 bucket
- [ ] Budget headroom ≥30%
- [ ] Fanout cancellation (hedged requests after p95 threshold)
- [ ] Tail-focused chaos tests.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** SLOs on p50 (meaningless for tail); SLO set from a bad histogram boundary configuration (P99 invisible — bucket ends at 500ms, everything above is an overflow bucket); alert at mean only; p99 spike isolated to one tenant (noisy neighbor — needs per-tenant dashboard); ignoring P999 (Fanout/tail for 100+ parallel shards); fixing tail with more retries (amplifies!).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://grafana.com/docs/
- https://sre.google/sre-book/service-level-objectives/

**Related topics in this library:** `#91 Latency`, `#94 Tail Latency`, `#66 Observability`, `#92 Throughput`, `#2 Caching`, `#42 Garbage Collection`.
