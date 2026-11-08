---
topic: 91
title: Latency
category: G
skill: production-engineering
status: stable
---

# 091 — Latency

## 1. Topic name and metadata

- **Number:** 91 of 111
- **Title:** Latency
- **Category:** G — Performance Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [performance-engineering.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/091-latency.md`

## 2. What it is

The elapsed time from request arrival to response delivery (often split: DNS, connect, TLS, TTFB/wait, body transfer); measured as a distribution, never an average.

## 3. Why it exists

Users feel elapsed time, not throughput averages.

## 4. The engineering problem it solves

"Average latency 120ms" hides that 5% of requests take 3s — and those are exactly the ones making your product feel broken and blowing SLOs.

## 5. How it works internally

Cost sources: network RTT, queueing (the dominant factor at high utilization — Little's Law: L = λW; as utilization →100%, queue time →∞), GC/runtime, DB (connection pool wait, lock wait, disk), downstream serialization, TLS handshake. Amdahl's Law limits parallel speedup; Universal Scalability Law shows contention (serialization) and coherency (cross-node chatter) dominate at scale. Measure at the edge (client-side) AND server-side — they differ; server sees only handler time. Percentiles from histograms (`histogram_quantile`); never averages; always segment by route — one slow route skews nothing if tracked separately.

## 6. Architecture and design principles

Budget decomposition along the call chain (each hop a line item with an owner); CDN/edge trims network latency; caches trim compute; pooling trims connection cost.

**Design principles for this category:** Measure distributions, not averages; optimize the top offender; quantify every trade-off in latency, memory, and cost.

## 7. When to use it

Always — measure everything, budget everything.

## 8. When NOT to use it

N/a; but prioritize optimization only after profiling.

**Alternatives:** latency SLOs + budgets (process, not alternative), throughput-vs-latency trade knobs (concurrency, queues).

## 9. Implementation strategies

```python
@app.middleware("http")
async def timing(request, call_next):
    t = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time"] = f"{(time.perf_counter()-t)*1000:.1f}ms"
    return response
```

```promql
h = histogram_quantile(0.95, sum by (le, route) (rate(http_request_seconds_bucket[5m])))
```

## 10. Production-grade implementation

**Scenario:** p95 700ms on `/orders`: breakdown showed 300ms payload encryption at gateway + 200ms DB + 100ms handler; moved serialization off hot path (orjson) and added covering index → 180ms p95; dashboard per hop made the fix obvious in one hour.

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

Stream tokens — perceived latency is TTFT, not total generation; optimize and SLO it.

## 15. Security considerations

Measure auth latency explicitly — fast paths that hide slow auth are insecure paths.

## 16. Performance considerations

The entire point: measure distributions, find the top offender, fix, re-measure — every claim here is a benchmark waiting to happen.

## 17. Common mistakes

Average as success metric; optimizing before profiling; micro-optimizing JSON parsing of a 10ms endpoint while DB takes 2s; no client-side measurement; tools tuned to 95th percentile only (P99 and P999 still hurt).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** p50/p95/p99 per route, breakdown by hop

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

k6/Locust at production-like RPS asserting p95/p99 thresholds; before/after benchmark on the targeted endpoint; load at 2x peak for headroom; CI performance regression gate; real-user monitoring (RUM) verification.

## 21. Deployment considerations

Performance changes ship behind A/B: measure p50/p95/p99 and cost before/after on real traffic; hedge, don't gamble.

## 22. Production-readiness checklist

- [ ] Measure percentiles, per route
- [ ] Decompose along the path (edge → app → DB)
- [ ] Budgets per hop with owners
- [ ] Keepalive end-to-end
- [ ] Balance payload size
- [ ] Optimize the top offender only (profile first)
- [ ] Test at production-like load
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Optimizing averages (user pain hidden); optimizing the wrong hop (cache the cache, not the DB); measurement at server only (client sees 2x more via network); TLS re-handshake per request (no keepalive); connection pool wait invisible (use pool wait metric); latency regression after a " harmless" dependency bump; no per-route breakdown — global p95 masks one bad endpoint; testing at low load then deploying to 10x.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://grafana.com/docs/
- https://en.wikipedia.org/wiki/Little%27s_law

**Related topics in this library:** `#92 Throughput`, `#93 P99 Latency`, `#94 Tail Latency`, `#2 Caching`, `#11 Timeouts`, `#28 Connection Pooling`.
