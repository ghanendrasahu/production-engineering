---
topic: 90
title: Serverless Limits
category: G
skill: production-engineering
status: stable
---

# 090 — Serverless Limits

## 1. Topic name and metadata

- **Number:** 90 of 111
- **Title:** Serverless Limits
- **Category:** G — Performance Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [performance-engineering.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/090-serverless-limits.md`

## 2. What it is

Hard platform ceilings for FaaS/serverless workloads: execution timeout (Lambda 15min), memory (Lambda 10GB), payload (6MB sync / 256KB async invocation), concurrency (1000/region default, soft), ephemeral storage (10GB /tmp), cold-start behavior, and per-request pricing.

## 3. Why it exists

Serverless platforms enforce ceilings you must design around.

## 4. The engineering problem it solves

Designing unbounded workloads onto bounded primitives — a video transcoder that hits 15min or a WebSocket app needing millions of concurrent connections — fails in production, not in the tutorial.

## 5. How it works internally

Lambda: 15min max, 10GB RAM (CPU scales with memory — 1 vCPU per 1.5-2GB), 6MB request/256KB response payloads, 10GB /tmp, ~1000 concurrent (soft limit, raisable). Cloud Run: 60min request timeout (HTTP streaming to 60min now), 4 vCPU/8GB, concurrency 250/instance default, cold starts; Azure Functions similar; KV/edge: 25MB response, 50ms CPU on some platforms. Pricing: per-GB-second + per-request — high sustained throughput costs MORE than containers; breakeven around 20-40% sustained utilization.

## 6. Architecture and design principles

Choose primitive by duration/statefulness: HTTP APIs (short, stateless) → Lambda/Cloud Run; streams/websockets → containers; GPU inference → dedicated instances.

**Design principles for this category:** Measure distributions, not averages; optimize the top offender; quantify every trade-off in latency, memory, and cost.

## 7. When to use it

Spiky, stateless, short-duration workloads; scale-to-zero savings real.

## 8. When NOT to use it

Sustained 24/7 throughput (containers win); >15min jobs; heavy GPU; stateful/websockets (containers).

**Alternatives:** K8s/ECS containers, Cloud Run, batch (Fargate/Spot), Kubernetes jobs.

## 9. Implementation strategies

```yaml
# serverless.yml / SAM (concept)
functions:
  process:
    timeout: 900            # seconds — hard cap
    memorySize: 3008        # ~2 vCPU
    reservedConcurrency: 100
```

```python
# chunk long work to fit limits: Step Functions / SQS fan-out
for batch in chunks(docs, 100):
    sqs.send_message(QueueUrl=Q, MessageBody=json.dumps(batch))  # many small functions
```

## 10. Production-grade implementation

**Scenario:** PDF pipeline: 8-minute renders on Lambda 15min cap — 3% of files timed out exactly at the cap; moved to SQS + container workers on K8s (no limit) and split Lambda API (fast) from workers (long) — timeouts gone, cost down 35%.

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

Know the provider's TPM/RPM and regional quotas before launch — 429 walls are the #1 AI launch failure.

## 15. Security considerations

Hard timeouts must not strand authorized in-flight operations without audit.

## 16. Performance considerations

The entire point: measure distributions, find the top offender, fix, re-measure — every claim here is a benchmark waiting to happen.

## 17. Common mistakes

15-minute batch jobs on Lambda; 128MB for compute-heavy work; holding DB connections per invocation (pool per warm instance only); ignoring /tmp reuse; serverless for steady high-throughput sustained services (containers cheaper).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `invocation_timeouts_total`, throttle 429s, concurrent-invocations vs quota

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Timeout-bound test (largest payload completes < cap); load to reserved concurrency; cost model audit; /tmp leak test across invocations on same instance; concurrency exhaustion drill.

## 21. Deployment considerations

Performance changes ship behind A/B: measure p50/p95/p99 and cost before/after on real traffic; hedge, don't gamble.

## 22. Production-readiness checklist

- [ ] Right primitive for job length
- [ ] Reserved/provisioned concurrency for critical paths
- [ ] Fan-out chunking for big jobs
- [ ] Keep handlers stateless
- [ ] /tmp cleaned (or use unique filenames)
- [ ] Pricing model review quarterly vs utilization
- [ ] Streaming via response streaming for LLM
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Timeout at exactly 15:00 killing the largest jobs; memory-CPU coupling surprise (128MB Lambda = also tiny CPU); payload limit on LLM contexts (6MB); concurrency cap under flash crowd → 429s from Lambda itself; per-request pricing at 50M req/month = more than a reserved VM; /tmp leftover files from prior invocation (pooled warm container reuses disk!) — sensitive data leaks between invocations on shared instance; sync invocation of heavy LLM call exceeding gateway 29s timeouts.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.aws.amazon.com/lambda/
- https://cloud.google.com/run/docs/container-contract

**Related topics in this library:** `#89 Cold Starts`, `#92 Throughput`, `#88 Cost Optimization`, `#11 Timeouts`, `#46 Horizontal Scaling`.
