---
topic: 11
title: Timeouts
category: A
skill: production-engineering
status: stable
---

# 011 — Timeouts

## 1. Topic name and metadata

- **Number:** 11 of 111
- **Title:** Timeouts
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/011-timeouts.md`

## 2. What it is

A bound on how long an operation may wait for a result before it is abandoned with an error; every blocking operation that crosses a process or network boundary must have one.

## 3. Why it exists

Unbounded waits are the number-one way a slow component becomes an outage.

## 4. The engineering problem it solves

Without timeouts, a hung dependency holds threads, connections, and transactions indefinitely; resources exhaust, and the whole service becomes unresponsive rather than failing a single request.

## 5. How it works internally

Client-side deadline propagation (gRPC deadline, `context.Context.WithDeadline`, `asyncio.wait_for`, `httpx.AsyncClient(timeout=…)`); server-side: request budget enforced by the framework (uvicorn `--timeout-keep-alive`, K8s `terminationGracePeriodSeconds`). Timers must account for the **entire** path: connect, TLS handshake, wait-for-first-byte, response body. Set the caller's timeout ≥ the sum of internal timeouts along the path plus slack — never smaller than what downstream needs, or you get 504s on work that will still complete (wasted).

## 6. Architecture and design principles

Every hop sets and passes budgets: gateway 30s → service A (25s) → service B (10s) → DB statement timeout 5s. Enforce at each client wrapper (DB pool `statement_timeout`, HTTP client, queue consume deadline).

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Always, for every outbound call and every database statement.

## 8. When NOT to use it

Truly indefinite batch work (use explicit kill-switch/cancellation instead).

**Alternatives:** deadlines/cancellation tokens, `context` propagation, request budgets in the mesh.

## 9. Implementation strategies

PostgreSQL: `statement_timeout = '5s'` per role/session; SQLAlchemy: `connect_timeout=5` and engine `pool_timeout=30`; httpx: `timeout=httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=1.0)`; asyncpg/asyncio: `asyncio.wait_for(coro, 5)`; Redis client `socket_timeout=2`; Celery `task_time_limit=300`; Kafka consumer `max.poll.interval.ms`.

```python
import httpx
async with httpx.AsyncClient(timeout=httpx.Timeout(connect=2.0, read=8.0, write=5.0, pool=2.0)) as client:
    r = await client.post(url, json=payload)
```

## 10. Production-grade implementation

**Scenario:** Checkout chain: ALB idle 60s → service 20s end-to-end → inventory gRPC 2s, pricing 3s, payments 10s → Postgres `statement_timeout=8s`. Payments latency degraded to 12s; timeouts shed fail-fast instead of hanging the pool; p99 capped at ~20s; partial-failure path returns "payment pending, we will reconcile".

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
import asyncio
from fastapi import HTTPException
@app.post("/summarize")
async def summarize(doc: str):
    try:
        return await asyncio.wait_for(llm.complete(doc), timeout=45.0)
    except asyncio.TimeoutError:
        raise HTTPException(504, "model timed out - retry shortly")
```

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Token-budgeted deadlines: timeout = f(max_tokens, expected tok/s + headroom); an 8k-token generation at 60 tok/s needs ≥140s or streaming. Degrade, don't hang.

## 15. Security considerations

Small explicit timeouts blunt slow-loris exhaustion; include connect vs read vs pool.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Infinite defaults (`requests.get(url)` without timeout); one global timeout for all endpoints; timeout smaller than DNS resolve + TLS + first byte combined; retrying inside the timeout window wastefully; converting timeouts into silent empty responses; setting DB `statement_timeout` longer than the app's.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `timeouts_total{operation}`, dependency latency p99 vs budget

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest with monkeypatched slow client + `asyncio.wait_for` asserting TimeoutError path; toxiproxy-injected delays; verify `statement_timeout` kills the query with `pg_stat_activity`; load test confirming pool does not exhaust under dependency latency injection.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Budget the whole path and write it down
- [ ] Align timeouts: gateway > service > DB
- [ ] Timeout on connect, read, write, AND pool
- [ ] Propagate remaining budget via `X-Request-Timeout`/gRPC metadata
- [ ] Log timeout as a metric labeled by dependency
- [ ] Pair every timeout with a retry budget and idempotency
- [ ] Graceful deadline errors with `Retry-After`.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Cascading timeout violation — upstream caller times out before downstream finishes → duplicate side effects (pair with `#14 Idempotency`); timeout == retry budget misconfiguration (timeout smaller than backoff gap) causing spurious errors; default timeouts that are infinite (requests library default: forever); `statement_timeout` in the DB higher than the app's, so the app gives up but the query keeps running and holds locks; timeouts only on connect, never on read → classic hung-socket outage.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://learn.microsoft.com/azure/architecture/patterns/circuit-breaker

**Related topics in this library:** `#12 Retries`, `#13 Exponential Backoff`, `#10 Circuit Breakers`, `#94 Tail Latency`, `#11 Timeouts` budgets flow into `#93 P99 Latency`.
