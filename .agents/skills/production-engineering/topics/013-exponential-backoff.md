---
topic: 13
title: Exponential Backoff
category: A
skill: production-engineering
status: stable
---

# 013 — Exponential Backoff

## 1. Topic name and metadata

- **Number:** 13 of 111
- **Title:** Exponential Backoff
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/013-exponential-backoff.md`

## 2. What it is

A delay strategy for retries in which the wait grows multiplicatively (e.g., 100ms, 200, 400, 800…) and is capped, usually combined with random jitter.

## 3. Why it exists

Synchronized retries after an outage re-break the recovering system.

## 4. The engineering problem it solves

Synchronized retries after a shared failure (deploy, dependency blip, 429 wave) return in lockstep and hammer the recovering service — a self-inflicted thundering herd that turns a 2-minute blip into a full outage.

## 5. How it works internally

delay_n = min(cap, base × 2^n); full jitter: sleep(random(0, delay_n)) spreads retries uniformly across the window; decorrelated jitter: delay = random(base, delay_prev × 3) — best under ongoing contention. Jitter is not optional: deterministic backoff preserves synchronization. Add a cap (≤30s typical) and an overall deadline. Clients often add `Retry-After` hints from the server that override the computed delay.

## 6. Architecture and design principles

Inside retry wrappers (tenacity/httpx/Celery), client SDK token-refresh loops, queue consumers re-delivering with broker `x-delay`, and LLM API clients honoring `Retry-After`.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Any retry exists — backoff+jitter is the default delay policy.

## 8. When NOT to use it

Operation is latency-critical and user-facing with immediate failure preferred (e.g., interactive checkout — surface error instantly); when retries are forbidden entirely (non-idempotent).

**Alternatives:** token bucket pacing, queue-based retry tiers, user-initiated retry.

## 9. Implementation strategies

```python
from tenacity import retry, stop_after_delay, wait_exponential_jitter, wait_random_exponential
@retry(stop=stop_after_delay(30), wait=wait_exponential_jitter(initial=0.1, max=10))
def call_llm(prompt: str): ...
# Celery: task = app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
```

Broker: RabbitMQ DLX + `x-message-ttl` per retry tier (10s/60s/5min); SQS `VisibilityTimeout` increase per attempt.

## 10. Production-grade implementation

**Scenario:** 429 rollout from an LLM provider. Full-jitter backoff (base 200ms, cap 20s, max 5 attempts) spread 300 retrying workers across ~20s with peak 60 req/s instead of a 300-req/s burst; error rate recovered without operator intervention.

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

Token-refresh on 401: single-flight refresh with backoff so 500 concurrent 401s do not each hit the IdP (see `#14 Idempotency` for dedupe of refresh requests).

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Provider rate-limit waves are exactly the synchronized-retry case — full jitter prevents the re-storm after every 429 window.

## 15. Security considerations

Honor Retry-After; IDP protection matters — jitter is a security feature here.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Fixed 1s retries; backoff without jitter; unbounded growth; no cap; implicit synchronization via identical fleets; backoff misread as user-facing latency budget.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `retry_delay_seconds` histogram, retry storms per dependency

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest asserting computed delays within [0, min(cap, base×2^n)] over 10k samples; mocked clock advancing; verify `Retry-After` honored; chaos test failing a dependency and confirming no correlated retry spike in metrics.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] Always full jitter
- [ ] Cap delay and total deadline
- [ ] Honor `Retry-After`
- [ ] Stagger bases per client class
- [ ] Log attempt count and final failure
- [ ] Monitor retry distribution
- [ ] Combine with `#14 Idempotency`
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** No jitter → lockstep retry storm; cap too high → request outlives caller timeout and uselessly completes; cap too low → gives up before recovery; backoff without a deadline → worker pinned for minutes; everyone uses the same base → partial synchronization.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

**Related topics in this library:** `#12 Retries`, `#10 Circuit Breakers`, `#14 Idempotency`, `#75 DDoS Protection` (defenders use the same math), `#90 Serverless Limits`.
