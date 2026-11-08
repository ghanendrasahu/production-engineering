---
topic: 10
title: Circuit Breakers
category: A
skill: production-engineering
status: stable
---

# 010 — Circuit Breakers

## 1. Topic name and metadata

- **Number:** 10 of 111
- **Title:** Circuit Breakers
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/010-circuit-breakers.md`

## 2. What it is

A client-side pattern that tracks failures to a dependency and, after a threshold, short-circuits calls (fails fast without sending them) for a cooldown period, then half-opens to probe recovery.

## 3. Why it exists

Without one, a sick dependency takes every caller down with it.

## 4. The engineering problem it solves

When a dependency is sick, callers otherwise pile up: threads/connections blocked on timeouts, retries amplifying load, and the failure cascading into every upstream until the whole system is down.

## 5. How it works internally

Three states — CLOSED (normal, count failures), OPEN (fail fast immediately for a cooldown, no network call), HALF-OPEN (allow one/few trial calls; success → CLOSED, failure → OPEN again). Counter thresholds (e.g., 50% of 20 requests in 10s, or N consecutive failures), plus optional sliding-window metrics. Implementations: pybreaker, resilience4j (JVM), Envoy outlier detection, K8s → Istio `outlierDetection` or `DestinationRule`.

## 6. Architecture and design principles

Client library wraps the dependency client (database, HTTP, gRPC, Redis, LLM provider) between business logic and the network stack. Sits alongside timeouts and retry logic — retries without a breaker are an amplifier.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Any remote dependency that can be slow/down (third-party API, shared DB under contention), high-QPS services.

## 8. When NOT to use it

Purely local calls; one-shot batch scripts; idempotent reads where simple retry suffices and timeout is tiny.

**Alternatives:** load-shed via `#44 Backpressure`, mesh-level outlier detection, bulkheads (separate pools per dependency).

## 9. Implementation strategies

```python
import pybreaker, time
brk = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30, exclude=[ValueError])

@brk
def charge(card: str, amount: int) -> dict:
    return payment_client.post("/charge", json={"card": card, "amount": amount})
```

For async: wrap with a manual counter or use `aiobreaker`. Envoy: `outlier_detection: { consecutive_5xx: 5, interval: 10s, base_ejection_time: 30s }`.

## 10. Production-grade implementation

**Scenario:** Payment provider starts returning 500s with 100% error rate. Breaker (fail_max=20 over 10s, reset 30s) opens after ~2s; upstream `POST /checkout` p95 falls from 30s to 2ms; alert fires; when provider recovers, half-open trial succeeds and breaker closes. Without it, uvicorn worker pool exhausted and the whole API went down.

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
from fastapi import HTTPException
@app.post("/orders")
async def create_order(order: Order):
    try:
        return await checkout(order)
    except pybreaker.CircuitBreakerError:
        raise HTTPException(503, "payment provider degraded - try again later")
```

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Provider outage → breaker opens → fallback chain (secondary provider/model/cached answer). Never retry 4xx (prompt errors); cap amplification at ~20% of traffic.

## 15. Security considerations

Fail closed on auth paths; breakers must not fall back to 'allow'.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Retry storm without a breaker; breaker with threshold so high it never opens; treating deterministic 400s as failures; no fallback — just exceptions; reset_timeout = forever; breaker per app instance without aggregate protection for a shared dependency.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `circuit_breaker_state{dep}`, OPEN events, short-circuit rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Unit test with a fake client failing N times → assert breaker opens, calls short-circuit, half-open probe after reset_timeout; integration test against toxiproxy-injected 500s; chaos test in staging verifying error rate drops and recovery closes the breaker.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Always pair breaker + timeout + bounded retries
- [ ] Exclude 4xx from failure counting
- [ ] Metric per dependency (`breaker_state{dep="payments"}`)
- [ ] Alert on OPEN
- [ ] Fallback path (serve cached/degraded response)
- [ ] Open on slow calls too (latency breaker)
- [ ] Test half-open behavior
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Breaker opens but alert is noisy and ignored; reset_timeout too long → half-open probe too rare; per-instance breakers in 30 replicas each needing 5 failures → provider melts before opening globally (use Envoy or shared Redis counter); breaker used for non-transient errors (bad input 500s) opens needlessly — exclude expected client errors; half-open allows full flood of traffic through one slow endpoint.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://learn.microsoft.com/azure/architecture/patterns/circuit-breaker

**Related topics in this library:** `#11 Timeouts`, `#12 Retries`, `#13 Exponential Backoff`, `#56 Health Checks`, `#10 Circuit Breakers` composes with `#55 Rollbacks` during deploys.
