---
topic: 44
title: Backpressure
category: B
skill: production-engineering
status: stable
---

# 044 — Backpressure

## 1. Topic name and metadata

- **Number:** 44 of 111
- **Title:** Backpressure
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [distributed-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/044-backpressure.md`

## 2. What it is

Flow control that propagates demand signals upstream so producers stop overwhelming consumers — the opposite of unbounded queueing that hides overload until collapse.

## 3. Why it exists

Nothing in production should buffer without bound.

## 4. The engineering problem it solves

Unbounded queues are invisible until they aren't: latency grows to minutes, memory blows up, timeouts fire everywhere, and the overloaded consumer dies anyway — with the backlog unprocessed.

## 5. How it works internally

Pull-based demand (Reactive Streams: `request(n)`; gRPC flow control windows; HTTP/2 `WINDOW_UPDATE`), bounded queues (block/fail/drop oldest when full), token buckets for rate shaping, semaphores capping concurrency (`asyncio.Semaphore(50)`), credit-based consumers (Kafka pull-based prefetch ≈ backpressure built-in), Little's Law: concurrency = throughput × latency — cap concurrency to protect the slowest stage. LLM inference: admit limited concurrent sequences; extra tokens/requests wait rather than degrade all.

## 6. Architecture and design principles

Between every producer/consumer boundary: HTTP handler → broker → worker → DB. Each hop needs a bounded buffer and a rejection/shedding policy.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Every stage boundary with a slower consumer.

## 8. When NOT to use it

Uniformly low load (limits never bind).

**Alternatives:** load shedding via `#1 Rate Limiting`, priorities/QoS, queue-per-tenant fairness, scale-up (`#46 Horizontal Scaling` + `#45 Autoscaling`).

## 9. Implementation strategies

```python
import asyncio
sem = asyncio.Semaphore(20)               # at most 20 in-flight LLM calls
async def infer(prompt):
    async with sem:
        return await llm.complete(prompt)   # request 21 waits, never overload provider
```

Bounded queue: `queue.Queue(maxsize=500)`; policy on full: block with timeout → 503, or drop with metric. K8s: KEDA scale-to-queue-depth (queue → add pods), not CPU-based scaling.

## 10. Production-grade implementation

**Scenario:** RAG ingestion: 10k docs/min burst; bounded 200-doc queue in Celery (backpressure to API → 503 with Retry-After); KEDA scales workers 3→40; DB write stage throttled by semaphore (pool limit 20); pipeline absorbs burst without data loss — excess is rejected cleanly at the edge, not corrupted in the middle.

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

Middleware capping concurrent requests to the expensive endpoint (return 429/503 when saturated): FastAPI + `anyio` semaphore or a reverse proxy (limit_req). Streaming endpoints: apply backpressure per-chunk, don't materialize whole responses.

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Admission control on inference: semaphore on in-flight requests; excess 429 — the GPU queue is not a queue.

## 15. Security considerations

Shed uniformly regardless of caller identity — no VIP bypass of backpressure.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

Unlimited `asyncio.create_task` fanout; unbounded `create_task` per request; relying on broker's disk to absorb infinite lag; retrying on shed responses; healthcheck that ignores saturation; unlimited concurrency against third-party APIs.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `queue_depth`, `rejected_requests_total`, `semaphore_wait_seconds`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Load test 2x capacity and assert 503s, not 30s latencies; verify queue never exceeds bound; KEDA scale-up/scale-down drill; cancellation test (client disconnect frees slot); downstream-slow chaos test.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] Bound everything (queues, concurrency, request bodies, streams)
- [ ] Shed with 503 + Retry-After at saturation
- [ ] Metric queue depth and wait time
- [ ] Scale consumers on lag not CPU
- [ ] Priority lanes for user vs batch
- [ ] Document the shed policy
- [ ] Alert on sustained saturation (not transient spikes).
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** N+1 retries after shedding re-floods the system; full healthcheck passing while semaphore is saturated; producer ignores 503 and retries immediately; unbounded in-memory buffer "temporarily"; measuring throughput but not queue depth — no visibility until collapse; mixed priority traffic (low-priority batch starves user requests).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://reactivex.io/rxjs/guide/backpressure.html
- https://www.oreilly.com/library/view/release-it/0321601915/

**Related topics in this library:** `#15 Message Queues`, `#1 Rate Limiting`, `#45 Autoscaling`, `#90 Serverless Limits`, `#11 Timeouts`, `#93 P99 Latency`.
