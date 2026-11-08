---
topic: 12
title: Retries
category: A
skill: production-engineering
status: stable
---

# 012 — Retries

## 1. Topic name and metadata

- **Number:** 12 of 111
- **Title:** Retries
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/012-retries.md`

## 2. What it is

Re-executing a failed operation, bounded in attempts and budget, typically only for transient, retryable failures.

## 3. Why it exists

Transient faults are normal; users should never see them.

## 4. The engineering problem it solves

Transient blips (network hiccup, leader election, deploy drain, 503 from an overloaded node) are common; without retries a 1-in-1000 failure becomes a user-visible error 1000x more often than it should.

## 5. How it works internally

Retry classifier decides retryable (network reset, timeout, 429, 5xx, 503) vs non-retryable (4xx validation, 409 conflict). Delay policy: fixed, exponential with full jitter, or decorrelated jitter. Budget: max attempts (2-3), overall deadline, and a retry budget at scale (e.g., ≤20% of requests may be retries) to prevent retry storms. Combine with idempotency keys for safe repeat of side-effecting calls. Server hints: honor `Retry-After`.

## 6. Architecture and design principles

Client-side wrapper around HTTP/gRPC/DB/queue clients, or in the queue itself (broker redelivers on nack). Mesh can inject retries (Istio VirtualService `retries: { attempts: 3, perTryTimeout: 2s }`) — pick one layer to own retries, not both.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Transient faults dominate and the operation is safe (read or idempotent-write).

## 8. When NOT to use it

Deterministic failures (validation, auth), non-idempotent side effects without keys, saturated dependencies (retry makes it worse).

**Alternatives:** DLQ + reprocess, `#10 Circuit Breakers`, fail-fast with user retry, queue-based buffering (`#15 Message Queues`).

## 9. Implementation strategies

httpx transport retries via `httpx-retries`; tenacity for arbitrary callables; `@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.5, max=8), retry=retry_if_exception(is_retryable))`. Celery: `autoretry_for=(ConnectionError,), retry_backoff=True, retry_jitter=True, max_retries=5`.

```python
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.5, max=10, jitter=2),
       retry=retry_if_exception_type((TimeoutError, ConnectionError)), reraise=True)
def fetch_profile(uid: int): ...
```

## 10. Production-grade implementation

**Scenario:** Order webhook to a flaky partner endpoint (0.5% failure rate). Tenacity: 3 attempts, exponential + jitter, honor `Retry-After`; failures after 3 attempts go to a DLQ table with `order_id`; reconciler job re-drives every 5 min; partner-facing duplicate rate controlled by idempotency-key header.

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

```python
from fastapi import BackgroundTasks
@app.post("/notify")
async def notify(msg: Notification, background: BackgroundTasks):
    background.add_task(deliver_with_retry, msg)  # retry with cap + DLQ on exhaustion
    return {"status": "queued"}
```

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

429/5xx from providers: exponential backoff + full jitter; NEVER retry 400 (schema/prompt rejection); honor Retry-After; idempotency keys dedupe billed calls.

## 15. Security considerations

Retry storms amplify brute force — cap attempts; alert on retry-rate anomalies.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Unbounded retries; immediate fixed-interval retry; retrying 4xx; retries on non-idempotent writes; nested retries across layers; ignoring `Retry-After`; retry as the fix for missing capacity; hiding failure rates from telemetry.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `retries_total{outcome}`, `retry_exhaustion_total`, amplification ratio

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest with a fake failing N times then succeeding; assert attempts count and backoff sleep called with jitter bounds (mock `time.sleep`); integration test: toxiproxy-cut connection mid-request; verify DLQ after max attempts; load test retry amplification against a failing dependency.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Retry only transient/5xx/timeout/connection errors
- [ ] Cap attempts (2-3) and total time
- [ ] Exponential backoff with full jitter
- [ ] Honor `Retry-After`
- [ ] Idempotent side effects or idempotency keys
- [ ] One layer owns retry policy
- [ ] Metric per outcome (`retry_attempt{outcome=exhausted}`)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Retry storm — 30s dependency blip, all 500 global users ×3 retries = 1500x amplification; retrying a non-idempotent charge endpoint → double billing (must have `#14 Idempotency`); retrying a 400 (validation) wastes budget forever; nested retries in gateway and service → multiplicative amplification; retrying beyond caller's timeout → work completes after caller already errored.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://learn.microsoft.com/azure/architecture/patterns/retry

**Related topics in this library:** `#13 Exponential Backoff`, `#14 Idempotency`, `#20 Dead Letter Queues`, `#10 Circuit Breakers`, `#11 Timeouts`, `#12 Retries` ⇄ latency of `#93 P99 Latency`.
